#!/usr/bin/env python3
"""Send GitHub Copilot Statuspage health as a Dynatrace custom metric."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("copilot_status_to_dynatrace")

DEFAULT_GITHUB_STATUS_URL = "https://www.githubstatus.com/api/v2/components.json"

DYNATRACE_ENVIRONMENTS = {
    "dev": "https://fzu06327.live.dynatrace.com/api/v2/metrics/ingest",
    "pre-prod": "https://ezd05500.live.dynatrace.com/api/v2/metrics/ingest",
    "prod-a": "https://vpx74458.live.dynatrace.com/api/v2/metrics/ingest",
}
DEFAULT_DYNATRACE_ENVIRONMENT = "prod-a"
DEFAULT_DYNATRACE_METRICS_INGEST_URL = DYNATRACE_ENVIRONMENTS[DEFAULT_DYNATRACE_ENVIRONMENT]
DEFAULT_COMPONENT_NAME = "Copilot"
# Metric key follows Ford's standard EAMS ID convention:
# ford.ingest.i<EAMS_ID>.<your-metric-name>
DEFAULT_METRIC_KEY = "ford.ingest.i57079.github.copilot.status"
# Dynatrace metadata for the metric (display name).
DEFAULT_METRIC_DISPLAY_NAME = "GitHub Copilot status"

STATUS_TO_METRIC_VALUE = {
    # TEMP: sending 0 instead of 1 for operational
    "operational": 1,
    "degraded_performance": 2,
    "partial_outage": 2,
    "major_outage": 6,
}


@dataclass(frozen=True)
class ComponentStatus:
    id: str
    name: str
    status: str
    updated_at: str | None


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def fetch_component_status(status_url: str, component_name: str) -> ComponentStatus:
    logger.info("Fetching GitHub status from %s", status_url)
    request = Request(status_url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))

    total_components = len(payload.get("components", []))
    logger.debug("Received %d components from GitHub status page", total_components)

    component = next(
        (
            item
            for item in payload.get("components", [])
            if item.get("name", "").casefold() == component_name.casefold()
        ),
        None,
    )

    if not component:
        logger.error("Component '%s' not found among %d components", component_name, total_components)
        raise LookupError(f"Component not found in GitHub Status response: {component_name}")

    resolved = ComponentStatus(
        id=str(component.get("id", "unknown")),
        name=str(component.get("name", component_name)),
        status=str(component.get("status", "unknown")),
        updated_at=component.get("updated_at"),
    )
    logger.info(
        "Resolved component '%s' (id=%s) status=%s updated_at=%s",
        resolved.name,
        resolved.id,
        resolved.status,
        resolved.updated_at,
    )
    return resolved


def map_status_to_metric_value(status: str) -> float:
    value = STATUS_TO_METRIC_VALUE.get(status.lower(), 0.0)
    if status.lower() not in STATUS_TO_METRIC_VALUE:
        logger.warning("Unknown status '%s'; defaulting metric value to %s", status, value)
    return value


def escape_dimension_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_metric_line(component: ComponentStatus, metric_key: str, timestamp_ms: int) -> str:
    metric_value = map_status_to_metric_value(component.status)
    value_text = f"{metric_value:g}"
    dimensions = {
        "component": component.name,
        "component_id": component.id,
        "status_text": component.status,
        "source": "github-statuspage",
    }
    dimension_text = ",".join(
        f'{key}="{escape_dimension_value(value)}"' for key, value in dimensions.items()
    )
    return f"{metric_key},{dimension_text} {value_text} {timestamp_ms}"


def build_metadata_line(metric_key: str, display_name: str) -> str:
    metadata = {
        "dt.meta.displayName": display_name,
        "dt.meta.unit": "Unspecified",
    }
    metadata_text = ",".join(
        f'{key}="{escape_dimension_value(value)}"' for key, value in metadata.items()
    )
    return f"#{metric_key} gauge {metadata_text}"


def send_metric_to_dynatrace(ingest_url: str, api_token: str, metric_line: str) -> tuple[int, str]:
    headers = {
        "Authorization": f"Api-Token {api_token}",
        "Content-Type": "text/plain; charset=utf-8",
    }
    request = Request(
        ingest_url,
        data=metric_line.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    logger.info("Sending metric payload to Dynatrace at %s", ingest_url)
    with urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
        logger.info("Dynatrace responded with HTTP %s", response.status)
        logger.debug("Dynatrace response body: %s", body)
        return response.status, body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send GitHub Copilot component status to Dynatrace as a custom metric."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the metric line without sending it to Dynatrace.",
    )
    parser.add_argument(
        "--environment",
        choices=sorted(DYNATRACE_ENVIRONMENTS),
        default=os.getenv("DYNATRACE_ENVIRONMENT", DEFAULT_DYNATRACE_ENVIRONMENT),
        help="Target Dynatrace environment (dev, pre-prod, prod-a).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity (default: INFO, or LOG_LEVEL env var).",
    )
    return parser.parse_args()


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    github_status_url = os.getenv("GITHUB_STATUS_URL", DEFAULT_GITHUB_STATUS_URL)
    component_name = os.getenv("GITHUB_STATUS_COMPONENT_NAME", DEFAULT_COMPONENT_NAME)
    metric_key = os.getenv("DYNATRACE_METRIC_KEY", DEFAULT_METRIC_KEY)
    metric_display_name = os.getenv("DYNATRACE_METRIC_DISPLAY_NAME", DEFAULT_METRIC_DISPLAY_NAME)

    logger.info(
        "Starting run: environment=%s component=%s metric_key=%s",
        args.environment,
        component_name,
        metric_key,
    )

    try:
        component = fetch_component_status(github_status_url, component_name)
        metric_line = build_metric_line(component, metric_key, int(time.time() * 1000))
        metadata_line = build_metadata_line(metric_key, metric_display_name)
        payload = f"{metadata_line}\n{metric_line}"
        logger.debug("Built payload:\n%s", payload)

        if args.dry_run:
            logger.info("Dry-run enabled; not sending to Dynatrace")
            print(payload)
            return 0

        dynatrace_ingest_url = os.getenv(
            "DYNATRACE_METRICS_INGEST_URL",
            DYNATRACE_ENVIRONMENTS[args.environment],
        )
        dynatrace_api_token = get_required_env("DYNATRACE_API_TOKEN")
        status_code, response_body = send_metric_to_dynatrace(
            dynatrace_ingest_url, dynatrace_api_token, payload
        )
        logger.info("Sent %s for %s: %s", metric_key, component.name, component.status)
        logger.info("Ingest URL: %s", dynatrace_ingest_url)
        logger.info("Payload sent:\n%s", payload)
        logger.info("Dynatrace API response (%s): %s", status_code, response_body)
        return 0
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace") or str(error)
        logger.error("HTTP error (%s): %s", error.code, details)
        return 1
    except URLError as error:
        logger.error("Network error: %s", error.reason)
        return 1
    except Exception:
        logger.exception("Unexpected error while sending metric")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

