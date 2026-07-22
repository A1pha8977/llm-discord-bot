"""Fixed-window rate limiter with request count and token tracking.

Usage::

    limiter = RateLimiter(max_requests=50, max_tokens=100000, window_seconds=3600)

    # Before each API call
    result = await limiter.check_request()
    if not result.allowed:
        # Inform user
        return

    # After a successful call
    await limiter.deduct_tokens(actual_total_tokens)
"""

import asyncio
import logging
import time
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """Result of a rate limit check.

    Attributes:
        allowed: ``True`` when the request may proceed.
        retry_after_seconds: Seconds to wait before retrying
            (0 when ``allowed`` is ``True``).
        reason: ``"requests"``, ``"tokens"``, or ``None`` when allowed.
    """

    allowed: bool
    retry_after_seconds: float = 0.0
    reason: str | None = None
    limit_value: int = 0
    window_seconds: float = 0.0


class RateLimiter:
    """Fixed-window rate limiter supporting request count and token tracking.

    Two independent dimensions:

    - **Request count**: limits the number of API calls per time window.
    - **Token count**: limits cumulative token usage per time window.
      The request that pushes over the limit is allowed; subsequent
      requests are blocked until the window resets.

    Set a dimension to 0 to disable it.  At least one dimension must
    be non-zero or a warning is logged.

    Thread-safe via ``asyncio.Lock``.

    Args:
        max_requests: Max API calls per window (0 = unlimited).
        max_tokens: Max cumulative tokens per window (0 = unlimited).
        window_seconds: Length of the time window in seconds.
        label: Optional label used in log messages (e.g. ``"global"``).
    """

    def __init__(
        self,
        max_requests: int = 0,
        max_tokens: int = 0,
        window_seconds: float = 3600.0,
        label: str = "",
    ):
        if max_requests < 0:
            raise ValueError("max_requests must be >= 0")
        if max_tokens < 0:
            raise ValueError("max_tokens must be >= 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if max_requests == 0 and max_tokens == 0:
            _logger.warning(
                "RateLimiter(%s): both max_requests=0 and max_tokens=0 — no limiting",
                label,
            )

        self._max_requests = max_requests
        self._max_tokens = max_tokens
        self._window = window_seconds
        self._label = label

        self._req_count = 0
        self._tok_count = 0
        self._window_start = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_request(self) -> RateLimitResult:
        """Check and record one request slot.

        - Request dimension: denies when ``count >= max_requests``.
        - Token dimension: denies when ``cumulative_tokens >= max_tokens``.
          (The request that pushes over the limit is still allowed.)

        Returns:
            A ``RateLimitResult`` — check ``.allowed`` to proceed.
        """
        async with self._lock:
            now = time.monotonic()
            self._refresh(now)

            # Request dimension check
            if self._max_requests > 0 and self._req_count >= self._max_requests:
                retry_after = self._window_start + self._window - now
                _logger.warning(
                    "RateLimiter(%s) denied (requests %d/%d), retry in %.0fs",
                    self._label,
                    self._req_count,
                    self._max_requests,
                    retry_after,
                )
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    reason="requests",
                    limit_value=self._max_requests,
                    window_seconds=self._window,
                )

            # Token dimension check
            if self._max_tokens > 0 and self._tok_count >= self._max_tokens:
                retry_after = self._window_start + self._window - now
                _logger.warning(
                    "RateLimiter(%s) denied (tokens %d/%d), retry in %.0fs",
                    self._label,
                    self._tok_count,
                    self._max_tokens,
                    retry_after,
                )
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    reason="tokens",
                    limit_value=self._max_tokens,
                    window_seconds=self._window,
                )

            # Consume one request slot
            self._req_count += 1
            return RateLimitResult(allowed=True)

    async def deduct_tokens(self, actual: int) -> None:
        """Record token usage after a successful API call.

        Args:
            actual: Total tokens consumed by the completed request
                (``TokenUsage.total_tokens`` from the API response).
        """
        if actual <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            self._refresh(now)
            old = self._tok_count
            self._tok_count += actual
            _logger.debug(
                "RateLimiter(%s) tokens %d -> %d (added %d)",
                self._label,
                old,
                self._tok_count,
                actual,
            )

    async def is_limited(self) -> bool:
        """Check whether any dimension is currently at its limit."""
        async with self._lock:
            now = time.monotonic()
            self._refresh(now)
            if self._max_requests > 0 and self._req_count >= self._max_requests:
                return True
            if self._max_tokens > 0 and self._tok_count >= self._max_tokens:
                return True
            return False

    async def get_request_count(self) -> int:
        """Return the number of requests consumed in the current window.

        Acquires the internal lock to ensure a consistent read.
        """
        async with self._lock:
            self._refresh(time.monotonic())
            return self._req_count

    async def get_token_count(self) -> int:
        """Return the cumulative tokens consumed in the current window.

        Acquires the internal lock to ensure a consistent read.
        """
        async with self._lock:
            self._refresh(time.monotonic())
            return self._tok_count

    @property
    def label(self) -> str:
        """Human-readable label for this limiter."""
        return self._label

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh(self, now: float) -> None:
        """Reset counters if the window has expired."""
        if now - self._window_start >= self._window:
            _logger.debug(
                "RateLimiter(%s) window reset (was %d req, %d tokens)",
                self._label,
                self._req_count,
                self._tok_count,
            )
            self._req_count = 0
            self._tok_count = 0
            self._window_start = now
