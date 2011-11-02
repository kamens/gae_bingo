import logging
import os

from google.appengine.ext.webapp import RequestHandler

from .gae_bingo import choose_alternative, delete_experiment, resume_experiment
from .cache import BingoCache
from .stats import describe_result_in_words
from .config import can_control_experiments
from .jsonify import jsonify
from .plots import get_experiment_timeline_data

class Experiments(RequestHandler):

    def get(self):

        if not can_control_experiments():
            return

        bingo_cache = BingoCache.get()

        experiment_results = {}

        for experiment_name in bingo_cache.experiments:
            experiment = bingo_cache.get_experiment(experiment_name)

            if experiment.canonical_name not in experiment_results:
                experiment_results[experiment.canonical_name] = experiment

        context = { "experiment_results": experiment_results.values() }

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(context))

class ExperimentSummary(RequestHandler):

    def get(self):

        if not can_control_experiments():
            return

        bingo_cache = BingoCache.get()
        canonical_name = self.request.get("canonical_name")
        experiments, alternatives = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

        if not experiments:
            raise Exception("No experiments matching canonical name: %s" % canonical_name)

        experiments = sorted(experiments, key=lambda experiment: experiment.conversion_name)

        context = {}
        is_first = True

        for experiment in experiments:
            if "canonical_name" not in context:
                context["canonical_name"] = experiment.canonical_name

            if "live" not in context:
                context["live"] = experiment.live

            if "multiple_experiments" not in context:
                context["multiple_experiments"] = len(experiments) > 1

            if "experiments" not in context:
                context["experiments"] = []

            context["experiments"].append({
                "conversion_name": experiment.conversion_name,
                "experiment_name": experiment.name,
                "is_first": is_first,
            })

            is_first = False

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(context))

class ExperimentConversions(RequestHandler):

    def get(self):

        if not can_control_experiments():
            return

        bingo_cache = BingoCache.get()
        experiment_name = self.request.get("experiment_name")
        experiment = bingo_cache.get_experiment(experiment_name)
        alternatives = bingo_cache.get_alternatives(experiment_name)

        if not experiment or not alternatives:
            raise Exception("No experiment matching name: %s" % canonical_name)

        for alternative in alternatives:
            alternative.live = experiment.live
            alternative.is_short_circuited = (not experiment.live) and (experiment.short_circuit_content == alternative.content)

        context = {
                "canonical_name": experiment.canonical_name,
                "live": experiment.live,
                "total_participants": reduce(lambda a, b: a + b, map(lambda alternative: alternative.participants, alternatives)),
                "total_conversions": reduce(lambda a, b: a + b, map(lambda alternative: alternative.conversions, alternatives)),
                "alternatives": alternatives,
                "significance_test_results": describe_result_in_words(alternatives),
                "y_axis_title": experiment.y_axis_title,
                "timeline_series": get_experiment_timeline_data(experiment),
        }

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(context))

class ControlExperiment(RequestHandler):

    def post(self):

        if not can_control_experiments():
            return

        canonical_name = self.request.get("canonical_name")
        action = self.request.get("action")

        if not action or not canonical_name:
            return

        bingo_cache = BingoCache.get()

        if action == "choose_alternative":
            choose_alternative(canonical_name, int(self.request.get("alternative_number")))
        elif action == "delete":
            delete_experiment(canonical_name)
        elif action == "resume":
            resume_experiment(canonical_name)

        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(jsonify(True))
