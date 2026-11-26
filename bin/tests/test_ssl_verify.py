import os
import platform
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

from bin.tests.conftest import requires_tool

BIN_DIR = Path(__file__).parent.parent
IS_DARWIN = platform.system() == "Darwin"


def run_script_function(tmp_path, name, call, extra_path=None):
    """Run one function, cut out of ssl_verify, so the script itself is never sourced."""
    body = subprocess.run(
        ["sed", "-n", f"/^{name}() {{/,/^}}/p", str(BIN_DIR / "ssl_verify")],
        capture_output=True, text=True, check=True,
    ).stdout
    assert body, f"{name} not found in ssl_verify"
    script = tmp_path / "function.sh"
    script.write_text(f"#!/bin/bash\n{body}\n{call}\n")
    env = {**os.environ, **({"PATH": extra_path} if extra_path else {})}
    return subprocess.run(["/bin/bash", str(script)], capture_output=True, text=True, env=env)


class TestCheckWildcardMatch:
    @pytest.mark.parametrize("hostname,pattern,expected", [
        ("www.example.com", "*.example.com", 0),
        ("sub.example.com", "*.example.com", 0),
        ("example.com", "example.com", 0),
        ("www.other.com", "*.example.com", 1),
        ("deep.sub.example.com", "*.example.com", 1),
        ("example.com", "*.example.com", 1),
        (".example.com", "*.example.com", 1),
        ("www.example.com.evil.org", "*.example.com", 1),
        ("a.b.example.com", "*.b.example.com", 0),
        ("www.example.com", "www.example.com", 0),
    ])
    def test_wildcard_matching(self, hostname, pattern, expected, tmp_path):
        result = run_script_function(tmp_path, "check_wildcard_match", f'check_wildcard_match "{hostname}" "{pattern}"')

        assert result.returncode == expected


class TestParseCertDatePortability:
    def test_function_exists_in_source(self):
        content = (BIN_DIR / "ssl_verify").read_text()
        assert "parse_cert_date()" in content

    def test_has_platform_branching(self):
        content = (BIN_DIR / "ssl_verify").read_text()
        assert "date -j -f" in content
        assert "date -d" in content
        assert "Darwin" in content

    @pytest.mark.parametrize("date_str", [
        "Mar 15 12:00:00 2025 GMT",
        "Jan  1 00:00:00 2025 GMT",
        "Dec 31 23:59:59 2024 GMT",
    ])
    def test_parse_cert_date_on_current_platform(self, tmp_path, date_str):
        script = tmp_path / "test.sh"
        script.write_text(f"""#!/bin/bash
parse_cert_date() {{
    local date_str
    date_str="$(echo "$1" | sed 's/  */ /g')"
    if [ "$(uname -s)" = "Darwin" ]; then
        TZ=UTC date -j -f "%b %d %T %Y %Z" "$date_str" "+%s" 2>/dev/null || echo 0
    else
        date -d "$1" "+%s" 2>/dev/null || echo 0
    fi
}}
result=$(parse_cert_date "{date_str}")
if [ "$result" -gt 0 ] 2>/dev/null; then
    echo "OK"
else
    echo "FAIL"
fi
""")
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        assert result.stdout.strip() == "OK"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until_listening(port):
    for _ in range(100):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise AssertionError(f"nothing listens on port {port}")


def make_certificate(directory, key_args):
    key, cert = directory / "key.pem", directory / "cert.pem"
    subprocess.run(["openssl", *[arg.replace("{key}", str(key)) for arg in key_args]], check=True, capture_output=True)
    subprocess.run(
        ["openssl", "req", "-new", "-x509", "-key", str(key), "-subj", "/CN=127.0.0.1", "-days", "2", "-out", str(cert)],
        check=True, capture_output=True,
    )
    return key, cert


@pytest.fixture
def tls_server(tmp_path):
    started = []

    def _start(key_args):
        key, cert = make_certificate(tmp_path, key_args)
        port = free_port()
        server = subprocess.Popen(
            ["openssl", "s_server", "-accept", str(port), "-cert", str(cert), "-key", str(key), "-www", "-quiet"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        started.append(server)
        wait_until_listening(port)
        return f"127.0.0.1:{port}"
    yield _start
    for server in started:
        server.terminate()
        server.wait()


@pytest.fixture
def closing_server():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    stop = threading.Event()

    def accept_and_close():
        listener.settimeout(0.1)
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                continue
            connection.close()
    thread = threading.Thread(target=accept_and_close, daemon=True)
    thread.start()
    yield f"127.0.0.1:{listener.getsockname()[1]}"
    stop.set()
    thread.join()
    listener.close()


EC_KEY = ["ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", "{key}"]
RSA_KEY = ["genrsa", "-out", "{key}", "2048"]
ED25519_KEY = ["genpkey", "-algorithm", "ED25519", "-out", "{key}"]
ED448_KEY = ["genpkey", "-algorithm", "ED448", "-out", "{key}"]


@requires_tool("openssl")
@requires_tool("nc")
class TestKeySize:
    def test_should_accept_a_256_bit_elliptic_curve_key(self, run_cli, tls_server):
        result = run_cli("ssl_verify", [tls_server(EC_KEY)])

        assert "Key Size: 256 bits" in result.stdout
        assert "Key size is adequate (256+ bits)" in result.stdout
        assert "weak" not in result.stdout.lower().replace("weak sha1", "")

    def test_should_accept_a_2048_bit_rsa_key(self, run_cli, tls_server):
        result = run_cli("ssl_verify", [tls_server(RSA_KEY)])

        assert "Key size is adequate (2048+ bits)" in result.stdout
        assert "weak" not in result.stdout.lower().replace("weak sha1", "")

    @pytest.mark.parametrize("key_args,bits", [(ED25519_KEY, 256), (ED448_KEY, 456)], ids=["ed25519", "ed448"])
    def test_should_report_the_fixed_key_size_of_an_edwards_curve_certificate(self, run_cli, tls_server, key_args, bits):
        result = run_cli("ssl_verify", [tls_server(key_args)])

        assert f"Key Size: {bits} bits" in result.stdout
        assert "weak" not in result.stdout.lower().replace("weak sha1", "")
        assert "4096+" not in result.stdout
        assert "integer expression expected" not in result.stderr

    def test_should_finish_the_report_for_a_certificate_without_authority_and_transparency_data(self, run_cli, tls_server):
        result = run_cli("ssl_verify", [tls_server(EC_KEY)])

        assert "No AIA extension found" in result.stdout
        assert "No Certificate Transparency information found" in result.stdout
        assert "Verification Complete" in result.stdout

    @pytest.mark.parametrize("algorithm,minimum", [
        ("rsaEncryption", 2048),
        ("rsassaPss", 2048),
        ("dsaEncryption", 2048),
        ("id-ecPublicKey", 256),
        ("ED25519", 256),
    ])
    def test_should_pick_the_minimum_key_size_by_algorithm(self, tmp_path, algorithm, minimum):
        result = run_script_function(tmp_path, "min_key_bits", f'min_key_bits "{algorithm}"')

        assert result.stdout.strip() == str(minimum)

    @pytest.mark.parametrize("line,bits", [
        ("Public-Key: (256 bit)", 256),
        ("Public-Key: (256 bit field, 128 bit security level)", 256),
        ("Public-Key: (2048 bit)", 2048),
        ("ED25519 Public-Key:", 256),
        ("ED448 Public-Key:", 456),
    ], ids=["openssl 3", "openssl 4 elliptic curve", "rsa", "ed25519", "ed448"])
    def test_should_read_the_key_size_from_the_public_key_line(self, tmp_path, line, bits):
        text = f"        Subject Public Key Info:\n                {line}\n"

        result = run_script_function(tmp_path, "public_key_bits", f"printf '%s' '{text}' | public_key_bits")

        assert result.stdout == f"{bits}\n"

    def test_should_read_no_key_size_when_the_public_key_line_has_no_bit_count(self, tmp_path):
        text = "        Subject Public Key Info:\n                X25519 Public-Key:\n"

        result = run_script_function(tmp_path, "public_key_bits", f"printf '%s' '{text}' | public_key_bits")

        assert result.stdout == ""


@requires_tool("openssl")
@requires_tool("nc")
class TestCertificateRetrieval:
    def test_should_report_the_failure_when_the_server_sends_no_certificate(self, run_cli, closing_server):
        result = run_cli("ssl_verify", [closing_server])

        assert result.returncode == 1
        assert "Failed to retrieve certificate" in result.stdout


class TestRunWithTimeout:
    PROBE = 'echo "probe $*"'

    @pytest.fixture
    def tools(self, tmp_path):
        directory = tmp_path / "tools"
        directory.mkdir()

        def _install(name, body):
            tool = directory / name
            tool.write_text(f"#!/bin/bash\n{body}\n")
            tool.chmod(0o755)
        _install("probe", self.PROBE)
        return directory, _install

    def test_should_use_timeout_when_it_exists(self, tmp_path, tools):
        directory, install = tools
        install("timeout", 'echo "timeout $1"; shift; exec "$@"')

        result = run_script_function(tmp_path, "run_with_timeout", "run_with_timeout 5 probe a", f"{directory}:/nonexistent")

        assert result.stdout.splitlines() == ["timeout 5", "probe a"]

    def test_should_fall_back_to_gtimeout_when_timeout_is_missing(self, tmp_path, tools):
        directory, install = tools
        install("gtimeout", 'echo "gtimeout $1"; shift; exec "$@"')

        result = run_script_function(tmp_path, "run_with_timeout", "run_with_timeout 5 probe a", f"{directory}:/nonexistent")

        assert result.stdout.splitlines() == ["gtimeout 5", "probe a"]

    def test_should_run_the_command_without_a_limit_when_neither_exists(self, tmp_path, tools):
        directory, _ = tools

        result = run_script_function(tmp_path, "run_with_timeout", "run_with_timeout 5 probe a b", f"{directory}:/nonexistent")

        assert result.stdout.splitlines() == ["probe a b"]
