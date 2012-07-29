import datetime
import os

from google.appengine.ext import db
from google.appengine.api import memcache

import pickle_util

# If you use a datastore model to uniquely identify each user,
# let it inherit from this class, like so...
#
#       class UserData(GAEBingoIdentityModel)
#
# ...this will let gae_bingo automatically take care of persisting ab_test
# identities from unregistered users to logged in users.
class GAEBingoIdentityModel(db.Model):
    gae_bingo_identity = db.StringProperty()

class ConversionTypes():
    # Binary conversions are counted at most once per user
    Binary = "binary"

    # Counting conversions increment each time
    Counting = "counting"

    @staticmethod
    def get_all_as_list():
        return [ConversionTypes.Binary, ConversionTypes.Counting]

    def __setattr__(self, attr, value):
        pass

class _GAEBingoExperiment(db.Model):
    name = db.StringProperty()

    # Not necessarily unique. Experiments "monkeys" and "monkeys (2)" both have
    # canonical_name "monkeys"
    canonical_name = db.StringProperty()
    family_name = db.StringProperty()
    conversion_name = db.StringProperty()
    conversion_type = db.StringProperty(default=ConversionTypes.Binary, choices=set(ConversionTypes.get_all_as_list()))

    # Experiments can be live (running), stopped (not running, not archived),
    # or archived (not running, permanently archived).
    # Stopped experiments aren't collecting data, but they exist and can be
    # used to "short-circuit" an alternative by showing it to all users even
    # before the code is appropriately modified to do so.
    live = db.BooleanProperty(default = True)
    archived = db.BooleanProperty(default = False)

    dt_started = db.DateTimeProperty(auto_now_add = True)
    short_circuit_pickled_content = db.BlobProperty()

    @property
    def stopped(self):
        return not (self.archived or self.live)

    @property
    def short_circuit_content(self):
        if self.short_circuit_pickled_content:
            return pickle_util.load(self.short_circuit_pickled_content)
        else:
            return None

    def set_short_circuit_content(self, value):
        self.short_circuit_pickled_content = pickle_util.dump(value)

    @property
    def pretty_name(self):
        return self.name.capitalize().replace("_", " ")

    @property
    def pretty_conversion_name(self):
        return self.conversion_name.capitalize().replace("_", " ")

    @property
    def pretty_canonical_name(self):
        return self.canonical_name.capitalize().replace("_", " ")

    @property
    def conversion_group(self):
        group = "_".join(self.conversion_name.split("_")[:-1])
        return group.capitalize().replace("_", " ")

    @property
    def hashable_name(self):
        return self.family_name if self.family_name else self.canonical_name

    @property
    def age_desc(self):
        if self.archived:
            return "Ran %s UTC" % self.dt_started.strftime('%Y-%m-%d at %H:%M:%S')

        days_running = (datetime.datetime.now() - self.dt_started).days
        
        if days_running < 1:
            return "Less than a day old"
        else:
            return "%s day%s old" % (days_running, ("" if days_running == 1 else "s"))

    @property
    def y_axis_title(self):
        if self.conversion_type == ConversionTypes.Counting:
            "Average Conversions per Participant"
        else:
            "Conversions (%)"


class _GAEBingoAlternative(db.Model):
    number = db.IntegerProperty()
    experiment_name = db.StringProperty()
    pickled_content = db.BlobProperty()
    conversions = db.IntegerProperty(default = 0)
    participants = db.IntegerProperty(default = 0)
    live = db.BooleanProperty(default = True)
    archived = db.BooleanProperty(default = False)
    weight = db.IntegerProperty(default = 1)

    @staticmethod
    def key_for_experiment_name_and_number(experiment_name, number):
        return "_gae_alternative:%s:%s" % (experiment_name, number)

    @property
    def content(self):
        return pickle_util.load(self.pickled_content)

    @property
    def pretty_content(self):
        return str(self.content).capitalize()

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
        """ Increment a memcache.incr-backed counter to keep track of participants in a scalable fashion.
        
        It's possible that the cached _GAEBingoAlternative entities will fall a bit behind
        due to concurrency issues, but the memcache.incr'd version should stay up-to-date and
        be persisted.

        Returns:
            True if participants was successfully incremented, False otherwise."
        """
        participants = memcache.incr("%s:participants" % self.key_for_self(), initial_value=self.participants)

        if participants is None:
            # Memcache may be down and returning None for incr. Don't update the model in this case.
            return False

        self.participants = participants
        return True

    def increment_conversions(self):
        """ Increment a memcache.incr-backed counter to keep track of conversions in a scalable fashion.

        It's possible that the cached _GAEBingoAlternative entities will fall a bit behind
        due to concurrency issues, but the memcache.incr'd version should stay up-to-date and
        be persisted.

        Returns:
            True if conversions was successfully incremented, False otherwise.
        """
        conversions = memcache.incr("%s:conversions" % self.key_for_self(), initial_value=self.conversions)

        if conversions is None:
            # Memcache may be down and returning None for incr. Don't update the model in this case.
            return False

        self.conversions = conversions
        return True

    def latest_participants_count(self):
        return max(self.participants, long(memcache.get("%s:participants" % self.key_for_self()) or 0))

    def latest_conversions_count(self):
        return max(self.conversions, long(memcache.get("%s:conversions" % self.key_for_self()) or 0))

    def reset_counts(self):
        memcache.delete_multi(["%s:participants" % self.key_for_self(), "%s:conversions" % self.key_for_self()])

    def load_latest_counts(self):
        # When persisting to datastore, we want to store the most recent value we've got
        self.participants = self.latest_participants_count()
        self.conversions = self.latest_conversions_count()


class _GAEBingoSnapshotLog(db.Model):
    alternative_number = db.IntegerProperty()
    conversions = db.IntegerProperty(default = 0)
    participants = db.IntegerProperty(default = 0)
    time_recorded = db.DateTimeProperty(auto_now_add = True)


class _GAEBingoExperimentNotes(db.Model):
    """Notes and list of emotions associated w/ results of an experiment."""

    # arbitrary user-supplied notes
    notes = db.TextProperty()

    # list of choices from selection of emotions, such as "happy" and "surprised"
    pickled_emotions = db.BlobProperty()

    @staticmethod
    def key_for_experiment(experiment):
        """Return the key for this experiment's notes."""
        return "_gae_bingo_notes:%s" % experiment.name

    @staticmethod
    def get_for_experiment(experiment):
        """Return GAEBingoExperimentNotes, if it exists, for the experiment."""
        return _GAEBingoExperimentNotes.get_by_key_name(
                _GAEBingoExperimentNotes.key_for_experiment(experiment),
                parent=experiment)

    @staticmethod
    def save(experiment, notes, emotions):
        """Save notes and emo list, associating with specified experiment."""
        notes = _GAEBingoExperimentNotes(
            key_name = _GAEBingoExperimentNotes.key_for_experiment(experiment),
            parent = experiment,
            notes = notes,
            pickled_emotions = pickle_util.dump(emotions))
        notes.put()

    @property
    def emotions(self):
        """Return unpickled list of emotions tied to these notes."""
        if self.pickled_emotions:
            return pickle_util.load(self.pickled_emotions)
        else:
            return None


class _GAEBingoIdentityRecord(db.Model):
    identity = db.StringProperty()
    pickled = db.BlobProperty()

    @staticmethod
    def key_for_identity(identity):
        return "_gae_bingo_identity_record:%s" % identity

    @staticmethod
    def load(identity):
        gae_bingo_identity_record = _GAEBingoIdentityRecord.get_by_key_name(_GAEBingoIdentityRecord.key_for_identity(identity))
        if gae_bingo_identity_record:
            return pickle_util.load(gae_bingo_identity_record.pickled)

        return None

def create_experiment_and_alternatives(experiment_name, canonical_name, alternative_params = None, conversion_name = None, conversion_type = ConversionTypes.Binary, family_name = None):

    if not experiment_name:
        raise Exception("gae_bingo experiments must be named.")

    conversion_name = conversion_name or experiment_name

    if not alternative_params:
        # Default to simple True/False testing
        alternative_params = [True, False]

    # Generate a random key name for this experiment so it doesn't collide with
    # any past experiments of the same name. All other entities, such as
    # alternatives, snapshots, and notes, will then use this entity as their
    # parent.
    experiment = _GAEBingoExperiment(
                key_name = "%s:%s" % (
                    experiment_name, os.urandom(8).encode("hex")),
                name = experiment_name,
                canonical_name = canonical_name,
                family_name = family_name,
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
                        pickled_content = pickle_util.dump(content),
                        live = True,
                        weight = alternative_params[content] if is_dict else 1,
                    )
                )

    return experiment, alternatives
