"""Token gate for requests that reach this PC through a Cloudflare tunnel.

Local requests keep the existing local-only rules. A request is remote when its Host is not a
loopback name or Cloudflare added its edge headers (clients cannot strip those). Remote requests
need ``Authorization: Bearer $REMOTE_ACCESS_TOKEN``; without a configured token they are refused.
"""

import os
import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "testserver")
EDGE_HEADERS = ("cf-ray", "cf-connecting-ip")
PUBLIC_PATHS = ("/health",)


def is_remote(request: Request) -> bool:
    return request.url.hostname not in LOCAL_HOSTS or any(
        header in request.headers for header in EDGE_HEADERS
    )


def has_valid_token(request: Request) -> bool:
    token = os.getenv("REMOTE_ACCESS_TOKEN", "")
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    return bool(token) and scheme.lower() == "bearer" and secrets.compare_digest(supplied, token)


async def remote_access_gate(request: Request, call_next):
    request.state.remote_authenticated = False
    if is_remote(request) and request.url.path not in PUBLIC_PATHS:
        if not os.getenv("REMOTE_ACCESS_TOKEN"):
            return JSONResponse({"detail": "remote_access_disabled"}, status_code=403)
        if not has_valid_token(request):
            return JSONResponse({"detail": "remote_token_required"}, status_code=401)
        request.state.remote_authenticated = True
    return await call_next(request)
