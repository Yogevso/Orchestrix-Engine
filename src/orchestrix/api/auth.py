"""Auth API routes — token generation and user info."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from orchestrix.auth import (
    Role,
    TokenPayload,
    create_access_token,
    get_current_user,
    require_role,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    subject: str = Field(..., examples=["admin@orchestrix.io"])
    role: str = Field(default="viewer", examples=["admin", "operator", "viewer"])
    tenant_id: str | None = Field(default=None)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
async def create_token(body: TokenRequest, _=Depends(require_role(Role.ADMIN))):
    """Generate a JWT token. Requires admin role (or auth disabled)."""
    token = create_access_token(
        subject=body.subject,
        tenant_id=body.tenant_id,
        role=Role(body.role),
    )
    return TokenResponse(access_token=token)


class MeResponse(BaseModel):
    subject: str | None = None
    role: str | None = None
    tenant_id: str | None = None
    auth_enabled: bool


@router.get("/me", response_model=MeResponse)
async def get_me(user: TokenPayload | None = Depends(get_current_user)):
    if user is None:
        from orchestrix.config import settings
        return MeResponse(auth_enabled=settings.auth_enabled)
    return MeResponse(
        subject=user.sub,
        role=user.role.value,
        tenant_id=user.tenant_id,
        auth_enabled=True,
    )
