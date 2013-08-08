import ast
import base64
import cookielib
import json
import os
import random
import unittest
import urllib2

import google.appengine.ext.deferred

from testutil import gae_model
from testutil import dev_appserver_utils
from testutil import random_util
from testutil import taskqueue_util
from testutil import testsize
from testutil import wsgi_test_utils

import endtoend_main
from .. import main as gae_bingo_main

_CURRENT_DIR = os.path.dirname(__file__)


class AppServerTests(unittest.TestCase):
    """The test case contains tests that require dev_appserver to run.

    TODO(chris): remove the need for the app server entirely. The
    dependencies for login tests in particular are hard to break.
    """

    def __init__(self, *args, **kwargs):
        super(AppServerTests, self).__init__(*args, **kwargs)
        self.last_opener = None

    def fetch(self, url, use_last_cookies=False):
        if not use_last_cookies or self.last_opener is None:
            cj = cookielib.CookieJar()
            self.last_opener = urllib2.build_opener(
                urllib2.HTTPCookieProcessor(cj))
        url = "%s%s" % (dev_appserver_utils.appserver_url, url)
        req = self.last_opener.open(url)
        try:
            return req.read()
        finally:
            req.close()

    @testsize.large()
    def setUp(self):
        super(AppServerTests, self).setUp()
        appdir = os.path.join(_CURRENT_DIR, 'app')
        tmpdir = dev_appserver_utils.create_sandbox(root=appdir)
        # Symlink gae_bingo into the test app's sandbox. We don't want
        # to keep a permanent symlink in the source tree because when
        # tools/runtests.py walks the tree to find tests, this would
        # create a cycle.
        os.symlink(os.path.join(_CURRENT_DIR, '..'),
                   os.path.join(tmpdir, 'gae_bingo'))
        dev_appserver_utils.start_dev_appserver_in_sandbox(tmpdir, root=appdir)

    def tearDown(self):
        super(AppServerTests, self).tearDown()
        # Let's emit the dev_appserver's logs in case those are helpful.
        # TODO(chris): only emit if there are >0 failures?
        print
        print '---------------- START DEV_APPSERVER LOGS ---------------------'
        print open(dev_appserver_utils.dev_appserver_logfile_name()).read()
        print '----------------- END DEV_APPSERVER LOGS ----------------------'
        dev_appserver_utils.stop_dev_appserver()

    def test_identity_with_login(self):
        # Ensure identity works correctly and consistently after login.
        last_id = None
        for _ in xrange(5):
            # Randomly generate an ID so we have a good chance of
            # having a new one.  If that assumption is wrong, the test
            # will fail -- clear the datastore to increase chances of
            # working.
            user = base64.urlsafe_b64encode(os.urandom(30)) + "%40example.com"
            self.fetch("/")  # Load / to get ID assigned
            first_id = self.fetch("/identity", use_last_cookies=True)
            self.assertNotEqual(first_id, last_id)
            self.fetch(
                "/_ah/login?email=" + user + "&action=Login&continue=%2Fpostlogin",
                use_last_cookies=True)
            # Now make sure the ID is consistent
            last_id = self.fetch("/identity", use_last_cookies=True)
            self.assertEqual(first_id, last_id)


class EndToEndTests(gae_model.GAEModelTestCase):
    def setUp(self):
        super(EndToEndTests, self).setUp(
            # TODO(chris): remove strong consistency. When I ported
            # the tests some required this to work.
            db_consistency_probability=1)
        self.runstep_client = wsgi_test_utils.TestApp(
            endtoend_main.application)
        self.bingo_client = wsgi_test_utils.TestApp(gae_bingo_main.application)
        random_util.stub_os_urandom(42)

    def tearDown(self):
        super(EndToEndTests, self).tearDown()
        random_util.unstub_os_urandom()

    def run_tasks(self):
        taskqueue_util.execute_until_empty(
            self.testbed,
            wsgi_test_utils.SetUpAppEngineEnvFromWsgiEnv(
                google.appengine.ext.deferred.application))

    def fetch_bingo_redirect(self, url, use_runstep_cookies=False):
        if use_runstep_cookies:
            self.bingo_client.cookies = self.runstep_client.cookies.copy()
        response = self.bingo_client.get(url, status=302)
        if use_runstep_cookies:
            self.runstep_client.cookies = self.bingo_client.cookies.copy()
        return response.headers['Location']

    def fetch_runstep_json(self, step="", data=None, headers=None,
                           bot=False, url=None, use_last_cookies=False):
        if not use_last_cookies:
            self.clear_runstep_cookies()
        if bot:
            if headers is None:
                headers = {}
            headers["User-agent"] = "monkeysmonkeys Googlebot monkeysmonkeys"
        if url is None:
            if data is None:
                data = {}
            data["step"] = step
            url = "/gae_bingo/tests/run_step"
        response = self.runstep_client.get(url, params=data, headers=headers,
                                           status=200)
        try:
            return json.loads(response.body)
        except ValueError:
            return None

    def clear_runstep_cookies(self):
        self.runstep_client.reset()

    def test_cookie_identity(self):
        # Identity should be carried over due to cookie
        ident1 = self.fetch_runstep_json("get_identity")
        ident2 = self.fetch_runstep_json("get_identity", use_last_cookies=True)
        self.assertEqual(ident1, ident2)

        # If identity is not in the cookie, a new one is generated
        ident1 = self.fetch_runstep_json("get_identity")
        ident2 = self.fetch_runstep_json("get_identity")
        self.assertNotEqual(ident1, ident2)

    def test_conversions(self):
        # We're going to try to add a conversion to the experiment
        self.assertIn(
            self.fetch_runstep_json("participate_in_hippos"),
            [True, False])
    
        self.assertTrue(self.fetch_runstep_json(
            "convert_in", {"conversion_name": "hippos_binary"},
            use_last_cookies=True))
    
        # Make sure participant counts are right
        self.assertEqual(1, self.fetch_runstep_json(
                                "count_participants_in",
                                {"experiment_name": "hippos (hippos_binary)"},
                                use_last_cookies=True))
        self.assertEqual(1, self.fetch_runstep_json(
                                "count_participants_in",
                                {"experiment_name": "hippos (hippos_counting)"},
                                use_last_cookies=True))
        # Make sure we have the right number of conversions
        dict_conversions_server = self.fetch_runstep_json(
                             "count_conversions_in",
                             {"experiment_name": "hippos (hippos_binary)"},
                             use_last_cookies=True)
        self.assertEqual(1, sum(dict_conversions_server.values()))
    
        dict_conversions_server = self.fetch_runstep_json(
                            "count_conversions_in",
                            {"experiment_name": "hippos (hippos_counting)"},
                            use_last_cookies=True)
        self.assertEqual(0, sum(dict_conversions_server.values()))
    
        self.assertIn(self.fetch_runstep_json("add_conversions", use_last_cookies=True), [True, False])
        self.assertEqual(3, self.fetch_runstep_json("count_experiments", use_last_cookies=True))
    
        # make sure that we have the /right/ experiments
        self.assertEqual(
            set(["hippos (hippos_binary)",
                 "hippos (hippos_counting)",
                 "hippos (rhinos_counting)"]),
            set(ast.literal_eval(self.fetch_runstep_json(
                                     "get_experiments",
                                     use_last_cookies=True)).keys()))
        
        self.assertTrue(self.fetch_runstep_json(
                            "convert_in",
                            {"conversion_name": "rhinos_counting"},
                            use_last_cookies=True))
    
        dict_conversions_server = self.fetch_runstep_json(
                            "count_conversions_in",
                            {"experiment_name": "hippos (hippos_binary)"})
        self.assertEqual(1, sum(dict_conversions_server.values()))
    
        dict_conversions_server = self.fetch_runstep_json(
                            "count_conversions_in",
                            {"experiment_name": "hippos (hippos_counting)"},
                            use_last_cookies=True)
        self.assertEqual(0, sum(dict_conversions_server.values()))
        
        dict_conversions_server = self.fetch_runstep_json(
                            "count_conversions_in",
                            {"experiment_name": "hippos (rhinos_counting)"},
                            use_last_cookies=True)
        
        self.assertEqual(1, sum(dict_conversions_server.values()))

    def test_conversions_with_user_switching(self):
        # Now try the same, but with switching users
        self.assertIn(self.fetch_runstep_json("participate_in_hippos"), [True, False])
        
        self.assertTrue(self.fetch_runstep_json(
                            "convert_in",
                            {"conversion_name":
                             "hippos_binary"}, use_last_cookies=True))
    
        self.assertIn(self.fetch_runstep_json("participate_in_hippos", use_last_cookies=False),
                      [True, False])
    
        self.assertIn(self.fetch_runstep_json("add_conversions", use_last_cookies=True),
                      [True, False])
    
        self.assertTrue(self.fetch_runstep_json(
                            "convert_in",
                            {"conversion_name":
                             "rhinos_counting"}, use_last_cookies=True))
        self.assertEqual(2, self.fetch_runstep_json(
                                "count_participants_in",
                                {"experiment_name": "hippos (hippos_binary)"}))
        self.assertEqual(1, self.fetch_runstep_json(
                                "count_participants_in",
                                {"experiment_name": "hippos (rhinos_counting)"}))
        dict_conversions_server = self.fetch_runstep_json(
                                     "count_conversions_in",
                                     {"experiment_name": "hippos (hippos_binary)"})
        self.assertEqual(1, sum(dict_conversions_server.values()))
        dict_conversions_server = self.fetch_runstep_json(
                                "count_conversions_in",
                                {"experiment_name": "hippos (rhinos_counting)"})
        self.assertEqual(1, sum(dict_conversions_server.values()))

    def test_conversions_with_redirects(self):
        # Test constructing a redirect URL that converts in monkey and chimps
        redirect_url_monkeys = self.fetch_runstep_json("create_monkeys_redirect_url")
        self.assertEqual(
            redirect_url_monkeys,
            "/gae_bingo/redirect?continue=/gae_bingo&conversion_name=monkeys")
    
        redirect_url_chimps = self.fetch_runstep_json("create_chimps_redirect_url")
        self.assertEqual(redirect_url_chimps,
                         ("/gae_bingo/redirect?continue=/gae_bingo&"
                          "conversion_name=chimps_conversion_1&"
                          "conversion_name=chimps_conversion_2"))
    
        # Test participating in monkeys and chimps once,
        # and use previously constructed redirect URLs to convert
        self.assertIn(self.fetch_runstep_json("participate_in_monkeys"), [True, False])
        self.fetch_bingo_redirect(redirect_url_monkeys, use_runstep_cookies=True)
        self.assertIn(self.fetch_runstep_json("participate_in_chimpanzees"), [True, False])
        self.fetch_bingo_redirect(redirect_url_chimps, use_runstep_cookies=True)
    
        # Make sure there's a single participant and conversion in monkeys
        self.assertEqual(1, self.fetch_runstep_json("count_participants_in",
                                          {"experiment_name": "monkeys"}))
        dict_conversions_server = self.fetch_runstep_json("count_conversions_in",
                                               {"experiment_name": "monkeys"})
        self.assertEqual(1, sum(dict_conversions_server.values()))
    
        # Make sure there's a single participant and two conversions in chimps
        self.assertEqual(1, self.fetch_runstep_json(
                                "count_participants_in",
                                {"experiment_name":
                                 "chimpanzees (chimps_conversion_1)"}))
        dict_conversions_server = self.fetch_runstep_json(
                                    "count_conversions_in",
                                    {"experiment_name":
                                        "chimpanzees (chimps_conversion_1)"})
        self.assertEqual(1, sum(dict_conversions_server.values()))
        dict_conversions_server = self.fetch_runstep_json(
                                    "count_conversions_in",
                                    {"experiment_name":
                                     "chimpanzees (chimps_conversion_2)"})
        self.assertEqual(1, sum(dict_conversions_server.values()))

    def test_too_many_alternatives(self):
        def participation_crash():
            self.fetch_runstep_json("participate_in_skunks")
        self.assertRaises(Exception, participation_crash)

    def test_simultaneous_experiment_creation(self):
        for _ in range(0, 3):
            # Start an experiment on a faked "new instance"
            self.assertIn(self.fetch_runstep_json(
                "participate_in_doppleganger_on_new_instance"),
                [True, False])

            # Persist from that instance
            self.assertTrue(self.fetch_runstep_json("persist"))

        # Make sure that only one experiment has been created
        self.assertEqual(1, self.fetch_runstep_json(
            "count_doppleganger_experiments"))

    # TODO(chris): divide this up into more targeted tests.
    # TODO(kamens): add unit tests for deleting experiments.
    @testsize.medium()  # lots going on here, takes a few seconds to run.
    def test_bots_conversions_weighting_and_lifecycle(self):
        # Refresh bot's identity record so it doesn't pollute tests
        self.assertTrue(self.fetch_runstep_json("refresh_identity_record", bot=True))
    
        # Participate in experiment A, check for correct alternative
        # valuesum(core_metrics.values(), [])s being returned,
        for _ in range(0, 20):
            self.assertIn(self.fetch_runstep_json("participate_in_monkeys"), [True, False])
    
        self.assertEqual(20, self.fetch_runstep_json("count_participants_in",
                                           {"experiment_name": "monkeys"}))
    
        # Identify as a bot a couple times (response should stay the same)
        bot_value = None
        for _ in range(0, 5):
            value = self.fetch_runstep_json("participate_in_monkeys", bot=True)
            self.assertIn(value, [True, False])
    
            if bot_value is None:
                bot_value = value
    
            self.assertEqual(value, bot_value)
    
        # Check total participants in A (1 extra for bots)
        self.assertEqual(21, self.fetch_runstep_json("count_participants_in",
                                           {"experiment_name": "monkeys"}))
    
        # Participate in experiment B (responses should be "a" "b" or "c")
        for _ in range(0, 15):
            self.assertIn(self.fetch_runstep_json("participate_in_gorillas"), ["a", "b", "c"])
    
        # Participate in experiment A,
        # using cookies half of the time to maintain identity
        for i in range(0, 20):
            self.assertIn(self.fetch_runstep_json("participate_in_monkeys",
                                        use_last_cookies=(i % 2 == 1)),
                          [True, False])
        # Check total participants in A
        # (should've only added 10 more in previous step)
        self.assertEqual(31, self.fetch_runstep_json("count_participants_in",
                                           {"experiment_name": "monkeys"}))
    
        # Participate in A once more with a lot of followup, 
        # persisting to datastore and flushing memcache between followups
        for i in range(0, 10):
            self.assertIn(self.fetch_runstep_json("participate_in_monkeys",
                                        use_last_cookies=(i not in [0, 5])),
                          [True, False])
    
            if i in [1, 6]:
    
                self.assertTrue(self.fetch_runstep_json("persist", use_last_cookies=True))
    
                # Wait for task queues to run
                self.run_tasks()
    
                self.assertTrue(self.fetch_runstep_json("flush_all_cache",
                                              use_last_cookies=True))
    
        # NOTE: It's possible for this to fail sometimes--maybe a race condition?
        # TODO(kamens,josh): figure out why this happens? (Or just wait to not use
        #                     AppEngine any more)
        # Check total participants in A
        # (should've only added 2 more in previous step)
        self.assertEqual(33, self.fetch_runstep_json("count_participants_in",
                                           {"experiment_name": "monkeys"}))
    
        # Participate and convert in experiment A,
        # using cookies to tie participation to conversions,
        # tracking conversions-per-alternative
        dict_conversions = {}
        for _ in range(0, 35):
            alternative_key = str(self.fetch_runstep_json("participate_in_monkeys"))
            self.assertTrue(self.fetch_runstep_json("convert_in",
                                          {"conversion_name": "monkeys"},
                                          use_last_cookies=True))
    
            if not alternative_key in dict_conversions:
                dict_conversions[alternative_key] = 0
            dict_conversions[alternative_key] += 1
    
        # Check total conversions-per-alternative in A
        self.assertEqual(2, len(dict_conversions))
        self.assertEqual(35, sum(dict_conversions.values()))
    
        dict_conversions_server = self.fetch_runstep_json("count_conversions_in",
                                               {"experiment_name": "monkeys"})
        self.assertEqual(len(dict_conversions), len(dict_conversions_server))
    
        for key in dict_conversions:
            self.assertEqual(dict_conversions[key], dict_conversions_server[key])

        # Participate in experiment B, using cookies to maintain identity
        # and making sure alternatives for B are stable per identity
        last_response = None
        for _ in range(0, 20):
            use_last_cookies = (last_response is not None and
                                 random.randint(0, 2) > 0)
    
            current_response = self.fetch_runstep_json("participate_in_gorillas",
                                             use_last_cookies=use_last_cookies)
    
            if not use_last_cookies:
                last_response = current_response
    
            self.assertIn(current_response, ["a", "b", "c"])
            self.assertEqual(last_response, current_response)
    
        # Participate in experiment C, which is a multi-conversion experiment,
        # and occasionally convert in *one* of the conversions
        expected_conversions = 0
        for _ in range(0, 20):
            self.assertIn(self.fetch_runstep_json("participate_in_chimpanzees"), [True, False])
    
            if random.randint(0, 2) > 0:
                self.assertTrue(
                    self.fetch_runstep_json("convert_in",
                                  {"conversion_name": "chimps_conversion_2"},
                                  use_last_cookies=True))
                expected_conversions += 1
    
        # This would be random if the RNG weren't seeded.
        self.assertEqual(13, expected_conversions)
    
        # Make sure conversions for the 2nd conversion type 
        # of this experiment are correct
        dict_conversions_server = self.fetch_runstep_json(
                                     "count_conversions_in",
                                     {"experiment_name":
                                         "chimpanzees (chimps_conversion_2)"})
        self.assertEqual(expected_conversions, sum(dict_conversions_server.values()))
    
        # Make sure conversions for the 1st conversion type 
        # of this experiment are empty
        dict_conversions_server = self.fetch_runstep_json(
                                    "count_conversions_in",
                                    {"experiment_name":
                                     "chimpanzees (chimps_conversion_1)"})
        self.assertEqual(0, sum(dict_conversions_server.values()))
    
        # Test that calling bingo multiple times for a single 
        # user creates only one conversion (for a BINARY conversion type)
        self.assertIn(self.fetch_runstep_json("participate_in_chimpanzees"), [True, False])
        self.assertTrue(self.fetch_runstep_json("convert_in",
                                      {"conversion_name": "chimps_conversion_1"},
                                      use_last_cookies=True))
    
        self.assertTrue(self.fetch_runstep_json(
            "convert_in",
            {"conversion_name": "chimps_conversion_1"},
            use_last_cookies=True))
    
        dict_conversions_server = self.fetch_runstep_json(
                                    "count_conversions_in",
                                    {"experiment_name":
                                        "chimpanzees (chimps_conversion_1)"})
        self.assertEqual(1, sum(dict_conversions_server.values()))
    
        # End experiment C, choosing a short-circuit alternative
        self.fetch_runstep_json("end_and_choose",
                     {"canonical_name": "chimpanzees", "alternative_number": 1})
    
        # Make sure short-circuited alternatives for 
        # C's experiments are set appropriately
        for _ in range(0, 5):
            self.assertFalse(self.fetch_runstep_json("participate_in_chimpanzees"))
    
        # Test an experiment with a Counting type conversion 
        # by converting multiple times for a single user
        self.assertIn(self.fetch_runstep_json("participate_in_hippos"), [True, False])
    
        # Persist to the datastore before Counting stress test
        self.assertTrue(self.fetch_runstep_json("persist", use_last_cookies=True))
    
        # Wait for task queues to run
        self.run_tasks()
    
        # Hit Counting conversions multiple times
        for i in range(0, 20):
    
            if i % 3 == 0:
                # Stress things out a bit by flushing the memcache .incr() 
                # counts of each hippo alternative
                self.assertTrue(self.fetch_runstep_json("persist", use_last_cookies=True))
                self.assertTrue(self.fetch_runstep_json("flush_hippo_counts_memcache",
                                              use_last_cookies=True))
            
            elif i % 5 == 0:
                # Stress things out even more flushing the core bingo memcache
                self.assertTrue(self.fetch_runstep_json("flush_bingo_cache",
                                              use_last_cookies=True))
    
            self.assertTrue(self.fetch_runstep_json(
                "convert_in",
                {"conversion_name": "hippos_binary"},
                use_last_cookies=True))
    
            self.assertTrue(self.fetch_runstep_json(
                "convert_in",
                {"conversion_name": "hippos_counting"},
                use_last_cookies=True))
    
        dict_conversions_server = self.fetch_runstep_json(
                                    "count_conversions_in",
                                    {"experiment_name": "hippos (hippos_binary)"})
        self.assertEqual(1, sum(dict_conversions_server.values()))
        dict_conversions_server = self.fetch_runstep_json(
                                    "count_conversions_in",
                                    {"experiment_name":
                                        "hippos (hippos_counting)"})
        self.assertEqual(20, sum(dict_conversions_server.values()))
    
        # Participate in experiment D (weight alternatives), 
        # keeping track of alternative returned count.
        dict_alternatives = {}
        for _ in range(0, 75):
            alternative = self.fetch_runstep_json("participate_in_crocodiles")
            self.assertIn(alternative, ["a", "b", "c"])
    
            if not alternative in dict_alternatives:
                dict_alternatives[alternative] = 0
            dict_alternatives[alternative] += 1
    
        # Make sure weighted alternatives work -> should be a < b < c < d < e,
        # and they should all exist. This would be random if the RNG weren't
        # seeded.
        self.assertEqual(5, dict_alternatives.get("a"))
        self.assertEqual(18, dict_alternatives.get("b"))
        self.assertEqual(52, dict_alternatives.get("c"))
    
        # Check experiments count
        self.assertEqual(7, self.fetch_runstep_json("count_experiments"))
    
        # Test persist and load from DS
        self.assertTrue(self.fetch_runstep_json("persist"))
        self.assertTrue(self.fetch_runstep_json("flush_all_cache"))

        # Wait for task queues to run
        self.run_tasks()

        # Check experiments and conversion counts 
        # remain after persist and memcache flush
        self.assertEqual(7, self.fetch_runstep_json("count_experiments"))
    
        dict_conversions_server = self.fetch_runstep_json(
                                    "count_conversions_in", 
                                    {"experiment_name":
                                        "chimpanzees (chimps_conversion_2)"})
        self.assertEqual(expected_conversions, sum(dict_conversions_server.values()))
    
        # Test archiving
        self.assertTrue(self.fetch_runstep_json("archive_monkeys"))

        # Wait for eventual consistency of archived experiment
        # TODO(chris): remove dependency on db_consistency=1
    
        # Test lack of presence in normal list of experiments after archive
        self.assertNotIn("monkeys", self.fetch_runstep_json("get_experiments"))
    
        # Test presence in list of archived experiments
        self.assertIn("monkeys", self.fetch_runstep_json("get_archived_experiments"))
    
        # Test participating in monkeys once again after archiving
        # and make sure there's only one participant
        self.assertIn(self.fetch_runstep_json("participate_in_monkeys"), [True, False])
        self.assertEqual(1, self.fetch_runstep_json("count_participants_in",
                                          {"experiment_name": "monkeys"}))
