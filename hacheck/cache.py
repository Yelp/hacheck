import contextlib
import copy
import functools
import time
try:
    from collections import Counter
except Exception:
    from .compat import Counter
from collections import namedtuple

from . import config as configuration

_cache = {}

config = {
    'cache_time': 10,
    'ignore_cache': False,
}

default_stats = Counter({
    'expirations': 0,
    'sets': 0,
    'gets': 0,
    'hits': 0,
    'misses': 0
})

stats = Counter()

Key = namedtuple('Key', ['original_key'])
Record = namedtuple('Record', ['expiry', 'value'])


def configure(cache_time=config['cache_time']):
    """Configure the cache and reset its values"""
    config['cache_time'] = cache_time
    stats.clear()
    stats.update(default_stats)
    _cache.clear()


def has_expired(record, now):
    if record.expiry < now:
        return True
    else:
        return False


def getv(key, now=None):
    """Get a key from the cache

    :param now: The current time
    :raises: KeyError if the key is not present or has expired
    :returns: The result
    """
    if now is None:
        now = time.time()
    key = Key(key)
    stats['gets'] += 1
    if key in _cache:
        record = _cache[key]
        if has_expired(record, now) or config['ignore_cache']:
            stats['expirations'] += 1
            del _cache[key]
        else:
            stats['hits'] += 1
            return record.value
    stats['misses'] += 1
    raise KeyError(key)


def setv(key, value):
    key = Key(key)
    stats['sets'] += 1
    expiration_time = time.time() + config['cache_time']
    rec = Record(expiration_time, value)
    _cache[key] = rec


def get_stats():
    return copy.copy(stats)


@contextlib.contextmanager
def maybe_bust(bust_or_not):
    previous_state = config['ignore_cache']
    config['ignore_cache'] = bust_or_not
    yield
    config['ignore_cache'] = previous_state


def cached(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        now = time.time()
        # To avoid duplicate healthchecks for one instance advertised on multiple namespaces,
        # drop the first positional arg, which is service name, from the cache key.
        # That leaves port, which still uniquely identifies an instance, and path.
        # But only drop service name from cache key if we don't pass it in the request header,
        # since there may be dynamic checking behavior.
        key = tuple([func.__name__, args if configuration.config.get('service_name_header') else args[1:]])
        try:
            response = getv(key, now)
        except KeyError:
            response = func(*args, **kwargs)
            setv(key, response)
        return response
    return wrapper
