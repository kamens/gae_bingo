from google.appengine.api import lib_config


class _ConfigDefaults(object):
    # CUSTOMIZE set queue_name to something other than "default"
    # if you'd like to use a non-default task queue.
    QUEUE_NAME = "default"

    # CUSTOMIZE can_see_experiments however you want to specify
    # whether or not the currently-logged-in user has access
    # to the experiment dashboard.
    def can_control_experiments():
        return False

    # CUSTOMIZE current_logged_in_identity to make your a/b sessions
    # stickier and more persistent per user.
    #
    # This should return one of the following:
    #
    #   A) a db.Model that identifies the current user, like
    #      user_models.UserData.current()
    #   B) a unique string that consistently identifies the current user, like
    #      users.get_current_user().user_id()
    #   C) None, if your app has no way of identifying the current user for the
    #      current request. In this case gae_bingo will automatically use a random
    #      unique identifier.
    #
    # Ideally, this should be connected to your app's existing identity system.
    #
    # To get the strongest identity tracking even when switching from a random, not
    # logged-in user to a logged in user, return a model that inherits from
    # GaeBingoIdentityModel.  See docs for details.
    #
    # Examples:
    #   return user_models.UserData.current()
    #         ...or...
    #   from google.appengine.api import users
    #   user = users.get_current_user()
    #   return user.user_id() if user else None
    def current_logged_in_identity():
        return None

    # Optionally, you can provide a function that will retrieve the identitiy given
    # a query.  If not used, simply return None.
    def retrieve_identity(query):
        return None

    # CUSTOMIZE is_safe_hostname to whitelist hostnames for gae_bingo.redirect
    def is_safe_hostname(hostname):
        return False

    # CUSTOMIZE wrap_wsgi_app if you want to add middleware around all of the
    # /gae_bingo endpoints, such as to clear a global per-request cache that
    # can_control_experiments uses. If not used, simply return app.
    #
    # Examples:
    #   return app  # No middleware
    #
    #   return RequestCacheMiddleware(app)
    def wrap_wsgi_app(app):
        return app


# TODO(chris): move config to the toplevel. Right now callers do
# config.config.VALUE rather than simply config.VALUE.  I wanted to
# avoid introspecting _ConfigDefaults and exporting values into the
# module namespace.  Until then use "from config import config".
config = lib_config.register('gae_bingo', _ConfigDefaults.__dict__)
