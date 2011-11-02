import os
import logging
import simplejson

from google.appengine.ext.webapp import RequestHandler
from google.appengine.api import memcache

from gae_bingo.gae_bingo import ab_test, bingo, choose_alternative
from gae_bingo.cache import BingoCache, BingoIdentityCache
from gae_bingo.config import can_control_experiments
from gae_bingo.api import ControlExperiment
from gae_bingo.models import ConversionTypes

# See gae_bingo/tests/run_tests.py for the full explanation/sequence of these tests

class RunStep(RequestHandler):

    def get(self):

        if not os.environ["SERVER_SOFTWARE"].startswith('Development'):
            return

        step = self.request.get("step")
        v = None

        if step == "delete_all":
            v = self.delete_all_experiments()
        if step == "refresh_identity_record":
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
        elif step == "flush_memcache":
            v = self.flush_memcache()

        self.response.out.write(simplejson.dumps(v))

    def delete_all_experiments(self):
        bingo_cache = BingoCache.get()
        
        for experiment_name in bingo_cache.experiments.keys():
            bingo_cache.delete_experiment_and_alternatives(bingo_cache.get_experiment(experiment_name))

        return len(bingo_cache.experiments)

    def refresh_identity_record(self):
        BingoIdentityCache.get().load_from_datastore()
        return True

    def participate_in_monkeys(self):
        return ab_test("monkeys")

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
        return ab_test("hippos", conversion_name=["hippos_binary", "hippos_counting"], conversion_type=[ConversionTypes.Binary, ConversionTypes.Counting])

    def convert_in(self):
        bingo(self.request.get("conversion_name"))
        return True

    def end_and_choose(self):
        bingo_cache = BingoCache.get()
        choose_alternative(self.request.get("canonical_name"), int(self.request.get("alternative_number")))

    def count_participants_in(self):
        return reduce(lambda a, b: a + b, 
                map(lambda alternative: alternative.participants, 
                    BingoCache.get().get_alternatives(self.request.get("experiment_name"))
                    )
                )

    def count_conversions_in(self):
        dict_conversions = {}

        for alternative in BingoCache.get().get_alternatives(self.request.get("experiment_name")):
            dict_conversions[alternative.content] = alternative.conversions

        return dict_conversions

    def count_experiments(self):
        return len(BingoCache.get().experiments)

    def persist(self):
        BingoCache.get().persist_to_datastore()
        BingoIdentityCache.persist_buckets_to_datastore()
        return True

    def flush_memcache(self):
        memcache.flush_all()
        return True
