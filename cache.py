import logging
import pickle
import random

from google.appengine.ext import db
from google.appengine.ext import deferred
from google.appengine.api import memcache
from google.appengine.datastore import entity_pb
from google.appengine.ext.webapp import RequestHandler

from .models import _GAEBingoExperiment, _GAEBingoAlternative, _GAEBingoIdentityRecord, _GAEBingoSnapshotLog
from identity import identity

# gae_bingo relies on the deferred library,
# and as such it is susceptible to the same path manipulation weaknesses explained here:
# http://stackoverflow.com/questions/2502215/permanenttaskfailure-in-appengine-deferred-library
#
# ...if you need to run one-time configuration or path manipulation code when an instance
# is started, you may need to add that code to this file as this file will become
# a possibly instance-starting entry point. See docs and above Stack Oveflow question.
#
# Example: import config_django

# REQUEST_CACHE is cleared before and after every requests by gae_bingo.middleware.
# NOTE: this request caching will need a bit of a touchup once Python 2.7 is released for GAE and concurrent requests are enabled.
REQUEST_CACHE = {}

def flush_request_cache():
    global REQUEST_CACHE
    REQUEST_CACHE = {}

def init_request_cache_from_memcache():
    global REQUEST_CACHE

    if not REQUEST_CACHE.get("loaded_from_memcache"):
        REQUEST_CACHE = memcache.get_multi([BingoCache.MEMCACHE_KEY, BingoIdentityCache.key_for_identity(identity())])
        REQUEST_CACHE["loaded_from_memcache"] = True

class BingoCache(object):

    MEMCACHE_KEY = "_gae_bingo_cache"

    @staticmethod
    def get():
        init_request_cache_from_memcache()

        if not REQUEST_CACHE.get(BingoCache.MEMCACHE_KEY):
            REQUEST_CACHE[BingoCache.MEMCACHE_KEY] = BingoCache.load_from_datastore()

        return REQUEST_CACHE[BingoCache.MEMCACHE_KEY]

    def __init__(self):
        self.dirty = False

        self.experiments = {} # Protobuf version of experiments for extremely fast (de)serialization
        self.experiment_models = {} # Deserialized experiment models

        self.alternatives = {} # Protobuf version of alternatives for extremely fast (de)serialization
        self.alternative_models = {} # Deserialized alternative models

        self.experiment_names_by_conversion_name = {} # Mapping of conversion names to experiment names
        self.experiment_names_by_canonical_name = {} # Mapping of canonical names to experiment names

    def store_if_dirty(self):

        # Only write to memcache if a change has been made
        if not self.dirty:
            return

        # Wipe out deserialized models before serialization for speed
        self.experiment_models = {}
        self.alternative_models = {}

        # No longer dirty
        self.dirty = False

        memcache.set(BingoCache.MEMCACHE_KEY, self)

    def persist_to_datastore(self):

        # Persist current state of experiment and alternative models to datastore.
        # Their sums might be slightly out-of-date during any given persist, but not by much.
        for experiment_name in self.experiments:
            experiment_model = self.get_experiment(experiment_name)
            if experiment_model:
                experiment_model.put()

        for experiment_name in self.alternatives:
            alternative_models = self.get_alternatives(experiment_name)
            for alternative_model in alternative_models:
                # When persisting to datastore, we want to store the most recent value we've got
                alternative_model.load_latest_counts()
                alternative_model.put()

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
            alternative_model.load_latest_counts()
            log_entry = _GAEBingoSnapshotLog(parent=experiment_model, alternative_number=alternative_model.number, conversions=alternative_model.conversions, participants=alternative_model.participants)
            log_entries.append(log_entry)

        return log_entries
    
    @staticmethod
    def load_from_datastore():

        # This shouldn't happen often (should only happen when memcache has been completely evicted),
        # but we still want to be as fast as possible.

        bingo_cache = BingoCache()

        experiment_dict = {}
        alternatives_dict = {}

        # Kick both of these off w/ run() so they'll prefetch asynchronously
        experiments = _GAEBingoExperiment.all().run()
        alternatives = _GAEBingoAlternative.all().order("number").run()

        for experiment in experiments:
            experiment_dict[experiment.name] = experiment

        for alternative in alternatives:
            if alternative.experiment_name not in alternatives_dict:
                alternatives_dict[alternative.experiment_name] = []
            alternatives_dict[alternative.experiment_name].append(alternative)

        for experiment_name in experiment_dict:
            bingo_cache.add_experiment(experiment_dict.get(experiment_name), alternatives_dict.get(experiment_name))

        # Immediately store in memcache as soon as possible after loading from datastore to minimize # of datastore loads
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

    def delete_experiment_and_alternatives(self, experiment):

        if not experiment:
            return

        # First delete from datastore
        experiment.delete()

        for alternative in self.get_alternatives(experiment.name):
            alternative.reset_counts()
            alternative.delete()

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
        return self.experiment_names_by_canonical_name.get(canonical_name) or []

class BingoIdentityCache(object):

    MEMCACHE_KEY = "_gae_bingo_identity_cache:%s"

    @staticmethod
    def key_for_identity(ident):
        return BingoIdentityCache.MEMCACHE_KEY % ident

    @staticmethod
    def get():
        init_request_cache_from_memcache()

        key = BingoIdentityCache.key_for_identity(identity())
        if not REQUEST_CACHE.get(key):
            REQUEST_CACHE[key] = BingoIdentityCache.load_from_datastore()

        return REQUEST_CACHE[key]

    def store_for_identity_if_dirty(self, ident):
        if not self.dirty:
            return

        # No longer dirty
        self.dirty = False

        memcache.set(BingoIdentityCache.key_for_identity(ident), self)

        # Always fire off a task queue to persist bingo identity cache
        # since there's no cron job persisting these objects like BingoCache.
        self.persist_to_datastore(ident)

    def persist_to_datastore(self, ident):

        # Add the memcache value to a random memcache bucket which
        # will be persisted to the datastore when it overflows
        # or when the periodic cron job is run
        bucket = random.randint(0, 50)
        key = "_gae_bingo_identity_bucket:%s" % bucket

        list_identities = memcache.get(key) or []
        list_identities.append(ident)

        if len(list_identities) > 50:

            # If over 50 identities are waiting for persistent storage, 
            # go ahead and kick off a deferred task to do so
            # in case it'll be a while before the cron job runs.
            deferred.defer(persist_gae_bingo_identity_records, list_identities)

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
        dict_buckets = memcache.get_multi(["_gae_bingo_identity_bucket:%s" % bucket for bucket in range(0, 50)])

        for key in dict_buckets:
            if len(dict_buckets[key]) > 0:
                deferred.defer(persist_gae_bingo_identity_records, dict_buckets[key])
                memcache.set(key, [])

    @staticmethod
    def load_from_datastore():
        bingo_identity_cache = _GAEBingoIdentityRecord.load(identity())
        
        if bingo_identity_cache:
            bingo_identity_cache.purge()
            bingo_identity_cache.dirty = True
            bingo_identity_cache.store_for_identity_if_dirty(identity())
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

def bingo_and_identity_cache():
    return BingoCache.get(), BingoIdentityCache.get()

def store_if_dirty():
    # Only load from request cache here -- if it hasn't been loaded from memcache previously, it's not dirty.
    bingo_cache = REQUEST_CACHE.get(BingoCache.MEMCACHE_KEY)
    bingo_identity_cache = REQUEST_CACHE.get(BingoIdentityCache.key_for_identity(identity()))

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
                        pickled = pickle.dumps(identity_cache),
                    )
            bingo_identity.put()

class PersistToDatastore(RequestHandler):
    def get(self):
        BingoCache.get().persist_to_datastore()
        BingoIdentityCache.persist_buckets_to_datastore()
        
class LogSnapshotToDatastore(RequestHandler):
    def get(self):
        BingoCache.get().log_cache_snapshot()

