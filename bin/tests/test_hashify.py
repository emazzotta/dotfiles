import sys
import hashlib
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import hashify


def test_hash_data_sha256():
    data = b"test"
    result = hashify.hash_data("sha256", data)
    expected = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert result == expected


def test_hash_data_md5():
    data = b"test"
    result = hashify.hash_data("md5", data)
    expected = "098f6bcd4621d373cade4e832627b4f6"
    assert result == expected


def test_hash_data_sha512():
    data = b"hello world"
    result = hashify.hash_data("sha512", data)
    expected = hashlib.sha512(b"hello world").hexdigest()
    assert result == expected


def test_hash_empty_data():
    data = b""
    result = hashify.hash_data("sha256", data)
    expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert result == expected


def test_hash_unicode_data():
    data = "Hello 世界".encode('utf-8')
    result = hashify.hash_data("sha256", data)
    assert len(result) == 64
    assert all(c in '0123456789abcdef' for c in result)


def test_hash_data_with_file():
    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
        f.write(b"test content")
        temp_path = Path(f.name)

    try:
        data = temp_path.read_bytes()
        result = hashify.hash_data("sha256", data)
        expected = hashlib.sha256(b"test content").hexdigest()
        assert result == expected
    finally:
        temp_path.unlink()


def test_different_algorithms():
    data = b"test"

    sha256_result = hashify.hash_data("sha256", data)
    assert len(sha256_result) == 64

    md5_result = hashify.hash_data("md5", data)
    assert len(md5_result) == 32

    sha1_result = hashify.hash_data("sha1", data)
    assert len(sha1_result) == 40
