import pytest


@pytest.fixture
def mod(load_script):
    return load_script("privateconf.py")


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    def _write(content):
        path = tmp_path / "private.env"
        path.write_text(content)
        monkeypatch.setenv("DOTFILES_PRIVATE_ENV", str(path))
        return path
    return _write


class TestLoad:
    def test_should_read_key_value_pairs(self, mod, config_file):
        config_file("HOST=example.internal\nPORT=8080\n")

        assert mod.load() == {"HOST": "example.internal", "PORT": "8080"}

    def test_should_ignore_comments_and_blank_lines(self, mod, config_file):
        config_file("# a comment\n\nHOST=example.internal\n\n   # indented comment\n")

        assert mod.load() == {"HOST": "example.internal"}

    def test_should_strip_surrounding_quotes(self, mod, config_file):
        config_file('HOST="example.internal"\nSHARE=\'smb://host/share\'\n')

        assert mod.load() == {"HOST": "example.internal", "SHARE": "smb://host/share"}

    def test_should_keep_equals_signs_inside_the_value(self, mod, config_file):
        config_file("URL=https://example.internal/?a=1&b=2\n")

        assert mod.load() == {"URL": "https://example.internal/?a=1&b=2"}

    def test_should_return_empty_mapping_when_the_file_is_absent(self, mod, tmp_path, monkeypatch):
        monkeypatch.setenv("DOTFILES_PRIVATE_ENV", str(tmp_path / "missing.env"))

        assert mod.load() == {}


class TestValue:
    def test_should_return_the_configured_value(self, mod, config_file):
        config_file("HOST=example.internal\n")

        assert mod.value("HOST") == "example.internal"

    def test_should_return_the_default_when_the_key_is_absent(self, mod, config_file):
        config_file("HOST=example.internal\n")

        assert mod.value("MISSING", "fallback") == "fallback"

    def test_should_return_empty_string_when_no_default_is_given(self, mod, config_file):
        config_file("HOST=example.internal\n")

        assert mod.value("MISSING") == ""

    def test_should_prefer_the_environment_over_the_file(self, mod, config_file, monkeypatch):
        config_file("HOST=from-file\n")
        monkeypatch.setenv("HOST", "from-environment")

        assert mod.value("HOST") == "from-environment"
