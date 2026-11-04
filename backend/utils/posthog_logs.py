"""Scoped OpenTelemetry log export for purpose-written PostHog log lines."""

from __future__ import annotations

import logging
from typing import Any

POSTHOG_LOGGER_NAME = "duct.posthog"
SERVICE_NAME = "duct-backend"

# This logger is intentionally isolated from the application's existing logging
# namespaces. Only the purpose-written lines in this integration reach PostHog.
posthog_log_logger = logging.getLogger(POSTHOG_LOGGER_NAME)


def configure_posthog_logs(
    *, host: str, project_token: str, environment: str = ""
) -> Any | None:
    """Attach an OTLP exporter only to ``posthog_log_logger``.

    The exporter is deliberately independent of the tracing provider, which
    preserves the pre-existing agent tracing configuration and prevents the
    application's existing logs from being exported.
    """
    if not host or not project_token:
        return None

    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        logging.getLogger(__name__).warning(
            "posthog logs: OpenTelemetry log exporter is unavailable; log export is disabled"
        )
        return None

    resource_attributes = {"service.name": SERVICE_NAME}
    if environment:
        resource_attributes["deployment.environment"] = environment
    provider = LoggerProvider(resource=Resource.create(resource_attributes))
    exporter = OTLPLogExporter(
        endpoint=f"{host.rstrip('/')}/i/v1/logs",
        headers={"Authorization": f"Bearer {project_token}"},
    )
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    posthog_log_logger.setLevel(logging.INFO)
    posthog_log_logger.addHandler(LoggingHandler(logger_provider=provider))
    posthog_log_logger.propagate = False
    return provider
