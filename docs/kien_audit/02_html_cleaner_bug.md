# 02 — HTML Cleaner Bug: Missing Content from div/span Elements

> **Date:** 2026-09-16  
> **Reporter:** Kiên  
> **File:** `src/clean/html_cleaner.py`  
> **Severity:** HIGH — causes AI extraction to return `null` for all fields

---

## 1. Symptom

Crawling `https://quotes.toscrape.com/` with fields `quote`, `author`, `tag` returns:

```json
{
  "status": "saved",
  "data": {"quote": null, "author": null, "tag": null},
  "confidence": 1.0
}
```

All field values are `null`. AI extraction appears to "succeed" but extracts nothing.

API endpoint `POST /crawl` returns **502 Bad Gateway** when called from the running backend.

---

## 2. Root Cause

### 2.1. HTML Cleaner Only Renders Specific Block Tags

**File:** `src/clean/html_cleaner.py:70-104`

The `_render_markdown()` function only searches for and renders these HTML tags:

```python
root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table"], recursive=True)
```

It does **NOT** render:
- `<div>` — the most common container element on the web
- `<span>` — the most common inline text wrapper
- `<a>` — links
- `<small>` — small text (used for author names on quotes.toscrape.com)

### 2.2. quotes.toscrape.com HTML Structure

The page `https://quotes.toscrape.com/` stores quotes in:

```html
<div class="quote">
    <span class="text">"The world as we have created it is a process..."</span>
    <span>by <small class="author">Albert Einstein</small>
        <a href="/author/Albert-Einstein">(about)</a></span>
    <div class="tags">
        Tags:
        <a class="tag" href="/tag/change/page/1/">change</a>
        <a class="tag" href="/tag/deep-thoughts/page/1/">deep-thoughts</a>
    </div>
</div>
```

**None of these elements** (`div`, `span`, `small`, `a`) are in the renderable tag list.

### 2.3. Cleaned Markdown Result

The cleaner finds only:
- `<h1>Quotes to Scrape</h1>` → `# Quotes to Scrape`
- `<h2>Top Ten tags</h2>` → `## Top Ten tags`

**Cleaned markdown = 42 characters:**
```
# Quotes to Scrape

Login

## Top Ten tags
```

The actual quote content (10 quotes with text, author, tags) is **completely missing**.

### 2.4. AI Receives Empty Content

The AI client (`src/ai/greennode_client.py:128-135`) builds a prompt with the cleaned markdown:

```
Nội dung trang (đã làm sạch, dạng Markdown):
"""
# Quotes to Scrape

Login

## Top Ten tags
"""
```

The AI correctly returns `null` for all fields because there is no quote data in the text it receives.

### 2.5. Confidence = 1.0 Explained

The AI returns `{"value": null, "confidence": 1, "evidence": null}` for each field — it's "confident" that the fields don't exist in the provided text. The pipeline calculates `overall_confidence = 1.0`, so `needs_review = False` — no warning is shown to the user.

### 2.6. API 502 Error

When calling `POST /crawl` through the running backend, the 502 error occurs because:
- The backend process may not have loaded `.env` correctly (different working directory)
- Or the AI call times out with the default 30s timeout when processing the full HTML
- The pipeline returns `status="extract_failed"` → API raises `HTTPException(502)`

---

## 3. Impact

- **All websites** that store content in `<div>`, `<span>`, or other non-block elements are affected.
- This includes most modern websites (React, Vue, etc.) which heavily use `<div>` and `<span>`.
- The bug makes the core crawl-and-extract functionality **unusable** for most real-world sites.
- Only sites with content in `<p>`, `<h1>-<h6>`, `<ul>`, `<ol>`, `<table>` work correctly.

---

## 4. Fix

### 4.1. Approach

Add `div` and `span` to the list of renderable tags. For div/span elements:
- **Container div/span** (contains child renderable elements like `p`, `h1-h6`, `ul`, `ol`, `table`, or nested `div`/`span`): **skip** — children will be rendered separately.
- **Leaf div/span** (no child renderable elements): **render text content** as a paragraph block.

This avoids duplicate text while capturing content in non-standard elements.

### 4.2. Changes to `src/clean/html_cleaner.py`

1. **Add `"div"` and `"span"` to `find_all` search list** (line 74)
2. **Add `"p"` to ancestor skip check** (line 79) — prevents spans inside `<p>` from duplicating text
3. **Add leaf div/span rendering logic** — skip containers, render leaf text
4. **Add `_RENDERABLE_TAGS` constant** — shared between `find_all` and child check

### 4.3. Expected Result After Fix

For `https://quotes.toscrape.com/`, the cleaned markdown should include:

```markdown
# Quotes to Scrape

"The world as we have created it is a process of our thinking. It cannot be changed without changing our thinking."

by Albert Einstein (about)

Tags: change deep-thoughts thinking world

...
```

AI should then correctly extract `quote`, `author`, and `tag` values.

---

## 5. Test Case

```
URL: https://quotes.toscrape.com/
Fields:
  quote: "The quote text shown on the page"
  author: "The author of the quote"
  tag: "The tags associated with the quote"
Expected: quote != null, author != null, tag != null
```

---

## 6. Related Files

| File | Role |
|------|------|
| `src/clean/html_cleaner.py` | **Bug location** — `_render_markdown()` function |
| `src/pipeline.py:75-85` | `fetch_and_clean()` — calls `clean_html()`, computes `content_hash` from cleaned markdown |
| `src/ai/greennode_client.py:128-135` | `_build_user_prompt()` — uses cleaned markdown to build AI prompt |
| `src/extract/structured_data.py` | Structured data extraction (JSON-LD/Open Graph) — runs on raw HTML, not affected |
| `tests/clean/test_html_cleaner.py` | Existing tests — need to verify no regression |
