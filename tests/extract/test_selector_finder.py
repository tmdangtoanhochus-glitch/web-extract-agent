"""Test module tìm/áp dụng CSS selector cho cache chiến lược extract theo
domain (CLAUDE.md mục 5) — thuần rule-based, không cần AI/mạng thật."""
from src.extract.selector_finder import apply_selector, find_selector

_HTML = """
<html><body>
  <div class="wrap">
    <span class="name">SJC 1L</span>
    <div class="prices">
      <span class="price-buy">78.200.000</span>
      <span class="price-sell">79.900.000</span>
    </div>
  </div>
</body></html>
"""


def test_find_selector_locates_value_and_apply_selector_returns_it_back():
    selector = find_selector(_HTML, "79.900.000")

    assert selector is not None
    assert apply_selector(_HTML, selector) == "79.900.000"


def test_find_selector_picks_most_specific_element_not_a_large_ancestor():
    selector = find_selector(_HTML, "78.200.000")

    # phải trỏ đúng <span class="price-buy">, không phải <div class="prices">
    # hay <div class="wrap"> (cũng chứa text này qua get_text() của con cháu).
    assert apply_selector(_HTML, selector) == "78.200.000"
    assert selector.split(" > ")[-1].startswith("span")


def test_find_selector_returns_none_when_value_not_present():
    assert find_selector(_HTML, "999.999.999") is None


def test_find_selector_normalizes_whitespace_when_matching():
    html = "<html><body><p>  giá   79.900.000   đồng  </p></body></html>"

    selector = find_selector(html, "79.900.000 đồng")

    assert selector is not None
    assert "79.900.000 đồng" in apply_selector(html, selector)


def test_apply_selector_returns_none_when_selector_no_longer_matches():
    other_html = "<html><body><p>trang đã đổi cấu trúc hoàn toàn</p></body></html>"
    selector = find_selector(_HTML, "79.900.000")

    assert apply_selector(other_html, selector) is None


def test_apply_selector_returns_none_for_syntactically_invalid_selector():
    assert apply_selector(_HTML, "###not a valid selector[[[") is None


def test_apply_selector_returns_none_for_empty_element_text():
    html = "<html><body><span class='empty'></span></body></html>"

    assert apply_selector(html, "span:nth-of-type(1)") is None


def test_selector_survives_content_change_at_same_dom_position():
    """Mô phỏng đúng use-case cache: giá đổi nhưng vị trí/cấu trúc DOM giữ
    nguyên — selector cache từ lần cào trước vẫn phải áp lại đúng."""
    selector = find_selector(_HTML, "79.900.000")

    updated_html = _HTML.replace("79.900.000", "85.000.000")

    assert apply_selector(updated_html, selector) == "85.000.000"
