import ast
import base64
import cookielib
import json
import os
import random
import time
import urllib
import urllib2

# TODO: convert this unit test file to the correct unit
# test pattern used by the rest of our codebase
TEST_GAE_HOST = "http://localhost:8111"

last_opener = None

def test_response(step="", data={}, use_last_cookies=False, bot=False, url=None):
    global last_opener

    if not use_last_cookies or last_opener is None:
        cj = cookielib.CookieJar()
        last_opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

        if bot:
            last_opener.addheaders = [(
                                'User-agent',
                                'monkeysmonkeys Googlebot monkeysmonkeys')]

    if url is None:
        data["step"] = step
        url = "/gae_bingo/tests/run_step?%s" % urllib.urlencode(data)

    req = last_opener.open("%s%s" % (TEST_GAE_HOST, url))

    try:
        response = req.read()
    finally:
        req.close()

    try:
        return json.loads(response)
    except ValueError:
        return None

def run_tests():

    # Delete all experiments (response should be count of experiments left)
    assert(test_response("delete_all") == 0)

    # Ensure the identity works correctly and consistently after login.
    for i in xrange(5):
        # Randomly generate an ID so we have a good chance of having a new one.
        # If that assumption is wrong, the test will fail--clear
        # the datastore to increase chances of working.
        user = base64.urlsafe_b64encode(os.urandom(30)) + "%40example.com"
        test_response(url="/")  # Load / to get ID assigned
        firstID = test_response("get_identity", use_last_cookies=True)  # get ID
        url = "/_ah/login?email=" + user + "&action=Login&continue=%2Fpostlogin"
        test_response(use_last_cookies=True, url=url)
        # Now make sure the ID is consistent
        assert(firstID == test_response("get_identity", use_last_cookies=True))

    assert(test_response("delete_all") == 0)  # Clear out experiments this made

    # We're going to try to add a conversion to the experiment
    assert(test_response("participate_in_hippos") in [True, False])

    assert(test_response("convert_in",
                        {"conversion_name":
                         "hippos_binary"}, use_last_cookies=True))

    # Make sure participant counts are right
    assert(test_response("count_participants_in",
                        {"experiment_name": "hippos (hippos_binary)"},
                        use_last_cookies=True)
           == 1)
    assert(test_response("count_participants_in",
                        {"experiment_name": "hippos (hippos_counting)"},
                        use_last_cookies=True)
           == 1)
    # Make sure we have the right number of conversions
    dict_conversions_server = test_response(
                         "count_conversions_in",
                         {"experiment_name": "hippos (hippos_binary)"},
                         use_last_cookies=True)
    assert(sum(dict_conversions_server.values()) == 1)

    dict_conversions_server = test_response(
                        "count_conversions_in",
                        {"experiment_name": "hippos (hippos_counting)"},
                        use_last_cookies=True)
    assert(sum(dict_conversions_server.values()) == 0)

    assert(test_response("add_conversions", use_last_cookies=True)
            in [True, False])
    assert(test_response("count_experiments", use_last_cookies=True) == 3)

    # make sure that we have the /right/ experiments
    assert(set(ast.literal_eval(test_response("get_experiments",
                                use_last_cookies=True)).keys()) ==
               set(["hippos (hippos_binary)",
                    "hippos (hippos_counting)",
                    "hippos (rhinos_counting)"]))
    
    assert(test_response("convert_in",
                        {"conversion_name": "rhinos_counting"},
                        use_last_cookies=True))

    dict_conversions_server = test_response(
                        "count_conversions_in",
                        {"experiment_name": "hippos (hippos_binary)"})
    assert(sum(dict_conversions_server.values()) == 1)

    dict_conversions_server = test_response(
                        "count_conversions_in",
                        {"experiment_name": "hippos (hippos_counting)"},
                         use_last_cookies=True)
    assert(sum(dict_conversions_server.values()) == 0)
    
    dict_conversions_server = test_response(
                        "count_conversions_in",
                        {"experiment_name": "hippos (rhinos_counting)"},
                        use_last_cookies=True)
    
    assert(sum(dict_conversions_server.values()) == 1)

    # get rid of this test's data so it doesn't affect other tests
    assert(test_response("delete_all") == 0)

    # Now try the same, but with switching users
    assert(test_response("participate_in_hippos") in [True, False])
    
    assert(test_response("convert_in",
                        {"conversion_name":
                         "hippos_binary"}, use_last_cookies=True))

    assert(test_response("participate_in_hippos", use_last_cookies=False) 
            in [True, False])

    assert(test_response("add_conversions", use_last_cookies=True) in 
            [True, False])

    assert(test_response("convert_in",
                        {"conversion_name":
                         "rhinos_counting"}, use_last_cookies=True))
    assert(test_response("count_participants_in",
                        {"experiment_name": "hippos (hippos_binary)"}) == 2)
    assert(test_response("count_participants_in",
                        {"experiment_name": "hippos (rhinos_counting)"}) == 1)
    dict_conversions_server = test_response(
                                 "count_conversions_in",
                                 {"experiment_name": "hippos (hippos_binary)"})
    assert(sum(dict_conversions_server.values()) == 1)
    dict_conversions_server = test_response(
                            "count_conversions_in",
                            {"experiment_name": "hippos (rhinos_counting)"})
    assert(sum(dict_conversions_server.values()) == 1)
    
    assert(test_response("delete_all") == 0)

    # Test constructing a redirect URL that converts in monkey and chimps
    redirect_url_monkeys = test_response("create_monkeys_redirect_url")
    assert(redirect_url_monkeys ==
           "/gae_bingo/redirect?continue=/gae_bingo" +
           "&conversion_name=monkeys")

    redirect_url_chimps = test_response("create_chimps_redirect_url")
    assert(redirect_url_chimps ==
           "/gae_bingo/redirect?continue=/gae_bingo&" +
           "conversion_name=chimps_conversion_1&" + 
           "conversion_name=chimps_conversion_2")

    # Test participating in monkeys and chimps once,
    # and use previously constructed redirect URLs to convert
    assert(test_response("participate_in_monkeys") in [True, False])
    test_response(use_last_cookies=True, url=redirect_url_monkeys)
    assert(test_response("participate_in_chimpanzees") in [True, False])
    test_response(use_last_cookies=True, url=redirect_url_chimps)

    # Make sure there's a single participant and conversion in monkeys
    assert(test_response("count_participants_in",
                        {"experiment_name": "monkeys"})
           == 1)
    dict_conversions_server = test_response("count_conversions_in",
                                           {"experiment_name": "monkeys"})
    assert(sum(dict_conversions_server.values()) == 1)

    # Make sure there's a single participant and two conversions in chimps
    assert(test_response(
                "count_participants_in",
               {"experiment_name": "chimpanzees (chimps_conversion_1)"}) == 1)
    dict_conversions_server = test_response(
                                "count_conversions_in",
                                {"experiment_name":
                                    "chimpanzees (chimps_conversion_1)"})
    assert(sum(dict_conversions_server.values()) == 1)
    dict_conversions_server = test_response(
                                "count_conversions_in",
                                {"experiment_name":
                                 "chimpanzees (chimps_conversion_2)"})
    assert(sum(dict_conversions_server.values()) == 1)

    # Delete all experiments for next round of tests
    # (response should be count of experiments left)
    assert(test_response("delete_all") == 0)

    # Refresh bot's identity record so it doesn't pollute tests
    assert(test_response("refresh_identity_record", bot=True))

    # Participate in experiment A, check for correct alternative
    # valuesum(core_metrics.values(), [])s being returned,
    for i in range(0, 20):
        assert(test_response("participate_in_monkeys") in [True, False])

    assert(test_response("count_participants_in",
                        {"experiment_name": "monkeys"})
            == 20)

    # Identify as a bot a couple times (response should stay the same)
    bot_value = None
    for i in range(0, 5):
        value = test_response("participate_in_monkeys", bot=True)
        assert(value in [True, False])

        if bot_value is None:
            bot_value = value

        assert(value == bot_value)

    # Check total participants in A (1 extra for bots)
    assert(test_response("count_participants_in",
                        {"experiment_name": "monkeys"}) == 21)

    # Participate in experiment B (responses should be "a" "b" or "c")
    for i in range(0, 15):
        assert(test_response("participate_in_gorillas") in ["a", "b", "c"])

    # Participate in experiment A,
    # using cookies half of the time to maintain identity
    for i in range(0, 20):
        assert(test_response("participate_in_monkeys",
                             use_last_cookies=(i % 2 == 1)) 
               in [True, False])
    # Check total participants in A
    # (should've only added 10 more in previous step)
    assert(test_response("count_participants_in",
                        {"experiment_name": "monkeys"}) == 31)

    # Participate in A once more with a lot of followup, 
    # persisting to datastore and flushing memcache between followups
    for i in range(0, 10):
        assert(test_response("participate_in_monkeys",
                             use_last_cookies=(i not in [0, 5]))
               in [True, False])

        if i in [1, 6]:

            assert(test_response("persist", use_last_cookies=True))

            # Wait 10 seconds for task queues to run
            time.sleep(10)

            assert(test_response("flush_all_memcache",
                                 use_last_cookies=True))

    # NOTE: It's possible for this to fail sometimes--maybe a race condition?
    # TODO(kamens,josh): figure out why this happens? (Or just wait to not use
    #                     AppEngine any more)
    # Check total participants in A
    # (should've only added 2 more in previous step)
    assert(test_response("count_participants_in",
                         {"experiment_name": "monkeys"}) == 33)

    # Participate and convert in experiment A,
    # using cookies to tie participation to conversions,
    # tracking conversions-per-alternative
    dict_conversions = {}
    for i in range(0, 35):
        alternative_key = str(test_response("participate_in_monkeys"))
        assert(test_response("convert_in",
                            {"conversion_name": "monkeys"},
                             use_last_cookies=True))


        if not alternative_key in dict_conversions:
            dict_conversions[alternative_key] = 0
        dict_conversions[alternative_key] += 1

    # Check total conversions-per-alternative in A
    assert(len(dict_conversions) == 2)
    assert(35 == sum(dict_conversions.values()))

    dict_conversions_server = test_response("count_conversions_in",
                                           {"experiment_name": "monkeys"})
    assert(len(dict_conversions) == len(dict_conversions_server))

    for key in dict_conversions:
        assert(dict_conversions[key] == dict_conversions_server[key])

    # Participate in experiment B, using cookies to maintain identity
    # and making sure alternatives for B are stable per identity
    last_response = None
    for i in range(0, 20):
        use_last_cookies = (last_response is not None and
                             random.randint(0, 2) > 0)

        current_response = test_response("participate_in_gorillas",
                                         use_last_cookies=use_last_cookies)

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
            assert(test_response("convert_in",
                                {"conversion_name": "chimps_conversion_2"},
                                use_last_cookies=True))
            expected_conversions += 1

    # It's statistically possible but incredibly unlikely 
    # for this to fail based on random.randint()'s behavior
    assert(expected_conversions > 0)

    # Make sure conversions for the 2nd conversion type 
    # of this experiment are correct
    dict_conversions_server = test_response(
                                 "count_conversions_in",
                                 {"experiment_name":
                                     "chimpanzees (chimps_conversion_2)"})
    assert(expected_conversions == sum(dict_conversions_server.values()))

    # Make sure conversions for the 1st conversion type 
    # of this experiment are empty
    dict_conversions_server = test_response(
                                "count_conversions_in",
                                {"experiment_name":
                                 "chimpanzees (chimps_conversion_1)"})
    assert(0 == sum(dict_conversions_server.values()))

    # Test that calling bingo multiple times for a single 
    # user creates only one conversion (for a BINARY conversion type)
    assert(test_response("participate_in_chimpanzees") in [True, False])
    assert(test_response("convert_in",
                        {"conversion_name": "chimps_conversion_1"},
                        use_last_cookies=True))

    assert(test_response("convert_in",
                        {"conversion_name": "chimps_conversion_1"},
                         use_last_cookies=True))

    dict_conversions_server = test_response(
                                "count_conversions_in",
                                {"experiment_name":
                                    "chimpanzees (chimps_conversion_1)"})
    assert(1 == sum(dict_conversions_server.values()))

    # End experiment C, choosing a short-circuit alternative
    test_response("end_and_choose",
                 {"canonical_name": "chimpanzees", "alternative_number": 1})

    # Make sure short-circuited alternatives for 
    # C's experiments are set appropriately
    for i in range(0, 5):
        assert(test_response("participate_in_chimpanzees") == False)

    # Test an experiment with a Counting type conversion 
    # by converting multiple times for a single user
    assert(test_response("participate_in_hippos") in [True, False])

    # Persist to the datastore before Counting stress test
    assert(test_response("persist", use_last_cookies=True))

    # Wait 20 seconds for task queues to run
    time.sleep(20)

    # Hit Counting conversions multiple times
    for i in range(0, 20):

        if i % 3 == 0:
            # Stress things out a bit by flushing the memcache .incr() 
            # counts of each hippo alternative
            assert(test_response("persist", use_last_cookies=True))
            assert(test_response("flush_hippo_counts_memcache", 
                                 use_last_cookies=True))
        
        elif i % 5 == 0:
            # Stress things out even more flushing the core bingo memcache
            assert(test_response("flush_bingo_memcache",
                                 use_last_cookies=True))


        assert(test_response("convert_in",
                            {"conversion_name": "hippos_binary"},
                            use_last_cookies=True))

        assert(test_response("convert_in",
                            {"conversion_name": "hippos_counting"},
                            use_last_cookies=True))


    dict_conversions_server = test_response(
                                "count_conversions_in",
                                {"experiment_name": "hippos (hippos_binary)"})
    assert(1 == sum(dict_conversions_server.values()))
    dict_conversions_server = test_response(
                                "count_conversions_in",
                                {"experiment_name":
                                    "hippos (hippos_counting)"})
    assert(20 == sum(dict_conversions_server.values()))

    # Participate in experiment D (weight alternatives), 
    # keeping track of alternative returned count.
    dict_alternatives = {}
    for i in range(0, 75):
        alternative = test_response("participate_in_crocodiles")
        assert(alternative in ["a", "b", "c"])

        if not alternative in dict_alternatives:
            dict_alternatives[alternative] = 0
        dict_alternatives[alternative] += 1

    # Make sure weighted alternatives work -> should be a < b < c < d < e, 
    # but they should all exist.
    #
    # Again, it is statistically possible for
    # the following asserts to occasionally fail during
    # these tests, but it should be exceedingly rare 
    # if weighted alternatives are working properly.
    for key in ["a", "b", "c"]:
        assert(dict_alternatives.get(key, 0) > 0)
    assert(dict_alternatives.get("a", 0) < dict_alternatives.get("b", 0))
    assert(dict_alternatives.get("b", 0) < dict_alternatives.get("c", 0))

    # Check experiments count
    assert(test_response("count_experiments") == 7)

    # Test persist and load from DS
    assert(test_response("persist"))
    assert(test_response("flush_all_memcache"))

    # Check experiments and conversion counts 
    # remain after persist and memcache flush
    assert(test_response("count_experiments") == 7)

    dict_conversions_server = test_response(
                                "count_conversions_in", 
                                {"experiment_name":
                                    "chimpanzees (chimps_conversion_2)"})
    assert(expected_conversions == sum(dict_conversions_server.values()))

    # Test archiving
    assert(test_response("archive_monkeys"))

    # Test lack of presence in normal list of experiments after archive
    assert("monkeys" not in test_response("get_experiments"))

    # Test presence in list of archived experiments
    assert("monkeys" in test_response("get_archived_experiments"))

    # Test participating in monkeys once again after archiving
    # and make sure there's only one participant
    assert(test_response("participate_in_monkeys") in [True, False])
    assert(test_response("count_participants_in",
                        {"experiment_name": "monkeys"})
           == 1)

    print "Tests successful."

if __name__ == "__main__":
    run_tests()


