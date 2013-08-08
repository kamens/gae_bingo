from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

from .. import config, middleware

import run_step


class Homepage(webapp.RequestHandler):
    def get(self):
        pass


application = webapp.WSGIApplication([
    ("/gae_bingo/tests/run_step", run_step.RunStep),
    ("/.*", Homepage),
])
application = middleware.GAEBingoWSGIMiddleware(application)
application = config.config.wrap_wsgi_app(application)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
