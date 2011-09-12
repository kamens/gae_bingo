import logging

from cache import flush_request_cache, store_if_dirty
from identity import identity, get_identity_cookie_value, set_identity_cookie_header, delete_identity_cookie_header, using_logged_in_bingo_identity, flush_identity_cache

class GAEBingoWSGIMiddleware(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):

        # Make sure request-cached values are cleared at start of request
        flush_request_cache()
        flush_identity_cache()

        def gae_bingo_start_response(status, headers, exc_info = None):

            if using_logged_in_bingo_identity():
                if get_identity_cookie_value():
                    # If using logged in identity, clear cookie b/c we don't need it
                    # and it can cause issues after logging out.
                    headers.append(("Set-Cookie", delete_identity_cookie_header()))
            else:
                # Not using logged-in identity. If current identity isn't already stored in cookie, 
                # do it now.
                if identity() != get_identity_cookie_value():
                    headers.append(("Set-Cookie", set_identity_cookie_header()))

            return start_response(status, headers, exc_info)

        result = self.app(environ, gae_bingo_start_response)
        for value in result:
            yield value

        # Persist any changed GAEBingo data to memcache
        store_if_dirty()

        # We probably don't need to do this b/c we clear the cache at the start of each request,
        # but what the heck, cache bugs are just the worst.
        flush_request_cache()
        flush_identity_cache()
