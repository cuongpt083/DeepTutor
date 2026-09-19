"""Prometheus metrics exposition endpoint."""

from fastapi import APIRouter, Response

router = APIRouter(tags=["metrics"])

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    # Ensure all metrics definitions are loaded into the default registry
    import deeptutor.core.observability.metrics  # noqa: F401
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


@router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics for scraping."""
    if not PROMETHEUS_AVAILABLE:
        return Response(
            content="# prometheus_client library not installed in runtime environment\n",
            status_code=503,
            media_type="text/plain",
        )
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
