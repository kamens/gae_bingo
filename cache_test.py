from google.appengine.api import memcache

from testutil import gae_model

from . import cache

class CacheTest(gae_model.GAEModelTestCase):
    def test_bingo_identity_bucket_max(self):
        # If the number of buckets changes then the magic number for the ident
        # needs to change. 166 is the lowest number that hashes to bucket 50.
        #
        # The magic number is derived from brute force application of the
        # bucketing hash function:
        #
        #  import hashlib
        #  num_buckets = 51
        #  next(i for i in xrange(0, 10000)
        #       if (num_buckets - 1) == (int(hashlib.md5(str(i)).hexdigest(),
        #                                    base=16) % num_buckets))
        self.assertEqual(51, cache.NUM_IDENTITY_BUCKETS)
        max_bucket_key = "_gae_bingo_identity_bucket:50"
        ident = 166

        ident_cache = cache.BingoIdentityCache()
        self.assertIsNone(memcache.get(max_bucket_key))
        # This puts the identity cache in memcache.
        ident_cache.persist_to_datastore(ident)
        self.assertEqual(1, len(memcache.get(max_bucket_key)))
        # This persists buckets in memcache to the datastore then clears them
        # from memcache.
        cache.BingoIdentityCache.persist_buckets_to_datastore()
        self.assertEqual(0, len(memcache.get(max_bucket_key)))
