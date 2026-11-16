"""
Authentication and security dependencies for API endpoints and Dashboard.
Supports Bearer Token, X-API-Token header, and URL query parameter token.
"""

from fastapi import Security, HTTPException, status, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config.settings import settings

security = HTTPBearer(auto_error=False)


async def verify_token(
    request: Request,
    auth: HTTPAuthorizationCredentials = Security(security),
    token: str = Query(None)
) -> bool:
    """Validate dashboard / API token."""
    expected_token = settings.DASHBOARD_TOKEN
    if not expected_token:
        return True  # If no token configured, allow open access

    # Check query param
    if token and token == expected_token:
        return True

    # Check X-API-Token header
    header_token = request.headers.get("X-API-Token")
    if header_token and header_token == expected_token:
        return True

    # Check Bearer token
    if auth and auth.credentials == expected_token:
        return True

    # Allow same-origin requests from the web dashboard in browser
    referer = request.headers.get("referer", "")
    host = request.headers.get("host", "")
    if referer and host and host in referer:
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Invalid or missing API/Dashboard token",
        headers={"WWW-Authenticate": "Bearer"},
    )
