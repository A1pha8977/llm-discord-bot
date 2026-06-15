"""Unit tests for RateLimiter."""

import asyncio
import unittest

from services.rate_limiter import RateLimiter


class TestRateLimiter(unittest.IsolatedAsyncioTestCase):
    """Tests for the fixed-window rate limiter."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_defaults_no_limiting(self):
        """Both dimensions zero -> no limiting (warning logged)."""
        limiter = RateLimiter(max_requests=0, max_tokens=0, label="noop")
        self.assertEqual(limiter.label, "noop")

    def test_invalid_max_requests(self):
        with self.assertRaises(ValueError):
            RateLimiter(max_requests=-1)

    def test_invalid_max_tokens(self):
        with self.assertRaises(ValueError):
            RateLimiter(max_tokens=-1)

    def test_invalid_window(self):
        with self.assertRaises(ValueError):
            RateLimiter(window_seconds=0)
        with self.assertRaises(ValueError):
            RateLimiter(window_seconds=-1)

    # ------------------------------------------------------------------
    # Request dimension
    # ------------------------------------------------------------------

    async def test_request_allowed_under_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            result = await limiter.check_request()
            self.assertTrue(result.allowed)

    async def test_request_denied_at_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            await limiter.check_request()
        result = await limiter.check_request()
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "requests")
        self.assertGreater(result.retry_after_seconds, 0)

    async def test_request_resets_after_window(self):
        limiter = RateLimiter(max_requests=1, window_seconds=0.1)
        r1 = await limiter.check_request()
        self.assertTrue(r1.allowed)

        await asyncio.sleep(0.15)
        r2 = await limiter.check_request()
        self.assertTrue(r2.allowed)

    # ------------------------------------------------------------------
    # Token dimension
    # ------------------------------------------------------------------

    async def test_token_allowed_under_limit(self):
        limiter = RateLimiter(max_tokens=100, window_seconds=60)
        result = await limiter.check_request()
        self.assertTrue(result.allowed)

        await limiter.deduct_tokens(60)
        result = await limiter.check_request()
        self.assertTrue(result.allowed)

    async def test_token_denied_when_exceeded(self):
        limiter = RateLimiter(max_tokens=100, window_seconds=60)
        await limiter.check_request()
        await limiter.deduct_tokens(100)

        result = await limiter.check_request()
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "tokens")

    async def test_token_allows_over_limit_once(self):
        """The request that pushes over the limit is still allowed."""
        limiter = RateLimiter(max_tokens=50, window_seconds=60)
        await limiter.check_request()
        await limiter.deduct_tokens(49)  # 49 < 50

        r1 = await limiter.check_request()
        self.assertTrue(r1.allowed)  # still 49 < 50
        await limiter.deduct_tokens(10)  # now 59 >= 50

        r2 = await limiter.check_request()
        self.assertFalse(r2.allowed)  # 59 >= 50
        self.assertEqual(r2.reason, "tokens")

    async def test_token_resets_after_window(self):
        limiter = RateLimiter(max_tokens=50, window_seconds=0.1)
        await limiter.check_request()
        await limiter.deduct_tokens(50)

        await asyncio.sleep(0.15)
        result = await limiter.check_request()
        self.assertTrue(result.allowed)

    # ------------------------------------------------------------------
    # Both dimensions
    # ------------------------------------------------------------------

    async def test_requests_checked_before_tokens(self):
        """When both dimensions exceed, request reason is returned first."""
        limiter = RateLimiter(max_requests=1, max_tokens=1, window_seconds=60)
        await limiter.check_request()
        await limiter.deduct_tokens(100)  # exceed tokens

        # Next check: requests already at limit (1)
        result = await limiter.check_request()
        self.assertEqual(result.reason, "requests")

    async def test_tokens_reason_when_only_tokens_exceed(self):
        limiter = RateLimiter(max_requests=5, max_tokens=50, window_seconds=60)
        await limiter.check_request()
        await limiter.deduct_tokens(51)

        result = await limiter.check_request()
        self.assertEqual(result.reason, "tokens")

    # ------------------------------------------------------------------
    # is_limited
    # ------------------------------------------------------------------

    async def test_is_limited_requests(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        self.assertFalse(await limiter.is_limited())
        await limiter.check_request()
        self.assertFalse(await limiter.is_limited())
        await limiter.check_request()
        self.assertTrue(await limiter.is_limited())

    async def test_is_limited_tokens(self):
        limiter = RateLimiter(max_tokens=100, window_seconds=60)
        self.assertFalse(await limiter.is_limited())
        await limiter.check_request()
        await limiter.deduct_tokens(100)
        self.assertTrue(await limiter.is_limited())

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    async def test_counters(self):
        limiter = RateLimiter(max_requests=5, max_tokens=1000, window_seconds=60)
        self.assertEqual(await limiter.get_request_count(), 0)
        self.assertEqual(await limiter.get_token_count(), 0)
        self.assertEqual(limiter.label, "")

        await limiter.check_request()
        self.assertEqual(await limiter.get_request_count(), 1)

        await limiter.deduct_tokens(500)
        self.assertEqual(await limiter.get_token_count(), 500)


if __name__ == "__main__":
    unittest.main()
