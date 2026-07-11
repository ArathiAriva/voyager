"""Optional Phoenix (OpenInference) tracing.

Enabled when PHOENIX_COLLECTOR_ENDPOINT is set, e.g.:

    PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces

Instruments both LLM paths:
  - OpenAI client (single-agent loop, memory extraction, eval judge)
  - LangChain/LangGraph (multi-agent planning graph)

If Phoenix or the instrumentors aren't installed, or the env var is unset,
this is a no-op — the app runs exactly as before.
"""
import logging
import os

logger = logging.getLogger("voyager.observability")


def setup_tracing() -> bool:
    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    if not endpoint:
        logger.info("observability | PHOENIX_COLLECTOR_ENDPOINT not set; tracing disabled")
        return False
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from openinference.instrumentation.openai import OpenAIInstrumentor
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as e:
        logger.warning("observability | tracing deps missing (%s); tracing disabled", e)
        return False

    provider = TracerProvider(
        resource=Resource.create({"service.name": os.environ.get("PHOENIX_PROJECT_NAME", "voyager")})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    OpenAIInstrumentor().instrument(tracer_provider=provider)
    LangChainInstrumentor().instrument(tracer_provider=provider)

    logger.info("observability | Phoenix tracing enabled -> %s", endpoint)
    return True
