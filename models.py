from collections import defaultdict
import datetime

from google.appengine.ext import db
from google.appengine.ext import ndb

import pickle_util
import synchronized_counter


# We are explicit here about which model properties are indexed and
# which aren't (even when we're just repeating the default behavior),
# to be maximally clear.  We keep indexed properties to a minimum to
# reduce put()-time.  (The cost is you can't pass an unindexed
# property to filter().)

# If you use a datastore model to uniquely identify each user,
# let it inherit from this class, like so...
#
#       class UserData(GAEBingoIdentityModel)
#
# ...this will let gae_bingo automatically take care of persisting ab_test
# identities from unregistered users to logged in users.
class GAEBingoIdentityModel(db.Model):
    gae_bingo_identity = db.StringProperty(indexed=False)

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
    # This is used for a db-query in fetch_for_experiment()
    name = db.StringProperty(indexed=True)

    # Not necessarily unique. Experiments "monkeys" and "monkeys (2)" both have
    # canonical_name "monkeys"
    # This isn't used for db-querying in code, but can be for one-offs.
    canonical_name = db.StringProperty(indexed=True)
    family_name = db.StringProperty(indexed=False)
    conversion_name = db.StringProperty(indexed=False)
    conversion_type = db.StringProperty(
        indexed=False,
        default=ConversionTypes.Binary,
        choices=set(ConversionTypes.get_all_as_list()))

    # Experiments can be live (running), stopped (not running, not archived),
    # or archived (not running, permanently archived).
    # Stopped experiments aren't collecting data, but they exist and can be
    # used to "short-circuit" an alternative by showing it to all users even
    # before the code is appropriately modified to do so.
    live = db.BooleanProperty(indexed=False, default=True)
    # This is used for a db-query in cache.py:load_from_datastore()
    archived = db.BooleanProperty(indexed=True, default=False)

    dt_started = db.DateTimeProperty(indexed=False, auto_now_add=True)
    short_circuit_pickled_content = db.BlobProperty(indexed=False)

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
        if "_" in self.conversion_name:
            group = "_".join(self.conversion_name.split("_")[:-1])
            return group.capitalize().replace("_", " ")
        else:
            return self.conversion_name

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

    @property
    def participants_key(self):
        return "%s:participants" % self.name

    @property
    def conversions_key(self):
        return "%s:conversions" % self.name

    def reset_counters(self):
        """Reset the participants and conversions accumulating counters."""
        synchronized_counter.SynchronizedCounter.delete_multi(
                [self.participants_key, self.conversions_key])


class _GAEBingoAlternative(db.Model):
    number = db.IntegerProperty(indexed=False)
    experiment_name = db.StringProperty(indexed=False)
    pickled_content = db.BlobProperty(indexed=False)
    conversions = db.IntegerProperty(indexed=False, default=0)
    participants = db.IntegerProperty(indexed=False, default=0)
    live = db.BooleanProperty(indexed=False, default=True)
    # This is used for a db-query in cache.py:load_from_datastore()
    archived = db.BooleanProperty(indexed=True, default=False)
    weight = db.IntegerProperty(indexed=False, default=1)

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

    @property
    def participants_key(self):
        return "%s:participants" % self.experiment_name

    @property
    def conversions_key(self):
        return "%s:conversions" % self.experiment_name

    @ndb.tasklet
    def increment_participants_async(self):
        """Increment a memcache.incr-backed counter to keep track of
        participants in a scalable fashion.

        It's possible that the cached _GAEBingoAlternative entities will fall a
        bit behind due to concurrency issues, but the memcache.incr'd version
        should stay up-to-date and be persisted.

        Returns:
            True if participants was successfully incremented, False otherwise.
        """
        incremented = (yield
                synchronized_counter.SynchronizedCounter.incr_async(
                    self.participants_key, self.number))
        raise ndb.Return(incremented)

    @ndb.tasklet
    def increment_conversions_async(self):
        """Increment a memcache.incr-backed counter to keep track of
        conversions in a scalable fashion.

        It's possible that the cached _GAEBingoAlternative entities will fall a
        bit behind due to concurrency issues, but the memcache.incr'd version
        should stay up-to-date and be persisted.

        Returns:
            True if conversions was successfully incremented, False otherwise.
        """
        incremented = (yield
            synchronized_counter.SynchronizedCounter.incr_async(
                self.conversions_key, self.number))
        raise ndb.Return(incremented)

    def latest_participants_count(self):
        running_count = synchronized_counter.SynchronizedCounter.get(
                self.participants_key, self.number)
        return self.participants + running_count

    def latest_conversions_count(self):
        running_count = synchronized_counter.SynchronizedCounter.get(
                self.conversions_key, self.number)
        return self.conversions + running_count


class _GAEBingoSnapshotLog(db.Model):
    """A snapshot of bingo metrics for a given experiment alternative.

    This is always created with the _GAEBingoExperiment as the entity parent.
    """
    alternative_number = db.IntegerProperty(indexed=False)
    conversions = db.IntegerProperty(indexed=False, default=0)
    participants = db.IntegerProperty(indexed=False, default=0)
    # This is used for a db-query in fetch_for_experiment().
    time_recorded = db.DateTimeProperty(indexed=True, auto_now_add=True)

    @staticmethod
    def fetch_for_experiment(name, limit=100):
        """Retrieves the most recent snapshots for a given experiment.

        Arguments:
            name -- the name of the experiment (not canonical name).
                e.g. "Homepage layout v2point3 (answer_added_binary)"
            limit -- number of snapshots across all the alternatives to fetch
                (note it could be that some alternatives have one more than
                others, depending on the distribution.)
        Returns:
            A dict of snapshots, indexed by alternative_number.
        """
        exp = _GAEBingoExperiment.all().filter("name =", name).get()
        if not exp:
            return {}

        results = (_GAEBingoSnapshotLog.all()
                       .ancestor(exp)
                       .order("-time_recorded")
                       .fetch(limit))
        groups = defaultdict(list)
        for s in results:
            groups[s.alternative_number].append(s)
        return groups


class _GAEBingoExperimentNotes(db.Model):
    """Notes and list of emotions associated w/ results of an experiment."""

    # arbitrary user-supplied notes
    notes = db.TextProperty(indexed=False)

    # list of choices from selection of emotions, such as "happy" and "surprised"
    pickled_emotions = db.BlobProperty(indexed=False)

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
    identity = db.StringProperty(indexed=False)

    # Stores a pickled BingoIdentityCache object.
    pickled = db.BlobProperty(indexed=False)

    # A timestamp for keeping track when this record was last updated.
    # Used (well, potentially used) by analytics.git:src/fetch_entities.py.
    backup_timestamp = db.DateTimeProperty(indexed=True, auto_now=True)

    @staticmethod
    def key_for_identity(identity):
        return "_gae_bingo_identity_record:%s" % identity

    @staticmethod
    def load(identity):
        gae_bingo_identity_record = (
                _GAEBingoIdentityRecord.get_by_key_name(
                    _GAEBingoIdentityRecord.key_for_identity(identity)))
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
                key_name = "_gae_experiment:%s" % experiment_name,
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
