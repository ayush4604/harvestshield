"""Server-side write authorization and bounded request buffering."""
import hmac
from starlette.responses import JSONResponse

MUTATIONS = frozenset({"/api/import", "/api/train", "/api/backtest", "/api/demo", "/api/feed/refresh"})


async def guard_request(request, call_next, settings):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.url.path.rstrip("/") in MUTATIONS:
            if settings.read_only:
                return JSONResponse({"detail": "This deployment is read-only. Administration is disabled."}, status_code=403)
            if settings.admin_token:
                supplied = request.headers.get("authorization", "")
                if not hmac.compare_digest(supplied.encode(), ("Bearer " + settings.admin_token).encode()):
                    return JSONResponse({"detail": "Administrator authentication required."}, status_code=401,
                                        headers={"WWW-Authenticate": "Bearer"})
        limit = 21 * 1024 * 1024 if request.url.path.rstrip("/") == "/api/import" else 1024 * 1024
        try:
            declared = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)
        if declared < 0 or declared > limit:
            return JSONResponse({"detail": "Request body exceeds the size limit."}, status_code=413)
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                return JSONResponse({"detail": "Request body exceeds the size limit."}, status_code=413)
            chunks.append(chunk)
        # Starlette's cached request is replayed to the downstream multipart/JSON parser.
        request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response
