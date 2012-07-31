"""Utility functions for pickling and unpickling.

These provide a thin wrapper around pickle.dumps and loads, but
automatically pick a fast pickle implementation and an efficient
pickle version.

Most important, these utilities deal with class renaming.  Sometimes
database entities are pickled -- see exercise_models.UserExercise,
which pickles AccuracyModel.  If we renamed AccuracyModel -- even just
by moving it to another location -- then unpickling UserExercise would
break.  To fix it, we keep a map in this file of oldname->newname.
Then, whenever we unpickle an object and see oldname, we can
instantiate a newname instead.
"""

# The trick we use to do the classname mapping requires us to use
# cPickle in particular, not pickle.  That's ok.
import cPickle
import cStringIO
import sys

# Provide some of the symbols from pickle so we can be a drop-in replacement.
from pickle import PicklingError   # @UnusedImport


# To update this: if you rename a subclass of db.model, add a new entry:
#   (old_modules, old_classname) -> (new_modules, new_classname)
# If you later want to rename newname to newername, you should add
#   (new_modules, new_classname) -> (newer_modules, newer_classname)
# but also modify the existing oldname entry to be:
#   (old_modules, old_classname) -> (newer_modules, newer_classname)
_CLASS_RENAME_MAP = {
    ('accuracy_model.accuracy_model', 'AccuracyModel'):
    ('exercises.accuracy_model', 'AccuracyModel'),

    ('accuracy_model', 'AccuracyModel'):
    ('exercises.accuracy_model', 'AccuracyModel'),
}


def _renamed_class_loader(module_name, class_name):
    """Return a class object for class class_name, loaded from module_name.

    The trick here is we look in _CLASS_RENAME_MAP before doing
    the loading.  So even if the class has moved to a different module
    since when this pickled object was created, we can still load it.
    """
    (actual_module_name, actual_class_name) = _CLASS_RENAME_MAP.get(
        (module_name, class_name),   # key to the map
        (module_name, class_name))   # what to return if the key isn't found

    # This is taken from pickle.py:Unpickler.find_class()
    __import__(actual_module_name)   # import the module if necessary
    module = sys.modules[actual_module_name]
    return getattr(module, actual_class_name)


def dump(obj):
    """Return a pickled string of obj: equivalent to pickle.dumps(obj)."""
    return cPickle.dumps(obj, cPickle.HIGHEST_PROTOCOL)


def load(s):
    """Return an unpickled object from s: equivalent to pickle.loads(s)."""
    unpickler = cPickle.Unpickler(cStringIO.StringIO(s))
    # See http://docs.python.org/library/pickle.html#subclassing-unpicklers
    unpickler.find_global = _renamed_class_loader
    return unpickler.load()
