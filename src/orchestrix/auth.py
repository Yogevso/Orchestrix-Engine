"""Authentication & RBAC — JWT-based auth with per-tenant authorization and role-based access."""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from orchestrix.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


# Role hierarchy: admin > operator > viewer
ROLE_HIERARCHY = {Role.ADMIN: 3, Role.OPERATOR: 2, Role.VIEWER: 1}


def create_access_token(
    subject: str,
    tenant_id: str | None = None,
    role: Role = Role.VIEWER,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=settings.jwt_expiry_hours))
    payload = {
        "sub": subject,
        "role": role.value,
        "iat": now,
        "exp": expire,
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Tries IAM-issued tokens first (if iam_jwt_secret_key is configured),
    then falls back to Engine-issued tokens.
    """
    # Try IAM token validation first
    if settings.iam_jwt_secret_key:
        try:
            payload = jwt.decode(
                token,
                settings.iam_jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
                issuer=settings.iam_jwt_issuer,
                options={"require": ["sub", "tenant_id", "role", "type", "exp", "iss"]},
            )
            if payload.get("type") == "access":
                # Map IAM roles to Engine roles
                iam_role = payload.get("role", "USER")
                role_map = {"SYS_ADMIN": "admin", "TENANT_ADMIN": "operator", "USER": "viewer"}
                payload["role"] = role_map.get(iam_role, "viewer")
                return payload
        except jwt.InvalidTokenError:
            pass  # Not an IAM token — try Engine token

    # Engine-issued token
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


class TokenPayload:
    """Parsed token data."""

    def __init__(self, sub: str, role: Role, tenant_id: str | None = None):
        self.sub = sub
        self.role = role
        self.tenant_id = tenant_id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> TokenPayload | None:
    """Extract and validate the current user from the Authorization header.
    Returns None if auth is disabled or no token is provided."""
    if not settings.auth_enabled:
        return None

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    data = decode_token(credentials.credentials)
    return TokenPayload(
        sub=data["sub"],
        role=Role(data.get("role", "viewer")),
        tenant_id=data.get("tenant_id"),
    )


def require_role(minimum_role: Role):
    """Dependency that enforces a minimum role level."""

    async def _check(user: TokenPayload | None = Depends(get_current_user)):
        if user is None:
            return None  # Auth disabled
        if ROLE_HIERARCHY.get(user.role, 0) < ROLE_HIERARCHY[minimum_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum_role.value} role or higher",
            )
        return user

    return _check
