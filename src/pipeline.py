"""Ghép fetch → clean → AI extract → storage thành 1 luồng crawl cho 1 URL.

Chỉ code (rule-based) quyết định: dùng dataset nào (so schema_signature), có
lưu record mới hay không (so content_hash để biết nội dung có đổi). AI CHỈ
trích xuất giá trị field — không tự quyết định các việc đó (CLAUDE.md mục 1).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

from .ai.base import AIClient
from .clean.html_cleaner import clean_html
from .fetch.base import FetchEngine
from .storage.base import Dataset, Record, StorageEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    status: str  # "saved" | "unchanged" | "fetch_failed" | "extract_failed"
    dataset: Optional[Dataset] = None
    record: Optional[Record] = None
    detail: Optional[str] = None


def run_crawl_job(
    url: str,
    field_descriptions: dict[str, str],
    fetcher: FetchEngine,
    ai_client: AIClient,
    storage: StorageEngine,
    dataset_id: Optional[str] = None,
    dataset_name: Optional[str] = None,
) -> PipelineResult:
    """Crawl 1 URL và lưu kết quả.

    - Truyền `dataset_id`: thêm URL này làm source của dataset đã có (người
      dùng đã xác nhận tường minh muốn gộp vào dataset đó). `field_descriptions`
      phải khớp đúng schema của dataset, nếu không trả về "schema_mismatch".
    - Không truyền `dataset_id`: LUÔN tạo dataset MỚI (dùng `dataset_name`,
      bắt buộc trong trường hợp này) — KHÔNG tự động gộp vào dataset có sẵn dù
      schema trùng, tránh gộp nhầm 2 nguồn không liên quan (CLAUDE.md mục 4).
    """
    schema_signature = sorted(field_descriptions.keys())

    if dataset_id is not None:
        dataset = storage.get_dataset(dataset_id)
        if dataset is None:
            return PipelineResult(status="dataset_not_found", detail=f"dataset_id {dataset_id} không tồn tại")
        if dataset.schema_signature != schema_signature:
            return PipelineResult(
                status="schema_mismatch",
                dataset=dataset,
                detail="field_descriptions không khớp schema_signature của dataset đã chọn",
            )
    else:
        if not dataset_name:
            raise ValueError("cần dataset_name khi không truyền dataset_id")
        dataset = storage.create_dataset(dataset_name, schema_signature)

    fetch_result = fetcher.fetch(url)
    if not fetch_result.success or fetch_result.html is None:
        logger.info("Fetch thất bại cho %s: %s", url, fetch_result.error)
        return PipelineResult(status="fetch_failed", dataset=dataset, detail=fetch_result.error)

    cleaned = clean_html(fetch_result.html)
    content_hash = hashlib.sha256(cleaned.markdown.encode("utf-8")).hexdigest()

    existing_sources = storage.list_sources(dataset.dataset_id, active_only=True)
    if not any(source.source_url == url for source in existing_sources):
        storage.add_source(dataset.dataset_id, url)

    latest = storage.get_latest_record_for_source(dataset.dataset_id, url)
    if latest is not None and latest.content_hash == content_hash:
        logger.info("Nội dung %s chưa đổi (content_hash trùng) — không lưu record mới.", url)
        return PipelineResult(status="unchanged", dataset=dataset, record=latest)

    extraction = ai_client.extract(cleaned.markdown, field_descriptions)
    if not extraction.success:
        logger.warning("AI extract thất bại cho %s: %s", url, extraction.error)
        return PipelineResult(status="extract_failed", dataset=dataset, detail=extraction.error)

    data = {name: fe.value for name, fe in extraction.fields.items()}
    evidence = {name: fe.evidence for name, fe in extraction.fields.items() if fe.evidence}
    confidences = [fe.confidence for fe in extraction.fields.values()]
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    record = storage.save_record(
        dataset_id=dataset.dataset_id,
        source_url=url,
        data=data,
        content_hash=content_hash,
        evidence=evidence,
        confidence=overall_confidence,
    )
    return PipelineResult(status="saved", dataset=dataset, record=record)
