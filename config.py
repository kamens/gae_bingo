from __future__ import absolute_import

from google.appengine.api import users

# CUSTOMIZE can_see_experiments however you want to specify
# whether or not the currently-logged-in user has access
# to the experiment dashboard.
def can_control_experiments():
    return users.is_current_user_admin()

# CUSTOMIZE current_logged_in_identity to make your a/b sessions
# stickier and more persistent per user.
#
# This should return one of the following:
#
#   A) a db.Model that identifies the current user, like models.UserData.current()
#   B) a unique string that consistently identifies the current user, like users.get_current_user().user_id()
#   C) None, if your app has no way of identifying the current user for the current request. In this case gae_bingo will automatically use a random unique identifier.
#
# Ideally, this should be connected to your app's existing identity system.
#
# To get the strongest identity tracking even when switching from a random, not logged-in user
# to a logged in user, return a model that inherits from GaeBingoIdentityModel.
# See docs for details.
#
# Examples:
#   return models.UserData.current()
#         ...or...
#   from google.appengine.api import users
#   return users.get_current_user().user_id() if users.get_current_user() else None
def current_logged_in_identity():
    from models import UserData
    return UserData.current(bust_cache=True)


