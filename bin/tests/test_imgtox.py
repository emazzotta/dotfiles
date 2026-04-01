import pytest


@pytest.fixture
def mod(load_script):
    return load_script("imgtox")


class TestFindImageFiles:
    def test_finds_common_formats(self, mod, tmp_path):
        for name in ("a.jpg", "b.png", "c.gif", "d.webp", "e.txt"):
            (tmp_path / name).touch()
        results = mod.find_image_files(tmp_path)
        names = {r.name for r in results}
        assert "a.jpg" in names
        assert "b.png" in names
        assert "c.gif" in names
        assert "d.webp" in names
        assert "e.txt" not in names

    def test_finds_uppercase_extensions(self, mod, tmp_path):
        (tmp_path / "photo.JPG").touch()
        results = mod.find_image_files(tmp_path)
        assert any(r.name == "photo.JPG" for r in results)

    def test_recursive_search(self, mod, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.png").touch()
        results = mod.find_image_files(tmp_path)
        assert any(r.name == "nested.png" for r in results)

    def test_empty_directory(self, mod, tmp_path):
        assert mod.find_image_files(tmp_path) == []
