"""OpenTelemetry instrumentation setup — distributed tracing across API, workers, and DB."""

import logging

from orchestrix.config import settings

logger = logging.getLogger(__name__)


def setup_telemetry(service_name: str = "orchestrix") -> None:
    """Initialize OpenTelemetry with OTLP exporter if enabled."""
    if not settings.otel_enabled:
        logger.info("OpenTelemetry disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_endpoint,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Auto-instrument SQLAlchemy
        from orchestrix.database import engine
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

        logger.info(
            "OpenTelemetry initialized (service=%s, endpoint=%s)",
            service_name,
            settings.otel_exporter_endpoint,
        )
    except ImportError as e:
        logger.warning("OpenTelemetry packages not installed: %s", e)
    except Exception as e:
        logger.error("Failed to initialize OpenTelemetry: %s", e)


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI app with OpenTelemetry (call after setup_telemetry)."""
    if not settings.otel_enabled:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumented with OpenTelemetry")
    except ImportError:
        pass
    except Exception as e:
        logger.error("Failed to instrument FastAPI: %s", e)


def get_tracer(name: str = "orchestrix"):
    """Get an OpenTelemetry tracer for manual span creation."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None
