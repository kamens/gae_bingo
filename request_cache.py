"""Routines for request-level caching.

The request-level cache is set up before and cleared after every
request by middleware.

Never assign to request_cache.cache when using webapp2_extras.local
for thread-safety. It is a thread-local proxy object that will no
longer be thread-safe if overwritten.

The cache interface is a dict:

   request_cache.cache['key'] = 'value'
   if 'key' in request_cache.cache:
      value = request_cache.cache['key']
"""

import logging

try:
    import webapp2_extras.local
    _local = webapp2_extras.local.Local()
    _local.cache = {}
    # cache is a LocalProxy. it forwards all operations (except
    # assignment) to the object that _local.cache is bound to.
    cache = _local('cache')
except ImportError:
    logging.warning("webapp2_extras.local is not available "
                    "so gae_bingo won't be thread-safe!")
    _local = None
    cache = {}


def flush_request_cache():
    """Release referenced data from the request cache."""
    if _local is not None:
        _local.__release_local__()
        _local.cache = {}
    else:
        cache = {}
