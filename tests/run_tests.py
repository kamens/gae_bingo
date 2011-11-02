import random
import time
import urllib
import urllib2
import cookielib
import json

TEST_GAE_URL = "http://localhost:8080/gae_bingo/tests/run_step"

last_opener = None

def test_response(step, data={}, use_last_cookies=False, bot=False):
    global last_opener

    if not use_last_cookies or last_opener is None:
        cj = cookielib.CookieJar()
        last_opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

        if bot:
            last_opener.addheaders = [('User-agent', 'monkeysmonkeys Googlebot monkeysmonkeys')]

    data["step"] = step

    req = last_opener.open("%s?%s" % (TEST_GAE_URL, urllib.urlencode(data)))

    try:
        response = req.read()
    finally:
        req.close()

    return json.loads(response)

def run_tests():

    # Delete all experiments (response should be count of experiments left)
    assert(test_response("delete_all") == 0)

    # Refresh bot's identity record so it doesn't pollute tests
    assert(test_response("refresh_identity_record", bot=True) == True)
    
    # Participate in experiment A, check for correct alternative values being returned,
    for i in range(0, 20):
        assert(test_response("participate_in_monkeys") in [True, False])

    # Identify as a bot a couple times (response should stay the same)
    bot_value = None
    for i in range(0, 5):
        value = test_response("participate_in_monkeys", bot=True)

        if bot_value is None:
            bot_value = value

        assert(value == bot_value)

    # Check total participants in A (1 extra for bots)
    assert(test_response("count_participants_in", {"experiment_name": "monkeys"}) == 21)

    # Participate in experiment B (responses should be "a" "b" or "c")
    for i in range(0, 15):
        assert(test_response("participate_in_gorillas") in ["a", "b", "c"])

    # Participate in experiment A, using cookies half of the time to maintain identity
    for i in range(0, 20):
        assert(test_response("participate_in_monkeys", use_last_cookies=(i % 2 == 1)) in [True, False])

    # Check total participants in A (should've only added 10 more in previous step)
    assert(test_response("count_participants_in", {"experiment_name": "monkeys"}) == 31)

    # Participate in A once more with a lot of followup, persisting to datastore and flushing memcache between followups
    for i in range(0, 10):
        assert(test_response("participate_in_monkeys", use_last_cookies=(i not in [0, 5])) in [True, False])

        if i in [0, 5]:
            assert(test_response("persist", use_last_cookies=True) == True)

            # Wait 15 seconds for task queues to run
            time.sleep(20)

            assert(test_response("flush_memcache", use_last_cookies=True) == True)

    # Check total participants in A (should've only added 2 more in previous step)
    assert(test_response("count_participants_in", {"experiment_name": "monkeys"}) == 33)

    # Participate and convert in experiment A, using cookies to tie participation to conversions,
    # tracking conversions-per-alternative
    dict_conversions = {}
    for i in range(0, 35):
        alternative_key = str(test_response("participate_in_monkeys")).lower()
        assert(test_response("convert_in", {"conversion_name": "monkeys"}, use_last_cookies=True) == True)

        if not alternative_key in dict_conversions:
            dict_conversions[alternative_key] = 0
        dict_conversions[alternative_key] += 1

    # Check total conversions-per-alternative in A
    assert(len(dict_conversions) == 2)
    assert(35 == reduce(lambda a, b: a + b, map(lambda key: dict_conversions[key], dict_conversions)))

    dict_conversions_server = test_response("count_conversions_in", {"experiment_name": "monkeys"})
    assert(len(dict_conversions) == len(dict_conversions_server))

    for key in dict_conversions:
        assert(dict_conversions[str(key).lower()] == dict_conversions_server[str(key).lower()])

    
    # Participate in experiment B, using cookies to maintain identity
    # and making sure alternatives for B are stable per identity
    last_response = None
    for i in range(0, 20):
        use_last_cookies = last_response is not None and random.randint(0, 2) > 0

        current_response = test_response("participate_in_gorillas", use_last_cookies=use_last_cookies)

        if not use_last_cookies:
            last_response = current_response

        assert(current_response in ["a", "b", "c"])
        assert(last_response == current_response)

    # Participate in experiment C, which is a multi-conversion experiment,
    # and occasionally convert in *one* of the conversions
    expected_conversions = 0
    for i in range(0, 20):
        assert(test_response("participate_in_chimpanzees") in [True, False])

        if random.randint(0, 2) > 0:
            assert(test_response("convert_in", {"conversion_name": "chimps_conversion_2"}, use_last_cookies=True) == True)
            expected_conversions += 1

    # It's statistically possible but incredibly unlikely for this to fail based on random.randint()'s behavior
    assert(expected_conversions > 0)

    # Make sure conversions for the 2nd conversion type of this experiment are correct
    dict_conversions_server = test_response("count_conversions_in", {"experiment_name": "chimpanzees (2)"})
    assert(expected_conversions == reduce(lambda a, b: a + b, map(lambda key: dict_conversions_server[key], dict_conversions_server)))

    # Make sure conversions for the 1st conversion type of this experiment are empty
    dict_conversions_server = test_response("count_conversions_in", {"experiment_name": "chimpanzees"})
    assert(0 == reduce(lambda a, b: a + b, map(lambda key: dict_conversions_server[key], dict_conversions_server)))

    # Test that calling bingo multiple times for a signle user creates only one conversion (for a BINARY conversion type)
    assert(test_response("participate_in_chimpanzees") in [True, False])
    assert(test_response("convert_in", {"conversion_name": "chimps_conversion_1"}, use_last_cookies=True) == True) 
    assert(test_response("convert_in", {"conversion_name": "chimps_conversion_1"}, use_last_cookies=True) == True) 
    dict_conversions_server = test_response("count_conversions_in", {"experiment_name": "chimpanzees"})
    assert(1 == reduce(lambda a, b: a + b, map(lambda key: dict_conversions_server[key], dict_conversions_server)))
    
    # End experiment C, choosing a short-circuit alternative
    test_response("end_and_choose", {"canonical_name": "chimpanzees", "alternative_number": 1})

    # Make sure short-circuited alternatives for C's experiments are set appropriately
    for i in range(0, 5):
        assert(test_response("participate_in_chimpanzees") == False)

    # Test an experiment with a Counting type conversion by converting multiple times for a single user
    assert(test_response("participate_in_hippos") in [True, False])
    for i in range(0, 5):
        assert(test_response("convert_in", {"conversion_name": "hippos_binary"}, use_last_cookies=True) == True)
        assert(test_response("convert_in", {"conversion_name": "hippos_counting"}, use_last_cookies=True) == True)
    dict_conversions_server = test_response("count_conversions_in", {"experiment_name": "hippos"})
    assert(1 == reduce(lambda a, b: a + b, map(lambda key: dict_conversions_server[key], dict_conversions_server)))
    dict_conversions_server = test_response("count_conversions_in", {"experiment_name": "hippos (2)"})
    assert(5 == reduce(lambda a, b: a + b, map(lambda key: dict_conversions_server[key], dict_conversions_server)))
    
    # Participate in experiment D (weight alternatives), keeping track of alternative returned count.
    dict_alternatives = {}
    for i in range(0, 75):
        alternative = test_response("participate_in_crocodiles")
        assert(alternative in ["a", "b", "c"])

        if not alternative in dict_alternatives:
            dict_alternatives[alternative] = 0
        dict_alternatives[alternative] += 1

    # Make sure weighted alternatives work -> should be a < b < c < d < e, but they should all exist.
    #
    # Again, it is statistically possible for the following asserts to occasionally fail during
    # these tests, but it should be exceedingly rare if weighted alternatives are working properly.
    for key in ["a", "b", "c"]:
        assert(dict_alternatives.get(key, 0) > 0)
    assert(dict_alternatives.get("a", 0) < dict_alternatives.get("b", 0))
    assert(dict_alternatives.get("b", 0) < dict_alternatives.get("c", 0))
    
    # Check experiments count
    assert(test_response("count_experiments") == 7)

    # Test persist and load from DS
    assert(test_response("persist") == True)
    assert(test_response("flush_memcache") == True)

    # Check experiments and converion counts remain after persist and memcache flush
    assert(test_response("count_experiments") == 7)

    dict_conversions_server = test_response("count_conversions_in", {"experiment_name": "chimpanzees (2)"})
    assert(expected_conversions == reduce(lambda a, b: a + b, map(lambda key: dict_conversions_server[key], dict_conversions_server)))

    print "Tests successful."

if __name__ == "__main__":
    run_tests()


