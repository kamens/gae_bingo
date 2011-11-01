import logging
import os

from google.appengine.ext.webapp import RequestHandler
from .config import can_control_experiments

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

