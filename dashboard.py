import logging
import os

from google.appengine.ext.webapp import template, RequestHandler

from .gae_bingo import choose_alternative, delete_experiment, resume_experiment
from .cache import BingoCache
from .stats import describe_result_in_words
from .config import can_control_experiments

class Dashboard(RequestHandler):

    def get(self):

        if not can_control_experiments():
            self.redirect("/")
            return

        path = os.path.join(os.path.dirname(__file__), "templates/dashboard.html")

        bingo_cache = BingoCache.get()

        experiment_results = []
        for experiment_name in bingo_cache.experiments:

            experiment = bingo_cache.get_experiment(experiment_name)
            alternatives = bingo_cache.get_alternatives(experiment_name)

            experiment_results.append([
                experiment,
                alternatives,
                reduce(lambda a, b: a + b, map(lambda alternative: alternative.participants, alternatives)),
                reduce(lambda a, b: a + b, map(lambda alternative: alternative.conversions, alternatives)),
                describe_result_in_words(alternatives),
            ])

        experiment_results = sorted(experiment_results, key=lambda results: results[0].name)

        self.response.out.write(
            template.render(path, {
                "experiment_results": experiment_results,
            })
        )

class ControlExperiment(RequestHandler):

    def post(self):

        if not can_control_experiments():
            return

        action = self.request.get("action")

        experiment_name = self.request.get("experiment_name")

        if not experiment_name:
            return

        if action == "choose_alternative":
            choose_alternative(experiment_name, int(self.request.get("alternative_number")))
        elif action == "delete":
            delete_experiment(experiment_name)
        elif action == "resume":
            resume_experiment(experiment_name)

        self.redirect("/gae_bingo/dashboard")
