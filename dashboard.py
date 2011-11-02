import logging
import csv
import os
import StringIO
import urllib

from google.appengine.ext.webapp import RequestHandler
from .config import can_control_experiments
from .cache import BingoCache
from .stats import describe_result_in_words

class Dashboard(RequestHandler):

    def get(self):

        if not can_control_experiments():
            self.redirect("/")
            return

        path = os.path.join(os.path.dirname(__file__), "templates/base.html")
        f = None

        try:
            f = open(path, "r")
            html = f.read()
        finally:
            if f:
                f.close()

        self.response.out.write(html)

class Export(RequestHandler):

    def get(self):

        if not can_control_experiments():
            self.redirect("/")
            return

        bingo_cache = BingoCache.get()

        canonical_name = self.request.get("canonical_name")
        experiments, alternatives = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

        if not experiments:
            raise Exception("No experiments matching canonical name: %s" % canonical_name)

        f = StringIO.StringIO()

        try:

            writer = csv.writer(f, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)

            writer.writerow(["EXPERIMENT: %s" % canonical_name])
            writer.writerow([])
            writer.writerow([])

            for experiment, alternatives in zip(experiments, alternatives):

                writer.writerow(["CONVERSION NAME: %s" % experiment.conversion_name])
                writer.writerow([])

                writer.writerow(["ALTERNATIVE NUMBER", "CONTENT", "PARTICIPANTS", "CONVERSIONS", "CONVERSION RATE"])
                for alternative in alternatives:
                    writer.writerow([alternative.number, alternative.content, alternative.participants, alternative.conversions, alternative.conversion_rate])

                writer.writerow([])
                writer.writerow(["SIGNIFICANCE TEST RESULTS: %s" % describe_result_in_words(alternatives)])
                writer.writerow([])

                writer.writerow([])
                writer.writerow([])

            self.response.headers["Content-Type"] = "text/csv"
            self.response.headers["Content-Disposition"] = "attachment; filename=gae_bingo-%s.csv" % urllib.quote(canonical_name)
            self.response.out.write(f.getvalue())

        finally:

            f.close()
