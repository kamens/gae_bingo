import hashlib
import logging
import time
import urllib

from google.appengine.api import memcache

from .cache import BingoCache, bingo_and_identity_cache
from .models import create_experiment_and_alternatives, ConversionTypes
from .identity import identity
from .config import can_control_experiments
from .cookies import get_cookie_value

def create_unique_experiments(canonical_name,
                              alternative_params,
                              conversion_names,
                              conversion_types,
                              family_name,
                              unique_experiment_names,
                              bingo_cache,
                              experiments):
    """Once we have a lock, create all of the unique experiments.

       canonical_name to family_name are all as in ab_test, except that
       conversion_names, conversion_types must be lists.

       unique_experiment_names are names unique to each experiment,
       generated in ab_test.

       bingo_cache and experiments are created in ab_test and passed to here,
       giving the current bingo_cache and current cached list of experiments.

    """

    if not(len(conversion_names) ==
                len(conversion_types) ==
                len(unique_experiment_names)):
        # The arguments should be correct length, since ab_test ensures that.
        # If they're not the same length, we don't know that ab_test ran
        # successfully, so we should abort (we might not even have a lock!)
        raise Exception("create_unique_experiments called with"
                        "arguments of mismatched length!")

    for i in range(len(conversion_names)):
        # We don't want to create a unique_experiment more than once
        # (note: it's fine to add experiments to one canonical name,
        #  which is how we can have one experiment with multiple conversions)
        if unique_experiment_names[i] not in experiments:
            exp, alts = create_experiment_and_alternatives(
                            unique_experiment_names[i],
                            canonical_name,
                            alternative_params,
                            conversion_names[i],
                            conversion_types[i],
                            family_name)

            bingo_cache.add_experiment(exp, alts)

    bingo_cache.store_if_dirty()

def participate_in_experiments(experiments,
                               alternative_lists,
                               bingo_identity_cache):
    """ Given a list of experiments (with unique names), alternatives for each,
        and an identity cache:
        --Enroll the current user in each experiment
        --return a value indicating which bucket a user is sorted into
            (this will be one of the entries in alternative_lists)

    """
    returned_content = None

    for i in range(len(experiments)):

        experiment, alternatives = experiments[i], alternative_lists[i]

        if not experiment.live:

            # Experiment has ended. Short-circuit and use selected winner
            # before user has had a chance to remove relevant ab_test code.
            returned_content = experiment.short_circuit_content

        else:

            alternative = _find_alternative_for_user(experiment.hashable_name,
                                                    alternatives)

            if experiment.name not in bingo_identity_cache.participating_tests:
                if alternative.increment_participants():
                    bingo_identity_cache.participate_in(experiment.name)

            # It shouldn't matter which experiment's alternative content
            # we send back -- alternative N should be the same across
            # all experiments w/ same canonical name.
            returned_content = alternative.content

    return returned_content

def ab_test(canonical_name,
            alternative_params = None,
            conversion_name = None,
            conversion_type = ConversionTypes.Binary,
            family_name = None):

    bingo_cache, bingo_identity_cache = bingo_and_identity_cache()

    # Make sure our conversion names and types are lists so that
    # we can more simply create one experiment for each one later.
    if isinstance(conversion_name, list):
        conversion_names = conversion_name
    else:
        conversion_names = [conversion_name]

    if isinstance(conversion_type, list):
        conversion_types = conversion_type
    else:
        conversion_types = [conversion_type] * len(conversion_names)


    # Unique name will have both canonical name and conversion.
    # This way, order of arguments in input list doesn't matter and
    # we still have unique experiment names.
    unique_experiment_names = ["%s (%s)" % (canonical_name, conv)
            if conv != None else canonical_name for conv in conversion_names]

    # Only create the experiment if it's necessary
    if any([conv not in bingo_cache.experiments
                    for conv in unique_experiment_names]):
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
                    # Lock looks available, try to take it with compare
                    # and set (expiration of 10 seconds)
                    got_lock = client.cas(lock_key, True, time=10)

                if not got_lock:
                    # If we didn't get it, wait a bit and try again
                    time.sleep(0.1)

            # We have the lock, go ahead and create the experiment
            experiments = BingoCache.get().experiments


            if len(conversion_names) != len(conversion_types):
                # we were called improperly with mismatched lists lengths.
                # Default everything to Binary
                logging.warning("ab_test(%s) called with lists of mismatched"
                                "length. Defaulting all conversions to binary!"
                                % canonical_name)
                conversion_types = ([ConversionTypes.Binary] *
                                        len(conversion_names))

            # Handle multiple conversions for a single experiment by just
            # quietly creating multiple experiments (one for each conversion).
            create_unique_experiments(canonical_name,
                                     alternative_params,
                                     conversion_names,
                                     conversion_types,
                                     family_name,
                                     unique_experiment_names,
                                     bingo_cache,
                                     experiments)

        finally:
            if got_lock:
                # Release the lock
                client.set(lock_key, False)

    # We might have multiple experiments connected to this single canonical
    # experiment name if it was started w/ multiple conversion possibilities.
    experiments, alternative_lists = (
            bingo_cache.experiments_and_alternatives_from_canonical_name(
                canonical_name))

    if not experiments or not alternative_lists:
        raise Exception(
            "Could not find experiment or alternatives with experiment_name %s"
            % canonical_name)

    return participate_in_experiments(experiments,
                                      alternative_lists,
                                      bingo_identity_cache)


def bingo(param):

    if type(param) == list:

        # Bingo for all conversions in list
        for conversion_name in param:
            bingo(conversion_name)
        return

    else:

        conv_name = str(param)
        bingo_cache = BingoCache.get()
        experiments = bingo_cache.get_experiment_names_by_conversion_name(
                conv_name)
        # Bingo for all experiments associated with this conversion
        for experiment_name in experiments:
            score_conversion(experiment_name)

def score_conversion(experiment_name):
    bingo_cache, bingo_identity_cache = bingo_and_identity_cache()

    if experiment_name not in bingo_identity_cache.participating_tests:
        return

    experiment = bingo_cache.get_experiment(experiment_name)

    if not experiment or not experiment.live:
        # Don't count conversions for short-circuited
        # experiments that are no longer live
        return

    if (experiment.conversion_type != ConversionTypes.Counting and
            experiment_name in bingo_identity_cache.converted_tests):
        # Only allow multiple conversions for
        # ConversionTypes.Counting experiments
        return

    alternative = _find_alternative_for_user(
                      experiment.hashable_name,
                      bingo_cache.get_alternatives(experiment_name))

    if alternative.increment_conversions():
        bingo_identity_cache.convert_in(experiment_name)

def choose_alternative(canonical_name, alternative_number):

    bingo_cache = BingoCache.get()

    # Need to end all experiments that may have been kicked off
    # by an experiment with multiple conversions
    experiments, alternative_lists = (
            bingo_cache.experiments_and_alternatives_from_canonical_name(
                canonical_name))

    if not experiments or not alternative_lists:
        return

    for i in range(len(experiments)):
        experiment, alternatives = experiments[i], alternative_lists[i]

        alternative_chosen = filter(
                                lambda alt: alt.number == alternative_number,
                                alternatives)

        if len(alternative_chosen) == 1:
            experiment.live = False
            experiment.set_short_circuit_content(alternative_chosen[0].content)
            bingo_cache.update_experiment(experiment)

def delete_experiment(canonical_name, bingo_cache=None):

    if not bingo_cache:
        bingo_cache = BingoCache.get()

    # Need to delete all experiments that may have been kicked off
    # by an experiment with multiple conversions
    experiments, alternative_lists = (
            bingo_cache.experiments_and_alternatives_from_canonical_name(
                canonical_name))

    if not experiments or not alternative_lists:
        return

    for experiment in experiments:
        bingo_cache.delete_experiment_and_alternatives(experiment)

def archive_experiment(canonical_name):
    """Archive named experiment permanently, removing it from active cache."""

    bingo_cache = BingoCache.get()

    # Need to archive all experiments that may have been kicked off
    # by an experiment with multiple conversions
    experiments, alternative_lists = (
            bingo_cache.experiments_and_alternatives_from_canonical_name(
                canonical_name))

    if not experiments or not alternative_lists:
        return

    for experiment in experiments:
        bingo_cache.archive_experiment_and_alternatives(experiment)

def resume_experiment(canonical_name):

    bingo_cache = BingoCache.get()

    # Need to resume all experiments that may have been kicked off
    # by an experiment with multiple conversions
    experiments, alternative_lists = (
            bingo_cache.experiments_and_alternatives_from_canonical_name(
                canonical_name))

    if not experiments or not alternative_lists:
        return

    for experiment in experiments:
        experiment.live = True
        bingo_cache.update_experiment(experiment)

def find_alternative_for_user(canonical_name, identity_val):
    """ Returns the alternative that the specified bingo identity belongs to.
    If the experiment does not exist, this will return None.
    If the experiment has ended, this will return the chosen alternative.
    Note that the user may not have been opted into the experiment yet - this
    is just a way to probe what alternative will be selected, or has been
    selected for the user without causing side effects.

    If an experiment has multiple instances (because it was created with
    different alternative sets), will operate on the last experiment.

    canonical_name -- the canonical name of the experiment
    identity_val -- a string or instance of GAEBingoIdentity

    """

    bingo_cache = BingoCache.get()
    experiment_names = bingo_cache.get_experiment_names_by_canonical_name(
            canonical_name)

    if not experiment_names:
        return None

    experiment_name = experiment_names[-1]
    experiment = bingo_cache.get_experiment(experiment_name)

    if not experiment:
        return None

    if not experiment.live:
        # Experiment has ended - return result that was selected.
        return experiment.short_circuit_content

    return _find_alternative_for_user(
                experiment.hashable_name,
                bingo_cache.get_alternatives(experiment_name),
                identity_val).content

def _find_alternative_for_user(experiment_hashable_name,
                               alternatives,
                               identity_val=None):

    if can_control_experiments():
        # If gae_bingo administrator, allow possible override of alternative
        cookie_val = get_cookie_value(
                        "GAEBingo_%s"
                        % (experiment_hashable_name
                           .replace(" ", "+")
                           .replace("-", "+")))

        if cookie_val:
            matches = filter(lambda alt: alt.number == int(cookie_val),
                             alternatives)
            if len(matches) == 1:
                return matches[0]

    return modulo_choose(experiment_hashable_name,
                         alternatives,
                         identity(identity_val))

def modulo_choose(experiment_hashable_name, alternatives, identity):
    alternatives_weight = sum(map(lambda alt: alt.weight, alternatives))

    sig = hashlib.md5(experiment_hashable_name + str(identity)).hexdigest()
    sig_num = int(sig, base=16)
    index_weight = sig_num % alternatives_weight

    current_weight = alternatives_weight
    for alternative in sorted(alternatives,
                              key=lambda alt: alt.weight,
                              reverse=True):

        current_weight -= alternative.weight
        if index_weight >= current_weight:
            return alternative

def create_redirect_url(destination, conversion_names):
    """ Create a URL that redirects to destination after scoring conversions
    in all listed conversion names
    """

    result = "/gae_bingo/redirect?continue=%s" % urllib.quote(destination)

    if type(conversion_names) != list:
        conversion_names = [conversion_names]

    for conversion_name in conversion_names:
        result += "&conversion_name=%s" % urllib.quote(conversion_name)

    return result

def _iri_to_uri(iri):
    """Convert an Internationalized Resource Identifier (IRI) for use in a URL.

    This function follows the algorithm from section 3.1 of RFC 3987 and is
    idempotent, iri_to_uri(iri_to_uri(s)) == iri_to_uri(s)

    Args:
        iri: A unicode string.

    Returns:
        An ASCII string with the encoded result. If iri is not unicode it
        is returned unmodified.
    """
    # Implementation heavily inspired by django.utils.encoding.iri_to_uri()
    # for its simplicity. We make the further assumption that the incoming
    # argument is a unicode string or is ignored.
    #
    # See also werkzeug.urls.iri_to_uri() for a more complete handling of
    # internationalized domain names.
    if isinstance(iri, unicode):
        byte_string = iri.encode("utf-8")
        return urllib.quote(byte_string, safe="/#%[]=:;$&()+,!?*@'~")
    return iri
