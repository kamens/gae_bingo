import pickle
import datetime
import logging

from google.appengine.ext import db
from google.appengine.api import memcache

# If you use a datastore model to uniquely identify each user,
# let it inherit from this class, like so...
#
#       class UserData(GAEBingoIdentityModel, db.Model)
#
# ...this will let gae_bingo automatically take care of persisting ab_test
# identities from unregistered users to logged in users.
class GAEBingoIdentityModel(db.Model):
    gae_bingo_identity = db.StringProperty()

class ConversionTypes():
    Binary = "binary"
    Counting = "counting"
    @staticmethod
    def get_all_as_list():
        return [ConversionTypes.Binary, ConversionTypes.Counting]
    def __setattr__(self, attr, value):
        pass

class _GAEBingoExperiment(db.Model):
    name = db.StringProperty()
    # Not necessarily unique. Experiments "monkeys" and "monkeys (2)" both have canonical_name "monkeys"
    canonical_name = db.StringProperty()
    conversion_name = db.StringProperty()
    conversion_type = db.StringProperty(default=ConversionTypes.Binary, choices=set(ConversionTypes.get_all_as_list()))
    live = db.BooleanProperty(default = True)
    dt_started = db.DateTimeProperty(auto_now_add = True)
    short_circuit_pickled_content = db.BlobProperty()

    @property
    def short_circuit_content(self):
        return pickle.loads(self.short_circuit_pickled_content)

    def set_short_circuit_content(self, value):
        self.short_circuit_pickled_content = pickle.dumps(value)

    @property
    def pretty_name(self):
        return self.name.capitalize().replace("_", " ")

    @property
    def pretty_canonical_name(self):
        return self.canonical_name.capitalize().replace("_", " ")

    @property
    def status(self):
        if self.live:
            days_running = (datetime.datetime.now() - self.dt_started).days
            
            if days_running < 1:
                return "Running for less than a day"
            else:
                return "Running for %s day%s" % (days_running, ("" if days_running == 1 else "s"))

        else:
            return "Ended manually"

    @property
    def y_axis_title(self):
        if self.conversion_type == ConversionTypes.Counting:
            "Average Conversions per Participant"
        else:
            "Conversions (%)"

    @staticmethod
    def key_for_name(name):
        return "_gae_experiment:%s" % name

    @staticmethod
    def exists(name):
        return cache.exists(Experiment.key_for_name(name))
    

class _GAEBingoAlternative(db.Model):
    number = db.IntegerProperty()
    experiment_name = db.StringProperty()
    pickled_content = db.BlobProperty()
    conversions = db.IntegerProperty(default = 0)
    participants = db.IntegerProperty(default = 0)
    live = db.BooleanProperty(default = True)
    weight = db.IntegerProperty(default = 1)

    @staticmethod
    def key_for_experiment_name_and_number(experiment_name, number):
        return "_gae_alternative:%s:%s" % (experiment_name, number)

    @property
    def content(self):
        return pickle.loads(self.pickled_content)

    @property
    def conversion_rate(self):
        if self.participants > 0:
            return float(self.conversions) / float(self.participants)
        return 0

    @property
    def pretty_conversion_rate(self):
        return "%4.2f%%" % (self.conversion_rate * 100)

    def key_for_self(self):
        return _GAEBingoAlternative.key_for_experiment_name_and_number(self.experiment_name, self.number)

    def increment_participants(self):
        # Use a memcache.incr-backed counter to keep track of increments in a scalable fashion.
        # It's possible that the cached _GAEBingoAlternative entities will fall a bit behind
        # due to concurrency issues, but the memcache.incr'd version should stay up-to-date and
        # be persisted.
        self.participants = long(memcache.incr("%s:participants" % self.key_for_self(), initial_value=self.participants))

    def increment_conversions(self):
        # Use a memcache.incr-backed counter to keep track of increments in a scalable fashion.
        # It's possible that the cached _GAEBingoAlternative entities will fall a bit behind
        # due to concurrency issues, but the memcache.incr'd version should stay up-to-date and
        # be persisted.
        self.conversions = long(memcache.incr("%s:conversions" % self.key_for_self(), initial_value=self.conversions))

    def reset_counts(self):
        memcache.delete_multi(["%s:participants" % self.key_for_self(), "%s:conversions" % self.key_for_self()])

    def load_latest_counts(self):
        # When persisting to datastore, we want to store the most recent value we've got
        self.participants = max(self.participants, long(memcache.get("%s:participants" % self.key_for_self()) or 0))
        self.conversions = max(self.conversions, long(memcache.get("%s:conversions" % self.key_for_self()) or 0))
        

class _GAEBingoSnapshotLog(db.Model):
    alternative_number = db.IntegerProperty()
    conversions = db.IntegerProperty(default = 0)
    participants = db.IntegerProperty(default = 0)
    time_recorded = db.DateTimeProperty(auto_now_add = True)
        
    
class _GAEBingoIdentityRecord(db.Model):
    identity = db.StringProperty()
    pickled = db.BlobProperty()

    @staticmethod
    def key_for_identity(identity):
        return "_gae_bingo_identity_record:%s" % identity

    @staticmethod
    def load(identity):
        gae_bingo_identity_record = _GAEBingoIdentityRecord.all().filter("identity =", identity).get()
        if gae_bingo_identity_record:
            return pickle.loads(gae_bingo_identity_record.pickled)

        return None

def create_experiment_and_alternatives(experiment_name, canonical_name, alternative_params = None, conversion_name = None, conversion_type = ConversionTypes.Binary):

    if not experiment_name:
        raise Exception("gae_bingo experiments must be named.")

    conversion_name = conversion_name or experiment_name

    if not alternative_params:
        # Default to simple True/False testing
        alternative_params = [True, False]

    experiment = _GAEBingoExperiment(
                key_name = _GAEBingoExperiment.key_for_name(experiment_name),
                name = experiment_name,
                canonical_name = canonical_name,
                conversion_name = conversion_name,
                conversion_type = conversion_type,
                live = True,
            )

    alternatives = []

    is_dict = type(alternative_params) == dict
    for i, content in enumerate(alternative_params):

        alternatives.append(
                _GAEBingoAlternative(
                        key_name = _GAEBingoAlternative.key_for_experiment_name_and_number(experiment_name, i),
                        parent = experiment,
                        experiment_name = experiment.name,
                        number = i,
                        pickled_content = pickle.dumps(content),
                        live = True,
                        weight = alternative_params[content] if is_dict else 1,
                    )
                )

    return experiment, alternatives
