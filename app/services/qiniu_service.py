"""Qiniu evidence flow helpers."""

from __future__ import annotations

import re
from statistics import mean, pstdev
from typing import Dict, List, Optional

from qiniu import Auth
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Resource
from app.services.evidence_policy_service import ensure_evidence_backfill_task


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


def _extract_ocr_candidates(ocr_text: str) -> List[int]:
    candidates = _extract_numbers(ocr_text)
    # Prefer counts close to explicit quantity context, e.g. "2台", "数量: 5".
    context_match = re.findall(r"(?:数量|盘点|总计|共|count)[:： ]*(\d+)", ocr_text or "", flags=re.IGNORECASE)
    context_candidates = [int(value) for value in context_match if value.isdigit()]
    return context_candidates + candidates


def _build_signal_candidates(
    evidence_url: str,
    ocr_text: str,
    observed_count: Optional[int],
) -> List[Dict[str, float]]:
    signals: List[Dict[str, float]] = []
    if observed_count is not None:
        signals.append({"source": "manual_observed_count", "count": float(observed_count), "weight": 1.0})

    ocr_candidates = _extract_ocr_candidates(ocr_text)
    if ocr_candidates:
        # OCR may be noisy; use average as robust center and keep medium weight.
        signals.append(
            {
                "source": "ocr_text",
                "count": float(round(mean(ocr_candidates))),
                "weight": 0.75,
            }
        )

    metadata_candidates = _extract_numbers(evidence_url)
    if metadata_candidates:
        signals.append(
            {
                "source": "evidence_metadata",
                "count": float(round(mean(metadata_candidates))),
                "weight": 0.45,
            }
        )

    return signals


def _fuse_signals(signals: List[Dict[str, float]], fallback: int) -> tuple[int, float, float]:
    if not signals:
        return fallback, 0.55, 0.0

    total_weight = sum(max(signal["weight"], 0.0) for signal in signals) or 1.0
    weighted = sum(signal["count"] * signal["weight"] for signal in signals) / total_weight
    fused_count = int(round(weighted))

    candidate_values = [signal["count"] for signal in signals]
    disagreement = 0.0
    if len(candidate_values) > 1:
        disagreement = float(pstdev(candidate_values))

    # Confidence increases with source quality and decreases with disagreement.
    strongest = max(signal["weight"] for signal in signals)
    source_factor = min(1.0, strongest)
    confidence = 0.6 + source_factor * 0.25 - min(disagreement * 0.08, 0.25)
    confidence = max(0.3, min(0.98, confidence))
    return fused_count, round(confidence, 4), round(disagreement, 4)


def analyze_inventory_evidence(
    db: Session,
    resource_id: int,
    evidence_url: str,
    evidence_type: str = "image",
    ocr_text: str = "",
    observed_count: Optional[int] = None,
    actor_user_id: Optional[int] = None,
) -> dict:
    """Analyze a simple inventory evidence payload and compare with system counts."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise ValueError("Resource not found")

    signals = _build_signal_candidates(evidence_url=evidence_url, ocr_text=ocr_text, observed_count=observed_count)
    recognized_count, confidence, disagreement = _fuse_signals(signals, fallback=resource.available_count)
    extracted_candidates = [int(signal["count"]) for signal in signals]
    recognized_sources = [str(signal["source"]) for signal in signals]

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

    if confidence < 0.65:
        suggestions.append("识别置信度偏低，建议补传更清晰照片或补充结构化数量字段。")
    if disagreement >= 2:
        suggestions.append("多来源识别结果分歧较大，建议人工复核后再执行库存调整。")

    evidence_backfill_created = ensure_evidence_backfill_task(
        db,
        resource=resource,
        transaction=None,
        evidence_url=evidence_url or "",
        evidence_type=evidence_type or "",
        scenario="盘点",
        assigned_user_id=actor_user_id,
    )
    if evidence_backfill_created:
        suggestions.append("证据字段不完整，系统已自动创建补证任务。")

    return {
        "resource_id": resource.id,
        "resource_name": resource.name,
        "evidence_url": evidence_url,
        "evidence_type": evidence_type,
        "recognized_count": recognized_count,
        "recognition_confidence": confidence,
        "recognized_sources": recognized_sources,
        "extracted_candidates": extracted_candidates,
        "disagreement_index": disagreement,
        "system_available_count": resource.available_count,
        "system_total_count": resource.total_count,
        "difference": difference,
        "suggestions": suggestions,
    }
