import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
A_UMLAUT = "\u00c4"
EURO = "\u20ac"
PASSWORD = f"p{A_UMLAUT}ss{EURO}"


@pytest.fixture
def pwvariants(load_module):
    return load_module("pwvariants")


def spelled(pwvariants, password):
    return dict(pwvariants.unique_spellings(password))


def test_should_offer_only_the_stored_spelling_when_the_password_is_ascii(pwvariants):
    result = pwvariants.unique_spellings("plain-ascii")

    assert result == [("as stored", b"plain-ascii")]


def test_should_offer_the_nfd_spelling_right_after_the_stored_one(pwvariants):
    result = pwvariants.unique_spellings(PASSWORD)

    assert result[0] == ("as stored", PASSWORD.encode())
    assert result[1] == ("NFD", unicodedata.normalize("NFD", PASSWORD).encode())


def test_should_offer_the_nfc_spelling_when_the_stored_password_is_decomposed(pwvariants):
    decomposed = unicodedata.normalize("NFD", PASSWORD)

    result = spelled(pwvariants, decomposed)

    assert result["NFC"] == PASSWORD.encode()


@pytest.mark.parametrize("label,expected", [
    ("latin-1 bytes", f"p{A_UMLAUT}ss?".encode("latin-1")),
    ("cp1252 bytes", PASSWORD.encode("cp1252")),
    ("mac_roman bytes", PASSWORD.encode("mac_roman")),
    ("UTF-8 read as latin-1", PASSWORD.encode().decode("latin-1").encode()),
    ("accents stripped, rest as ?", b"pAss?"),
    ("non-ASCII as ?", b"p?ss?"),
    ("non-ASCII dropped", b"pss"),
])
def test_should_offer_the_spellings_older_tools_produced(pwvariants, label, expected):
    result = spelled(pwvariants, PASSWORD)

    assert result[label] == expected


def test_should_never_offer_the_same_bytes_twice(pwvariants):
    values = [value for _, value in pwvariants.unique_spellings(PASSWORD)]

    assert len(values) == len(set(values))


def test_should_skip_spellings_that_lose_every_character(pwvariants):
    values = [value for _, value in pwvariants.unique_spellings(EURO)]

    assert b"" not in values


def run_cli(stdin):
    return subprocess.run(
        [sys.executable, "-I", str(BIN_DIR / "pwvariants.py")],
        input=stdin, capture_output=True, check=True,
    ).stdout


def test_should_print_nul_separated_label_and_value_pairs():
    output = run_cli(b"plain")

    assert output == b"as stored\0plain\0"


def test_should_pass_undecodable_input_through_unchanged():
    output = run_cli(b"p\xffss")

    assert output == b"as stored\0p\xffss\0"
