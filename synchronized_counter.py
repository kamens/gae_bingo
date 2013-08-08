"""Synchronized counters are memcache counters that get evicted synchronously.

In other words, you can use synchronized counters to track two different
incrementing numbers, A and B, that should be evicted from memcache
consistently w/r/t each other. This is especially useful when you need a fast
atomic incrementor (which memcache's incr() provides) while also maintaining
two or more numbers that are related to each other.

There are two nouns you should think of when reading through this file,
"combinations" and "counters"

    - "Combinations" are groups of up to 4 counters that stay in memcache
      together and are evicted at the same time.

    - "Counters" are simple incrementing counters.

You get the following benefits when using synchronized counters:

    - If one counter in a combination is present in memcache, all counters in
      that combination are present.
    
    - If one counter in a combination is evicted from memcache, all counters are
      evicted.

In order to achieve this, these counters suffer from some limitations:

    - Each combination can only have four individual counters.

    - Counters have a maximum value of 65,535. *Client code is responsible for
      calling pop_counters to get and reset the current counter state when
      appropriate, otherwise these counters will rollover over 65,535 and reset
      their entire combination of counters. See below.*

    - Counters can still be randomly evicted by memcache -- this does not make
      memcache more stable or persistent. This only guarantees that all
      counters in a single combination will be evicted at the same time.

Example usage:

    # Create and increment the 0th individual counter in a combination of
    # counters called "GorillaCombination"
    SynchronizedCounter.incr_async("GorillaCombination", 0)

    # Increment the 2nd individual counter as well. Now the 0th and 2nd
    # counters in "GorillaCombination" will remain in (or be evicted from)
    # memcache together.
    SynchronizedCounter.incr_async("GorillaCombination", 2)

    # Get the current value of the 2nd counter in "GorillaCombination" -- in
    # this case, it will return 1.
    current_count_2 = SynchronizedCounter.get("GorillaCombination", 2)

    # Get all current gorilla counts and pop them off the accumulating counters
    # This return value should be: {"GorillaCombination": [0, 0, 1, 0]}
    gorilla_counts = SynchronizedCounter.pop_counters(["GorillaCombination"])

    # ...and after the pop, the counters will be reset and this assert should
    # succeed.
    current_count_2 = SynchronizedCounter.get("GorillaCombination", 2)
    assertEqual(current_count_2, 0)
"""
import logging

from google.appengine.api import memcache
from google.appengine.ext import ndb


# total # of bits in a memcache incr() int
BITS_IN_MEMCACHE_INT = 64

# number of counters in each combination
COUNTERS_PER_COMBINATION = 4

# number of bits in each counter in the combination
BITS_PER_COUNTER = BITS_IN_MEMCACHE_INT / COUNTERS_PER_COMBINATION

# max value each counter can represent
MAX_COUNTER_VALUE = 2**BITS_PER_COUNTER - 1

# above this value, counters will start warning of rollover possibilities
WARNING_HIGH_COUNTER_VALUE = 2**(BITS_PER_COUNTER - 1)


class SynchronizedCounter(object):
    """Tool for managing combinations of synchronized memcache counters."""

    @staticmethod
    def get(key, number):
        """Return value of the n'th counter in key's counter combination.
        
        Args:
            key: name of the counter combination
            number: n'th counter value being queried
        """
        if not (0 <= number < COUNTERS_PER_COMBINATION):
            raise ValueError("Invalid counter number.")

        # Get the combined count for this counter combination
        combined_count = long(memcache.get(key) or 0)

        # Return the single counter value for the n'th counter
        return SynchronizedCounter._single_counter_value(combined_count, number)

    @staticmethod
    def _single_counter_value(combined_count, number):
        """Return the n'th counter value from the combination's total value.
        
        Args:
            combined_count: combined count value for the entire counter
                combination, usually taken directly from memcache
            number: n'th counter value being queried
        """
        if combined_count is None:
            return 0

        # Shift the possiblty-left-shifted bits over into the rightmost spot
        shifted_count = combined_count >> (number * BITS_PER_COUNTER)

        # And mask off all bits other than the n'th counter's bits
        mask = 2**BITS_PER_COUNTER - 1
        return shifted_count & mask

    @staticmethod
    @ndb.tasklet
    def incr_async(key, number, delta=1):
        """Increment the n'th counter in key's counter combination.
        
        Args:
            key: name of the counter combination
            number: n'th counter value being incremented
            delta: amount to increment by
        """
        if not (0 <= number < COUNTERS_PER_COMBINATION):
            raise ValueError("Invalid counter number.")

        if delta < 0:
            raise ValueError("Cannot decrement synchronized counters.")

        # We want to increment the counter, but we need to increment the
        # counter that's sitting in this combination's correct bit position. So
        # we shift our increment-by-1 to the left by the number of bits
        # necessary to get to the correct counter.
        delta_base = 1 << (number * BITS_PER_COUNTER)
        delta_shifted = delta_base * delta

        ctx = ndb.get_context()
        combined_count = yield ctx.memcache_incr(key, delta=delta_shifted,
                initial_value=0)

        if combined_count is None:
            # Memcache may be down and returning None for incr.
            raise ndb.Return(False)

        # If the value we get back from memcache's incr is less than the delta
        # we sent, then we've rolled over this counter's maximum value (2^16).
        # That's a problem, because it bleeds data from this counter into the
        # next one in its combination.
        #
        # As noted above, it is the client code's responsibility to call
        # pop_counters frequently enough to prevent this from happening.
        #
        # However, if this does happen, we wipe this entire corrupted counter
        # from memcache and act just as if the memcache key was randomly
        # evicted.
        count = SynchronizedCounter._single_counter_value(combined_count,
                number)
        if count < delta:
            # This is an error worth knowing about in our logs
            logging.error("SynchronizedCounter %s exceeded its maximum value" %
                    key)
            # Evict corrupted data from memcache
            SynchronizedCounter.delete_multi([key])
        elif count > WARNING_HIGH_COUNTER_VALUE:
            logging.warning("SynchronizedCounter %s approaching max value" %
                    key)

        raise ndb.Return(True)

    @staticmethod
    def pop_counters(keys):
        """Return all counters in provided combinations and reset their counts.

        This will return a dict mapping the provided key values to a list of
        each of their current counter values.
        Example return value: {
            "MonkeyCombination": [1, 5, 0, 12],
            "GorillaCombination": [0, 0, 0, 9],
        }

        This will also clear out the current counts for all combinations listed
        in keys, so after calling this the counts for each specified
        combination's counter should be 0.

        Note: while pop_counters tries to do the get and pop as atomically as
        possible, it is not truly atomic. This means there are rare edge cases
        during which problematic memcache evictions and incr()s can happen
        between the results being retrieved and the counters being popped. When
        this happens, we detect the situation and pretend like this combination
        of counters has simply been evicted from memcache (by deleting the
        combination of counters). This situation should hopefully be very rare.

        Args:
            keys: list of names of counter combinations
        """
        results = {k: [0] * COUNTERS_PER_COMBINATION for k in keys}

        # Grab all accumulating counters...
        combined_counters = memcache.get_multi(keys)

        # ...and immediately offset them by the inverse of their current counts
        # as quickly as possible.
        negative_offsets = {k: -1 * count
                for k, count in combined_counters.iteritems()}
        offset_results = memcache.offset_multi(negative_offsets)

        # Now that we've tried to pop the counter values from the accumulators,
        # make sure that none of the pops caused an overflow rollover due to
        # the race condition described in the above docstring.
        for key in offset_results:
            offset_counter = offset_results[key]
            for i in range(COUNTERS_PER_COMBINATION):
                count = SynchronizedCounter._single_counter_value(
                        offset_counter, i)
                if count > WARNING_HIGH_COUNTER_VALUE:
                    # We must've rolled a counter over backwards due to the
                    # memcache race condition described above. Warn and clear
                    # this counter.
                    #
                    # We don't expect this to happen, but if it does we should
                    # know about it without crashing on the user. See above
                    # explanation.
                    #
                    # TODO(kamens): find a nicer way to protect this scenario
                    logging.error("SynchronizedCounter %s rolled over on pop" %
                            key)
                    SynchronizedCounter.delete_multi([key])

        # Prepare popped results in form {
        #   "counter combination A": [<counter 1>, ..., <counter 4>],
        #   "counter combination B": [<counter 1>, ..., <counter 4>],
        # }
        for key in combined_counters:
            combined_counter = combined_counters[key]

            for i in range(COUNTERS_PER_COMBINATION):
                results[key][i] = SynchronizedCounter._single_counter_value(
                        combined_counter, i)

        return results

    @staticmethod
    def delete_multi(keys):
        """Delete all counters in provided keys."""
        memcache.delete_multi(keys)

