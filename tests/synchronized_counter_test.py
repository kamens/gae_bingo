import mock

from google.appengine.api import memcache

from gae_bingo import synchronized_counter
from testutil import gae_model


class SynchronizedCounterTest(gae_model.GAEModelTestCase):
    """Test gae/bingo's synchronized memcache counter."""

    def sync_incr(self, key, number, delta=1):
        future = synchronized_counter.SynchronizedCounter.incr_async(key,
                number, delta=delta)
        self.assertTrue(future.get_result())

    def pop_counters(self, keys):
        results = synchronized_counter.SynchronizedCounter.pop_counters(keys)
        self.assertTrue(isinstance(results, dict))
        return results

    def assert_counter_value(self, key, number, expected):
        count = synchronized_counter.SynchronizedCounter.get(key, number)
        self.assertEqual(count, expected)

    def test_simple_incr(self):
        self.sync_incr("monkeys", 0)
        self.sync_incr("monkeys", 0)
        self.sync_incr("monkeys", 0)

        self.assert_counter_value("monkeys", 0, 3)

    def test_multiple_incrs(self):
        for _ in range(10):
            self.sync_incr("monkeys", 1)

        for _ in range(12):
            self.sync_incr("monkeys", 2)

        for _ in range(5):
            self.sync_incr("monkeys", 0)

        for _ in range(7):
            self.sync_incr("monkeys", 3)

        for i in range(20):
            self.sync_incr("gorillas", i % 2)

        self.assert_counter_value("monkeys", 0, 5)
        self.assert_counter_value("monkeys", 1, 10)
        self.assert_counter_value("monkeys", 2, 12)
        self.assert_counter_value("monkeys", 3, 7)

        self.assert_counter_value("gorillas", 0, 10)
        self.assert_counter_value("gorillas", 1, 10)

    def test_incr_multiple_deltas(self):
        self.sync_incr("monkeys", 0, delta=5)
        self.sync_incr("monkeys", 0)
        self.sync_incr("monkeys", 0, delta=12)

        self.assert_counter_value("monkeys", 0, 18)

    def test_rollover(self):
        max_value = synchronized_counter.MAX_COUNTER_VALUE

        # Setup a combination of counters with one of the individual counters
        # at max value
        self.sync_incr("walrus", 0)

        # Bring walrus[1] up to max value
        with mock.patch('logging.warning') as log_warning:
            self.sync_incr("walrus", 1, max_value-1)  # should trigger warning
            self.sync_incr("walrus", 1)  # should trigger another warning
            self.assertEquals(2, log_warning.call_count)  # expect 2 warnings

        self.sync_incr("walrus", 2)
        self.sync_incr("walrus", 3)

        self.assert_counter_value("walrus", 0, 1)
        self.assert_counter_value("walrus", 1, max_value)
        self.assert_counter_value("walrus", 2, 1)
        self.assert_counter_value("walrus", 3, 1)

        # Increment the non-max value counters, make sure everything still
        # looks good
        self.sync_incr("walrus", 0)
        self.sync_incr("walrus", 2)

        self.assert_counter_value("walrus", 0, 2)
        self.assert_counter_value("walrus", 1, max_value)
        self.assert_counter_value("walrus", 2, 2)

        # Increment the max value counter. ROLLOVER!
        with mock.patch('logging.error') as log_error:
            self.sync_incr("walrus", 1) 
            self.assertEquals(1, log_error.call_count)  # expecting 1 error log

        # Rollover should've completely erased all counters.
        self.assert_counter_value("walrus", 0, 0)
        self.assert_counter_value("walrus", 1, 0)
        self.assert_counter_value("walrus", 2, 0)
        self.assert_counter_value("walrus", 3, 0)

        # Increment another couple counters in a new, single combination
        self.sync_incr("giraffe", 0, delta=5)
        self.sync_incr("giraffe", 2, delta=2)

        self.assert_counter_value("giraffe", 0, 5)
        self.assert_counter_value("giraffe", 2, 2)

        # Cause another rollover, this time due to a large delta.
        with mock.patch('logging.error') as log_error:
            self.sync_incr("giraffe", 0, max_value)
            self.assertEquals(1, log_error.call_count)  # expecting 1 error log

        # Make sure rollover completely erased the counter
        self.assert_counter_value("giraffe", 0, 0)
        self.assert_counter_value("giraffe", 2, 0)

    def test_invalid_input(self):
        def negative_delta():
            self.sync_incr("chimps", 1, delta=-1)

        def invalid_counter_number():
            self.sync_incr("chimps",
                    synchronized_counter.COUNTERS_PER_COMBINATION + 1)

        def negative_counter_number():
            self.sync_incr("chimps", -1)

        self.assertRaises(ValueError, negative_delta)
        self.assertRaises(ValueError, invalid_counter_number)
        self.assertRaises(ValueError, negative_counter_number)

    def test_pop(self):
        self.sync_incr("monkeys", 0, delta=5)
        self.sync_incr("giraffes", 3, delta=5)
        self.sync_incr("giraffes", 2)
        self.sync_incr("giraffes", 1)
        self.sync_incr("giraffes", 1)

        results = self.pop_counters(["monkeys", "giraffes"])
        results_after_pop = self.pop_counters(["monkeys", "giraffes"])

        self.assertEqual(results["giraffes"], [0, 2, 1, 5])
        self.assertEqual(results["monkeys"], [5, 0, 0, 0])

        self.assertEqual(results_after_pop["giraffes"], [0, 0, 0, 0])
        self.assertEqual(results_after_pop["monkeys"], [0, 0, 0, 0])

    def test_bad_pop(self):
        """Test dangerous race condition situation during pop."""
        self.sync_incr("penguins", 2)
        self.sync_incr("giraffes", 2)

        # We want to simulate a memcache eviction followed by an incr() right
        # *before* offset_multi gets called. So we mock out offset_multi to do
        # exactly that, and we use "penguins" as the problematically evicted
        # memcache key.
        old_offset_multi = memcache.offset_multi
        def evict_and_incr_during_pop(d):
            synchronized_counter.SynchronizedCounter.delete_multi(["penguins"])
            self.sync_incr("penguins", 3)
            self.sync_incr("giraffes", 3)
            return old_offset_multi(d)

        self.mock_function('google.appengine.api.memcache.offset_multi',
                evict_and_incr_during_pop)

        # During this pop, we should've detected the dangerous eviction, wiped
        # out the value for "penguins", and logged an error.
        with mock.patch('logging.error') as log_error:
            results = self.pop_counters(["penguins", "giraffes"])
            self.assertEquals(1, log_error.call_count)  # expecting 1 error log

        # The original pop will still return correct values...
        self.assertEqual(results["penguins"], [0, 0, 1, 0])
        self.assertEqual(results["giraffes"], [0, 0, 1, 0])

        # ...but after the rolled over pop, even though penguin's 3rd counter
        # was incr()'d, the counter should've been erased due to rollover
        # during pop. So a subsequent get() should not find anything in the
        # counter.
        self.assert_counter_value("penguins", 3, 0)
        self.assert_counter_value("giraffes", 3, 1)
