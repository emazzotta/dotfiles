import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

EMS_PATH = Path(__file__).parent.parent / "ems"


def _load() -> object:
    loader = importlib.machinery.SourceFileLoader("ems_mod", str(EMS_PATH))
    spec   = importlib.util.spec_from_loader("ems_mod", loader)
    mod    = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def ems():
    return _load()


@pytest.fixture(autouse=True)
def fake_creds(monkeypatch):
    monkeypatch.setenv("EMS_USER", "testuser")
    monkeypatch.setenv("EMS_PASSWORD", "testpass")
    monkeypatch.setenv("JIRA_EMAIL", "test@leonardo.ag")


# ── _auth_header ──────────────────────────────────────────────────────────────

class TestAuthHeader:
    def test_base64_encoded(self, ems):
        import base64
        header = ems._auth_header()
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header[6:]).decode()
        assert decoded == "testuser:testpass"

    def test_missing_creds(self, ems, monkeypatch):
        monkeypatch.delenv("EMS_USER", raising=False)
        monkeypatch.delenv("EMS_PASSWORD", raising=False)
        header = ems._auth_header()
        assert header.startswith("Basic ")


# ── _is_internal_email ────────────────────────────────────────────────────────

class TestIsInternalEmail:
    def test_internal_domain(self, ems):
        assert ems._is_internal_email("test@leonardo.ag") is True

    def test_external_domain(self, ems):
        assert ems._is_internal_email("user@acme.com") is False

    def test_case_insensitive(self, ems):
        assert ems._is_internal_email("user@LEONARDO.AG") is True

    def test_partial_match_not_internal(self, ems):
        assert ems._is_internal_email("user@notleonardo.ag") is False


# ── _extract_customer_email ───────────────────────────────────────────────────

class TestExtractCustomerEmail:
    def test_extracts_first_contact(self, ems):
        data = {"customer": {"contacts": {"contact": [{"emailId": "a@b.com"}, {"emailId": "c@d.com"}]}}}
        assert ems._extract_customer_email(data) == "a@b.com"

    def test_single_contact_dict(self, ems):
        data = {"customer": {"contacts": {"contact": {"emailId": "a@b.com"}}}}
        assert ems._extract_customer_email(data) == "a@b.com"

    def test_no_contacts_returns_empty(self, ems):
        assert ems._extract_customer_email({}) == ""


# ── _entitlement_payload ──────────────────────────────────────────────────────

class TestEntitlementPayload:
    def test_required_fields(self, ems):
        p = ems._entitlement_payload("LEONARDO Abonnement", "2026-05-07", None, None)
        ent = p["entitlement"]
        assert ent["marketGroup"]["name"] == "QQZQI"
        assert ent["channel"]["name"] == "QQZQI"
        assert ent["state"] == "ENABLE"
        pk = ent["productKeys"]["productKey"][0]
        item_product = pk["item"]["itemProduct"]
        assert item_product["product"]["nameVersion"]["name"] == "LEONARDO Abonnement"
        feat = item_product["itemProductFeatures"]["itemProductFeature"][0]
        expiry_attr = next(a for a in feat["itemFeatureLicenseModel"]["attributes"]["attribute"] if a["name"] == "EXPIRATION_DATE")
        assert "2026-05-07" in expiry_attr["value"]

    def test_customer_and_contact_included(self, ems):
        p = ems._entitlement_payload("P", "2026-01-01", "cust-42", "a@b.com")
        ent = p["entitlement"]
        assert ent["customer"]["id"] == "cust-42"
        assert ent["contact"]["emailId"] == "a@b.com"

    def test_no_customer_omitted(self, ems):
        p = ems._entitlement_payload("P", "2026-01-01", None, None)
        ent = p["entitlement"]
        assert "customer" not in ent
        assert "contact" not in ent


# ── op_create_contact dry-run ─────────────────────────────────────────────────

class TestOpCreateContactDryRun:
    def test_dry_run_prints_payload(self, ems, capsys):
        ems.op_create_contact("https://example.com", "user@example.com", "Test User", dry_run=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["contact"]["emailId"] == "user@example.com"
        assert data["contact"]["marketGroup"]["name"] == "QQZQI"


# ── op_create_customer dry-run ────────────────────────────────────────────────

class TestOpCreateCustomerDryRun:
    def test_dry_run_returns_empty_string(self, ems, capsys):
        result = ems.op_create_customer("https://example.com", "Acme AG", "admin@acme.ch", dry_run=True)
        assert result == ""
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["customer"]["name"] == "Acme AG"
        assert data["customer"]["marketGroup"]["name"] == "QQZQI"


# ── op_create_entitlement dry-run ─────────────────────────────────────────────

class TestOpCreateEntitlementDryRun:
    def test_dry_run_prints_payload(self, ems, capsys):
        result = ems.op_create_entitlement(
            "https://example.com", "LEONARDO Abonnement", "2026-05-07",
            customer_id="123", email="test@leonardo.ag",
            dry_run=True,
        )
        assert result == ""
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["entitlement"]["productKeys"]["productKey"][0]["item"]["itemProduct"]["product"]["nameVersion"]["name"] == "LEONARDO Abonnement"

    def test_dry_run_defaults_to_real(self, ems, capsys):
        ems.op_create_entitlement(
            "https://example.com", "LEONARDO Abonnement", "2026-05-07",
            email="client@acme.com", dry_run=True,
        )
        data = json.loads(capsys.readouterr().out)
        assert data["entitlement"]["isTest"] is False

    def test_dry_run_internal_email_defaults_to_real(self, ems, capsys):
        ems.op_create_entitlement(
            "https://example.com", "LEONARDO Abonnement", "2026-05-07",
            email="test@leonardo.ag", dry_run=True,
        )
        data = json.loads(capsys.readouterr().out)
        assert data["entitlement"]["isTest"] is False

    def test_dry_run_test_flag_marks_as_test(self, ems, capsys):
        ems.op_create_entitlement(
            "https://example.com", "LEONARDO Abonnement", "2026-05-07",
            email="test@leonardo.ag", dry_run=True, test=True,
        )
        data = json.loads(capsys.readouterr().out)
        assert data["entitlement"]["isTest"] is True


# ── op_link_customer dry-run ──────────────────────────────────────────────────

class TestOpLinkCustomerDryRun:
    def test_dry_run_prints_payload(self, ems, capsys):
        ems.op_link_customer("https://example.com", "eid-123", "cust-42", "a@b.com", dry_run=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["entitlement"]["customer"]["id"] == "cust-42"
        assert data["entitlement"]["contact"]["emailId"] == "a@b.com"


# ── op_v2cp dry-run ───────────────────────────────────────────────────────────

class TestOpV2cpDryRun:
    def test_dry_run_prints_would_write(self, ems, capsys):
        with patch.object(ems, "ems_get_json") as mock_get:
            mock_get.return_value = {
                "entitlement": {"productKeys": {"productKey": [{"pkId": "key-abc"}]}}
            }
            ems.op_v2cp("https://example.com", "eid-123", "/tmp", dry_run=True)
        out = capsys.readouterr().out
        assert "key-abc.v2cp" in out
        assert "would write" in out


# ── op_activate dry-run ───────────────────────────────────────────────────────

_ENT_WITH_KEY = {"entitlement": {"productKeys": {"productKey": [{"pkId": "pk-001"}]}}}


class TestOpActivateDryRun:
    def test_dry_run_prints_payload(self, ems, capsys):
        with patch.object(ems, "ems_get_json") as mock_get:
            mock_get.return_value = _ENT_WITH_KEY
            ems.op_activate("https://example.com", "eid-123", output_dir="/tmp", dry_run=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["bulkActivation"]["activationProductKeys"]["activationProductKey"][0]["pkId"] == "pk-001"

    def test_dry_run_with_c2v_file(self, ems, capsys, tmp_path):
        c2v_file = tmp_path / "key.c2v"
        c2v_file.write_text("<hasp_info>...</hasp_info>")
        with patch.object(ems, "ems_get_json") as mock_get:
            mock_get.return_value = _ENT_WITH_KEY
            ems.op_activate("https://example.com", "eid-123", str(c2v_file), "/tmp", dry_run=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "C2V" in data["bulkActivation"]["extnLDK"]

    def test_dry_run_with_personal_c2v(self, ems, capsys):
        fake_c2v = "<hasp_info><host_fingerprint type='SL-AdminMode' crc='999'>FAKE</host_fingerprint></hasp_info>"
        with patch.object(ems, "ems_get_json") as mock_get, \
             patch.object(ems, "_fetch_personal_c2v", return_value=fake_c2v):
            mock_get.return_value = _ENT_WITH_KEY
            ems.op_activate("https://example.com", "eid-123", output_dir="/tmp", dry_run=True, personal_c2v=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "C2V" in data["bulkActivation"]["extnLDK"]
        assert fake_c2v in data["bulkActivation"]["extnLDK"]["C2V"]


# ── _fetch_personal_c2v ───────────────────────────────────────────────────────

class TestFetchPersonalC2v:
    def test_parses_my_id_response(self, ems):
        my_id_xml = """<?xml version="1.0" encoding="UTF-8" ?>
<location>
 <license_manager id="test-id-000" time="0">
  <host_fingerprint type="SL-AdminMode" crc="0000000001">
   AAAA BBBB
   CCCC
  </host_fingerprint>
 </license_manager>
</location>"""
        with patch("urllib.request.urlopen") as mock_open:
            mock_cm = MagicMock()
            mock_cm.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=my_id_xml.encode())))
            mock_cm.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_cm
            result = ems._fetch_personal_c2v()
        assert '<host_fingerprint type="SL-AdminMode" crc="0000000001">' in result
        assert "AAAABBBBCCCC" in result
        assert result.startswith('<?xml version="1.0"')
        assert "<hasp_info>" in result

    def test_exits_when_sentinel_unreachable(self, ems):
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            with pytest.raises(SystemExit):
                ems._fetch_personal_c2v()



# ── HTTP error handling ───────────────────────────────────────────────────────

class TestEmsError:
    def test_error_has_status(self, ems):
        err = ems.EmsError(404, "not found")
        assert err.status == 404
        assert "not found" in str(err)


# ── find_customer_with_email ──────────────────────────────────────────────────

class TestFindCustomerWithEmail:
    def test_returns_id_and_email(self, ems):
        with patch.object(ems, "ems_get_json") as mock_get:
            mock_get.side_effect = [
                {"customers": {"customer": [{"id": "42", "name": "Emanuele Mazzotta"}]}},
                {"customer": {"id": "42", "name": "Emanuele Mazzotta", "contacts": {"contact": [{"emailId": "test@leonardo.ag"}]}}},
            ]
            result = ems.find_customer_with_email("https://example.com", "Emanuele Mazzotta")
        assert result == ("42", "test@leonardo.ag")

    def test_returns_none_when_not_found(self, ems):
        with patch.object(ems, "ems_get_json") as mock_get:
            mock_get.return_value = {"customers": {"customer": []}}
            result = ems.find_customer_with_email("https://example.com", "Unknown Person")
        assert result is None

    def test_case_insensitive_name_match(self, ems):
        with patch.object(ems, "ems_get_json") as mock_get:
            mock_get.side_effect = [
                {"customers": {"customer": [{"id": "5", "name": "ACME AG"}]}},
                {"customer": {"id": "5", "name": "ACME AG", "contacts": {"contact": [{"emailId": "a@acme.ch"}]}}},
            ]
            result = ems.find_customer_with_email("https://example.com", "acme ag")
        assert result == ("5", "a@acme.ch")


# ── _pkids_for_entitlement ────────────────────────────────────────────────────

class TestPkidsForEntitlement:
    def test_extracts_pkids(self, ems):
        with patch.object(ems, "ems_get_json") as mock_get:
            mock_get.return_value = {"entitlement": {"productKeys": {"productKey": [{"pkId": "pk-1"}, {"pkId": "pk-2"}]}}}
            result = ems._pkids_for_entitlement("https://example.com", "eid-123")
        assert result == ["pk-1", "pk-2"]

    def test_empty_when_no_keys(self, ems):
        with patch.object(ems, "ems_get_json") as mock_get:
            mock_get.return_value = {}
            result = ems._pkids_for_entitlement("https://example.com", "eid-123")
        assert result == []


# ── _print_entitlement ────────────────────────────────────────────────────────

class TestPrintEntitlement:
    def test_prints_key_fields(self, ems, capsys):
        data = {
            "entitlement": {
                "eId": "eid-abc",
                "state": {"name": "DEPLOYED"},
                "customer": {"name": "Acme"},
                "contact": {"emailId": "a@acme.com"},
                "productKeys": {"productKey": []},
            }
        }
        ems._print_entitlement(data)
        out = capsys.readouterr().out
        assert "eid-abc" in out
        assert "DEPLOYED" in out
        assert "Acme" in out


# ── URL construction ──────────────────────────────────────────────────────────

class TestUrlConstruction:
    def test_prod_default(self, ems):
        assert ems.PROD_BASE == "https://leonardo.prod.sentinelcloud.com/ems/api/v5"

    def test_dev_base(self, ems):
        assert ems.DEV_BASE == "https://leonardo.dev.sentinelcloud.com/ems/api/v5"

    def test_typical_email_is_internal(self, ems):
        assert ems._is_internal_email(ems._typical_email()) is True
