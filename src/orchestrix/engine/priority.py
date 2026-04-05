"""Weighted fair scheduling — distributes poll slots across priority bands within a queue."""

import random
from collections import defaultdict


def weighted_queue_selection(queues: list[str], weights: dict[str, int] | None = None) -> list[str]:
    """Sort queues by weighted priority for polling order.

    Each queue has a weight (default 1). Higher weight = more poll slots.
    Uses weighted random selection to prevent starvation.
    """
    if not queues:
        return []
    if not weights:
        return queues

    weighted_list = []
    for q in queues:
        w = weights.get(q, 1)
        weighted_list.extend([q] * w)

    random.shuffle(weighted_list)
    # Deduplicate while preserving weighted order
    seen = set()
    result = []
    for q in weighted_list:
        if q not in seen:
            seen.add(q)
            result.append(q)
    return result


class PriorityBandScheduler:
    """Groups jobs into priority bands and allocates poll capacity proportionally.

    Bands:
      - critical: priority >= 100
      - high: priority >= 50
      - normal: priority >= 10
      - low: priority < 10

    Band weights determine what fraction of poll cycles each band gets.
    """

    BANDS = [
        ("critical", 100, 8),  # name, min_priority, weight
        ("high", 50, 4),
        ("normal", 10, 2),
        ("low", 0, 1),
    ]

    @classmethod
    def select_priority_range(cls) -> tuple[int, int | None]:
        """Weighted random selection of a priority band for the next poll.

        Returns (min_priority, max_priority_exclusive_or_None).
        """
        total_weight = sum(w for _, _, w in cls.BANDS)
        r = random.uniform(0, total_weight)
        cumulative = 0
        for i, (name, min_p, weight) in enumerate(cls.BANDS):
            cumulative += weight
            if r <= cumulative:
                max_p = cls.BANDS[i - 1][1] if i > 0 else None
                return (min_p, max_p)
        # Fallback
        return (0, None)
