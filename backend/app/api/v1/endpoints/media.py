"""/api/v1/media — image uploads (sellers) and file serving."""

from __future__ import annotations

from fastapi import APIRouter, Response, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentPrincipal
from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.rbac import P
from app.integrations.storage import ALLOWED_IMAGE_TYPES, get_storage

router = APIRouter(prefix="/media", tags=["media"])

_MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class UploadOut(BaseModel):
    url: str
    content_type: str
    size: int


@router.post("/upload", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile, principal: CurrentPrincipal) -> UploadOut:
    principal.require(P.PRODUCTS_MANAGE_OWN, P.PRODUCTS_MANAGE_ALL)
    ctype = (file.content_type or "").lower()
    if ctype not in _MAGIC:  # SVG uploads are refused (script injection risk)
        raise ValidationFailed("Only JPEG, PNG or WebP images are accepted", code="UNSUPPORTED_MEDIA_TYPE")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise ValidationFailed(f"Image exceeds {get_settings().max_upload_mb} MB", code="PAYLOAD_TOO_LARGE")
    if not any(data.startswith(sig) for sig in _MAGIC[ctype]):
        raise ValidationFailed("File content does not match its declared type", code="UNSUPPORTED_MEDIA_TYPE")
    storage = get_storage()
    url = storage.save(storage.new_key(f"uploads/{principal.user_id.hex}", ctype), data, ctype)
    return UploadOut(url=url, content_type=ctype, size=len(data))


@router.get("/files/{key:path}", include_in_schema=False)
def serve(key: str) -> Response:
    data, ctype = get_storage().open(key)
    headers = {"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"}
    if ctype == "image/svg+xml":
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return Response(content=data, media_type=ctype, headers=headers)


__all__ = ["ALLOWED_IMAGE_TYPES", "router"]
