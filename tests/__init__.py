import os

# use json in Python 2.7, fallback to simplejson for Python 2.5
try:
    import json
except ImportError:
    import simplejson as json

from google.appengine.ext.webapp import RequestHandler
from google.appengine.api import memcache

from gae_bingo.api import ControlExperiment
from gae_bingo.cache import BingoCache, BingoIdentityCache
from gae_bingo.config import can_control_experiments
from gae_bingo.gae_bingo import ab_test, bingo, choose_alternative, create_redirect_url
import gae_bingo.identity
from gae_bingo.models import ConversionTypes

# See gae_bingo/tests/run_tests.py for the full explanation/sequence of these tests
# TODO(kamens): this whole file and ad-hoc test process should be replaced w/
# our real unit testing or end-to-end testing framework.

class RunStep(RequestHandler):

    def get(self):

        if not os.environ["SERVER_SOFTWARE"].startswith('Development'):
            return

        step = self.request.get("step")
        v = None

        if step == "delete_all":
            v = self.delete_all_experiments()
        elif step == "get_identity":
            v = self.get_identity()
        elif step == "refresh_identity_record":
            v = self.refresh_identity_record()
        elif step == "participate_in_monkeys":
            v = self.participate_in_monkeys()
        elif step == "participate_in_gorillas":
            v = self.participate_in_gorillas()
        elif step == "participate_in_chimpanzees":
            v = self.participate_in_chimpanzees()
        elif step == "participate_in_crocodiles":
            v = self.participate_in_crocodiles()
        elif step == "participate_in_hippos":
            v = self.participate_in_hippos()
        elif step == "add_conversions":
            v = self.add_conversions()
        elif step == "get_experiments":
            v = self.get_experiments()
        elif step == "get_archived_experiments":
            v = self.get_experiments(archives=True)
        elif step == "print_cache":
            v = self.print_cache()
        elif step == "convert_in":
            v = self.convert_in()
        elif step == "count_participants_in":
            v = self.count_participants_in()
        elif step == "count_conversions_in":
            v = self.count_conversions_in()
        elif step == "count_experiments":
            v = self.count_experiments()
        elif step == "end_and_choose":
            v = self.end_and_choose()
        elif step == "persist":
            v = self.persist()
        elif step == "flush_hippo_counts_memcache":
            v = self.flush_hippo_counts_memcache()
        elif step == "flush_bingo_memcache":
            v = self.flush_bingo_memcache()
        elif step == "flush_all_memcache":
            v = self.flush_all_memcache()
        elif step == "create_monkeys_redirect_url":
            v = self.create_monkeys_redirect_url()
        elif step == "create_chimps_redirect_url":
            v = self.create_chimps_redirect_url()
        elif step == "archive_monkeys":
            v = self.archive_monkeys()

        self.response.out.write(json.dumps(v))

    def delete_all_experiments(self):
        bingo_cache = BingoCache.get()
        for experiment_name in bingo_cache.experiments.keys():
            bingo_cache.delete_experiment_and_alternatives(
                    bingo_cache.get_experiment(experiment_name))

        bingo_cache_archives = BingoCache.load_from_datastore(archives=True)
        for experiment_name in bingo_cache_archives.experiments.keys():
            bingo_cache_archives.delete_experiment_and_alternatives(
                    bingo_cache_archives.get_experiment(experiment_name))

        return (len(bingo_cache.experiments) +
                len(bingo_cache_archives.experiments))

    def get_identity(self):
        return gae_bingo.identity.identity()

    def refresh_identity_record(self):
        BingoIdentityCache.get().load_from_datastore()
        return True

    def participate_in_monkeys(self):
        return ab_test("monkeys")

    def archive_monkeys(self):
        bingo_cache = BingoCache.get()
        bingo_cache.archive_experiment_and_alternatives(bingo_cache.get_experiment("monkeys"))
        return True

    def participate_in_gorillas(self):
        return ab_test("gorillas", ["a", "b", "c"])

    def participate_in_chimpanzees(self):
        # Multiple conversions test
        return ab_test("chimpanzees", conversion_name=["chimps_conversion_1", "chimps_conversion_2"])

    def participate_in_crocodiles(self):
        # Weighted test
        return ab_test("crocodiles", {"a": 100, "b": 200, "c": 400})

    def participate_in_hippos(self):
        # Multiple conversions test
        return ab_test("hippos",
                        conversion_name=["hippos_binary",
                                         "hippos_counting"],
                        conversion_type=[ConversionTypes.Binary,
                                         ConversionTypes.Counting])

    # Should be called after participate_in_hippos to test adding
    # conversions mid-experiment
    def add_conversions(self):
        return ab_test("hippos",
                       conversion_name=["hippos_binary",
                                        "hippos_counting",
                                        "rhinos_counting"],
                       conversion_type=[ConversionTypes.Binary,
                                        ConversionTypes.Counting,
                                        ConversionTypes.Counting])

    def get_experiments(self, archives=False):
        if archives:
            bingo_cache = BingoCache.load_from_datastore(archives=True)
        else:
            bingo_cache = BingoCache.get()

        return str(bingo_cache.experiments)

    def try_this_bad(self):
        cache = BingoCache.get()
        return len(cache.get_experiment_names_by_canonical_name("hippos"))

    def convert_in(self):
        bingo(self.request.get("conversion_name"))
        return True

    def create_monkeys_redirect_url(self):
        return create_redirect_url("/gae_bingo", "monkeys")

    def create_chimps_redirect_url(self):
        return create_redirect_url("/gae_bingo",
                                  ["chimps_conversion_1",
                                   "chimps_conversion_2"])

    def end_and_choose(self):
        bingo_cache = BingoCache.get()
        choose_alternative(self.request.get("canonical_name"), int(self.request.get("alternative_number")))

    def count_participants_in(self):
        return sum(
                map(lambda alternative: alternative.latest_participants_count(),
                    BingoCache.get().get_alternatives(self.request.get("experiment_name"))
                    )
                )

    def count_conversions_in(self):
        dict_conversions = {}

        for alternative in BingoCache.get().get_alternatives(self.request.get("experiment_name")):
            dict_conversions[alternative.content] = alternative.latest_conversions_count()

        return dict_conversions

    def count_experiments(self):
        return len(BingoCache.get().experiments)

    def persist(self):
        BingoCache.get().persist_to_datastore()
        BingoIdentityCache.persist_buckets_to_datastore()
        return True

    def flush_hippo_counts_memcache(self):
        experiments, alternative_lists = BingoCache.get().experiments_and_alternatives_from_canonical_name("hippos")

        for alternatives in alternative_lists:
            for alternative in alternatives:
                memcache.delete("%s:conversions" % alternative.key_for_self())
                memcache.delete("%s:participants" % alternative.key_for_self())

        return True

    def flush_bingo_memcache(self):
        memcache.delete(BingoCache.MEMCACHE_KEY)
        return True

    def flush_all_memcache(self):
        memcache.flush_all()
        return True
