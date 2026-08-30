import pytest


@pytest.fixture
def mod(load_script):
    return load_script("siteconf.py")


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Points both layers at tmp_path so the shipped site.env never leaks in."""
    defaults = tmp_path / "defaults.env"
    override = tmp_path / "override.env"
    monkeypatch.setenv("DOTFILES_SITE_DEFAULTS", str(defaults))
    monkeypatch.setenv("DOTFILES_SITE_ENV", str(override))

    def _write(defaults_content=None, override_content=None):
        if defaults_content is not None:
            defaults.write_text(defaults_content)
        if override_content is not None:
            override.write_text(override_content)

    return _write


class TestParse:
    def test_should_read_key_value_pairs(self, mod, config, tmp_path):
        config(defaults_content="HOST=example.internal\nPORT=8080\n")

        assert mod.parse(tmp_path / "defaults.env") == {"HOST": "example.internal", "PORT": "8080"}

    def test_should_ignore_comments_and_blank_lines(self, mod, config, tmp_path):
        config(defaults_content="# a comment\n\nHOST=example.internal\n\n   # indented\n")

        assert mod.parse(tmp_path / "defaults.env") == {"HOST": "example.internal"}

    def test_should_strip_surrounding_quotes(self, mod, config, tmp_path):
        config(defaults_content='HOST="example.internal"\nSHARE=\'smb://host/share\'\n')

        assert mod.parse(tmp_path / "defaults.env") == {
            "HOST": "example.internal", "SHARE": "smb://host/share"}

    def test_should_keep_equals_signs_inside_the_value(self, mod, config, tmp_path):
        config(defaults_content="URL=https://example.internal/?a=1&b=2\n")

        assert mod.parse(tmp_path / "defaults.env") == {"URL": "https://example.internal/?a=1&b=2"}

    def test_should_return_empty_mapping_when_the_file_is_absent(self, mod, tmp_path):
        assert mod.parse(tmp_path / "missing.env") == {}


class TestLoad:
    def test_should_fall_back_to_the_defaults(self, mod, config):
        config(defaults_content="HOST=from-defaults\nPORT=8080\n")

        assert mod.load() == {"HOST": "from-defaults", "PORT": "8080"}

    def test_should_let_the_override_win_key_by_key(self, mod, config):
        config(defaults_content="HOST=from-defaults\nPORT=8080\n",
               override_content="HOST=from-override\n")

        assert mod.load() == {"HOST": "from-override", "PORT": "8080"}

    def test_should_work_with_no_defaults_file(self, mod, config):
        config(override_content="HOST=from-override\n")

        assert mod.load() == {"HOST": "from-override"}

    def test_should_return_empty_mapping_when_neither_file_exists(self, mod, config):
        assert mod.load() == {}


class TestValue:
    def test_should_return_the_configured_value(self, mod, config):
        config(defaults_content="HOST=example.internal\n")

        assert mod.value("HOST") == "example.internal"

    def test_should_return_the_default_when_the_key_is_absent(self, mod, config):
        config(defaults_content="HOST=example.internal\n")

        assert mod.value("MISSING", "fallback") == "fallback"

    def test_should_return_empty_string_when_no_default_is_given(self, mod, config):
        config(defaults_content="HOST=example.internal\n")

        assert mod.value("MISSING") == ""

    def test_should_prefer_the_environment_over_both_files(self, mod, config, monkeypatch):
        config(defaults_content="HOST=from-defaults\n", override_content="HOST=from-override\n")
        monkeypatch.setenv("HOST", "from-environment")

        assert mod.value("HOST") == "from-environment"


class TestShippedDefaults:
    def test_should_ship_defaults_for_every_key_the_scripts_read(self, mod):
        shipped = mod.parse(mod.defaults_path())

        assert set(shipped) >= {"NETWORK_DRIVE_SERVER_IP", "NETWORK_DRIVE_FOLDER",
                                "VM_DRIVE_MOUNT_POINT", "LEONARDO_STATUS_HOST", "HOST_ALIASES"}

    def test_should_ship_host_aliases_that_parse(self, mod, load_script):
        host_resolver = load_script("host-resolver")

        assert host_resolver.parse_host_aliases(mod.parse(mod.defaults_path())["HOST_ALIASES"])
