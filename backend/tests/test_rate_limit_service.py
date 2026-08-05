import fnmatch
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from app.config.rate_limit_settings import RateLimitPolicy, RateLimitSettings
from app.services.rate_limit_service import RateLimitService


class MutableClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeRedis:
    """Thread-safe Redis script double; no external Redis server is required."""

    def __init__(self, clock: MutableClock) -> None:
        self.clock = clock
        self.values: dict[str, int] = {}
        self.expiry: dict[str, int] = {}
        self.sets: dict[str, set[str]] = {}
        self.lock = threading.Lock()

    def register_script(self, script):
        def execute(*, keys, args):
            with self.lock:
                self._expire()
                key = keys[0]
                if "testforge:rate-limit" in script:
                    limit, reset_at = int(args[0]), int(args[1])
                    current = self.values.get(key, 0)
                    if current >= limit:
                        return [0, current]
                    current += 1
                    self.values[key] = current
                    self.expiry[key] = reset_at
                    return [1, current]
                if "testforge:concurrency-acquire" in script:
                    limit, resource_id, ttl = int(args[0]), str(args[1]), int(args[2])
                    members = self.sets.setdefault(key, set())
                    if resource_id in members:
                        return [1, len(members), 1]
                    if len(members) >= limit:
                        return [0, len(members), 0]
                    members.add(resource_id)
                    self.expiry[key] = int(self.clock()) + ttl
                    return [1, len(members), 0]
                if "testforge:concurrency-release" in script:
                    members = self.sets.get(key, set())
                    removed = int(str(args[0]) in members)
                    members.discard(str(args[0]))
                    if not members:
                        self.sets.pop(key, None)
                        self.expiry.pop(key, None)
                    return removed
                if "testforge:concurrency-replace" in script:
                    members = self.sets.setdefault(key, set())
                    members.discard(str(args[0]))
                    members.add(str(args[1]))
                    self.expiry[key] = int(self.clock()) + int(args[2])
                    return len(members)
                if "testforge:concurrency-reconcile" in script:
                    resource_ids = {str(value) for value in args[1:]}
                    if resource_ids:
                        self.sets[key] = resource_ids
                        self.expiry[key] = int(self.clock()) + int(args[0])
                    else:
                        self.sets.pop(key, None)
                        self.expiry.pop(key, None)
                    return len(resource_ids)
                raise AssertionError("Unknown script")
        return execute

    def scan_iter(self, match, count=100):
        del count
        with self.lock:
            self._expire()
            return iter([key for key in [*self.values, *self.sets] if fnmatch.fnmatch(key, match)])

    def scard(self, key):
        with self.lock:
            self._expire()
            return len(self.sets.get(key, set()))

    def delete(self, *keys):
        with self.lock:
            for key in keys:
                self.values.pop(key, None)
                self.sets.pop(key, None)
                self.expiry.pop(key, None)

    def _expire(self):
        for key, expires_at in list(self.expiry.items()):
            if expires_at <= int(self.clock()):
                self.values.pop(key, None)
                self.sets.pop(key, None)
                self.expiry.pop(key, None)


def settings() -> RateLimitSettings:
    return RateLimitSettings(
        enabled=True,
        environment="test",
        redis_url="redis://unused",
        policies={"test": RateLimitPolicy(2, 60)},
        active_previews_per_user=1,
        active_browser_sessions_per_user=1,
        concurrency_ttl_seconds=120,
    )


class RateLimitServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()
        self.redis = FakeRedis(self.clock)
        self.service = RateLimitService(settings(), self.redis, self.clock)

    def test_allowed_rejected_remaining_and_reset(self) -> None:
        first = self.service.check_and_consume("user", "ai", 2, 60)
        second = self.service.check_and_consume("user", "ai", 2, 60)
        rejected = self.service.check_and_consume("user", "ai", 2, 60)
        self.assertTrue(first.allowed)
        self.assertEqual(first.remaining, 1)
        self.assertTrue(second.allowed)
        self.assertEqual(second.remaining, 0)
        self.assertFalse(rejected.allowed)
        self.assertEqual(rejected.current, 2)
        self.assertEqual(int(rejected.reset_at.timestamp()), 120)

    def test_counter_expires_at_next_window(self) -> None:
        self.service.check_and_consume("user", "ai", 1, 60)
        self.assertFalse(self.service.check_and_consume("user", "ai", 1, 60).allowed)
        self.clock.value = 120
        self.assertTrue(self.service.check_and_consume("user", "ai", 1, 60).allowed)

    def test_users_and_actions_have_independent_counters(self) -> None:
        self.service.check_and_consume("one", "chat", 1, 60)
        self.assertTrue(self.service.check_and_consume("two", "chat", 1, 60).allowed)
        self.assertTrue(self.service.check_and_consume("one", "generation", 1, 60).allowed)

    def test_concurrent_requests_cannot_exceed_limit(self) -> None:
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(
                lambda _: self.service.check_and_consume("user", "generation", 5, 60).allowed,
                range(20),
            ))
        self.assertEqual(sum(results), 5)

    def test_preview_acquire_reject_and_idempotent_release(self) -> None:
        acquired = self.service.acquire_concurrency_slot("user", "preview", 1, "preview-one")
        rejected = self.service.acquire_concurrency_slot("user", "preview", 1, "preview-two")
        self.assertTrue(acquired.allowed)
        self.assertFalse(rejected.allowed)
        self.assertEqual(rejected.active, 1)
        self.service.release_concurrency_slot("user", "preview", "preview-one")
        self.service.release_concurrency_slot("user", "preview", "preview-one")
        self.assertTrue(self.service.acquire_concurrency_slot("user", "preview", 1, "preview-two").allowed)

    def test_failed_creation_releases_reserved_slot(self) -> None:
        self.service.acquire_concurrency_slot("user", "preview", 1, "reservation")
        try:
            raise RuntimeError("creation failed")
        except RuntimeError:
            self.service.release_concurrency_slot("user", "preview", "reservation")
        self.assertTrue(self.service.acquire_concurrency_slot("user", "preview", 1, "next").allowed)

    def test_reconcile_and_admin_clear_remove_stale_entries(self) -> None:
        self.service.acquire_concurrency_slot("user", "preview", 2, "stale")
        self.assertEqual(self.service.reconcile_concurrency("user", "preview", ["active"]), 1)
        self.service.check_and_consume("user", "ai", 2, 60)
        result = self.service.clear_user("user")
        self.assertEqual(result.request_keys_removed, 1)
        self.assertEqual(result.concurrency_entries_removed, 1)


if __name__ == "__main__":
    unittest.main()
