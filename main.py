from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

from gae_bingo import cache, dashboard, middleware, plots, blotter, api

application = webapp.WSGIApplication([
    ("/gae_bingo/persist", cache.PersistToDatastore),
    ("/gae_bingo/log_snapshot", cache.LogSnapshotToDatastore),
    ("/gae_bingo/blotter/ab_test", blotter.AB_Test),
    ("/gae_bingo/blotter/bingo", blotter.Bingo),

    ("/gae_bingo/dashboard", dashboard.Dashboard),
    ("/gae_bingo/dashboard/export", dashboard.Export),
    ("/gae_bingo/api/v1/experiments", api.Experiments),
    ("/gae_bingo/api/v1/experiments/summary", api.ExperimentSummary),
    ("/gae_bingo/api/v1/experiments/conversions", api.ExperimentConversions),
    ("/gae_bingo/api/v1/experiments/control", api.ControlExperiment),
])
application = middleware.GAEBingoWSGIMiddleware(application)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()

