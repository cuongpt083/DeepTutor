"""Prometheus metrics exposition endpoint."""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

# Ensure all metrics definitions are loaded into the default registry
import deeptutor.core.observability.metrics  # noqa: F401

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics for scraping."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
