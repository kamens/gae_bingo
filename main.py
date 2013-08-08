from __future__ import absolute_import

from google.appengine.ext.webapp.util import run_wsgi_app
import webapp2
from webapp2_extras.routes import RedirectRoute

from gae_bingo import (cache, dashboard, middleware, plots, blotter,
                       api, redirect, persist)
from gae_bingo.config import config

application = webapp2.WSGIApplication([
    ("/gae_bingo/persist", persist.GuaranteePersistTask),
    ("/gae_bingo/log_snapshot", cache.LogSnapshotToDatastore),
    ("/gae_bingo/blotter/ab_test", blotter.AB_Test),
    ("/gae_bingo/blotter/bingo", blotter.Bingo),

    ("/gae_bingo/redirect", redirect.Redirect),

    ("/gae_bingo", dashboard.Dashboard),
    RedirectRoute('/gae_bingo/dashboard', redirect_to='/gae_bingo'),
    ("/gae_bingo/dashboard/archives", dashboard.Dashboard),
    ("/gae_bingo/dashboard/export", dashboard.Export),

    ("/gae_bingo/api/v1/experiments", api.Experiments),
    ("/gae_bingo/api/v1/experiments/summary", api.ExperimentSummary),
    ("/gae_bingo/api/v1/experiments/conversions", api.ExperimentConversions),
    ("/gae_bingo/api/v1/experiments/control", api.ControlExperiment),
    ("/gae_bingo/api/v1/experiments/notes", api.NoteExperiment),
    ("/gae_bingo/api/v1/alternatives", api.Alternatives),

])
application = middleware.GAEBingoWSGIMiddleware(application)
application = config.wrap_wsgi_app(application)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
