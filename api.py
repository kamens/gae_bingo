import itertools
import logging
import os

from google.appengine.ext.webapp import RequestHandler

from .gae_bingo import choose_alternative, delete_experiment, resume_experiment
from .gae_bingo import archive_experiment, modulo_choose
from .models import _GAEBingoExperimentNotes
from .cache import BingoCache
from .stats import describe_result_in_words
from .config import can_control_experiments, retrieve_identity
from .jsonify import jsonify
from .plots import get_experiment_timeline_data
from .identity import identity

class GAEBingoAPIRequestHandler(RequestHandler):
    """Request handler for all GAE/Bingo API requests.
    
    Each individual GAE/Bingo API request is either interacting with live data
    or archived data. Live and archived data are stored and cached differently,
    and this request handler can load each set of data as specified by the
    request.
    """

    def is_requesting_archives(self):
        """True if request is interacting with archived data."""
        return self.request.get("archives") == "1"

    def request_bingo_cache(self):
        """Return BingoCache object for live/archived data, as appropriate.

        A BingoCache obect acts as the datastore for experiments and
        alternatives for the length of an API request. If loaded from archives,
        the experiments will be inactive and read-only unless permanently
        deleting them.
        """
        if self.is_requesting_archives():
            return BingoCache.load_from_datastore(archives=True)
        else:
            return BingoCache.get()

class Experiments(GAEBingoAPIRequestHandler):

    def get(self):

        if not can_control_experiments():
            return

        bingo_cache = self.request_bingo_cache()

        experiment_results = {}

        for canonical_name in bingo_cache.experiment_names_by_canonical_name:
            experiments, alternative_lists = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

            if not experiments or not alternative_lists:
                continue

            for experiment, alternatives in itertools.izip(
                    experiments, alternative_lists):

                # Combine related experiments and alternatives into a single
                # canonical experiment for response
                if experiment.canonical_name not in experiment_results:
                    experiment.alternatives = alternatives
                    experiment_results[experiment.canonical_name] = experiment

        # Sort by status primarily, then name or date
        results = experiment_results.values()

        if self.is_requesting_archives():
            results.sort(key=lambda ex: ex.dt_started, reverse=True)
        else:
            results.sort(key=lambda ex: ex.canonical_name)

        results.sort(key=lambda ex: ex.live, reverse=True)

        context = { "experiment_results": results }

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(context))

class ExperimentSummary(GAEBingoAPIRequestHandler):

    def get(self):

        if not can_control_experiments():
            return

        bingo_cache = self.request_bingo_cache()
        canonical_name = self.request.get("canonical_name")
        experiments, alternatives = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

        if not experiments:
            raise Exception("No experiments matching canonical name: %s" % canonical_name)

        context = {}
        prev = None
        prev_dict = {}

        experiment_notes = _GAEBingoExperimentNotes.get_for_experiment(experiments[0])
        if experiment_notes:
            context["notes"] = experiment_notes.notes
            context["emotions"] = experiment_notes.emotions

        experiments = sorted(experiments, key=lambda experiment: experiment.conversion_name)
        for experiment in experiments:
            if "canonical_name" not in context:
                context["canonical_name"] = experiment.canonical_name

            if "live" not in context:
                context["live"] = experiment.live

            if "multiple_experiments" not in context:
                context["multiple_experiments"] = len(experiments) > 1

            if "experiments" not in context:
                context["experiments"] = []

            exp_dict = {
                "conversion_name": experiment.conversion_name,
                "experiment_name": experiment.name,
                "pretty_conversion_name": experiment.pretty_conversion_name,
                "archived": experiment.archived,
            }

            if prev and prev.conversion_group == experiment.conversion_group:
                if "conversion_group" not in prev_dict:
                    prev_dict["start_conversion_group"] = True
                    prev_dict["conversion_group"] = prev.conversion_group
                exp_dict["conversion_group"] = experiment.conversion_group
            else:
                if "conversion_group" in prev_dict:
                    prev_dict["end_conversion_group"] = True

            context["experiments"].append(exp_dict)
            prev_dict = exp_dict
            prev = experiment

        if "conversion_group" in prev_dict:
            prev_dict["end_conversion_group"] = True

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(context))

class ExperimentConversions(GAEBingoAPIRequestHandler):

    def get(self):

        if not can_control_experiments():
            return

        bingo_cache = self.request_bingo_cache()
        experiment_name = self.request.get("experiment_name")
        experiment = bingo_cache.get_experiment(experiment_name)
        alternatives = bingo_cache.get_alternatives(experiment_name)

        if not experiment or not alternatives:
            raise Exception("No experiment matching name: %s" % canonical_name)

        short_circuit_number = -1

        for alternative in alternatives:
            if ((not experiment.live) and 
                    experiment.short_circuit_content == alternative.content):
                short_circuit_number = alternative.number

            alternative.load_latest_counts()

        context = {
                "canonical_name": experiment.canonical_name,
                "live": experiment.live,
                "total_participants": reduce(lambda a, b: a + b, map(lambda alternative: alternative.participants, alternatives)),
                "total_conversions": reduce(lambda a, b: a + b, map(lambda alternative: alternative.conversions, alternatives)),
                "alternatives": alternatives,
                "significance_test_results": describe_result_in_words(alternatives),
                "y_axis_title": experiment.y_axis_title,
                "timeline_series": get_experiment_timeline_data(experiment),
                "short_circuit_number": short_circuit_number
        }

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(context))

class ControlExperiment(GAEBingoAPIRequestHandler):

    def post(self):

        if not can_control_experiments():
            return

        canonical_name = self.request.get("canonical_name")
        action = self.request.get("action")

        if self.is_requesting_archives() and action != "delete":
            # Can only delete archived experiments
            return

        if not action or not canonical_name:
            return

        if action == "choose_alternative":
            choose_alternative(canonical_name, int(self.request.get("alternative_number")))
        elif action == "delete":
            delete_experiment(canonical_name, self.request_bingo_cache())
        elif action == "resume":
            resume_experiment(canonical_name)
        elif action == "archive":
            archive_experiment(canonical_name)

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(True))

class NoteExperiment(GAEBingoAPIRequestHandler):
    """Request handler for saving experiments' notes and list of emotions."""

    def post(self):

        if not can_control_experiments():
            return

        bingo_cache = self.request_bingo_cache()
        canonical_name = self.request.get("canonical_name")
        experiments, alternative_lists = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

        if not experiments:
            raise Exception("No experiments matching name: %s" % canonical_name)

        notes = self.request.get("notes")
        emotions = self.request.get_all("emotions[]")

        _GAEBingoExperimentNotes.save(experiments[0], notes, emotions)

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(True))

class Alternatives(GAEBingoAPIRequestHandler):

    def get(self):

        if not can_control_experiments():
            return

        query = self.request.get("query")
        if query:
            id = retrieve_identity(query)
        else:
            id = identity()

        if not id:
            raise Exception("Error getting identity for query: %s" % str(query))
        
        bingo_cache = self.request_bingo_cache()

        chosen_alternatives = {}

        for experiment_name in bingo_cache.experiments:
            experiment = bingo_cache.get_experiment(experiment_name)

            if experiment.canonical_name not in chosen_alternatives:
                alternatives = bingo_cache.get_alternatives(experiment_name)
                alternative = modulo_choose(experiment.hashable_name, alternatives, id)
                chosen_alternatives[experiment.canonical_name] = str(alternative.content)

        context = {
            "identity": id,
            "alternatives": chosen_alternatives,
        }

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(context))
