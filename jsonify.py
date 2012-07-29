# Based on http://appengine-cookbook.appspot.com/recipe/extended-jsonify-function-for-dbmodel,
# with modifications for flask and performance.

# use json in Python 2.7, fallback to simplejson for Python 2.5
try:
    import json
except ImportError:
    import simplejson as json

from google.appengine.ext import db
from datetime import datetime
import re

SIMPLE_TYPES = (int, long, float, bool, basestring)


def dumps(obj, camel_cased=False):
    if isinstance(obj, SIMPLE_TYPES):
        return obj
    elif obj == None:
        return None
    elif isinstance(obj, list):
        items = []
        for item in obj:
            items.append(dumps(item, camel_cased))
        return items
    elif isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif isinstance(obj, dict):
        properties = {}
        for key in obj:
            value = dumps(obj[key], camel_cased)
            if camel_cased:
                properties[camel_casify(key)] = value
            else:
                properties[key] = value
        return properties

    properties = dict()
    if isinstance(obj, db.Model):
        properties['kind'] = obj.kind()

    serialize_blacklist = []
    if hasattr(obj, "_serialize_blacklist"):
        serialize_blacklist = obj._serialize_blacklist

    serialize_list = dir(obj)
    if hasattr(obj, "_serialize_whitelist"):
        serialize_list = obj._serialize_whitelist

    for property in serialize_list:
        if _is_visible_property(property, serialize_blacklist):
            try:
                value = obj.__getattribute__(property)
                if not _is_visible_property_value(value):
                    continue

                valueClass = str(value.__class__)
                if is_visible_class_name(valueClass):
                    value = dumps(value, camel_cased)
                    if camel_cased:
                        properties[camel_casify(property)] = value
                    else:
                        properties[property] = value
            except:
                continue

    if len(properties) == 0:
        return str(obj)
    else:
        return properties

UNDERSCORE_RE = re.compile("_([a-z])")


def camel_case_replacer(match):
    """ converts "_[a-z]" to remove the underscore and uppercase the letter """
    return match.group(0)[1:].upper()


def camel_casify(str):
    return re.sub(UNDERSCORE_RE, camel_case_replacer, str)


def _is_visible_property(property, serialize_blacklist):
    return (property[0] != '_' and
            not property.startswith("INDEX_") and
            not property in serialize_blacklist)


def _is_visible_property_value(value):
    # Right now only db.Blob objects are
    # blacklisted (since they may contain binary that doesn't JSONify well)
    if isinstance(value, db.Blob):
        return False
    return True


def is_visible_class_name(class_name):
    return not(
                ('function' in class_name) or 
                ('built' in class_name) or 
                ('method' in class_name) or
                ('db.Query' in class_name)
            )


class JSONModelEncoder(json.JSONEncoder):
    def default(self, o):
        """ Turns objects into serializable dicts for the default encoder """
        return dumps(o)


class JSONModelEncoderCamelCased(json.JSONEncoder):
    def encode(self, obj):
        # We override encode() instead of the usual default(), since we need
        # to handle built in types like lists and dicts ourselves as well.
        # Specifically, we need to re-construct the object with camelCasing
        # anyways, so do that before encoding.
        obj = dumps(obj, camel_cased=True)
        return super(self.__class__, self).encode(obj)


def jsonify(data, camel_cased=False):
    """jsonify data in a standard (human friendly) way. If a db.Model
    entity is passed in it will be encoded as a dict.

    If the current request being served is being served via Flask, and
    has a parameter "casing" with the value "camel", properties in the
    resulting output will be converted to use camelCase instead of the
    regular Pythonic underscore convention.
    """

    if camel_cased:
        encoder = JSONModelEncoderCamelCased
    else:
        encoder = JSONModelEncoder
    return json.dumps(data,
                      skipkeys=True,
                      sort_keys=True,
                      ensure_ascii=False,
                      indent=4,
                      cls=encoder)
