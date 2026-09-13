"""Ghép fetch → structured data → cache chiến lược → clean → AI extract →
storage thành 1 luồng crawl cho 1 URL.

Có 2 luồng lưu kết quả NGANG HÀNG, không phải ghi kép — người dùng chọn 1 khi
tạo job (storage_mode "db" | "file"):
- `run_crawl_job()`: lưu DB qua `StorageEngine` — có schema-match, dedup theo
  content_hash, tạo/dùng `dataset_id` (CLAUDE.md mục 4).
- `run_file_crawl_job()`: ghi ra file JSON qua `src/storage/file_writer.py` —
  KHÔNG dedup, KHÔNG schema-match, KHÔNG tạo dataset (đơn giản hơn có chủ đích).

Cả 2 dùng chung `fetch_and_clean()` (fetch + làm sạch HTML) và `ai_extract()`
(structured data → cache chiến lược theo domain → AI cho field còn lại) —
phần "trích xuất" giống hệt nhau bất kể lưu vào đâu, chỉ bước lưu cuối cùng rẽ
nhánh. Chỉ code (rule-based) quyết định: dùng dataset nào, có lưu record mới
hay không, field nào lấy được từ structured data/cache hay phải hỏi AI. AI CHỈ
trích xuất giá trị field — không tự quyết định các việc đó (CLAUDE.md mục 1).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .ai.base import AIClient, FieldExtraction
from .clean.html_cleaner import clean_html
from .extract.selector_finder import apply_selector, find_selector
from .extract.structured_data import extract_structured_data, match_field
from .fetch.base import FetchEngine, FetchResult, domain_of
from .storage.base import Dataset, Record, StorageEngine
from .storage.file_writer import EXPORTS_ROOT, InvalidFilePathError, InvalidKeyFieldError, write_record

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    status: str  # "saved" | "unchanged" | "fetch_failed" | "extract_failed"
    dataset: Optional[Dataset] = None
    record: Optional[Record] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class FileCrawlResult:
    status: str  # "saved" | "fetch_failed" | "extract_failed" | "invalid_file_config"
    file_path: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    confidence: Optional[float] = None
    needs_review: bool = False
    detail: Optional[str] = None


_DEFAULT_CONFIDENCE_THRESHOLD = 0.7


@dataclass(frozen=True)
class FetchAndClean:
    """Kết quả fetch + làm sạch HTML — dùng chung cho cả luồng DB và file."""

    fetch_result: FetchResult
    markdown: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class AiExtractResult:
    fields: dict[str, FieldExtraction] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None


def fetch_and_clean(url: str, fetcher: FetchEngine) -> FetchAndClean:
    """Fetch 1 URL và làm sạch HTML nếu thành công. `fetch_result.success`
    quyết định có tiếp tục được không — tầng gọi tự kiểm tra trước khi dùng
    `markdown`/`content_hash` (rỗng nếu fetch thất bại)."""
    fetch_result = fetcher.fetch(url)
    if not fetch_result.success or fetch_result.html is None:
        return FetchAndClean(fetch_result=fetch_result)

    cleaned = clean_html(fetch_result.html)
    content_hash = hashlib.sha256(cleaned.markdown.encode("utf-8")).hexdigest()
    return FetchAndClean(fetch_result=fetch_result, markdown=cleaned.markdown, content_hash=content_hash)


def ai_extract(
    url: str,
    html: str,
    markdown: str,
    field_descriptions: dict[str, str],
    ai_client: AIClient,
    storage: StorageEngine,
) -> AiExtractResult:
    """Trích xuất field theo thứ tự ưu tiên: structured data (JSON-LD/Open
    Graph, CLAUDE.md mục 2) → cache chiến lược theo domain (CLAUDE.md mục 5)
    → AI cho field còn lại. Dùng chung cho cả luồng DB và luồng file."""
    structured = extract_structured_data(html)
    domain = domain_of(url)
    resolved_fields: dict[str, FieldExtraction] = {}
    remaining_descriptions: dict[str, str] = {}

    for name, description in field_descriptions.items():
        matched = match_field(name, structured)
        if matched is not None:
            resolved_fields[name] = FieldExtraction(
                value=matched.value, confidence=1.0, evidence=f"{matched.source}={matched.value!r}"
            )
            continue

        # Cache chiến lược extract theo domain (CLAUDE.md mục 5): field đã
        # từng được AI định vị trên domain này thì áp lại selector rule-based
        # trước — chỉ gọi AI lại khi selector không còn khớp (site đổi cấu trúc).
        cached_strategy = storage.get_extraction_strategy(domain, name)
        cached_value = (
            apply_selector(html, cached_strategy.selector) if cached_strategy is not None else None
        )
        if cached_value is not None:
            resolved_fields[name] = FieldExtraction(
                value=cached_value,
                confidence=0.9,
                evidence=f"cached_selector:{cached_strategy.selector}={cached_value!r}",
            )
            continue

        if cached_strategy is not None:
            logger.info(
                "Selector cache cho field '%s' trên domain %s không còn khớp — fallback sang AI.",
                name, domain,
            )
        remaining_descriptions[name] = description

    if remaining_descriptions:
        extraction = ai_client.extract(markdown, remaining_descriptions)
        if not extraction.success:
            logger.warning("AI extract thất bại cho %s: %s", url, extraction.error)
            return AiExtractResult(fields=resolved_fields, success=False, error=extraction.error)
        resolved_fields.update(extraction.fields)

        # AI vừa định vị được field mới (hoặc định vị lại field cache cũ đã
        # fail) — suy ra selector rồi lưu/ghi đè cache cho lần cào sau.
        for name, fe in extraction.fields.items():
            if fe.value in (None, ""):
                continue
            selector = find_selector(html, fe.value)
            if selector is not None:
                storage.save_extraction_strategy(domain, name, selector, sample_value=str(fe.value))
    else:
        logger.info(
            "Toàn bộ field của %s lấy được từ structured data/cache — bỏ qua AI.",
            url,
        )

    return AiExtractResult(fields=resolved_fields, success=True)


def run_crawl_job(
    url: str,
    field_descriptions: dict[str, str],
    fetcher: FetchEngine,
    ai_client: AIClient,
    storage: StorageEngine,
    dataset_id: Optional[str] = None,
    dataset_name: Optional[str] = None,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
) -> PipelineResult:
    """Crawl 1 URL và lưu kết quả vào DB.

    - Truyền `dataset_id`: thêm URL này làm source của dataset đã có (người
      dùng đã xác nhận tường minh muốn gộp vào dataset đó). `field_descriptions`
      phải khớp đúng schema của dataset, nếu không trả về "schema_mismatch".
    - Không truyền `dataset_id`: LUÔN tạo dataset MỚI (dùng `dataset_name`,
      bắt buộc trong trường hợp này) — KHÔNG tự động gộp vào dataset có sẵn dù
      schema trùng, tránh gộp nhầm 2 nguồn không liên quan (CLAUDE.md mục 4).

    `confidence_threshold` (mặc định lấy từ `AI_CONFIDENCE_THRESHOLD`, xem
    `src/config.py`): record vẫn LUÔN được lưu bất kể confidence — ngưỡng này
    CHỈ dùng để gắn cờ `needs_review` cho UI/API cảnh báo, KHÔNG loại bỏ hay
    chặn lưu record nào.
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

    fac = fetch_and_clean(url, fetcher)
    if not fac.fetch_result.success or fac.fetch_result.html is None:
        logger.info("Fetch thất bại cho %s: %s", url, fac.fetch_result.error)
        return PipelineResult(status="fetch_failed", dataset=dataset, detail=fac.fetch_result.error)

    existing_sources = storage.list_sources(dataset.dataset_id, active_only=True)
    if not any(source.source_url == url for source in existing_sources):
        storage.add_source(dataset.dataset_id, url)

    latest = storage.get_latest_record_for_source(dataset.dataset_id, url)
    if latest is not None and latest.content_hash == fac.content_hash:
        logger.info("Nội dung %s chưa đổi (content_hash trùng) — không lưu record mới.", url)
        return PipelineResult(status="unchanged", dataset=dataset, record=latest)

    extraction = ai_extract(url, fac.fetch_result.html, fac.markdown, field_descriptions, ai_client, storage)
    if not extraction.success:
        return PipelineResult(status="extract_failed", dataset=dataset, detail=extraction.error)

    data = {name: fe.value for name, fe in extraction.fields.items()}
    evidence = {name: fe.evidence for name, fe in extraction.fields.items() if fe.evidence}
    confidences = [fe.confidence for fe in extraction.fields.values()]
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    record = storage.save_record(
        dataset_id=dataset.dataset_id,
        source_url=url,
        data=data,
        content_hash=fac.content_hash,
        evidence=evidence,
        confidence=overall_confidence,
        needs_review=overall_confidence < confidence_threshold,
    )
    return PipelineResult(status="saved", dataset=dataset, record=record)


def run_file_crawl_job(
    url: str,
    field_descriptions: dict[str, str],
    file_path: str,
    write_mode: str,
    fetcher: FetchEngine,
    ai_client: AIClient,
    storage: StorageEngine,
    key_field: Optional[str] = None,
    exports_root: Path = EXPORTS_ROOT,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
) -> FileCrawlResult:
    """Crawl 1 URL và ghi kết quả ra file JSON (`src/storage/file_writer.py`)
    — KHÔNG dedup theo content_hash, KHÔNG schema-match, KHÔNG tạo dataset
    (đối lập có chủ đích với `run_crawl_job()`). `storage` vẫn cần truyền vào
    vì `ai_extract()` dùng nó để đọc/ghi cache chiến lược theo domain
    (CLAUDE.md mục 5) — cache này độc lập với dataset/records, dùng chung
    được cho cả 2 luồng.

    `confidence_threshold`: giống `run_crawl_job()` — chỉ gắn cờ `needs_review`
    trong record ghi ra file, KHÔNG chặn ghi."""
    fac = fetch_and_clean(url, fetcher)
    if not fac.fetch_result.success or fac.fetch_result.html is None:
        logger.info("Fetch thất bại cho %s: %s", url, fac.fetch_result.error)
        return FileCrawlResult(status="fetch_failed", detail=fac.fetch_result.error)

    extraction = ai_extract(url, fac.fetch_result.html, fac.markdown, field_descriptions, ai_client, storage)
    if not extraction.success:
        return FileCrawlResult(status="extract_failed", detail=extraction.error)

    data = {name: fe.value for name, fe in extraction.fields.items()}
    evidence = {name: fe.evidence for name, fe in extraction.fields.items() if fe.evidence}
    confidences = [fe.confidence for fe in extraction.fields.values()]
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    needs_review = overall_confidence < confidence_threshold

    record = {
        "source_url": url,
        "data": data,
        "evidence": evidence,
        "confidence": overall_confidence,
        "needs_review": needs_review,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        write_result = write_record(
            file_path=file_path,
            record=record,
            write_mode=write_mode,
            key_field=key_field,
            field_names=list(field_descriptions.keys()),
            exports_root=exports_root,
        )
    except (InvalidFilePathError, InvalidKeyFieldError) as exc:
        logger.warning("Cấu hình file không hợp lệ cho %s: %s", url, exc)
        return FileCrawlResult(status="invalid_file_config", detail=str(exc))

    return FileCrawlResult(
        status="saved",
        file_path=write_result.file_path,
        data=data,
        confidence=overall_confidence,
        needs_review=needs_review,
    )
