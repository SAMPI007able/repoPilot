import unittest

from redis.exceptions import RedisError

from app.services.ai_response_cache_service import AIResponseCacheService


class UnavailableRedis:
    def get(self, _key):
        raise RedisError("offline")

    def setex(self, _key, _ttl, _value):
        raise RedisError("offline")


class AIResponseCacheTests(unittest.TestCase):
    def test_falls_back_to_bounded_process_cache(self):
        cache = AIResponseCacheService(redis_client=UnavailableRedis())
        key = cache.key("user", "workspace", "chat", "prompt")

        cache.set(key, "cached answer")

        self.assertEqual(cache.get(key), "cached answer")
        self.assertNotEqual(key, cache.key("other-user", "workspace", "chat", "prompt"))


if __name__ == "__main__":
    unittest.main()
