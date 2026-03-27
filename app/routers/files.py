"""Evidence and Qiniu file routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import InventoryVisionRequest, InventoryVisionResponse
from app.services.qiniu_service import analyze_inventory_evidence, get_qiniu_private_download_url, get_qiniu_upload_token

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/qiniu-token")
def fetch_qiniu_token(
    key: str = Query(default="", description="Object storage key"),
    scene: str = Query(default="general", description="Business scene"),
    evidence_type: str = Query(default="file", description="Evidence type"),
    current_user: User = Depends(get_current_user),
):
    """Get a Qiniu upload token."""
    return get_qiniu_upload_token(key, scene, evidence_type)


@router.get("/qiniu-private-url")
def fetch_qiniu_private_url(
    key: str = Query(..., description="Object storage key"),
    expire_seconds: int = Query(default=3600, description="URL expiration in seconds"),
    current_user: User = Depends(get_current_user),
):
    """Get a temporary signed URL for a private object."""
    return get_qiniu_private_download_url(key, expire_seconds)


@router.post("/evidence/inventory-vision", response_model=InventoryVisionResponse)
def inspect_inventory_evidence(
    payload: InventoryVisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analyze inventory evidence and compare it with system stock."""
    return InventoryVisionResponse(
        **analyze_inventory_evidence(
            db=db,
            resource_id=payload.resource_id,
            evidence_url=payload.evidence_url,
            evidence_type=payload.evidence_type,
            ocr_text=payload.ocr_text,
            observed_count=payload.observed_count,
        )
    )
