"""Qiniu evidence flow helpers."""

from __future__ import annotations

import re
from typing import List, Optional

from qiniu import Auth
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Resource


def get_qiniu_upload_token(key: str = "", scene: str = "general", evidence_type: str = "file") -> dict:
    """Create a Qiniu upload token for direct upload."""
    if not all([settings.qiniu_access_key, settings.qiniu_secret_key, settings.qiniu_bucket]):
        return {
            "enabled": False,
            "message": "Qiniu is not configured. Please set QINIU_* in .env.",
        }

    qiniu_auth = Auth(settings.qiniu_access_key, settings.qiniu_secret_key)
    token = qiniu_auth.upload_token(settings.qiniu_bucket, key, settings.qiniu_upload_token_expire)
    return {
        "enabled": True,
        "upload_token": token,
        "bucket": settings.qiniu_bucket,
        "key": key,
        "domain": settings.qiniu_domain,
        "expire_seconds": settings.qiniu_upload_token_expire,
        "scene": scene,
        "evidence_type": evidence_type,
    }


def get_qiniu_private_download_url(key: str, expire_seconds: int = 3600) -> dict:
    """Create a temporary private download URL."""
    if not all(
        [
            settings.qiniu_access_key,
            settings.qiniu_secret_key,
            settings.qiniu_bucket,
            settings.qiniu_domain,
        ]
    ):
        return {
            "enabled": False,
            "message": "Qiniu is not fully configured. Please check QINIU_* values.",
        }
    if not key:
        return {"enabled": False, "message": "key cannot be empty"}

    qiniu_auth = Auth(settings.qiniu_access_key, settings.qiniu_secret_key)
    base_url = f"{settings.qiniu_domain.rstrip('/')}/{key.lstrip('/')}"
    private_url = qiniu_auth.private_download_url(base_url, expires=expire_seconds)
    return {
        "enabled": True,
        "bucket": settings.qiniu_bucket,
        "key": key,
        "expires_in": expire_seconds,
        "private_url": private_url,
    }


def _extract_numbers(text: str) -> List[int]:
    return [int(match) for match in re.findall(r"\d+", text or "")]


def analyze_inventory_evidence(
    db: Session,
    resource_id: int,
    evidence_url: str,
    evidence_type: str = "image",
    ocr_text: str = "",
    observed_count: Optional[int] = None,
) -> dict:
    """Analyze a simple inventory evidence payload and compare with system counts."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise ValueError("Resource not found")

    if observed_count is not None:
        recognized_count = observed_count
    else:
        candidates = _extract_numbers(ocr_text) or _extract_numbers(evidence_url)
        recognized_count = candidates[0] if candidates else resource.available_count

    difference = recognized_count - resource.available_count
    suggestions = []
    if difference == 0:
        suggestions.append("盘点结果与系统可用库存一致。")
    elif difference > 0:
        suggestions.append("现场数量高于系统记录，建议核查是否有未入库或未归还登记。")
        suggestions.append("如确认无误，可发起盘点补录或库存调整。")
    else:
        suggestions.append("现场数量低于系统记录，建议优先排查超时未归还、损坏隔离和丢失登记。")
        suggestions.append("请补充证据并生成追责或补录任务。")

    return {
        "resource_id": resource.id,
        "resource_name": resource.name,
        "evidence_url": evidence_url,
        "evidence_type": evidence_type,
        "recognized_count": recognized_count,
        "system_available_count": resource.available_count,
        "system_total_count": resource.total_count,
        "difference": difference,
        "suggestions": suggestions,
    }
