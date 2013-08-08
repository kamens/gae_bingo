"""Persist tools are used to continually persist data from gae/bingo's caches.

The current persistence technique works by chaining together task queue tasks.
Each task loads all current memcached gae/bingo data and stores it in the
datastore. At the end of each persist task, a new task is queued up. In this
way, persistence should be happening 'round the clock.

In the event that the persist chain has broken down at some point due to a
problem we didn't foresee (gasp!), a one-per-minute cron job will be hitting
GuaranteePersistTask and attempting to re-insert any missing persist task.
"""
import datetime
import logging
import os
import time

from google.appengine.api import datastore_errors
from google.appengine.api import taskqueue
from google.appengine.ext import deferred
from google.appengine.ext import ndb
from google.appengine.ext.webapp import RequestHandler

import cache
from config import config
import instance_cache
import request_cache


class _GAEBingoPersistLockEntry(ndb.Model):
    """A db entry used for creating a lock. See PersistLock for details.

    TODO(benkomalo): this is used in place of a memcache based lock, since we
    were seeing fairly constant, spontaneous evictions of the memcache entry
    within a matter of seconds, making the lock unreliable. Using a db entity
    for locking is non-ideal, and can hopefully be changed later.
    """

    # Can be "None" to signify the lock is not taken. Otherwise, if non-empty,
    # this means the lock has been taken and will expire at the specified time.
    expiry = ndb.DateTimeProperty(indexed=False)


class PersistLock(object):
    """PersistLock makes sure we're only running one persist task at a time.

    It can also be acquired to temporarily prevent persist tasks from running.
    """

    KEY = "_gae_bingo_persist_lock"

    def __init__(self, key=KEY):
        self._entity = None
        self._key = key

    def take(self, lock_timeout=60):
        """Take the gae/bingo persist lock.

        This is only a quick, one-time attempt to take the lock. This doesn't
        spin waiting for the lock at all, because we often expect another
        persist to already be running, and that's ok.

        This lock will expire on its own after a timeout. We do this to avoid
        completely losing the lock if some bug causes the lock to not be
        released.

        Arguments:
            lock_timeout -- how long in seconds the lock should be valid for
                after being successful in taking it
        Returns:
            True if lock successfully taken, False otherwise.
        """
        def txn():
            entity = _GAEBingoPersistLockEntry.get_or_insert(
                    self._key,
                    expiry=None)

            if entity.expiry and entity.expiry > datetime.datetime.utcnow():
                return None
            entity.expiry = (datetime.datetime.utcnow() +
                             datetime.timedelta(seconds=lock_timeout))
            entity.put()
            return entity

        try:
            self._entity = ndb.transaction(txn, retries=0)
        except datastore_errors.TransactionFailedError, e:
            # If there was a transaction collision, it probably means someone
            # else acquired the lock. Just wipe out any old values and move on.
            self._entity = None
        return self._entity is not None

    def spin_and_take(self, attempt_timeout=60, lock_timeout=60):
        """Take the gae/bingo persist lock, hard spinning until success.

        This is essentially used for clients interested in altering bingo
        data without colliding with the persist tasks.

        Arguments:
            attempt_timeout -- how long in seconds to try to take the
                lock before giving up and bailing
            lock_timeout -- how long in seconds the lock should be valid for
                after being successful in taking it
        Returns:
            True if lock successfully taken, False otherwise.
        """

        # Just use wall clock time for the attempt_timeout
        start = time.time()

        attempts = 0
        while time.time() - start < attempt_timeout:
            attempts += 1
            if self.take(lock_timeout):
                logging.info("took PersistLock after %s attempts" % attempts)
                return True
        logging.error("Failed to take PersistLock after %s attempts" %
                      attempts)
        return False

    def is_active(self):
        return self._entity is not None

    def release(self):
        """Release the gae/bingo persist lock."""
        if self.is_active():
            self._entity.expiry = None
            self._entity.put()
            self._entity = None


def persist_task():
    """Persist all gae/bingo cache entities to the datastore.

    After persisting, this task should queue itself up for another run quickly
    thereafter.

    This function uses a lock to make sure that only one persist task
    is running at a time.
    """
    lock = PersistLock()

    # Take the lock (only one persist should be running at a time)
    if not lock.take():
        logging.info("Skipping gae/bingo persist, persist lock already owned.")
        return

    logging.info("Persisting gae/bingo state from memcache to datastore")

    try:
        # Make sure request and instance caches are flushed, because this task
        # doesn't go through the normal gae/bingo WSGI app which is wrapped in
        # middleware. Regardless, we want to flush instance cache so that we're
        # persisting the current shared memcache state of all exercises to the
        # datastore.
        request_cache.flush_request_cache()
        instance_cache.flush()

        cache.BingoCache.get().persist_to_datastore()
        cache.BingoIdentityCache.persist_buckets_to_datastore()
    finally:
        # Always release the persist lock
        lock.release()

    # In production, at the end of every persist task, queue up the next one.
    # An unbroken chain of persists should always be running.
    if not os.environ["SERVER_SOFTWARE"].startswith('Development'):
        queue_new_persist_task()


def queue_new_persist_task():
    """Queue up a new persist task on the task queue via deferred library.

    These tasks should fire off immediately. If they're being backed off by GAE
    due to errors, they shouldn't try less frequently than once every 60
    seconds."""
    try:
        deferred.defer(persist_task, _queue=config.QUEUE_NAME,
            _retry_options=taskqueue.TaskRetryOptions(max_backoff_seconds=60))
    except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError):
        logging.info("Task for gae/bingo persist already exists.")


class GuaranteePersistTask(RequestHandler):
    """Triggered by cron, this GET handler makes sure a persist task exists.

    This should be triggered once every minute. We expect the vast majority of
    this handler's attempts to queue up a new persist task to be unable to grab
    the PersistLock, which is expected.

    Since persist tasks always queue up another task at the end of their job,
    there should be an unbroken chain of tasks always running.
    GuaranteePersistTask is just an extra safety measure in case something has
    gone terribly wrong with task queues and the persist task queue chain was
    broken.
    """
    def get(self):
        queue_new_persist_task()
