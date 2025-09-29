+41
-0

from __future__ import annotations

import time
from typing import Any, Dict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .analytics_config import ANALYTICS_ENABLED


class PerformanceAnalyticsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not ANALYTICS_ENABLED:
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            queue = getattr(request.app.state, "analytics_queue", None)
            if queue:
                event: Dict[str, Any] = {
                    "event": "http_request",
                    "anonymous_id": "server",
                    "session_id": "server",
                    "route": request.url.path,
                    "duration_ms": duration_ms,
                    "props": {
                        "method": request.method,
                        "status": status_code,
                    },
                    "context": {"source": "api"},
                }
                queue.put_nowait(event)