import cache
import identity
import request_cache

class GAEBingoWSGIMiddleware(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):

        try:
            # Make sure request-cached values are cleared at start of request
            request_cache.flush_request_cache()

            def gae_bingo_start_response(status, headers, exc_info = None):

                if identity.using_logged_in_bingo_identity():
                    if identity.get_identity_cookie_value():
                        # If using logged in identity, clear cookie b/c we don't need it
                        # and it can cause issues after logging out.
                        headers.append(("Set-Cookie",
                                        identity.delete_identity_cookie_header()))
                else:
                    # Not using logged-in identity. If current identity isn't
                    # already stored in cookie, do it now.
                    if identity.identity() != identity.get_identity_cookie_value():
                        headers.append(("Set-Cookie",
                                        identity.set_identity_cookie_header()))

                return start_response(status, headers, exc_info)

            result = self.app(environ, gae_bingo_start_response)
            for value in result:
                yield value

            # Persist any changed GAEBingo data to memcache
            cache.store_if_dirty()

            # If we got a new ID, we should put it to the datastore so it persists
            identity.put_id_if_necessary()

        finally:
            request_cache.flush_request_cache()
