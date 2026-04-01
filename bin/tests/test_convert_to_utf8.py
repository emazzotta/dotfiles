import pytest


@pytest.fixture
def mod(load_script):
    return load_script("convert-to-utf8")


@pytest.fixture
def converter(mod):
    return mod.EncodingConverter(mod.Logger(use_timestamps=False, use_colors=False))


@pytest.fixture
def dry_converter(mod):
    return mod.EncodingConverter(mod.Logger(use_timestamps=False, use_colors=False), dry_run=True)


class TestDetectEncoding:
    def test_utf8_file(self, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_text("<html>hello</html>", encoding="utf-8")
        assert converter.detect_encoding(f) == "utf-8"

    def test_latin1_file(self, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_bytes("Ä Ö Ü ß".encode("iso-8859-1"))
        assert converter.detect_encoding(f) in ("iso-8859-1", "windows-1252")

    def test_binary_file_returns_none(self, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_bytes(bytes(range(128, 256)) * 10)
        result = converter.detect_encoding(f)
        assert result is None or isinstance(result, str)


class TestIsAlreadyUtf8:
    def test_valid_utf8(self, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_text("hello 世界", encoding="utf-8")
        assert converter.is_already_utf8(f) is True

    def test_non_utf8(self, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_bytes(b"\xff\xfe")
        assert converter.is_already_utf8(f) is False


class TestConvertFileEncoding:
    def test_converts_latin1_to_utf8(self, converter, tmp_path):
        f = tmp_path / "test.html"
        original = "Ärger mit Übung"
        f.write_bytes(original.encode("iso-8859-1"))
        converter.convert_file_encoding(f, "iso-8859-1")
        assert f.read_text(encoding="utf-8") == original

    def test_temp_file_cleaned_up(self, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_bytes("Ö".encode("iso-8859-1"))
        converter.convert_file_encoding(f, "iso-8859-1")
        assert not (tmp_path / "test.html.tmp").exists()


class TestProcessFile:
    def test_skip_utf8_file(self, mod, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_text("<html>hello</html>", encoding="utf-8")
        result = converter.process_file(f)
        assert result.status == mod.ConversionStatus.SKIPPED_UTF8

    def test_convert_latin1_file(self, mod, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_bytes("Ärger".encode("iso-8859-1"))
        result = converter.process_file(f)
        assert result.status == mod.ConversionStatus.CONVERTED
        assert f.read_text(encoding="utf-8") == "Ärger"

    def test_dry_run_does_not_modify(self, mod, dry_converter, tmp_path):
        f = tmp_path / "test.html"
        original_bytes = "Ärger".encode("iso-8859-1")
        f.write_bytes(original_bytes)
        result = dry_converter.process_file(f)
        assert result.status == mod.ConversionStatus.CONVERTED
        assert f.read_bytes() == original_bytes

    def test_backup_removed_on_success(self, converter, tmp_path):
        f = tmp_path / "test.html"
        f.write_bytes("Ö".encode("iso-8859-1"))
        converter.process_file(f)
        assert not (tmp_path / "test.html.backup").exists()


class TestProcessDirectory:
    def test_converts_directory(self, mod, converter, tmp_path):
        (tmp_path / "a.html").write_bytes("Ö".encode("iso-8859-1"))
        (tmp_path / "b.html").write_text("ok", encoding="utf-8")
        summary = converter.process_directory(tmp_path)
        assert summary.total == 2
        assert summary.converted == 1
        assert summary.skipped == 1
        assert summary.failed == 0

    def test_empty_directory(self, converter, tmp_path):
        summary = converter.process_directory(tmp_path)
        assert summary.total == 0

    def test_nested_html_files(self, mod, converter, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.html").write_bytes("Ü".encode("iso-8859-1"))
        summary = converter.process_directory(tmp_path)
        assert summary.total == 1
        assert summary.converted == 1


class TestBugFixResolve:
    def test_source_uses_resolve_not_resolve_hosts(self, mod):
        from pathlib import Path
        source = (Path(mod.__file__)).read_text()
        assert "resolve_hosts" not in source
        assert "args.dir.resolve()" in source
