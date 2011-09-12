from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

from gae_bingo.tests import RunStep
from gae_bingo import middleware

application = webapp.WSGIApplication([
    ("/gae_bingo/tests/run_step", RunStep),
])
application = middleware.GAEBingoWSGIMiddleware(application)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()

