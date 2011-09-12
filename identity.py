from __future__ import absolute_import

import base64
import logging
import os
import re

from google.appengine.ext import db

from gae_bingo import cookies
from .models import GAEBingoIdentityModel
from .config import current_logged_in_identity

# NOTE: this request caching will need a bit of a touchup once Python 2.7 is released for GAE and concurrent requests are enabled.
IDENTITY_CACHE = None
LOGGED_IN_IDENTITY_CACHE = None
IDENTITY_COOKIE_KEY = "gae_b_id"

def logged_in_bingo_identity():
    global LOGGED_IN_IDENTITY_CACHE

    if LOGGED_IN_IDENTITY_CACHE is None:
        LOGGED_IN_IDENTITY_CACHE = current_logged_in_identity()

    return LOGGED_IN_IDENTITY_CACHE

def identity():
    global IDENTITY_CACHE

    if IDENTITY_CACHE is None:

        if is_bot():

            # Just make all bots identify as the same single user so they don't
            # bias results. Following simple suggestion in
            # http://www.bingocardcreator.com/abingo/faq
            IDENTITY_CACHE = "_gae_bingo_bot"

        else:

            # Try to get unique (hopefully persistent) identity from user's implementation,
            # otherwise grab the current cookie value, otherwise grab random value.
            IDENTITY_CACHE = str(get_logged_in_bingo_identity_value() or get_identity_cookie_value() or get_random_identity_value())

    return IDENTITY_CACHE

def using_logged_in_bingo_identity():
    return identity() and identity() == get_logged_in_bingo_identity_value()

def get_logged_in_bingo_identity_value():
    val = logged_in_bingo_identity()

    if val is None:
        return None

    if isinstance(val, db.Model):

        if isinstance(val, GAEBingoIdentityModel):
            # If it's a db.Model that inherited from GAEBingoIdentityModel, return bingo identity

            if not val.gae_bingo_identity:
                if is_random_identity_value(get_identity_cookie_value()):
                    # If the current model doesn't have a bingo identity associated w/ it
                    # and we have a random cookie value already set, associate it with this identity model.
                    #
                    # This keeps the user's experience consistent between using the site pre- and post-login.
                    val.gae_bingo_identity = get_identity_cookie_value()
                else:
                    # Otherwise just use the key, it's guaranteed to be unique
                    val.gae_bingo_identity = str(val.key())

                val.put()

            return val.gae_bingo_identity

        # If it's just a normal db instance, just use its unique key
        return str(val.key())

    # Otherwise it's just a plain unique string
    return str(val)

def get_random_identity_value():
    return "_gae_bingo_random:%s" % base64.urlsafe_b64encode(os.urandom(30))

def is_random_identity_value(val):
    return val and val.startswith("_gae_bingo_random")

def get_identity_cookie_value():
    cookie_val = cookies.get_cookie_value(IDENTITY_COOKIE_KEY)

    if cookie_val:
        try:
            return base64.urlsafe_b64decode(cookie_val)
        except:
            pass

    return None

def set_identity_cookie_header():
    return cookies.set_cookie_value(IDENTITY_COOKIE_KEY, base64.urlsafe_b64encode(identity()))

def delete_identity_cookie_header():
    return cookies.set_cookie_value(IDENTITY_COOKIE_KEY, "")

def flush_identity_cache():
    global IDENTITY_CACHE, LOGGED_IN_IDENTITY_CACHE
    IDENTITY_CACHE = None
    LOGGED_IN_IDENTITY_CACHE = None

# I am well aware that this is a far-from-perfect, hacky method of quickly
# determining who's a bot or not. If necessary, in the future we could implement
# a javascript check like a/bingo and django-lean do -- but for now, I'm sticking
# w/ the simplest possible implementation for devs (don't need to add JS in any template code)
# that doesn't strongly bias the statistical outcome (undetected bots aren't a distaster,
# because they shouldn't favor one side over the other).
bot_regex = re.compile("(Baidu|Gigabot|Googlebot|libwww-perl|lwp-trivial|msnbot|SiteUptime|Slurp|WordPress|ZIBB|ZyBorg)", re.IGNORECASE)
def is_bot():
    return bool(bot_regex.search(os.environ.get("HTTP_USER_AGENT") or ""))
