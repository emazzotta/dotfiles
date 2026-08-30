import pytest


NETWORK_DRIVE_SERVER = "fileserver.test"


@pytest.fixture
def leopath(load_script, tmp_path, monkeypatch):
    config = tmp_path / "private.env"
    config.write_text(f"NETWORK_DRIVE_SERVER_IP={NETWORK_DRIVE_SERVER}\n")
    monkeypatch.setenv("DOTFILES_PRIVATE_ENV", str(config))
    return load_script("leopath")


TEST_CASES = [
    pytest.param("K:", "K:\\Daten", id="k_drive_alone"),
    pytest.param("K:\\Bereich_Informatik\\PROJEKTE\\file.leon",
                 "K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon", id="k_drive_without_daten"),
    pytest.param("K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon",
                 "K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon", id="k_drive_with_daten"),
    pytest.param(f"\\\\{NETWORK_DRIVE_SERVER}\\Bereich_Informatik\\PROJEKTE\\file.leon",
                 "K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon", id="unc_path_without_daten"),
    pytest.param(f"\\{NETWORK_DRIVE_SERVER}\\Bereich_Informatik\\PROJEKTE\\file.leon",
                 "K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon", id="unc_path_single_slash"),
    pytest.param(f"\\\\{NETWORK_DRIVE_SERVER}\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon",
                 "K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon", id="unc_path_with_daten"),
    pytest.param("C:\\emanuelemazzotta\\windows_mount\\Daten\\Bereich_Informatik\\file.leon",
                 "K:\\Daten\\Bereich_Informatik\\file.leon", id="c_drive_with_daten"),
    pytest.param("D:\\backup\\old\\Daten\\projects\\subfolder\\file.txt",
                 "K:\\Daten\\projects\\subfolder\\file.txt", id="d_drive_with_daten"),
    pytest.param("/Users/someone/mount/Daten/subfolder/file.leon",
                 "K:\\Daten\\subfolder\\file.leon", id="unix_path_with_daten"),
    pytest.param("C:/roland/meineSachen/Daten/important/document.pdf",
                 "K:\\Daten\\important\\document.pdf", id="mixed_slashes_with_daten"),
    pytest.param("\\\\server\\share\\nested\\folders\\Daten\\work\\project.leon",
                 "K:\\Daten\\work\\project.leon", id="deep_unc_path_with_daten"),
    pytest.param(
        "K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon",
        "K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon",
        id="complex_path_with_special_chars",
    ),
]

DYNAMIC_HOME_CASES = [
    pytest.param("subfolder/file.leon", "K:\\Daten\\subfolder\\file.leon", id="unix_home_daten_path"),
    pytest.param("", "K:\\Daten", id="unix_home_daten_root"),
]

INVALID_CASES = [
    pytest.param("C:\\random\\path\\without\\target", id="no_daten_no_k_no_ip"),
    pytest.param("/usr/local/bin/something", id="unix_path_without_daten"),
    pytest.param("\\\\other.server\\share\\file.txt", id="different_server_without_daten"),
]


@pytest.mark.parametrize("input_path,expected", TEST_CASES)
def test_normalize_path(leopath, input_path, expected):
    assert leopath.normalize_path(input_path) == expected


@pytest.mark.parametrize("suffix,expected", DYNAMIC_HOME_CASES)
def test_normalize_path_home_daten(leopath, suffix, expected):
    input_path = leopath.HOME_DATEN + ("/" + suffix if suffix else "")
    assert leopath.normalize_path(input_path) == expected


@pytest.mark.parametrize("invalid_path", INVALID_CASES)
def test_normalize_path_raises_error(leopath, invalid_path):
    with pytest.raises(ValueError, match="Path must contain 'Daten', start with K:, or start with the network drive server"):
        leopath.normalize_path(invalid_path)
