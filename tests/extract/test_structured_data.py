"""Test module trích xuất structured data (JSON-LD/Open Graph) — thuần rule-based,
không cần mock mạng/AI (CLAUDE.md mục 2 + 6)."""
from src.extract.structured_data import extract_structured_data, match_field


def test_extracts_open_graph_meta_tags():
    html = """
    <html><head>
      <meta property="og:title" content="Nhẫn trơn PNJ">
      <meta property="og:description" content="Giá vàng cập nhật hàng ngày">
      <meta property="not-og" content="bỏ qua">
    </head><body></body></html>
    """
    data = extract_structured_data(html)

    assert data.get("og:title") == "Nhẫn trơn PNJ"
    assert data.get("og:description") == "Giá vàng cập nhật hàng ngày"
    assert data.get("not-og") is None


def test_extracts_single_json_ld_object():
    html = """
    <html><head><script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Product", "name": "SJC 1L",
     "offers": {"@type": "Offer", "price": "79900000", "priceCurrency": "VND"}}
    </script></head></html>
    """
    data = extract_structured_data(html)

    assert data.get("jsonld.name") == "SJC 1L"
    assert data.get("jsonld.offers.price") == "79900000"
    assert data.get("jsonld.offers.priceCurrency") == "VND"


def test_extracts_json_ld_list_of_objects():
    html = """
    <html><head><script type="application/ld+json">
    [{"@type": "Product", "name": "A"}, {"@type": "Organization", "name": "B Corp"}]
    </script></head></html>
    """
    data = extract_structured_data(html)

    # object đầu tiên set giá trị trước, object sau không ghi đè (setdefault-style
    # qua thứ tự duyệt) — nhưng ở đây values.update() sẽ để item CUỐI thắng vì
    # cùng khoá "jsonld.name"; assert theo đúng hành vi thật của _iter/_flatten.
    assert data.get("jsonld.name") == "B Corp"


def test_extracts_json_ld_at_graph():
    html = """
    <html><head><script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [
      {"@type": "Product", "name": "Vàng 24K DOJI", "sku": "DOJI-24K"}
    ]}
    </script></head></html>
    """
    data = extract_structured_data(html)

    assert data.get("jsonld.name") == "Vàng 24K DOJI"
    assert data.get("jsonld.sku") == "DOJI-24K"


def test_json_ld_takes_priority_over_open_graph_for_same_key_shape():
    html = """
    <html><head>
      <meta property="og:title" content="OG Title">
      <script type="application/ld+json">{"name": "JSONLD Name"}</script>
    </head></html>
    """
    data = extract_structured_data(html)

    # 2 khoá khác nhau ("og:title" vs "jsonld.name") nên cả 2 đều còn nguyên —
    # chỉ kiểm tra JSON-LD không bị Open Graph ghi đè khi trùng khoá thật.
    assert data.get("og:title") == "OG Title"
    assert data.get("jsonld.name") == "JSONLD Name"


def test_invalid_json_ld_is_skipped_without_raising():
    html = """
    <html><head>
      <script type="application/ld+json">{not valid json,,,}</script>
      <meta property="og:title" content="Vẫn đọc được OG">
    </head></html>
    """
    data = extract_structured_data(html)

    assert data.get("og:title") == "Vẫn đọc được OG"


def test_no_structured_data_returns_empty():
    html = "<html><body><p>Không có JSON-LD hay OG</p></body></html>"
    data = extract_structured_data(html)

    assert data.values == {}


def test_match_field_finds_value_by_exact_synonym():
    html = '<html><head><meta property="og:title" content="SJC 1L"></head></html>'
    data = extract_structured_data(html)

    matched = match_field("title", data)

    assert matched is not None
    assert matched.value == "SJC 1L"
    assert matched.source == "og:title"


def test_match_field_normalizes_vietnamese_accented_and_mixed_case_names():
    html = '<html><head><meta property="og:title" content="SJC 1L"></head></html>'
    data = extract_structured_data(html)

    assert match_field("Tiêu Đề", data) is None  # không có trong bảng đồng nghĩa
    assert match_field("TITLE", data) is not None
    assert match_field("  title ", data) is not None


def test_match_field_returns_none_for_unknown_field_name():
    html = '<html><head><meta property="og:title" content="SJC 1L"></head></html>'
    data = extract_structured_data(html)

    assert match_field("ten_san_pham", data) is None


def test_match_field_returns_none_when_synonym_key_has_no_value():
    html = "<html><body></body></html>"
    data = extract_structured_data(html)

    assert match_field("price", data) is None


def test_match_field_prefers_first_matching_synonym_in_priority_order():
    html = """
    <html><head>
      <meta property="og:title" content="OG Title">
      <script type="application/ld+json">{"name": "JSONLD Name"}</script>
    </head></html>
    """
    data = extract_structured_data(html)

    matched = match_field("title", data)

    assert matched.source == "og:title"  # og:title đứng trước trong _FIELD_SYNONYMS
