import instance_cache
from testutil import gae_model


class InstanceCacheTest(gae_model.GAEModelTestCase):
    def setUp(self):
        super(InstanceCacheTest, self).setUp()

    def test_no_expiry_should_last_forever(self):
        instance_cache.set('foo', 'bar', expiry=None)
        # A month passes - what incredible up time we have!
        month_in_secs = 60 * 60 * 24 * 31
        self.adjust_time(delta_in_seconds=month_in_secs)
        self.assertEquals('bar', instance_cache.get('foo'))

    def test_expiry_works_as_expected(self):
        instance_cache.set('foo', 'bar', expiry=60)
        self.assertEquals('bar', instance_cache.get('foo'))
        self.adjust_time(delta_in_seconds=61)
        self.assertEquals(None, instance_cache.get('foo'))

