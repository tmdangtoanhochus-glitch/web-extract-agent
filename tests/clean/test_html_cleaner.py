from src.clean.html_cleaner import CleanedDocument, clean_html


def test_strips_script_style_nav_footer():
    html = """
    <html><head><title>Trang test</title>
    <style>body{color:red}</style>
    <script>alert('x')</script>
    </head>
    <body>
      <nav>menu</nav>
      <header>header content</header>
      <p>Nội dung chính cần giữ lại.</p>
      <footer>footer content</footer>
    </body></html>
    """
    doc = clean_html(html)

    assert isinstance(doc, CleanedDocument)
    assert doc.title == "Trang test"
    assert "Nội dung chính cần giữ lại." in doc.markdown
    assert "alert" not in doc.markdown
    assert "color:red" not in doc.markdown
    assert "menu" not in doc.markdown
    assert "header content" not in doc.markdown
    assert "footer content" not in doc.markdown


def test_headings_and_paragraphs_render_as_markdown():
    html = "<html><body><h1>Tiêu đề</h1><p>Đoạn văn.</p></body></html>"
    doc = clean_html(html)

    assert "# Tiêu đề" in doc.markdown
    assert "Đoạn văn." in doc.markdown


def test_unordered_list_renders_with_dashes():
    html = "<html><body><ul><li>Item A</li><li>Item B</li></ul></body></html>"
    doc = clean_html(html)

    assert "- Item A" in doc.markdown
    assert "- Item B" in doc.markdown


def test_ordered_list_renders_with_numbers():
    html = "<html><body><ol><li>Bước 1</li><li>Bước 2</li></ol></body></html>"
    doc = clean_html(html)

    assert "1. Bước 1" in doc.markdown
    assert "2. Bước 2" in doc.markdown


def test_table_renders_as_markdown_table():
    html = """
    <table>
      <tr><th>Tên</th><th>Giá</th></tr>
      <tr><td>Táo</td><td>10000</td></tr>
      <tr><td>Cam</td><td>12000</td></tr>
    </table>
    """
    doc = clean_html(f"<html><body>{html}</body></html>")

    assert "| Tên | Giá |" in doc.markdown
    assert "| --- | --- |" in doc.markdown
    assert "| Táo | 10000 |" in doc.markdown
    assert "| Cam | 12000 |" in doc.markdown


def test_missing_title_returns_none():
    html = "<html><body><p>Không có title.</p></body></html>"
    doc = clean_html(html)

    assert doc.title is None


def test_length_fields_are_populated():
    html = "<html><body><p>abc</p></body></html>"
    doc = clean_html(html)

    assert doc.original_length == len(html)
    assert doc.cleaned_length == len(doc.markdown)
    assert doc.cleaned_length > 0


def test_div_span_layout_content_is_not_lost_when_page_also_has_unrelated_heading():
    """Regression cho bug docs/kien_audit/02 (2 người độc lập tìm ra cùng lúc):
    nội dung chính nằm trong div/span (không có <p> bao quanh), nhưng trang có
    sẵn <h1>/<p> khác KHÔNG liên quan (vd. tiêu đề trang, link "Login") ở chỗ
    khác. Trước fix, code coi "đã tìm thấy heading/p nào đó" là đủ và bỏ qua
    toàn bộ div/span, khiến AI nhận markdown gần như rỗng."""
    html = """
    <html><body>
      <h1>Quotes to Scrape</h1>
      <p>Login</p>
      <div class="quote">
        <span class="text">"Đời là bể khổ."</span>
        <span>by <small class="author">Albert Einstein</small></span>
        <div class="tags">Tags: change, thinking</div>
      </div>
    </body></html>
    """
    doc = clean_html(html)

    assert "Đời là bể khổ" in doc.markdown
    assert "Albert Einstein" in doc.markdown
    assert "change" in doc.markdown


def test_repeated_div_items_stay_separated_not_merged_into_one_line():
    """Nhiều mục lặp lại kiểu <div class="quote"> liên tiếp (trang danh sách)
    phải tách dòng riêng — không dính chung 1 dòng, để AI phân biệt được từng
    mục khi trích xuất multi-record."""
    html = """
    <html><body>
      <div class="quote"><span>Quote A</span></div>
      <div class="quote"><span>Quote B</span></div>
    </body></html>
    """
    doc = clean_html(html)

    assert "Quote A" in doc.markdown
    assert "Quote B" in doc.markdown
    lines = [line for line in doc.markdown.split("\n\n") if line.strip()]
    assert any("Quote A" in line and "Quote B" not in line for line in lines)


def test_empty_html_does_not_crash():
    doc = clean_html("")

    assert doc.markdown == ""
    assert doc.title is None
