"""Test download_image() bằng httpx.MockTransport — không tải ảnh thật."""
import httpx
import pytest

from src.storage.image_downloader import download_image


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_image_saves_file_and_returns_relative_path(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8\xff fake jpeg")

    result = download_image(
        "https://example.com/photo.jpg",
        record_key="ds1",
        field_name="anh_chinh",
        images_root=tmp_path,
        client=_client(handler),
    )

    assert result.success is True
    assert result.local_path.endswith(".jpg")
    saved_file = tmp_path / result.local_path
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"\xff\xd8\xff fake jpeg"


def test_download_image_rejects_non_http_url(tmp_path):
    result = download_image(
        "file:///etc/passwd", record_key="ds1", field_name="anh", images_root=tmp_path
    )

    assert result.success is False
    assert "http" in result.error.lower()


def test_download_image_rejects_non_image_content_type(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")

    result = download_image(
        "https://example.com/not-an-image",
        record_key="ds1",
        field_name="anh",
        images_root=tmp_path,
        client=_client(handler),
    )

    assert result.success is False
    assert "Content-Type" in result.error


def test_download_image_rejects_oversized_file(tmp_path):
    big_content = b"x" * (15 * 1024 * 1024 + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=big_content)

    result = download_image(
        "https://example.com/huge.jpg",
        record_key="ds1",
        field_name="anh",
        images_root=tmp_path,
        client=_client(handler),
    )

    assert result.success is False
    assert "giới hạn" in result.error


def test_download_image_http_error_returns_failure_not_raise(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    result = download_image(
        "https://example.com/missing.jpg",
        record_key="ds1",
        field_name="anh",
        images_root=tmp_path,
        client=_client(handler),
    )

    assert result.success is False
    assert result.local_path is None


def test_download_image_network_error_is_caught_not_raised(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    result = download_image(
        "https://example.com/photo.jpg",
        record_key="ds1",
        field_name="anh",
        images_root=tmp_path,
        client=_client(handler),
    )

    assert result.success is False
    assert "boom" in result.error


def test_download_image_different_calls_produce_unique_filenames(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"png-bytes")

    result1 = download_image(
        "https://example.com/a.png", "ds1", "anh", images_root=tmp_path, client=_client(handler)
    )
    result2 = download_image(
        "https://example.com/a.png", "ds1", "anh", images_root=tmp_path, client=_client(handler)
    )

    assert result1.local_path != result2.local_path
