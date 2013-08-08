from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import gae_bingo.config
import gae_bingo.identity
import gae_bingo.middleware


class Homepage(webapp.RequestHandler):
    def get(self):
        pass


class Identity(webapp.RequestHandler):
    def get(self):
        self.response.out.write(gae_bingo.identity.identity())

application = webapp.WSGIApplication([
    ("/identity", Identity),
    ("/.*", Homepage),
])
application = gae_bingo.middleware.GAEBingoWSGIMiddleware(application)
application = gae_bingo.config.config.wrap_wsgi_app(application)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
