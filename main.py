from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

from gae_bingo import cache
from gae_bingo import dashboard
from gae_bingo import middleware

application = webapp.WSGIApplication([
    ("/gae_bingo/persist", cache.PersistToDatastore),
    ("/gae_bingo/dashboard", dashboard.Dashboard),
    ("/gae_bingo/dashboard/control_experiment", dashboard.ControlExperiment),
])
application = middleware.GAEBingoWSGIMiddleware(application)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()

