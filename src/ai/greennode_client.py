"""AI client thật — gọi endpoint Qwen/GLM do GreenNode cấp qua MaaS (CLAUDE.md mục B).

Format đã XÁC NHẬN qua docs.greennode.ai (mục "Model as a Service" / "Kết nối
OpenAI-compatible với GreenNode MaaS"), không phải giả định:
- Base URL thật: `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` — LUÔN có
  hậu tố `/v1`, client OpenAI-compatible trỏ vào URL này rồi tự nối thêm path.
- Endpoint: `POST {base_url}/chat/completions`, header `Authorization: Bearer
  <api-key>` — KHÔNG cần header nào khác cho chat completions (header
  `portal-user-id` chỉ dùng cho API OCR riêng, không áp dụng ở đây).
- Request/response body đúng chuẩn OpenAI chat completions
  (`{"model", "messages", ...}` → `choices[0].message.content`).
- QUAN TRỌNG: `model` phải là ID có prefix nhà cung cấp lấy từ catalog GreenNode
  (VD xác nhận được: `"openai/gpt-4o"`), KHÔNG phải tên hiển thị (VD sai:
  "Qwen 3.6 Flash", "qwen-3.6-flash") — lấy ID thật qua `GET {base_url}/models`
  hoặc trang API Keys/Model Catalog trên console, điền vào `AI_MODEL` trong
  `.env`. Code ở đây KHÔNG hard-code hay validate cứng chuỗi model, chỉ truyền
  thẳng giá trị từ `.env` xuống — người vận hành chịu trách nhiệm điền đúng ID.

Dùng endpoint OpenAI-compatible `/chat/completions` (không dùng SDK `openai` để
tránh thêm dependency ngoài tech stack đã chốt — gọi thẳng qua `httpx`, vốn đã
có sẵn trong requirements.txt cho tầng fetch).

Endpoint thật + model name lấy từ `.env` (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`)
— KHÔNG hard-code giá trị thật trong code.

Trang có thể chứa NHIỀU bản ghi giống nhau (vd. 10 quote, 20 sách trên 1 trang
danh sách) — prompt yêu cầu AI trả về JSON ARRAY (mỗi phần tử là 1 bản ghi),
không phải 1 object duy nhất như trước (xem docs/kien_audit/03).
"""
from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

import httpx

from ..progress import safe_emit
from .base import AIClient, ExtractionResult, FieldExtraction
from .rate_limiter import ModelRateLimiter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Bạn là hệ thống trích xuất dữ liệu có cấu trúc từ nội dung trang web đã "
    "được làm sạch. Chỉ trích xuất giá trị THỰC SỰ xuất hiện trong nội dung "
    "được cung cấp, KHÔNG suy diễn hay bịa thông tin không có trong text. "
    "Trang có thể chứa 1 hoặc nhiều bản ghi giống nhau (vd. nhiều sách, nhiều "
    "quote). Với mỗi bản ghi và mỗi field, trả về: value (giá trị trích được, "
    "hoặc null nếu không tìm thấy), confidence (số 0-1 thể hiện độ chắc chắn), "
    "evidence (câu/đoạn gốc trong nội dung chứa giá trị đó, hoặc null). "
    "Trả về 1 JSON array, mỗi phần tử là 1 object với key là tên field, value "
    "là object có dạng {\"value\": ..., \"confidence\": ..., \"evidence\": ...}. "
    "Nếu trang chỉ có 1 bản ghi, trả về array 1 phần tử. "
    "CHỈ trả lời bằng JSON array, không kèm giải thích, không dùng markdown code fence."
)


class GreenNodeChatClient(AIClient):
    """`client` cho phép inject 1 `httpx.Client` có sẵn (vd. `httpx.MockTransport`
    khi test) — theo adapter/test-double pattern ở CLAUDE.md mục 6."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        client: Optional[httpx.Client] = None,
        rate_limiter: Optional[ModelRateLimiter] = None,
    ) -> None:
        _warn_if_base_url_missing_v1_suffix(base_url)
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._injected_client = client
        # Không truyền = không giới hạn cấu hình, nhưng vẫn xử lý 429/Retry-After (xem _extract_chunk_with_retry).
        self._rate_limiter = rate_limiter or ModelRateLimiter()

    def extract(
        self,
        markdown: str,
        field_descriptions: dict[str, str],
        parallel: bool = False,
        on_progress: Optional[Callable[[dict], None]] = None,
    ) -> ExtractionResult:
        """Trang dài được chia thành nhiều đoạn (theo ranh giới dòng) và gọi AI từng
        đoạn rồi gộp bản ghi — không cắt bỏ phần đuôi trang nữa (trước đây bản ghi
        ở phần sau bị mất im lặng).

        Mỗi đoạn: thử lại 1 lần với timeout dài hơn nếu lỗi (timeout của model
        thường là tải đột biến tạm thời — xem `_extract_chunk_with_retry`). Một
        đoạn lỗi (kể cả đoạn đầu) KHÔNG làm hỏng cả lượt — bỏ qua đoạn đó, tiếp
        tục các đoạn còn lại; chỉ trả lỗi khi TẤT CẢ đoạn đều lỗi. Kết quả thành
        công một phần (có đoạn bị bỏ, hoặc trang bị cắt vì quá nhiều đoạn) được
        báo qua `warning`, không phải `error`.

        `parallel`: người dùng tự tick chọn (mặc định tắt) — gọi TẤT CẢ đoạn
        ĐỒNG THỜI thay vì tuần tự (xem `_call_chunks_parallel`). Kết quả gộp
        lại giống hệt hành vi tuần tự (đúng thứ tự đoạn, cùng cơ chế thử lại và
        bỏ qua đoạn lỗi) — chỉ khác THỜI GIAN CHỜ, không đổi số lượt gọi AI.

        Mọi lượt gọi đi qua bộ giới hạn theo model (`ModelRateLimiter`): vượt hạn mức thì TỰ CHỜ (delay) thay vì bắn
        rồi nhận 429; nếu vẫn gặp 429 thì chờ đúng `Retry-After` rồi thử lại (không tính là đoạn lỗi). `on_progress`
        nhận số đoạn đã xong/tổng và trạng thái "đang gọi model"/"đang chờ hạn mức" để UI hiển thị."""
        if not field_descriptions:
            raise ValueError("field_descriptions không được rỗng")
        chunks, truncated = _split_markdown(markdown)
        tracker = _ProgressTracker(on_progress, self._model, len(chunks), truncated)
        if len(chunks) == 1:
            return self._run_chunk(chunks[0], field_descriptions, tracker)
        logger.info(
            "Trang dài %d ký tự — chia %d đoạn để gọi AI (%s).",
            len(markdown), len(chunks), "song song" if parallel else "tuần tự",
        )
        results = (
            self._call_chunks_parallel(chunks, field_descriptions, tracker)
            if parallel
            else [self._run_chunk(chunk, field_descriptions, tracker, index)
                  for index, chunk in enumerate(chunks, 1)]
        )
        return self._merge_chunk_results(results, truncated, len(chunks))

    def _run_chunk(
        self, chunk: str, field_descriptions: dict[str, str], tracker: "_ProgressTracker", index: Optional[int] = None
    ) -> ExtractionResult:
        if index is not None:  # chỉ chế độ tuần tự biết chắc "đang ở đoạn thứ mấy"
            tracker.set_current(index)
        result = self._extract_chunk_with_retry(chunk, field_descriptions, tracker)
        tracker.chunk_done(result.success)
        return result

    def _call_chunks_parallel(
        self, chunks: list[str], field_descriptions: dict[str, str], tracker: "_ProgressTracker"
    ) -> list[ExtractionResult]:
        """Gọi tất cả đoạn ĐỒNG THỜI bằng ThreadPoolExecutor (mỗi lượt `_extract_chunk`
        tự tạo `httpx.Client` riêng khi không có client inject — an toàn giữa các
        luồng, xem `_extract_chunk`). Submit hết rồi mới chờ kết quả để các đoạn
        THỰC SỰ chạy cùng lúc, không phải tuần tự trá hình."""
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            futures = [
                executor.submit(self._run_chunk, chunk, field_descriptions, tracker)
                for chunk in chunks
            ]
            return [future.result() for future in futures]

    def _merge_chunk_results(
        self, results: list[ExtractionResult], truncated: bool, total_chunks: int
    ) -> ExtractionResult:
        records: list = []
        raw_parts: list[str] = []
        chunk_errors: list[str] = []
        for index, result in enumerate(results, 1):
            if not result.success:
                logger.warning(
                    "Đoạn %d/%d lỗi sau khi thử lại (%s) — bỏ qua đoạn này, tiếp tục các đoạn còn lại.",
                    index, total_chunks, result.error,
                )
                chunk_errors.append(f"đoạn {index}/{total_chunks}: {result.error}")
                continue
            records.extend(result.records)
            raw_parts.append(result.raw_response or "")
        if not records:
            return ExtractionResult(
                success=False,
                error="; ".join(chunk_errors) if chunk_errors else "không có đoạn nào trả về bản ghi",
            )
        return ExtractionResult(
            records=records,
            raw_response="\n".join(raw_parts),
            success=True,
            warning=_build_warning(chunk_errors, truncated, total_chunks),
        )

    def _extract_chunk_with_retry(
        self, markdown: str, field_descriptions: dict[str, str], tracker: Optional["_ProgressTracker"] = None
    ) -> ExtractionResult:
        """Timeout (đọc phản hồi model) thường là tải đột biến tạm thời, không
        phải lỗi cố định — thử lại 1 lần với timeout dài hơn trước khi coi là
        lỗi hẳn.

        429 (vượt hạn mức request/phút của GreenNode) KHÁC lỗi thường: đó là lỗi TẠM THỜI có hẹn giờ — chờ đúng
        `Retry-After` (chặn mọi luồng gọi model này, xem `ModelRateLimiter.penalize`) rồi thử lại, KHÔNG tính vào
        lần thử lại của lỗi thường; tối đa `_MAX_RATE_LIMIT_RETRIES` lần thì mới coi là lỗi."""
        attempt = 1
        rate_limit_retries = 0
        while True:
            try:
                result = self._extract_chunk(
                    markdown, field_descriptions, timeout=self._timeout_for(markdown, attempt=attempt), tracker=tracker
                )
            except _RateLimited as limited:
                rate_limit_retries += 1
                if rate_limit_retries > _MAX_RATE_LIMIT_RETRIES:
                    return ExtractionResult(
                        success=False,
                        error=f"rate_limited: vẫn bị giới hạn tốc độ sau {_MAX_RATE_LIMIT_RETRIES} lần chờ",
                    )
                logger.warning(
                    "AI trả 429 (vượt hạn mức) — chờ %.0fs theo Retry-After rồi thử lại (lần %d/%d).",
                    limited.retry_after, rate_limit_retries, _MAX_RATE_LIMIT_RETRIES,
                )
                self._rate_limiter.penalize(self._model, limited.retry_after)
                continue
            if result.success or attempt >= 2:
                return result
            logger.info("Gọi AI lỗi (%s) — thử lại 1 lần với timeout dài hơn.", result.error)
            if tracker is not None:
                tracker.note_retry()
            attempt = 2

    def _timeout_for(self, chunk: str, attempt: int) -> float:
        """Đoạn càng gần kích thước tối đa (_MAX_CHUNK_CHARS) càng cần nhiều thời
        gian hơn — thời gian model trả lời tỉ lệ với SỐ BẢN GHI phải sinh JSON
        (value+confidence+evidence từng field), không chỉ độ dài input. Đo thật
        với qwen/qwen3.6-flash qua GreenNode MaaS (2026-09-20, markdown càng
        nhiều dòng bản ghi càng lâu gần tuyến tính): 10 bản ghi (~1300 ký tự
        input) ~31s, 25 bản ghi (~3300 ký tự) ~57s, 60 bản ghi (đầy 1 đoạn
        8000 ký tự) ~101s — hệ số 0.5+ratio (tối đa 1.5x) trước đây chỉ cho tối
        đa 45s ở đoạn đầy, LUÔN timeout với trang nhiều bản ghi. Hệ số mới hiệu
        chỉnh theo số liệu đo được, có biên an toàn ~20%; `self._timeout_seconds`
        (từ AI_TIMEOUT_SECONDS) luôn là mức sàn. Lần thử lại (attempt=2) nhân
        thêm 1.5 lần."""
        ratio = min(len(chunk) / _MAX_CHUNK_CHARS, 1.0) if _MAX_CHUNK_CHARS else 1.0
        scaled = max(self._timeout_seconds, self._timeout_seconds * (1.0 + 3.0 * ratio))
        return scaled * 1.5 if attempt >= 2 else scaled

    def _extract_chunk(
        self,
        markdown: str,
        field_descriptions: dict[str, str],
        timeout: Optional[float] = None,
        tracker: Optional["_ProgressTracker"] = None,
    ) -> ExtractionResult:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(markdown, field_descriptions)},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        # Delay theo hạn mức của model TRƯỚC khi gửi (không tính vào timeout đọc phản hồi).
        self._rate_limiter.acquire(self._model, on_wait=tracker.on_wait if tracker else None)
        owns_client = self._injected_client is None
        client = self._injected_client or httpx.Client(
            base_url=self._base_url, timeout=timeout if timeout is not None else self._timeout_seconds
        )
        if tracker is not None:
            tracker.begin_call()
        try:
            response = client.post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            self._learn_limit(response)
            if response.status_code == 429:
                raise _RateLimited(_retry_after_seconds(response))
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = _parse_json(content)
            records = _to_records(parsed, field_descriptions)
            return ExtractionResult(records=records, raw_response=content, success=True)
        except httpx.HTTPError as exc:
            logger.warning("Gọi AI extract lỗi mạng/HTTP: %s", exc)
            return ExtractionResult(success=False, error=str(exc))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            logger.warning("Response AI không hợp lệ: %s", exc)
            return ExtractionResult(success=False, error=f"invalid_ai_response: {exc}")
        finally:
            if tracker is not None:
                tracker.end_call()
            if owns_client:
                client.close()

    def _learn_limit(self, response: httpx.Response) -> None:
        """Header `x-ratelimit-limit-minute` của GreenNode là nguồn chuẩn cho hạn mức request/phút."""
        raw = response.headers.get("x-ratelimit-limit-minute")
        if raw and raw.strip().isdigit():
            self._rate_limiter.learn(self._model, int(raw.strip()))


_MAX_RATE_LIMIT_RETRIES = 4
_DEFAULT_RETRY_AFTER_SECONDS = 30.0
_MAX_RETRY_AFTER_SECONDS = 120.0


class _RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


def _retry_after_seconds(response: httpx.Response) -> float:
    for name in ("retry-after", "ratelimit-reset"):
        raw = response.headers.get(name)
        try:
            value = float(raw) if raw is not None else None
        except ValueError:
            value = None
        if value is not None and value >= 0:
            return min(value + 1.0, _MAX_RETRY_AFTER_SECONDS)
    return _DEFAULT_RETRY_AFTER_SECONDS


class _ProgressTracker:
    """Gom trạng thái các đoạn (đã xong, đang gọi model, đang chờ hạn mức) thành sự kiện cho UI. An toàn giữa các
    luồng vì chế độ "Nhanh" gọi các đoạn song song."""

    def __init__(self, callback: Optional[Callable[[dict], None]], model: str, total: int, truncated: bool) -> None:
        self._callback = callback
        self._model = model
        self._lock = threading.Lock()
        self.total = total
        self.truncated = truncated
        self.done = 0
        self.failed = 0
        self.retries = 0
        self.calling = 0
        self.current: Optional[int] = None
        self.waiting: dict[int, float] = {}
        self._emit()

    def _emit(self) -> None:
        if self._callback is None:
            return
        wait = round(min(self.waiting.values())) if self.waiting else 0
        safe_emit(self._callback, {
            "phase": "ai", "ai_model": self._model, "ai_chunks_total": self.total,
            "ai_chunks_done": self.done, "ai_chunks_failed": self.failed, "ai_retries": self.retries,
            "ai_calling": self.calling, "ai_waiting": len(self.waiting), "ai_wait_seconds": wait,
            "ai_truncated": self.truncated, "ai_current_chunk": self.current,
        })

    def set_current(self, index: int) -> None:
        with self._lock:
            self.current = index
            self._emit()

    def on_wait(self, seconds: float) -> None:
        with self._lock:
            self.waiting[threading.get_ident()] = seconds
            self._emit()

    def begin_call(self) -> None:
        with self._lock:
            self.waiting.pop(threading.get_ident(), None)
            self.calling += 1
            self._emit()

    def end_call(self) -> None:
        with self._lock:
            self.calling = max(self.calling - 1, 0)
            self._emit()

    def note_retry(self) -> None:
        with self._lock:
            self.retries += 1
            self._emit()

    def chunk_done(self, success: bool) -> None:
        with self._lock:
            self.done += 1
            if not success:
                self.failed += 1
            self._emit()


def _warn_if_base_url_missing_v1_suffix(base_url: str) -> None:
    """GreenNode MaaS yêu cầu base URL kết thúc bằng `/v1` (đã xác nhận qua
    docs.greennode.ai) — thiếu hậu tố này khiến mọi request 404 ở runtime mà
    lỗi rất khó đoán ra nguyên nhân. Chỉ cảnh báo (không raise) vì có thể đang
    trỏ tới 1 proxy/gateway khác có quy ước path riêng."""
    if base_url and not base_url.rstrip("/").endswith("/v1"):
        logger.warning(
            "AI_BASE_URL (%s) không kết thúc bằng '/v1' — endpoint GreenNode MaaS "
            "thật yêu cầu dạng 'https://<host>/v1'. Kiểm tra lại nếu request bị 404.",
            base_url,
        )


_MAX_CHUNK_CHARS = 8000
_MAX_CHUNKS = 6


def _split_markdown(markdown: str) -> tuple[list[str], bool]:
    """Chia markdown thành các đoạn <= _MAX_CHUNK_CHARS theo ranh giới dòng (dòng
    quá dài tự cắt cứng). Tối đa _MAX_CHUNKS đoạn — vượt quá thì cắt bớt và trả
    `truncated=True` để gọi nơi báo cho người dùng (xem `_build_warning`)."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in markdown.split("\n"):
        pieces = [line[i:i + _MAX_CHUNK_CHARS] for i in range(0, len(line), _MAX_CHUNK_CHARS)] or [""]
        for piece in pieces:
            if current and size + len(piece) + 1 > _MAX_CHUNK_CHARS:
                chunks.append("\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece) + 1
    if current:
        chunks.append("\n".join(current))
    truncated = len(chunks) > _MAX_CHUNKS
    if truncated:
        logger.warning("Trang quá dài (%d đoạn) — chỉ xử lý %d đoạn đầu.", len(chunks), _MAX_CHUNKS)
        chunks = chunks[:_MAX_CHUNKS]
    return (chunks or [""]), truncated


def _build_warning(chunk_errors: list[str], truncated: bool, total_chunks: int) -> Optional[str]:
    parts = []
    if chunk_errors:
        parts.append(
            f"{len(chunk_errors)}/{total_chunks} đoạn lỗi sau khi thử lại, đã bỏ qua (giữ các đoạn còn lại): "
            + "; ".join(chunk_errors)
        )
    if truncated:
        parts.append(
            f"Trang quá dài — chỉ xử lý {_MAX_CHUNKS} đoạn đầu (~{_MAX_CHUNKS * _MAX_CHUNK_CHARS} ký tự); "
            "phần cuối trang chưa được trích xuất."
        )
    return " | ".join(parts) if parts else None


def _build_user_prompt(markdown: str, field_descriptions: dict[str, str]) -> str:
    fields_desc = "\n".join(f"- {name}: {desc}" for name, desc in field_descriptions.items())
    _MAX_MD = 8000
    if len(markdown) > _MAX_MD:
        markdown = markdown[:_MAX_MD] + "\n\n[... nội dung còn lại bị cắt để giới hạn thời gian xử lý]"
    return (
        f"Các field cần trích xuất:\n{fields_desc}\n\n"
        f"Nội dung trang (đã làm sạch, dạng Markdown):\n\"\"\"\n{markdown}\n\"\"\"\n\n"
        f"Trả về 1 JSON array, mỗi phần tử là 1 object với key là tên field, "
        f"value là object có dạng {{\"value\": ..., \"confidence\": ..., "
        f"\"evidence\": ...}}. Trang có thể có NHIỀU bảng cùng cấu trúc — "
        f"trích xuất TẤT CẢ bản ghi từ TẤT CẢ bảng, không bỏ sót. "
        f"Tối đa 100 bản ghi."
    )


def _parse_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Fallback 1: model trả thêm text/markdown fence — lấy đoạn JSON đầu tiên.
    match = re.search(r"[\[{].*[\]}]", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback 2: response bị truncate (max_tokens cắt giữa chừng) —
    # tìm record hoàn chỉnh cuối cùng, cắt bỏ phần dở dang, đóng array.
    repaired = _repair_truncated_json(content)
    if repaired is not None:
        logger.warning("AI response bị truncate — đã repair (%d -> %d chars).",
                        len(content), len(repaired))
        return json.loads(repaired)

    raise ValueError(f"không parse được JSON từ AI response ({len(content)} chars)")


def _repair_truncated_json(content: str) -> Optional[str]:
    """Repair JSON array bị truncate bằng cách scan tracking string state,
    tìm } đóng record hoàn chỉnh cuối cùng (không nằm trong string)."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    if not text.startswith("["):
        return None

    in_string = False
    escape = False
    depth = 0
    last_close = -1
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{" or ch == "[":
            depth += 1
        elif ch == "}" or ch == "]":
            depth -= 1
            if ch == "}" and depth == 1:
                last_close = i

    if last_close <= 0:
        return None
    truncated = text[:last_close + 1].rstrip().rstrip(",")
    return truncated + "]"


def _to_records(
    parsed: Any, field_descriptions: dict[str, str]
) -> list[dict[str, FieldExtraction]]:
    # AI trả về array → mỗi phần tử là 1 record.
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        # Backward compat: AI trả về single object → wrap thành array 1 phần tử.
        items = [parsed]
    else:
        raise ValueError(f"response AI không phải JSON array/object: {parsed!r}")

    records: list[dict[str, FieldExtraction]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        records.append(_to_field_extractions(item, field_descriptions))
    return records


def _to_field_extractions(
    item: dict[str, Any], field_descriptions: dict[str, str]
) -> dict[str, FieldExtraction]:
    # Model đôi khi trả key khác hoa/thường hoặc thừa khoảng trắng so với tên
    # field yêu cầu (vd. "quote" thay vì "Quote") dù đã trích đúng giá trị —
    # so khớp không phân biệt hoa/thường thay vì exact-match để field không bị
    # rơi về None/confidence 0 chỉ vì lệch cách viết hoa.
    normalized_item = {str(key).strip().lower(): value for key, value in item.items()}

    fields: dict[str, FieldExtraction] = {}
    unmatched: list[str] = []
    for name in field_descriptions:
        entry = normalized_item.get(name.strip().lower())
        if not isinstance(entry, dict):
            fields[name] = FieldExtraction(value=None, confidence=0.0, evidence=None)
            unmatched.append(name)
            continue
        fields[name] = FieldExtraction(
            value=entry.get("value"),
            confidence=_safe_confidence(entry.get("confidence")),
            evidence=entry.get("evidence"),
        )
    if unmatched:
        logger.warning(
            "AI response không có field %s (đã so khớp không phân biệt hoa/thường) "
            "— response thật trả về key: %s", unmatched, list(item.keys()),
        )
    return fields


def _safe_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return min(max(value, 0.0), 1.0)
