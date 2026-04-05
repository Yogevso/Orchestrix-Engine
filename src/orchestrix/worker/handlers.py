"""Built-in task handlers for demo/testing purposes."""

import asyncio
import logging
import random

logger = logging.getLogger(__name__)

# Registry of task handlers keyed by job type
HANDLERS: dict[str, callable] = {}


def register(job_type: str):
    """Decorator to register a handler for a job type."""
    def decorator(func):
        HANDLERS[job_type] = func
        return func
    return decorator


@register("email.send")
async def handle_email_send(payload: dict) -> dict:
    logger.info("Sending email to %s: %s", payload.get("to"), payload.get("subject"))
    await asyncio.sleep(random.uniform(0.5, 2.0))
    return {"sent": True, "to": payload.get("to")}


@register("data.process")
async def handle_data_process(payload: dict) -> dict:
    logger.info("Processing data: %s", payload.get("source", "unknown"))
    await asyncio.sleep(random.uniform(1.0, 3.0))
    return {"processed": True, "records": random.randint(100, 10000)}


@register("report.generate")
async def handle_report_generate(payload: dict) -> dict:
    logger.info("Generating report: %s", payload.get("report_type", "unknown"))
    await asyncio.sleep(random.uniform(2.0, 5.0))
    return {"generated": True}


@register("chaos.fail")
async def handle_chaos_fail(payload: dict) -> dict:
    """Always fails — useful for testing retries and dead-letter."""
    raise RuntimeError(f"Chaos failure: {payload.get('reason', 'simulated crash')}")


@register("chaos.slow")
async def handle_chaos_slow(payload: dict) -> dict:
    """Takes a very long time — useful for testing lease expiry."""
    duration = payload.get("duration", 120)
    logger.info("Chaos slow task: sleeping %ss", duration)
    await asyncio.sleep(duration)
    return {"survived": True}


@register("chaos.random")
async def handle_chaos_random(payload: dict) -> dict:
    """Randomly succeeds or fails — useful for retry demos."""
    if random.random() < payload.get("fail_rate", 0.5):
        raise RuntimeError("Random chaos failure")
    await asyncio.sleep(random.uniform(0.5, 1.5))
    return {"lucky": True}
