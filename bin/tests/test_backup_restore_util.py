from pathlib import Path

import pytest


@pytest.fixture
def mod(load_script):
    return load_script("backup_restore_util")


class TestDmgFormat:
    @pytest.mark.parametrize("value,expected_value", [
        ("compressed", "UDZO"),
        ("UDZO", "UDZO"),
        ("raw", "UDRW"),
        ("UDRW", "UDRW"),
        ("readonly", "UDRO"),
        ("UDRO", "UDRO"),
    ])
    def test_parse_valid(self, mod, value, expected_value):
        result = mod.DmgFormat.parse(value)
        assert result.value == expected_value

    def test_parse_invalid_exits(self, mod):
        with pytest.raises(SystemExit):
            mod.DmgFormat.parse("invalid")

    def test_description(self, mod):
        assert "compressed" in mod.DmgFormat.COMPRESSED.description()
        assert "read/write" in mod.DmgFormat.RAW.description()
        assert "read-only" in mod.DmgFormat.READONLY.description()


class TestConvertSizeToBytes:
    @pytest.mark.parametrize("size,expected", [
        ("1K", 1_000),
        ("1KB", 1_000),
        ("10M", 10_000_000),
        ("2G", 2_000_000_000),
        ("1T", 1_000_000_000_000),
        ("1.5G", 1_500_000_000),
        ("500", 500),
    ])
    def test_conversions(self, mod, size, expected):
        assert mod.convert_size_to_bytes(size) == expected

    def test_empty_string(self, mod):
        assert mod.convert_size_to_bytes("") == 0

    def test_non_numeric(self, mod):
        assert mod.convert_size_to_bytes("abc") == 0


class TestExtractVolumeName:
    @pytest.mark.parametrize("volume,expected", [
        ("/Volumes/My Drive", "My_Drive"),
        ("/Volumes/USB", "USB"),
        ("/Volumes/path/with/slash", "slash"),
    ])
    def test_extraction(self, mod, volume, expected):
        assert mod.extract_volume_name(volume) == expected


class TestIsMountedVolume:
    def test_volumes_path(self, mod):
        assert mod.is_mounted_volume("/Volumes/USB") is True

    def test_non_volumes_path(self, mod):
        assert mod.is_mounted_volume("/tmp/data") is False

    def test_empty_string(self, mod):
        assert mod.is_mounted_volume("") is False


class TestCalculateDirectorySize:
    def test_with_files(self, mod, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world!")
        total, count = mod.calculate_directory_size(tmp_path)
        assert total == 11
        assert count == 2

    def test_empty_directory(self, mod, tmp_path):
        total, count = mod.calculate_directory_size(tmp_path)
        assert total == 0
        assert count == 0

    def test_nested_files(self, mod, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").write_text("data")
        total, count = mod.calculate_directory_size(tmp_path)
        assert total == 4
        assert count == 1


class TestFindFileSize:
    def test_existing_file(self, mod, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = mod.find_file_size(str(f))
        assert result == 11

    def test_nonexistent_file(self, mod):
        result = mod.find_file_size("/tmp/nonexistent_12345.img")
        assert result is None
