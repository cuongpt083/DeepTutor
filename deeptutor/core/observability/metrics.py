"""Prometheus metrics definitions and safe recording functions."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = None
    Histogram = None

if PROMETHEUS_AVAILABLE:
    # Turn level
    TURN_DURATION = Histogram(
        "deeptutor_turn_duration_seconds",
        "End-to-end conversation turn duration in seconds",
        ["capability", "status"],
        buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
    )

    # Tool execution
    TOOL_DURATION = Histogram(
        "deeptutor_tool_execution_duration_seconds",
        "Tool execution duration in seconds",
        ["tool_name", "status"],
        buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0],
    )

    # RAG search overall
    RAG_SEARCH_DURATION = Histogram(
        "deeptutor_rag_search_duration_seconds",
        "RAG service search duration in seconds",
        ["provider", "mode", "status"],
        buckets=[0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 60.0],
    )

    # Remote LightRAG client request RTT
    LIGHTRAG_REMOTE_REQUEST_DURATION = Histogram(
        "deeptutor_lightrag_remote_request_duration_seconds",
        "Total HTTP round-trip time for remote LightRAG query in seconds",
        ["endpoint", "mode", "status_code"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
    )

    # Remote LightRAG server-reported processing time
    LIGHTRAG_SERVER_REPORTED_DURATION = Histogram(
        "deeptutor_lightrag_server_reported_duration_seconds",
        "Processing time reported inside LightRAG response payload in seconds",
        ["mode"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
    )

    # Inferred network overhead
    LIGHTRAG_NETWORK_LATENCY = Histogram(
        "deeptutor_lightrag_network_latency_seconds",
        "Inferred network transfer and serialization latency in seconds (client RTT - server reported)",
        ["mode"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    # Payload bytes
    LIGHTRAG_PAYLOAD_BYTES = Histogram(
        "deeptutor_lightrag_payload_bytes",
        "Payload size of requests and responses exchanged with LightRAG in bytes",
        ["direction", "mode"],
        buckets=[128, 512, 1024, 4096, 16384, 65536, 262144, 1048576],
    )
else:
    TURN_DURATION = None
    TOOL_DURATION = None
    RAG_SEARCH_DURATION = None
    LIGHTRAG_REMOTE_REQUEST_DURATION = None
    LIGHTRAG_SERVER_REPORTED_DURATION = None
    LIGHTRAG_NETWORK_LATENCY = None
    LIGHTRAG_PAYLOAD_BYTES = None


def record_remote_request(endpoint: str, mode: str, status_code: str, duration: float) -> None:
    if not PROMETHEUS_AVAILABLE or LIGHTRAG_REMOTE_REQUEST_DURATION is None:
        return
    try:
        LIGHTRAG_REMOTE_REQUEST_DURATION.labels(
            endpoint=str(endpoint or "/query"),
            mode=str(mode or "default"),
            status_code=str(status_code or "unknown"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record remote request metric: {exc}")


def record_server_reported(mode: str, duration: float) -> None:
    if not PROMETHEUS_AVAILABLE or LIGHTRAG_SERVER_REPORTED_DURATION is None:
        return
    try:
        LIGHTRAG_SERVER_REPORTED_DURATION.labels(
            mode=str(mode or "default"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record server reported metric: {exc}")


def record_network_latency(mode: str, duration: float) -> None:
    if not PROMETHEUS_AVAILABLE or LIGHTRAG_NETWORK_LATENCY is None:
        return
    try:
        LIGHTRAG_NETWORK_LATENCY.labels(
            mode=str(mode or "default"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record network latency metric: {exc}")


def record_payload_bytes(direction: str, mode: str, num_bytes: int) -> None:
    if not PROMETHEUS_AVAILABLE or LIGHTRAG_PAYLOAD_BYTES is None:
        return
    try:
        LIGHTRAG_PAYLOAD_BYTES.labels(
            direction=str(direction),
            mode=str(mode or "default"),
        ).observe(max(0.0, float(num_bytes)))
    except Exception as exc:
        logger.debug(f"Failed to record payload bytes metric: {exc}")


def record_rag_search(provider: str, mode: str, status: str, duration: float) -> None:
    if not PROMETHEUS_AVAILABLE or RAG_SEARCH_DURATION is None:
        return
    try:
        RAG_SEARCH_DURATION.labels(
            provider=str(provider or "unknown"),
            mode=str(mode or "default"),
            status=str(status or "unknown"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record rag search metric: {exc}")


def record_turn_duration(capability: str, status: str, duration: float) -> None:
    if not PROMETHEUS_AVAILABLE or TURN_DURATION is None:
        return
    try:
        TURN_DURATION.labels(
            capability=str(capability or "unknown"),
            status=str(status or "unknown"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record turn duration metric: {exc}")


def record_tool_duration(tool_name: str, status: str, duration: float) -> None:
    if not PROMETHEUS_AVAILABLE or TOOL_DURATION is None:
        return
    try:
        TOOL_DURATION.labels(
            tool_name=str(tool_name or "unknown"),
            status=str(status or "unknown"),
        ).observe(max(0.0, float(duration)))
    except Exception as exc:
        logger.debug(f"Failed to record tool duration metric: {exc}")
