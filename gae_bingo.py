import logging
import hashlib
import os
import cgi
import time

from google.appengine.api import memcache

from .cache import BingoCache, bingo_and_identity_cache
from .models import create_experiment_and_alternatives, ConversionTypes
from .identity import identity

def ab_test(canonical_name, alternative_params = None, conversion_name = None, conversion_type = ConversionTypes.Binary):

    bingo_cache, bingo_identity_cache = bingo_and_identity_cache()

    if canonical_name not in bingo_cache.experiments:

        # Creation logic w/ high concurrency protection
        client = memcache.Client()
        lock_key = "_gae_bingo_test_creation_lock"
        got_lock = False

        try:

            # Make sure only one experiment gets created
            while not got_lock:
                locked = client.gets(lock_key)

                while locked is None:
                    # Initialize the lock if necessary
                    client.set(lock_key, False)
                    locked = client.gets(lock_key)

                if not locked:
                    # Lock looks available, try to take it with compare and set (expiration of 10 seconds)
                    got_lock = client.cas(lock_key, True, time=10)
                
                if not got_lock:
                    # If we didn't get it, wait a bit and try again
                    time.sleep(0.1)

            # We have the lock, go ahead and create the experiment if still necessary
            if canonical_name not in BingoCache.get().experiments:

                # Handle multiple conversions for a single experiment by just quietly
                # creating multiple experiments for each conversion
                conversion_names = conversion_name if type(conversion_name) == list else [conversion_name]
                conversion_types = conversion_type if type(conversion_type) == list else [conversion_type] * len(conversion_names)

                if len(conversion_names) != len(conversion_types):
                    # we were called improperly with mismatched lists lengths.. default everything to Binary
                    conversion_types = [ConversionTypes.Binary] * len(conversion_names)

                for i, (conversion_name, conversion_type) in enumerate(zip(conversion_names,conversion_types)):
                    unique_experiment_name = canonical_name if i == 0 else "%s (%s)" % (canonical_name, i + 1)

                    exp, alts = create_experiment_and_alternatives(
                                    unique_experiment_name,
                                    canonical_name,
                                    alternative_params, 
                                    conversion_name,
                                    conversion_type
                                    )

                    bingo_cache.add_experiment(exp, alts)

                bingo_cache.store_if_dirty()

        finally:
            if got_lock:
                # Release the lock
                client.set(lock_key, False)

    # We might have multiple experiments connected to this single canonical experiment name
    # if it was started w/ multiple conversion possibilities.
    experiments, alternative_lists = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

    if not experiments or not alternative_lists:
        raise Exception("Could not find experiment or alternatives with experiment_name %s" % canonical_name)

    returned_content = None

    for i in range(len(experiments)):

        experiment, alternatives = experiments[i], alternative_lists[i]

        if not experiment.live:

            # Experiment has ended. Short-circuit and use selected winner before user has had a chance to remove relevant ab_test code.
            returned_content = experiment.short_circuit_content

        else:

            alternative = find_alternative_for_user(canonical_name, alternatives)

            if experiment.name not in bingo_identity_cache.participating_tests:
                bingo_identity_cache.participate_in(experiment.name)

                alternative.increment_participants()
                bingo_cache.update_alternative(alternative)

            # It shouldn't matter which experiment's alternative content we send back --
            # alternative N should be the same across all experiments w/ same canonical name.
            returned_content = alternative.content

    return returned_content

def bingo(param):

    if type(param) == list:

        # Bingo for all conversions in list
        for experiment_name in param:
            bingo(experiment_name)
        return

    else:

        conversion_name = str(param)
        canonical_name = None
        bingo_cache = BingoCache.get()

        # Bingo for all experiments associated with this conversion
        for experiment_name in bingo_cache.get_experiment_names_by_conversion_name(conversion_name):

            if not canonical_name:
                experiment = bingo_cache.get_experiment(experiment_name)
                canonical_name = experiment.canonical_name

            score_conversion(experiment_name, canonical_name)

def score_conversion(experiment_name, canonical_name):

    bingo_cache, bingo_identity_cache = bingo_and_identity_cache()

    if experiment_name not in bingo_identity_cache.participating_tests:
        return

    experiment = bingo_cache.get_experiment(experiment_name)

    if not experiment or not experiment.live:
        # Don't count conversions for short-circuited experiments that are no longer live
        return

    if experiment_name in bingo_identity_cache.converted_tests and experiment.conversion_type!=ConversionTypes.Counting:
        return

    alternative = find_alternative_for_user(canonical_name, bingo_cache.get_alternatives(experiment_name))

    alternative.increment_conversions()
    bingo_cache.update_alternative(alternative)

    bingo_identity_cache.convert_in(experiment_name)

def choose_alternative(canonical_name, alternative_number):

    bingo_cache = BingoCache.get()

    # Need to end all experiments that may have been kicked off
    # by an experiment with multiple conversions
    experiments, alternative_lists = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

    if not experiments or not alternative_lists:
        return

    for i in range(len(experiments)):
        experiment, alternatives = experiments[i], alternative_lists[i]

        alternative_chosen = filter(lambda alternative: alternative.number == alternative_number , alternatives)

        if len(alternative_chosen) == 1:
            experiment.live = False
            experiment.set_short_circuit_content(alternative_chosen[0].content)
            bingo_cache.update_experiment(experiment)

def delete_experiment(canonical_name):

    bingo_cache = BingoCache.get()

    # Need to delete all experiments that may have been kicked off
    # by an experiment with multiple conversions
    experiments, alternative_lists = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

    if not experiments or not alternative_lists:
        return

    for i in range(len(experiments)):
        experiment, alternatives = experiments[i], alternative_lists[i]

        if experiment.live:
            raise Exception("Cannot delete a live experiment")

        bingo_cache.delete_experiment_and_alternatives(experiment)

def resume_experiment(canonical_name):

    bingo_cache = BingoCache.get()

    # Need to resume all experiments that may have been kicked off
    # by an experiment with multiple conversions
    experiments, alternative_lists = bingo_cache.experiments_and_alternatives_from_canonical_name(canonical_name)

    if not experiments or not alternative_lists:
        return

    for i in range(len(experiments)):
        experiment, alternatives = experiments[i], alternative_lists[i]

        experiment.live = True

        bingo_cache.update_experiment(experiment)

def find_alternative_for_user(experiment_name, alternatives):

    if os.environ["SERVER_SOFTWARE"].startswith('Development'):
        # If dev server, allow possible override of alternative
        qs_dict = cgi.parse_qs(os.environ.get("QUERY_STRING") or "")

        alternative_number_override = qs_dict.get("gae_bingo_alternative_number")
        if alternative_number_override:

            matches = filter(lambda alternative: alternative.number == int(alternative_number_override[0]), alternatives)
            if len(matches) == 1:
                return matches[0]

    return modulo_choose(experiment_name, alternatives)

def modulo_choose(experiment_name, alternatives):
    alternatives_weight = sum(map(lambda alternative: alternative.weight, alternatives))

    sig = hashlib.md5(experiment_name + str(identity())).hexdigest()
    sig_num = int(sig, base=16)
    index_weight = sig_num % alternatives_weight

    current_weight = alternatives_weight
    for alternative in sorted(alternatives, key=lambda alternative: alternative.weight, reverse=True):
        current_weight -= alternative.weight
        if index_weight >= current_weight:
            return alternative

