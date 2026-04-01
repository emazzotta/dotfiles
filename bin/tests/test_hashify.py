import hashlib

import pytest


@pytest.fixture
def hashify(load_script):
    return load_script("hashify")


class TestHashData:
    @pytest.mark.parametrize("algo,data,expected_len", [
        ("sha256", b"test", 64),
        ("md5", b"test", 32),
        ("sha1", b"test", 40),
        ("sha512", b"test", 128),
    ])
    def test_algorithm_output_length(self, hashify, algo, data, expected_len):
        result = hashify.hash_data(algo, data)
        assert len(result) == expected_len
        assert all(c in "0123456789abcdef" for c in result)

    def test_sha256_known_value(self, hashify):
        assert hashify.hash_data("sha256", b"test") == \
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

    def test_md5_known_value(self, hashify):
        assert hashify.hash_data("md5", b"test") == "098f6bcd4621d373cade4e832627b4f6"

    def test_sha512_matches_hashlib(self, hashify):
        data = b"hello world"
        assert hashify.hash_data("sha512", data) == hashlib.sha512(data).hexdigest()

    def test_empty_data(self, hashify):
        assert hashify.hash_data("sha256", b"") == \
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_unicode_data(self, hashify):
        result = hashify.hash_data("sha256", "Hello 世界".encode("utf-8"))
        assert len(result) == 64

    def test_file_hashing(self, hashify, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"test content")
        result = hashify.hash_data("sha256", f.read_bytes())
        assert result == hashlib.sha256(b"test content").hexdigest()

    def test_unsupported_algorithm(self, hashify):
        with pytest.raises(SystemExit):
            hashify.hash_data("nonexistent_algo", b"test")
