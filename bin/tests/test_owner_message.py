from __future__ import annotations

import base64
import json
import os
import subprocess

import pytest

PAGE_KEY = "s7M71Gj/xMisbXthnZnUZK3UwL8IUJjA4N76qLxtg6g="
PAGE_TOKEN = (
    "eyJ2IjoxLCJ0ZXh0IjoieWVzLCBwdXNoIHBlcnNvbmFsLWluZnJhIDA2YmU1MjRjXG5mw7xyIGRpY2gg4oCTIG9rIiwidG8iOnsiY29udmVyc2F0aW9uIjoiMjEyZGYzOGUtN2M0Yi00YTUxLTlkMGUtM2Y2YjJhOGMxZTU3IiwiYm94IjoibWFjYm9vayJ9LCJub25jZSI6IkFBRUNBd1FGQmdjSUNRb0xEQTBPRHciLCJpYXQiOjE3OTUwMDAwMDAsImV4cCI6MTc5NTAwMDYwMH0"
    ".ymjybYU5P-kjvgepm1j282KjY_bDBtmKB6MInLn-xHb870txlx4av5ZrByY9QWeec0JXF90EqJw0NT50sZITCQ"
)
CONVERSATION = "212df38e-7c4b-4a51-9d0e-3f6b2a8c1e57"
OTHER = "aaaaaaaa-0000-4000-8000-000000000001"
ISSUED = 1_795_000_000
NONCE = "AAECAwQFBgcICQoLDA0ODw"


def payload(**over):
    return {"v": 1, "text": "yes, push", "to": {"conversation": CONVERSATION, "box": "macbook"}, "nonce": NONCE,
            "iat": ISSUED, "exp": ISSUED + 600, **over}


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.fixture
def owner_key(owner_message, tmp_path):
    openssl = owner_message.openssl()
    work = tmp_path / "owner-key"
    work.mkdir()
    key = work / "owner.pem"
    subprocess.run([openssl, "genpkey", "-algorithm", "ed25519", "-out", str(key)], check=True, capture_output=True)
    public = subprocess.run([openssl, "pkey", "-in", str(key), "-pubout", "-outform", "DER"], check=True, capture_output=True).stdout

    def signed(body) -> str:
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        message = work / "payload"
        message.write_bytes(raw)
        signature = subprocess.run([openssl, "pkeyutl", "-sign", "-inkey", str(key), "-rawin", "-in", str(message)],
                                   check=True, capture_output=True).stdout
        return f"{b64url(raw)}.{b64url(signature)}"

    return base64.b64encode(public[-32:]).decode(), signed


@pytest.fixture
def owner_message(load_script, monkeypatch):
    module = load_script("owner-message")
    monkeypatch.setattr(module, "OWNER_PUBLIC_KEY", PAGE_KEY)
    return module


@pytest.fixture
def verify(owner_message, tmp_path, capsys):
    used = tmp_path / "used"

    def _verify(token: str, now: float = ISSUED + 30, session: str = CONVERSATION):
        code = owner_message.main(["verify", token], {"CLAUDE_CODE_SESSION_ID": session}, now, used)
        out, err = capsys.readouterr()
        return code, out, err

    return _verify


@pytest.fixture
def ours(owner_message, owner_key, monkeypatch):
    public, signed = owner_key
    monkeypatch.setattr(owner_message, "OWNER_PUBLIC_KEY", public)
    return signed


class TestVerify:
    def should_print_the_text_of_a_token_the_approve_page_signed(self, verify):
        assert verify(PAGE_TOKEN) == (0, "yes, push personal-infra 06be524c\nf\u00fcr dich \u2013 ok\n", "")

    def should_refuse_a_token_it_already_accepted(self, verify):
        verify(PAGE_TOKEN)

        assert verify(PAGE_TOKEN) == (1, "", "owner-message: this token was used before\n")

    def should_refuse_a_token_whose_message_changed_after_the_owner_signed_it(self, verify):
        altered = b64url(json.dumps(payload(text="yes, force push")).encode())

        assert verify(f"{altered}.{PAGE_TOKEN.split('.')[1]}") == (1, "", "owner-message: the owner key did not sign this token\n")

    def should_refuse_a_token_another_key_signed(self, verify, owner_key):
        _, signed = owner_key

        assert verify(signed(payload())) == (1, "", "owner-message: the owner key did not sign this token\n")

    @pytest.mark.parametrize("token", ["eyJ2IjoxfQ", "a.b.c", "eyJ2IjoxfQ.c2ln+bmF0dXJl", "eyJ2IjoxfQ.", "eyJ2I.c2lnbmF0dXJl"],
                             ids=["no dot", "three parts", "a character outside base64url", "no signature", "a part that is no base64"])
    def should_refuse_what_is_no_token(self, verify, token):
        assert verify(token) == (1, "", "owner-message: this is no owner token\n")

    @pytest.mark.parametrize("body", [
        b"yes, push",
        payload(v=2),
        payload(v=True),
        payload(text=""),
        payload(to=None),
        payload(to={"box": "macbook"}),
        payload(nonce="../../escape"),
        payload(nonce=None),
        payload(iat=ISSUED + 0.5),
        payload(exp=str(ISSUED + 600)),
        payload(exp=True),
    ], ids=["no JSON", "another version", "a version that is true", "an empty text", "no addressee", "no conversation",
            "a nonce that is a path", "no nonce", "a time that is no whole number", "an expiry as text", "an expiry that is true"])
    def should_refuse_a_signed_payload_that_is_no_owner_message(self, verify, ours, body):
        assert verify(ours(body)) == (1, "", "owner-message: the signed payload is no owner message\n")

    def should_refuse_a_message_the_owner_signed_for_another_session(self, verify):
        assert verify(PAGE_TOKEN, session=OTHER) == (1, "", f"owner-message: the owner signed this message for {CONVERSATION}, not this session\n")

    @pytest.mark.parametrize("body,now,reason", [
        (payload(), ISSUED + 600, "the owner's signature has expired"),
        (payload(), ISSUED - 61, "the owner signed this message ahead of this machine's clock"),
        (payload(exp=ISSUED + 601), ISSUED, "the owner's signature claims to last over 600 s"),
    ], ids=["expired", "issued over 60 s ahead", "lasting over 600 s"])
    def should_refuse_a_signature_outside_its_time(self, verify, ours, body, now, reason):
        assert verify(ours(body), now=now) == (1, "", f"owner-message: {reason}\n")

    @pytest.mark.parametrize("now", [ISSUED - 60, ISSUED + 599], ids=["issued 60 s ahead", "a second before it expires"])
    def should_accept_a_signature_at_the_edges_of_its_time(self, verify, ours, now):
        assert verify(ours(payload()), now=now)[0] == 0

    def should_refuse_to_check_outside_a_claude_code_session(self, verify):
        assert verify(PAGE_TOKEN, session="") == (
            1, "", "owner-message: CLAUDE_CODE_SESSION_ID is not set: only a Claude Code session checks an owner message\n")

    def should_refuse_every_token_while_no_owner_key_is_pinned(self, verify, owner_message, monkeypatch):
        monkeypatch.setattr(owner_message, "OWNER_PUBLIC_KEY", "")

        assert verify(PAGE_TOKEN) == (1, "", "owner-message: no owner key is pinned in this script\n")

    def should_refuse_when_openssl_cannot_check_an_ed25519_signature(self, verify, owner_message, tmp_path, monkeypatch):
        libressl = tmp_path / "openssl"
        libressl.write_text("#!/bin/sh\necho 'pkeyutl: Unknown option: -rawin' >&2\nexit 1\n")
        libressl.chmod(0o755)
        monkeypatch.setattr(owner_message, "openssl", lambda: str(libressl))

        assert verify(PAGE_TOKEN) == (1, "", "owner-message: openssl could not check the signature: pkeyutl: Unknown option: -rawin\n")


class TestUsed:
    def should_keep_the_used_nonces_where_only_this_user_reads_them(self, verify, tmp_path):
        verify(PAGE_TOKEN)

        assert (oct((tmp_path / "used").stat().st_mode & 0o777), (tmp_path / "used" / NONCE).exists()) == ("0o700", True)

    def should_forget_a_nonce_once_its_token_can_no_longer_be_valid(self, verify, owner_message, tmp_path):
        used = tmp_path / "used"
        used.mkdir(mode=0o700)
        old = used / "OldOldOldOldOldOldOldO"
        old.touch()
        day_ago = ISSUED + 30 - owner_message.KEEP_USED_S - 1
        os.utime(old, (day_ago, day_ago))

        verify(PAGE_TOKEN)

        assert sorted(path.name for path in used.iterdir()) == [NONCE]


class TestCli:
    def should_print_its_usage(self, run_cli):
        result = run_cli("owner-message", ["--help"])

        assert (result.returncode, "verify" in result.stdout) == (0, True)

    def should_fail_with_a_reason_and_no_traceback(self, run_cli):
        result = run_cli("owner-message", ["verify", "nonsense"], env_extra={"CLAUDE_CODE_SESSION_ID": CONVERSATION})

        assert (result.returncode, result.stdout, result.stderr.startswith("owner-message: "), "Traceback" in result.stderr) == (1, "", True, False)
