"""Configurable retry policies — fixed, linear, exponential backoff per job type."""

from enum import Enum

from orchestrix.config import settings


class RetryStrategy(str, Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class RetryPolicy:
    """Configurable retry policy for a job type."""

    def __init__(
        self,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        base_delay: float | None = None,
        max_delay: float | None = None,
        multiplier: float = 2.0,
    ):
        self.strategy = strategy
        self.base_delay = base_delay or settings.retry_base_delay_seconds
        self.max_delay = max_delay or settings.retry_max_delay_seconds
        self.multiplier = multiplier

    def compute_delay(self, attempt: int) -> float:
        """Compute the delay in seconds before the next retry.

        `attempt` is 1-based (first failure = attempt 1).
        """
        if self.strategy == RetryStrategy.FIXED:
            delay = self.base_delay
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (self.multiplier ** (attempt - 1))
        else:
            delay = self.base_delay

        return min(delay, self.max_delay)


# ── Registry: job_type -> RetryPolicy ──

_POLICIES: dict[str, RetryPolicy] = {}

# Default policy (exponential backoff)
DEFAULT_POLICY = RetryPolicy(strategy=RetryStrategy.EXPONENTIAL)


def register_retry_policy(job_type: str, policy: RetryPolicy) -> None:
    """Register a custom retry policy for a specific job type."""
    _POLICIES[job_type] = policy


def get_retry_policy(job_type: str) -> RetryPolicy:
    """Get the retry policy for a job type (falls back to default)."""
    return _POLICIES.get(job_type, DEFAULT_POLICY)


# ── Pre-configured policies for demo handlers ──

register_retry_policy("email.send", RetryPolicy(
    strategy=RetryStrategy.EXPONENTIAL, base_delay=5.0, max_delay=120.0,
))
register_retry_policy("data.process", RetryPolicy(
    strategy=RetryStrategy.LINEAR, base_delay=10.0, max_delay=300.0,
))
register_retry_policy("report.generate", RetryPolicy(
    strategy=RetryStrategy.FIXED, base_delay=30.0, max_delay=30.0,
))
register_retry_policy("chaos.random", RetryPolicy(
    strategy=RetryStrategy.EXPONENTIAL, base_delay=2.0, max_delay=60.0, multiplier=3.0,
))
