import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "utf8-lenient"

LATIN1_DIFF = (
    b"diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n"
    b"-La cl\xe9 est enregistr\xe9e\n+La cl\xe9 est modifi\xe9e\n"
)


ANSI = re.compile(rb"\x1b\[[0-9;]*m")


def filter_bytes(payload):
    return subprocess.run([str(SCRIPT)], input=payload, capture_output=True)


def should_reread_invalid_utf8_bytes_as_latin1():
    result = filter_bytes(b"La cl\xe9 est enregistr\xe9e\n")

    assert result.returncode == 0
    assert result.stdout.decode("utf-8") == "La clé est enregistrée\n"


def should_pass_valid_utf8_through_byte_identical():
    payload = "Grüße 日本語 \U0001f389 “quoted”\n".encode("utf-8")

    result = filter_bytes(payload)

    assert result.returncode == 0
    assert result.stdout == payload


def should_preserve_ansi_colour_codes():
    payload = b"\x1b[32m+La cl\xe9\x1b[m\n"

    result = filter_bytes(payload)

    assert result.stdout.startswith(b"\x1b[32m")
    assert result.stdout.endswith(b"\x1b[m\n")


@pytest.mark.parametrize("flag", ["-h", "--help"])
def should_print_usage(flag):
    result = subprocess.run([str(SCRIPT), flag], capture_output=True, text=True)

    assert result.returncode == 0
    assert "usage:" in result.stdout


@pytest.mark.skipif(shutil.which("diff-so-fancy") is None, reason="diff-so-fancy not available")
def should_let_diff_so_fancy_render_a_latin1_diff_it_would_otherwise_abort_on():
    unfiltered = subprocess.run(["diff-so-fancy"], input=LATIN1_DIFF, capture_output=True)
    assert unfiltered.returncode != 0 and not unfiltered.stdout

    filtered = subprocess.run(
        ["diff-so-fancy"], input=filter_bytes(LATIN1_DIFF).stdout, capture_output=True
    )

    assert filtered.returncode == 0
    assert "modifiée".encode("utf-8") in ANSI.sub(b"", filtered.stdout)
