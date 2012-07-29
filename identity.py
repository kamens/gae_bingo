from __future__ import absolute_import

import base64
import logging
import os
import re

from google.appengine.ext import db

from gae_bingo import cookies
from gae_bingo import request_cache
from .models import GAEBingoIdentityModel
from .config import current_logged_in_identity

IDENTITY_COOKIE_KEY = "gae_b_id"
IDENTITY_CACHE_KEY = "IDENTITY_CACHE"
LOGGED_IN_IDENTITY_CACHE_KEY = "LOGGED_IN_IDENTITY_CACHE"
ID_TO_PUT_CACHE_KEY = "ID_TO_PUT"

def logged_in_bingo_identity():
    if request_cache.cache.get(LOGGED_IN_IDENTITY_CACHE_KEY) is None:
        request_cache.cache[LOGGED_IN_IDENTITY_CACHE_KEY] = current_logged_in_identity()

    return request_cache.cache[LOGGED_IN_IDENTITY_CACHE_KEY]

def identity(identity_val=None):
    """ Determines the Bingo identity for the specified user. If no user
    is specified, this will attempt to infer one based on cookies/logged in user


    identity_val -- a string or instance of GAEBingoIdentityModel specifying
    which bingo identity to retrieve.
    """
    if identity_val:
        # Don't cache for arbitrarily passed in identity_val
        return bingo_identity_for_value(identity_val, associate_with_cookie=False)

    if request_cache.cache.get(IDENTITY_CACHE_KEY) is None:

        if is_bot():

            # Just make all bots identify as the same single user so they don't
            # bias results. Following simple suggestion in
            # http://www.bingocardcreator.com/abingo/faq
            request_cache.cache[IDENTITY_CACHE_KEY] = "_gae_bingo_bot"

        else:

            # Try to get unique (hopefully persistent) identity from user's implementation,
            # otherwise grab the current cookie value, otherwise grab random value.
            request_cache.cache[IDENTITY_CACHE_KEY] = str(get_logged_in_bingo_identity_value() or get_identity_cookie_value() or get_random_identity_value())

    return request_cache.cache[IDENTITY_CACHE_KEY]

def using_logged_in_bingo_identity():
    return identity() and identity() == get_logged_in_bingo_identity_value()

def get_logged_in_bingo_identity_value():
    val = logged_in_bingo_identity()
    return bingo_identity_for_value(val)

def bingo_identity_for_value(val, associate_with_cookie=True):
    # We cache the ID we generate here, to put only at the end of the request

    if val is None:
        return None

    if isinstance(val, db.Model):

        if isinstance(val, GAEBingoIdentityModel):
            # If it's a db.Model that inherited from GAEBingoIdentityModel, return bingo identity

            if not val.gae_bingo_identity:

                if (is_random_identity_value(get_identity_cookie_value()) and
                    associate_with_cookie):
                    # If the current model doesn't have a bingo identity associated w/ it
                    # and we have a random cookie value already set, associate it with this identity model.
                    #
                    # This keeps the user's experience consistent between using the site pre- and post-login.
                    request_cache.cache[ID_TO_PUT_CACHE_KEY] = get_identity_cookie_value()
                else:
                    # Otherwise just use the key, it's guaranteed to be unique
                    request_cache.cache[ID_TO_PUT_CACHE_KEY] = str(val.key())


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

def put_id_if_necessary():
    """To be called at the end of a request.
    Check to see if we should put() the gae_bingo_identity, and put() it if so.

    """
    id_to_put = request_cache.cache.get(ID_TO_PUT_CACHE_KEY)
    if id_to_put:
        val = current_logged_in_identity()
        if val is None:
            return
        if isinstance(val, GAEBingoIdentityModel):
            if val.gae_bingo_identity and id_to_put != val.gae_bingo_identity:
                logging.warning(
                        "val.gae_bingo_identity got set to %s unexpectedly,"
                        "but id_to_put is %s"
                        % (val.gae_bingo_identity, id_to_put))
            else:
                val.gae_bingo_identity = id_to_put

                val.put()

                # Flush the transaction so the HR datastore doesn't suffer from
                # eventual consistency issues when next grabbing this UserData.
                db.get(val.key())

def set_identity_cookie_header():
    return cookies.set_cookie_value(IDENTITY_COOKIE_KEY, base64.urlsafe_b64encode(identity()))

def delete_identity_cookie_header():
    return cookies.set_cookie_value(IDENTITY_COOKIE_KEY, "")

# I am well aware that this is a far-from-perfect, hacky method of quickly
# determining who's a bot or not. If necessary, in the future we could implement
# a javascript check like a/bingo and django-lean do -- but for now, I'm sticking
# w/ the simplest possible implementation for devs (don't need to add JS in any template code)
# that doesn't strongly bias the statistical outcome (undetected bots aren't a distaster,
# because they shouldn't favor one side over the other).
bot_regex = re.compile("(Baidu|Gigabot|Googlebot|libwww-perl|lwp-trivial|msnbot|SiteUptime|Slurp|WordPress|ZIBB|ZyBorg)", re.IGNORECASE)
def is_bot():
    return bool(bot_regex.search(os.environ.get("HTTP_USER_AGENT") or ""))
