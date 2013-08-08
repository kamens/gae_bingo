"""Tools for caching the state of all bingo experiments.

There are two main objects cached by bingo: BingoCache and BingoIdentityCache.

BingoCache caches the state of all Experiment and Alternative models, and it is
shared among all users.

BingoIdentityCache caches individual users' participation and conversion
histories, and one exists for every user.

Each of them are cached at multiple layers, summarized below:
    BingoCache itself is cached in:
        request_cache (so we only retrieve it once per request)
        instance_cache (so we only load it from memcache once every minute)
        memcache (when instance_cache is empty, we load from memcache)
        datastore (if memcache is empty, we load all Experiment/Alternative
            models from the datastore)

    BingoIdentityCaches are cached in:
        request_cache (so we only retrieve it once per request)
        memcache (when a user becomes active, we hope to keep their bingo
            history in memcache)
        datastore (whenever an individual user's history isn't in memcache, we
            load it from a cached-in-datastore model, _GAEBingoIdentityRecord)

    This sequence of cache loading and expiration is handled by CacheLayers.
"""

import hashlib
import logging
import zlib

from google.appengine.ext import db
from google.appengine.ext import deferred
from google.appengine.api import memcache
from google.appengine.datastore import entity_pb
from google.appengine.ext.webapp import RequestHandler

from .models import _GAEBingoExperiment, _GAEBingoAlternative, _GAEBingoIdentityRecord, _GAEBingoSnapshotLog
from config import config
from identity import identity
import instance_cache
import pickle_util
import request_cache
import synchronized_counter


NUM_IDENTITY_BUCKETS = 51


class CacheLayers(object):
    """Gets and sets BingoCache/BingoIdentityCaches in multiple cache layers.

    BingoCache and BingoIdentityCache use CacheLayers.get to load themselves.

    Since these objects are cached in multiple layers (request cache, instance
    cache, memcache, and the datastore), CacheLayers handles the logic for
    loading these objects on each request.

    Each request loads both the BingoCache (a collection of experiments and
    alternatives) and the current user's BingoIdentityCache (a collection of
    current user's participation in various experiments). BingoCache's state
    can be safely shared among multiple users.

    The loading and caching logic works like this:

        1) Prefetch both BingoCache and BingoIdentityCache from memcache.

            1a) If BingoCache is already in the current instance's instance
            cache and the instance cache hasn't expired (1-minute expiry), then
            only BingoIdentityCache will be loaded from memcache.

        2) If either cache is still missing, load them from the datastore. Both
            BingoCache and BingoIdentityCache implement their own
            load_from_datastore methods.

        3) Store both BingoCache and BingoIdentityCache in the request cache so
        we don't have to look them up again for the rest of the request.

            3a) Store BingoCache in the instance cache with a 1-minute expiry
            so it doesn't need to be loaded from memcache again for a bit.

    Note: The use of instance caching for BingoCache, even with a 1-min expiry,
    means that sometimes when controlling a bingo experiment (say, by choosing
    a specific alternative for all users), old instances won't see the new
    state of the experiment until the cache expires. This means some users may
    experience "flopping" back and forth between two versions of an experiment
    when, say, an alternative is chosen by the gae/bingo admin control panel
    and they issue multiple requests which are sent to App Engine instances w/
    different cached states. We consider this an acceptable tradeoff, for now.

    TODO(kamens): improve the above 1-minute version "flopping" if necessary.
    """

    INSTANCE_SECONDS = 60  # number of secs BingoCache stays in instance cache

    @staticmethod
    def fill_request_cache():
        """Load BingoCache/BingoIdentityCache from instance cache/memcache.

        This loads the shared BingoCache and the individual BingoIdentityCache
        for the current request's bingo identity and stores them both in the
        request cache.
        """
        if not request_cache.cache.get("bingo_request_cache_filled"):

            # Assume that we're going to grab both BingoCache and
            # BingoIdentityCache from memcache
            memcache_keys = [
                BingoCache.CACHE_KEY,
                BingoIdentityCache.key_for_identity(identity())
            ]

            # Try to grab BingoCache from instance cache
            bingo_instance = instance_cache.get(BingoCache.CACHE_KEY)
            if bingo_instance:
                # If successful, use instance cached version...
                request_cache.cache[BingoCache.CACHE_KEY] = bingo_instance
                # ...and don't load BingoCache from memcache
                memcache_keys.remove(BingoCache.CACHE_KEY)

            # Load necessary caches from memcache
            dict_memcache = memcache.get_multi(memcache_keys)

            # Decompress BingoCache if we loaded it from memcache
            if BingoCache.CACHE_KEY in dict_memcache:
                dict_memcache[BingoCache.CACHE_KEY] = CacheLayers.decompress(
                        dict_memcache[BingoCache.CACHE_KEY])

            # Update request cache with values loaded from memcache
            request_cache.cache.update(dict_memcache)

            if not bingo_instance:
                # And if BingoCache wasn't in the instance cache already, store
                # it with a 1-minute expiry
                instance_cache.set(BingoCache.CACHE_KEY,
                        request_cache.cache.get(BingoCache.CACHE_KEY),
                        expiry=CacheLayers.INSTANCE_SECONDS)

            request_cache.cache["bingo_request_cache_filled"] = True

    @staticmethod
    def compress(value):
        """Compress value so it'll fit in a single memcache value."""
        pickled = pickle_util.dump(value)
        return zlib.compress(pickled)

    @staticmethod
    def decompress(data):
        """Decompress value from its compressed memcache state."""
        pickled = zlib.decompress(data)
        return pickle_util.load(pickled)

    @staticmethod
    def set(key, value):
        """Set value in instance cache and a compressed version in memcache.
        
        BingoCache is always only stored in instance cache for up to 1 minute.
        """
        instance_cache.set(key, value, expiry=CacheLayers.INSTANCE_SECONDS)
        memcache.set(key, CacheLayers.compress(value))

        logging.info("Set BingoCache in instance cache and memcache")

    @staticmethod
    def get(key, fxn_load):
        """Load BingoCache or BingoIdentityCache into request cache.

        This will first try to prefetch the expected entities from memcache.

        If the requested BingoCache or BingoIdentityCache key still isn't in
        the current request cache after prefetching, load the key's value from
        the datastore using the passed-in loader function and update the
        current request cache.

        Args:
            key: cache key of BingoCache or specific user's BingoIdentityCache
            fxn_load: function to run that loads desired cache in the event of
                a memcache and instance cache miss during prefetch.
        """
        CacheLayers.fill_request_cache()

        if not request_cache.cache.get(key):
            request_cache.cache[key] = fxn_load()

        return request_cache.cache[key]


class BingoCache(object):
    """Stores all shared bingo experiment and alternative data."""
    CACHE_KEY = "_gae_bingo_compressed_cache"

    @staticmethod
    def get():
        return CacheLayers.get(BingoCache.CACHE_KEY,
                BingoCache.load_from_datastore)

    def __init__(self):
        self.dirty = False
        self.storage_disabled = False # True if loading archives that shouldn't be cached

        self.experiments = {} # Protobuf version of experiments for extremely fast (de)serialization
        self.experiment_models = {} # Deserialized experiment models

        self.alternatives = {} # Protobuf version of alternatives for extremely fast (de)serialization
        self.alternative_models = {} # Deserialized alternative models

        self.experiment_names_by_conversion_name = {} # Mapping of conversion names to experiment names
        self.experiment_names_by_canonical_name = {} # Mapping of canonical names to experiment names

    def store_if_dirty(self):
        # Only write cache if a change has been made
        if getattr(self, "storage_disabled", False) or not self.dirty:
            return

        # Wipe out deserialized models before serialization for speed
        self.experiment_models = {}
        self.alternative_models = {}

        # No longer dirty
        self.dirty = False

        CacheLayers.set(self.CACHE_KEY, self)

    def persist_to_datastore(self):
        """Persist current state of experiment and alternative models.

        This persists the entire BingoCache state to the datastore. Individual
        participants/conversions sums might be slightly out-of-date during any
        given persist, but hopefully not by much. This can be caused by
        memcache being cleared at unwanted times between a participant or
        conversion count increment and a persist.
        TODO(kamens): make persistence not rely on memcache so heavily.

        This persistence should be run constantly in the background via chained
        task queues.
        """

        # Start putting the experiments asynchronously.
        experiments_to_put = []
        for experiment_name in self.experiments:
            experiment_model = self.get_experiment(experiment_name)
            experiments_to_put.append(experiment_model)
        async_experiments = db.put_async(experiments_to_put)

        # Fetch all current counts available in memcache...
        counter_keys = []
        for experiment_name in self.experiments:
            experiment_model = self.get_experiment(experiment_name)
            counter_keys.append(experiment_model.participants_key)
            counter_keys.append(experiment_model.conversions_key)

        # ...and when we grab the current counts, reset the currently
        # accumulating counters at the same time.
        count_results = synchronized_counter.SynchronizedCounter.pop_counters(
                counter_keys)

        # Now add the latest accumulating counters to each alternative.
        alternatives_to_put = []
        for experiment_name in self.alternatives:

            experiment_model = self.get_experiment(experiment_name)
            alternative_models = self.get_alternatives(experiment_name)
            participants = count_results[experiment_model.participants_key]
            conversions = count_results[experiment_model.conversions_key]

            for alternative_model in alternative_models:

                # When persisting to datastore, we want to update with the most
                # recent accumulated counter from memcache.
                if alternative_model.number < len(participants):
                    delta_participants = participants[alternative_model.number]
                    alternative_model.participants += delta_participants

                if alternative_model.number < len(conversions):
                    delta_conversions = conversions[alternative_model.number]
                    alternative_model.conversions += delta_conversions

                alternatives_to_put.append(alternative_model)
                self.update_alternative(alternative_model)

        # When periodically persisting to datastore, first make sure memcache
        # has relatively up-to-date participant/conversion counts for each
        # alternative.
        self.dirty = True
        self.store_if_dirty()

        # Once memcache is done, put alternatives.
        async_alternatives = db.put_async(alternatives_to_put)

        async_experiments.get_result()
        async_alternatives.get_result()

    def log_cache_snapshot(self):

        # Log current data on live experiments to the datastore
        log_entries = []

        for experiment_name in self.experiments:
            experiment_model = self.get_experiment(experiment_name)
            if experiment_model and experiment_model.live:
                log_entries += self.log_experiment_snapshot(experiment_model)

        db.put(log_entries)

    def log_experiment_snapshot(self, experiment_model):

        log_entries = []

        alternative_models = self.get_alternatives(experiment_model.name)
        for alternative_model in alternative_models:
            # When logging, we want to store the most recent value we've got
            log_entry = _GAEBingoSnapshotLog(parent=experiment_model, alternative_number=alternative_model.number, conversions=alternative_model.latest_conversions_count(), participants=alternative_model.latest_participants_count())
            log_entries.append(log_entry)

        return log_entries

    @staticmethod
    def load_from_datastore(archives=False):
        """Load BingoCache from the datastore, using archives if specified."""

        # This shouldn't happen often (should only happen when memcache has
        # been completely evicted), but we still want to be as fast as
        # possible.

        bingo_cache = BingoCache()

        if archives:
            # Disable cache writes if loading from archives
            bingo_cache.storage_disabled = True

        experiment_dict = {}
        alternatives_dict = {}

        # Kick both of these off w/ run() so they'll prefetch asynchronously
        experiments = _GAEBingoExperiment.all().filter(
                "archived =", archives).run(batch_size=400)
        alternatives = _GAEBingoAlternative.all().filter(
                "archived =", archives).run(batch_size=400)

        for experiment in experiments:
            experiment_dict[experiment.name] = experiment

        alternatives = sorted(list(alternatives), key=lambda alt: alt.number)

        for alternative in alternatives:
            if alternative.experiment_name not in alternatives_dict:
                alternatives_dict[alternative.experiment_name] = []
            alternatives_dict[alternative.experiment_name].append(alternative)

        for experiment_name in experiment_dict:
            ex, alts = (experiment_dict.get(experiment_name),
                        alternatives_dict.get(experiment_name))
            if ex and alts:
                bingo_cache.add_experiment(ex, alts)

        # Immediately store in memcache as soon as possible after loading from
        # datastore to minimize # of datastore loads
        bingo_cache.store_if_dirty()

        return bingo_cache

    def add_experiment(self, experiment, alternatives):

        if not experiment or not alternatives:
            raise Exception("Cannot add empty experiment or empty alternatives to BingoCache")

        self.experiment_models[experiment.name] = experiment
        self.experiments[experiment.name] = db.model_to_protobuf(experiment).Encode()

        if not experiment.conversion_name in self.experiment_names_by_conversion_name:
            self.experiment_names_by_conversion_name[experiment.conversion_name] = []
        self.experiment_names_by_conversion_name[experiment.conversion_name].append(experiment.name)

        if not experiment.canonical_name in self.experiment_names_by_canonical_name:
            self.experiment_names_by_canonical_name[experiment.canonical_name] = []
        self.experiment_names_by_canonical_name[experiment.canonical_name].append(experiment.name)

        for alternative in alternatives:
            self.update_alternative(alternative)

        self.dirty = True

    def update_experiment(self, experiment):
        self.experiment_models[experiment.name] = experiment
        self.experiments[experiment.name] = db.model_to_protobuf(experiment).Encode()

        self.dirty = True

    def update_alternative(self, alternative):
        if not alternative.experiment_name in self.alternatives:
            self.alternatives[alternative.experiment_name] = {}

        self.alternatives[alternative.experiment_name][alternative.number] = db.model_to_protobuf(alternative).Encode()

        # Clear out alternative models cache so they'll be re-grabbed w/ next .get_alternatives
        if alternative.experiment_name in self.alternative_models:
            del self.alternative_models[alternative.experiment_name]

        self.dirty = True

    def remove_from_cache(self, experiment):
        # Remove from current cache
        if experiment.name in self.experiments:
            del self.experiments[experiment.name]

        if experiment.name in self.experiment_models:
            del self.experiment_models[experiment.name]

        if experiment.name in self.alternatives:
            del self.alternatives[experiment.name]

        if experiment.name in self.alternative_models:
            del self.alternative_models[experiment.name]

        if experiment.conversion_name in self.experiment_names_by_conversion_name:
            self.experiment_names_by_conversion_name[experiment.conversion_name].remove(experiment.name)

        if experiment.canonical_name in self.experiment_names_by_canonical_name:
            self.experiment_names_by_canonical_name[experiment.canonical_name].remove(experiment.name)

        self.dirty = True

        # Immediately store in memcache as soon as possible after deleting from datastore
        self.store_if_dirty()

    @db.transactional(xg=True)
    def delete_experiment_and_alternatives(self, experiment):
        """Permanently delete specified experiment and all alternatives."""
        if not experiment:
            return

        # First delete from datastore
        experiment.delete()
        experiment.reset_counters()

        for alternative in self.get_alternatives(experiment.name):
            alternative.delete()

        self.remove_from_cache(experiment)

    @db.transactional(xg=True)
    def archive_experiment_and_alternatives(self, experiment):
        """Permanently archive specified experiment and all alternatives.

        Archiving an experiment maintains its visibility for historical
        purposes, but it will no longer be loaded into the cached list of
        active experiments.

        Args:
            experiment: experiment entity to be archived.
        """
        if not experiment:
            return

        experiment.archived = True
        experiment.live = False
        experiment.put()

        alts = self.get_alternatives(experiment.name)
        for alternative in alts:
            alternative.archived = True
            alternative.live = False

        db.put(alts)

        self.remove_from_cache(experiment)

    def experiments_and_alternatives_from_canonical_name(self, canonical_name):
        experiment_names = self.get_experiment_names_by_canonical_name(canonical_name)

        return [self.get_experiment(experiment_name) for experiment_name in experiment_names], \
                [self.get_alternatives(experiment_name) for experiment_name in experiment_names]

    def get_experiment(self, experiment_name):
        if experiment_name not in self.experiment_models:
            if experiment_name in self.experiments:
                self.experiment_models[experiment_name] = db.model_from_protobuf(entity_pb.EntityProto(self.experiments[experiment_name]))

        return self.experiment_models.get(experiment_name)

    def get_alternatives(self, experiment_name):
        if experiment_name not in self.alternative_models:
            if experiment_name in self.alternatives:
                self.alternative_models[experiment_name] = []
                for alternative_number in self.alternatives[experiment_name]:
                    self.alternative_models[experiment_name].append(db.model_from_protobuf(entity_pb.EntityProto(self.alternatives[experiment_name][alternative_number])))

        return self.alternative_models.get(experiment_name) or []

    def get_experiment_names_by_conversion_name(self, conversion_name):
        return self.experiment_names_by_conversion_name.get(conversion_name) or []

    def get_experiment_names_by_canonical_name(self, canonical_name):
        return sorted(self.experiment_names_by_canonical_name.get(canonical_name) or [])


class BingoIdentityCache(object):
    """Stores conversion and participation data in tests for a bingo identity.

    This is stored in several layers of caches, including memcache. It is
    persisted using _GAEBingoIdentityRecord.
    """
    CACHE_KEY = "_gae_bingo_identity_cache:%s"

    @staticmethod
    def key_for_identity(ident):
        return BingoIdentityCache.CACHE_KEY % ident

    @staticmethod
    def get(identity_val=None):
        key = BingoIdentityCache.key_for_identity(identity(identity_val))
        return CacheLayers.get(key,
                lambda: BingoIdentityCache.load_from_datastore(identity_val))

    def store_for_identity_if_dirty(self, ident):
        if not self.dirty:
            return

        # No longer dirty
        self.dirty = False

        # memcache.set_async isn't exposed; make a Client so we can use it
        client = memcache.Client()
        future = client.set_multi_async(
            {BingoIdentityCache.key_for_identity(ident): self})

        # Always fire off a task queue to persist bingo identity cache
        # since there's no cron job persisting these objects like BingoCache.
        self.persist_to_datastore(ident)
        # TODO(alpert): If persist_to_datastore has more than 50 identities and
        # creates a deferred task AND that task runs before the above memcache
        # set finishes then we could lose a tiny bit of data for a user, but
        # that's extremely unlikely to happen.

        future.get_result()

    def persist_to_datastore(self, ident):

        # Add the memcache value to a memcache bucket which
        # will be persisted to the datastore when it overflows
        # or when the periodic cron job is run
        sig = hashlib.md5(str(ident)).hexdigest()
        sig_num = int(sig, base=16)
        bucket = sig_num % NUM_IDENTITY_BUCKETS
        key = "_gae_bingo_identity_bucket:%s" % bucket

        list_identities = memcache.get(key) or []
        list_identities.append(ident)

        if len(list_identities) > 50:

            # If over 50 identities are waiting for persistent storage, 
            # go ahead and kick off a deferred task to do so
            # in case it'll be a while before the cron job runs.
            deferred.defer(persist_gae_bingo_identity_records, list_identities, _queue=config.QUEUE_NAME)

            # There are race conditions here such that we could miss persistence
            # of some identities, but that's not a big deal as long as
            # there is no statistical correlation b/w the experiment and those
            # being lost.
            memcache.set(key, [])

        else:

            memcache.set(key, list_identities)

    @staticmethod
    def persist_buckets_to_datastore():
        # Persist all memcache buckets to datastore
        dict_buckets = memcache.get_multi(["_gae_bingo_identity_bucket:%s" % bucket for bucket in range(0, NUM_IDENTITY_BUCKETS)])

        for key in dict_buckets:
            if len(dict_buckets[key]) > 0:
                deferred.defer(persist_gae_bingo_identity_records, dict_buckets[key], _queue=config.QUEUE_NAME)
                memcache.set(key, [])

    @staticmethod
    def load_from_datastore(identity_val=None):
        ident = identity(identity_val)
        bingo_identity_cache = _GAEBingoIdentityRecord.load(ident)

        if bingo_identity_cache:
            bingo_identity_cache.purge()
            bingo_identity_cache.dirty = True
            bingo_identity_cache.store_for_identity_if_dirty(ident)
        else:
            bingo_identity_cache = BingoIdentityCache()

        return bingo_identity_cache

    def __init__(self):
        self.dirty = False

        self.participating_tests = [] # List of test names currently participating in
        self.converted_tests = {} # Dict of test names:number of times user has successfully converted

    def purge(self):
        bingo_cache = BingoCache.get()

        for participating_test in self.participating_tests:
            if not participating_test in bingo_cache.experiments:
                self.participating_tests.remove(participating_test)

        for converted_test in self.converted_tests.keys():
            if not converted_test in bingo_cache.experiments:
                del self.converted_tests[converted_test]

    def participate_in(self, experiment_name):
        self.participating_tests.append(experiment_name)
        self.dirty = True

    def convert_in(self, experiment_name):
        if experiment_name not in self.converted_tests:
            self.converted_tests[experiment_name] = 1 
        else:
            self.converted_tests[experiment_name] += 1
        self.dirty = True


def bingo_and_identity_cache(identity_val=None):
    return BingoCache.get(), BingoIdentityCache.get(identity_val)


def store_if_dirty():
    # Only load from request cache here -- if it hasn't been loaded from memcache previously, it's not dirty.
    bingo_cache = request_cache.cache.get(BingoCache.CACHE_KEY)
    bingo_identity_cache = request_cache.cache.get(BingoIdentityCache.key_for_identity(identity()))

    if bingo_cache:
        bingo_cache.store_if_dirty()

    if bingo_identity_cache:
        bingo_identity_cache.store_for_identity_if_dirty(identity())


def persist_gae_bingo_identity_records(list_identities):

    dict_identity_caches = memcache.get_multi([BingoIdentityCache.key_for_identity(ident) for ident in list_identities])

    for ident in list_identities:
        identity_cache = dict_identity_caches.get(BingoIdentityCache.key_for_identity(ident))

        if identity_cache:
            bingo_identity = _GAEBingoIdentityRecord(
                        key_name = _GAEBingoIdentityRecord.key_for_identity(ident),
                        identity = ident,
                        pickled = pickle_util.dump(identity_cache),
                    )
            bingo_identity.put()


class LogSnapshotToDatastore(RequestHandler):
    def get(self):
        BingoCache.get().log_cache_snapshot()

