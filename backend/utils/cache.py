import hashlib
import time

class SimpleCache:
    def __init__(self, ttl=10):
        self._cache = {}
        self.ttl = ttl

    def _hash(self, data):
        return hashlib.md5(data.encode()).hexdigest()[:16]

    def get(self, key):
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry['timestamp'] > self.ttl:
            del self._cache[key]
            return None
        return entry['value']

    def set(self, key, value):
        self._cache[key] = {
            'value': value,
            'timestamp': time.time()
        }

    def make_key(self, image_b64, action):
        return f"{action}_{self._hash(image_b64)}"

    def clear(self):
        self._cache = {}

    def size(self):
        return len(self._cache)

cache = SimpleCache(ttl=10)