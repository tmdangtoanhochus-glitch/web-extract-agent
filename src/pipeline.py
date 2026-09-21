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

1 URL có thể chứa NHIỀU bản ghi (vd. trang danh sách 10 quote/20 sách) — AI
trả về `records: list[dict[str, FieldExtraction]]` (xem `src/ai/base.py`),
`ai_extract()` gộp structured-data/cache vào TỪNG record, cả `run_crawl_job()`
và `run_file_crawl_job()` lưu/ghi TẤT CẢ record chứ không chỉ record đầu.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .ai.base import AIClient, FieldExtraction
from .api_source import ApiSourceError, extract_api_records
from .clean.html_cleaner import clean_html
from .extract.selector_finder import apply_selector, find_selector
from .extract.structured_data import extract_structured_data, match_field
from .fetch.base import FetchEngine, FetchResult, domain_of
from .progress import ProgressCallback, safe_emit
from .storage.base import Dataset, Record, StorageEngine
from .storage.file_writer import EXPORTS_ROOT, InvalidFilePathError, InvalidKeyFieldError, write_record
from .storage.image_downloader import IMAGES_ROOT, download_image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    status: str  # "saved" | "unchanged" | "fetch_failed" | "extract_failed"
    dataset: Optional[Dataset] = None
    record: Optional[Record] = None
    record_count: int = 0
    detail: Optional[str] = None


@dataclass(frozen=True)
class FileCrawlResult:
    status: str  # "saved" | "fetch_failed" | "extract_failed" | "invalid_file_config"
    file_path: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    confidence: Optional[float] = None
    needs_review: bool = False
    record_count: int = 0
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
    records: list[dict[str, FieldExtraction]] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    warning: Optional[str] = None


# Đặt lại toàn bộ số đếm của giai đoạn AI khi bắt đầu 1 URL mới (job nền dùng chung 1 dict tiến độ cho nhiều URL).
_PROGRESS_RESET = {
    "ai_model": None, "ai_chunks_total": 0, "ai_chunks_done": 0, "ai_chunks_failed": 0, "ai_retries": 0,
    "ai_calling": 0, "ai_waiting": 0, "ai_wait_seconds": 0, "ai_truncated": False, "ai_skipped": False,
    "unchanged": False, "markdown_chars": 0,
}


def fetch_and_clean(
    url: str, fetcher: FetchEngine, on_progress: Optional[ProgressCallback] = None, api_source: bool = False
) -> FetchAndClean:
    """Fetch 1 URL và làm sạch HTML nếu thành công. `fetch_result.success`
    quyết định có tiếp tục được không — tầng gọi tự kiểm tra trước khi dùng
    `markdown`/`content_hash` (rỗng nếu fetch thất bại).

    `on_progress`: báo giai đoạn cho UI — "fetch" (đang tải trang, code chạy) → "clean" (đang làm sạch, code chạy)
    → "cleaned" (xong, kèm số ký tự markdown sẽ gửi AI).

    `api_source`: nguồn là API JSON — không làm sạch HTML, `markdown` giữ nguyên thân JSON
    và `content_hash` tính trên thân đó (để phát hiện dữ liệu đổi)."""
    safe_emit(on_progress, {**_PROGRESS_RESET, "phase": "fetch"})
    logger.info("[%s] Bắt đầu fetch...", url)
    fetch_result = fetcher.fetch(url)
    if not fetch_result.success or fetch_result.html is None:
        logger.warning("[%s] Fetch thất bại: %s", url, fetch_result.error)
        return FetchAndClean(fetch_result=fetch_result)

    logger.info(
        "[%s] Fetch thành công (status=%s, %d bytes HTML) — đang làm sạch...",
        url, fetch_result.status_code, len(fetch_result.html),
    )
    if api_source:
        body = fetch_result.html
        safe_emit(on_progress, {"phase": "cleaned", "markdown_chars": 0})
        return FetchAndClean(
            fetch_result=fetch_result, markdown=body, content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest()
        )
    safe_emit(on_progress, {"phase": "clean"})
    cleaned = clean_html(fetch_result.html, base_url=fetch_result.final_url or url)
    content_hash = hashlib.sha256(cleaned.markdown.encode("utf-8")).hexdigest()
    safe_emit(on_progress, {"phase": "cleaned", "markdown_chars": len(cleaned.markdown)})
    logger.info(
        "[%s] Làm sạch xong — markdown còn %d ký tự (từ %d ký tự HTML gốc).",
        url, len(cleaned.markdown), len(fetch_result.html),
    )
    return FetchAndClean(fetch_result=fetch_result, markdown=cleaned.markdown, content_hash=content_hash)


def ai_extract(
    url: str,
    html: str,
    markdown: str,
    field_descriptions: dict[str, str],
    ai_client: AIClient,
    storage: StorageEngine,
    parallel_extract: bool = False,
    on_progress: Optional[ProgressCallback] = None,
    api_source: bool = False,
) -> AiExtractResult:
    """Trích xuất field theo thứ tự ưu tiên: structured data (JSON-LD/Open
    Graph, CLAUDE.md mục 2) → cache chiến lược theo domain (CLAUDE.md mục 5)
    → AI cho field còn lại. Dùng chung cho cả luồng DB và luồng file.

    Trang có thể có NHIỀU bản ghi — `resolved_fields` (structured data/cache,
    áp dụng chung cho cả trang) được gộp vào TỪNG record AI trả về.

    `parallel_extract`: người dùng tự tick chọn ở Bước 3 (mặc định tắt) — chỉ có
    tác dụng khi trang dài bị chia nhiều đoạn, xem `AIClient.extract()`."""
    logger.info("[%s] Bắt đầu trích xuất %d field: %s", url, len(field_descriptions), list(field_descriptions))
    if api_source:
        # Nguồn API JSON: ghép field với khóa JSON bằng code, KHÔNG gọi AI.
        safe_emit(on_progress, {"phase": "ai_skipped", "ai_skipped": True})
        try:
            return AiExtractResult(records=extract_api_records(html, field_descriptions))
        except ApiSourceError as exc:
            return AiExtractResult(success=False, error=str(exc))
    structured = extract_structured_data(html)
    domain = domain_of(url)
    resolved_fields: dict[str, FieldExtraction] = {}
    remaining_descriptions: dict[str, str] = {}

    for name, description in field_descriptions.items():
        matched = match_field(name, structured)
        if matched is not None:
            logger.info("[%s] Field '%s' lấy được từ structured data (%s), KHÔNG cần gọi AI.", url, name, matched.source)
            resolved_fields[name] = FieldExtraction(
                value=matched.value, confidence=1.0, evidence=f"{matched.source}={matched.value!r}"
            )
            continue

        remaining_descriptions[name] = description

    # Cache chiến lược theo domain (CLAUDE.md mục 5). Selector là đường dẫn tuyệt
    # đối => chỉ ra ĐÚNG 1 giá trị, nên chỉ hợp lệ với trang 1-record. Để không
    # "khoá" trang nhiều record về 1 giá trị: (1) chỉ GHI cache khi AI trả đúng 1
    # bản ghi; (2) chỉ ÁP cache khi TẤT CẢ field còn lại đều có selector khớp
    # (all-or-nothing) — nếu thiếu 1 field thì cả nhóm đi qua AI.
    if remaining_descriptions:
        cached: dict[str, FieldExtraction] = {}
        for name in remaining_descriptions:
            strategy = storage.get_extraction_strategy(domain, name)
            value = apply_selector(html, strategy.selector) if strategy is not None else None
            if value is None:
                break
            cached[name] = FieldExtraction(
                value=value, confidence=0.9, evidence=f"cached_selector:{strategy.selector}={value!r}"
            )
        else:
            logger.info("[%s] Toàn bộ field còn lại lấy từ cache selector theo domain %s, KHÔNG gọi AI.", url, domain)
            resolved_fields.update(cached)
            remaining_descriptions = {}

    if remaining_descriptions:
        logger.info(
            "[%s] Gửi nội dung trang (%d ký tự markdown) cho AI trích xuất %d field còn lại: %s",
            url, len(markdown), len(remaining_descriptions), list(remaining_descriptions),
        )
        extraction = ai_client.extract(
            markdown, remaining_descriptions, parallel=parallel_extract, on_progress=on_progress
        )
        if not extraction.success:
            logger.warning("[%s] AI extract thất bại: %s", url, extraction.error)
            return AiExtractResult(records=[resolved_fields], success=False, error=extraction.error)
        if extraction.warning:
            logger.warning("[%s] AI extract thành công một phần: %s", url, extraction.warning)

        # AI trả về array các record — gộp resolved_fields (structured data/cache,
        # dùng chung cho cả trang) vào MỖI record.
        all_records: list[dict[str, FieldExtraction]] = [
            {**resolved_fields, **ai_fields} for ai_fields in extraction.records
        ]
        logger.info(
            "[%s] AI trả về %d bản ghi — confidence trung bình từng field của bản ghi đầu: %s",
            url, len(all_records),
            {name: fe.confidence for name, fe in all_records[0].items()} if all_records else {},
        )
        if len(extraction.records) == 1:
            for name, fe in extraction.records[0].items():
                if name in remaining_descriptions and fe.value not in (None, ""):
                    selector = find_selector(html, fe.value)
                    if selector is not None:
                        storage.save_extraction_strategy(domain, name, selector, sample_value=str(fe.value))
    else:
        logger.info(
            "Toàn bộ field của %s lấy được từ structured data/cache — bỏ qua AI.",
            url,
        )
        all_records = [resolved_fields]
        extraction = None
        safe_emit(on_progress, {"phase": "ai_skipped", "ai_skipped": True})

    return AiExtractResult(records=all_records, success=True, warning=extraction.warning if extraction else None)


def _apply_image_downloads(
    data: dict[str, Any],
    image_fields: list[str],
    record_key: str,
    images_root: Path,
) -> dict[str, Any]:
    """Tải file cho các field được người dùng đánh dấu tường minh là ảnh
    (`image_fields`) — code (rule-based) quyết định hành động "tải file về",
    AI chỉ trả URL như 1 field bình thường (CLAUDE.md mục 1). Thay giá trị
    field bằng đường dẫn local (tương đối trong `images_root`) nếu tải thành
    công; giữ nguyên URL gốc + ghi log cảnh báo nếu tải lỗi — KHÔNG chặn cả
    record chỉ vì 1 ảnh tải lỗi, nhất quán với cách `ai_extract()` xử lý lỗi
    từng field riêng lẻ."""
    updated = dict(data)
    for field_name in image_fields:
        value = updated.get(field_name)
        if not value:
            continue
        result = download_image(
            str(value), record_key=record_key, field_name=field_name, images_root=images_root
        )
        if result.success:
            updated[field_name] = result.local_path
        else:
            logger.warning(
                "Tải ảnh thất bại cho field '%s' (url=%s): %s", field_name, value, result.error
            )
    return updated


def run_crawl_job(
    url: str,
    field_descriptions: dict[str, str],
    fetcher: FetchEngine,
    ai_client: AIClient,
    storage: StorageEngine,
    dataset_id: Optional[str] = None,
    dataset_name: Optional[str] = None,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
    image_fields: Optional[list[str]] = None,
    images_root: Path = IMAGES_ROOT,
    parallel_extract: bool = False,
    on_progress: Optional[ProgressCallback] = None,
    api_source: bool = False,
) -> PipelineResult:
    """Crawl 1 URL và lưu kết quả vào DB — có thể lưu NHIỀU record nếu trang
    có nhiều bản ghi (`extraction.records`, xem `ai_extract()`).

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

    fac = fetch_and_clean(url, fetcher, on_progress, api_source)
    if not fac.fetch_result.success or fac.fetch_result.html is None:
        logger.info("Fetch thất bại cho %s: %s", url, fac.fetch_result.error)
        return PipelineResult(status="fetch_failed", dataset=dataset, detail=fac.fetch_result.error)

    existing_sources = storage.list_sources(dataset.dataset_id, active_only=True)
    if not any(source.source_url == url for source in existing_sources):
        storage.add_source(dataset.dataset_id, url)

    latest = storage.get_latest_record_for_source(dataset.dataset_id, url)
    if latest is not None and latest.content_hash == fac.content_hash:
        logger.info("Nội dung %s chưa đổi (content_hash trùng) — không lưu record mới.", url)
        safe_emit(on_progress, {"phase": "done", "ai_skipped": True, "unchanged": True})
        return PipelineResult(status="unchanged", dataset=dataset, record=latest)

    extraction = ai_extract(
        url, fac.fetch_result.html, fac.markdown, field_descriptions, ai_client, storage,
        parallel_extract=parallel_extract, on_progress=on_progress, api_source=api_source,
    )
    if not extraction.success:
        return PipelineResult(status="extract_failed", dataset=dataset, detail=extraction.error)
    safe_emit(on_progress, {"phase": "save"})

    saved_records: list[Record] = []
    for index, fields in enumerate(extraction.records):
        data = {name: fe.value for name, fe in fields.items()}
        if image_fields:
            data = _apply_image_downloads(
                data, image_fields, record_key=f"{dataset.dataset_id}_{index}", images_root=images_root
            )
        evidence = {name: fe.evidence for name, fe in fields.items() if fe.evidence}
        confidences = [fe.confidence for fe in fields.values()]
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
        saved_records.append(record)

    logger.info(
        "[%s] Đã lưu %d record vào dataset %s.", url, len(saved_records), dataset.dataset_id,
    )
    safe_emit(on_progress, {"phase": "done"})
    return PipelineResult(
        status="saved",
        dataset=dataset,
        record=saved_records[0] if saved_records else None,
        record_count=len(saved_records),
        detail=extraction.warning,
    )


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
    image_fields: Optional[list[str]] = None,
    images_root: Path = IMAGES_ROOT,
    parallel_extract: bool = False,
    on_progress: Optional[ProgressCallback] = None,
    api_source: bool = False,
) -> FileCrawlResult:
    """Crawl 1 URL và ghi kết quả ra file (`src/storage/file_writer.py`,
    JSON/CSV/XLSX/Parquet theo đuôi file) — KHÔNG dedup theo content_hash,
    KHÔNG schema-match, KHÔNG tạo dataset (đối lập có chủ đích với
    `run_crawl_job()`). Có thể ghi NHIỀU record nếu trang có nhiều bản ghi.
    `storage` vẫn cần truyền vào vì `ai_extract()` dùng nó để đọc/ghi cache
    chiến lược theo domain (CLAUDE.md mục 5) — cache này độc lập với
    dataset/records, dùng chung được cho cả 2 luồng.

    `confidence_threshold`: giống `run_crawl_job()` — chỉ gắn cờ `needs_review`
    trong record ghi ra file, KHÔNG chặn ghi."""
    fac = fetch_and_clean(url, fetcher, on_progress, api_source)
    if not fac.fetch_result.success or fac.fetch_result.html is None:
        logger.info("Fetch thất bại cho %s: %s", url, fac.fetch_result.error)
        return FileCrawlResult(status="fetch_failed", detail=fac.fetch_result.error)

    extraction = ai_extract(
        url, fac.fetch_result.html, fac.markdown, field_descriptions, ai_client, storage,
        parallel_extract=parallel_extract, on_progress=on_progress, api_source=api_source,
    )
    if not extraction.success:
        return FileCrawlResult(status="extract_failed", detail=extraction.error)
    safe_emit(on_progress, {"phase": "save"})

    first_data: Optional[dict[str, Any]] = None
    first_confidence: Optional[float] = None
    first_needs_review = False
    write_result = None

    for index, fields in enumerate(extraction.records):
        data = {name: fe.value for name, fe in fields.items()}
        if image_fields:
            data = _apply_image_downloads(
                data, image_fields, record_key=f"{domain_of(url)}_{index}", images_root=images_root
            )
        confidences = [fe.confidence for fe in fields.values()]
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        needs_review = overall_confidence < confidence_threshold

        record = {
            **data,
            "source_url": url,
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

        if first_data is None:
            first_data = data
            first_confidence = overall_confidence
            first_needs_review = needs_review

    logger.info(
        "[%s] Đã ghi %d record vào file %s.",
        url, len(extraction.records), write_result.file_path if write_result else file_path,
    )
    safe_emit(on_progress, {"phase": "done"})
    return FileCrawlResult(
        status="saved",
        file_path=write_result.file_path if write_result else None,
        data=first_data,
        confidence=first_confidence,
        needs_review=first_needs_review,
        record_count=len(extraction.records),
        detail=extraction.warning,
    )
