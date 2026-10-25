import json
import shutil

import pytest

from contractguard.config import REPO_ROOT
from contractguard.errors import PolicyError
from contractguard.policy.schema import bump_patch, list_policies, load_policy, save_policy


@pytest.fixture
def policy_dir(tmp_path):
    src = REPO_ROOT / "policies"
    for name in ("policy.schema.json", "default_vendor_v1.json"):
        shutil.copy(src / name, tmp_path / name)
    return tmp_path


def test_load_default_policy(policy_dir):
    p = load_policy("default_vendor_v1", policy_dir)
    assert p.version == "1.0.0" and len(p.rules) == 10
    assert p.rules[2].threshold == 30


def test_list_policies_skips_schema(policy_dir):
    assert [p.policy_id for p in list_policies(policy_dir)] == ["default_vendor_v1"]


def test_unknown_and_unsafe_ids(policy_dir):
    with pytest.raises(PolicyError) as e:
        load_policy("nope", policy_dir)
    assert e.value.code == PolicyError.NOT_FOUND
    with pytest.raises(PolicyError):
        load_policy("../etc/passwd", policy_dir)


def test_bump_patch():
    assert bump_patch("1.0.9") == "1.0.10"


def test_save_bumps_version_and_keeps_history(policy_dir):
    data = json.loads((policy_dir / "default_vendor_v1.json").read_text())
    data["rules"][2]["threshold"] = 45
    saved = save_policy("default_vendor_v1", data, policy_dir)
    assert saved.version == "1.0.1"
    assert (policy_dir / "history" / "default_vendor_v1@1.0.0.json").is_file()
    assert load_policy("default_vendor_v1", policy_dir).rules[2].threshold == 45


def test_save_rejects_invalid_and_keeps_file(policy_dir):
    data = json.loads((policy_dir / "default_vendor_v1.json").read_text())
    data["rules"][0]["severity"] = "CRITICAL"
    with pytest.raises(PolicyError) as e:
        save_policy("default_vendor_v1", data, policy_dir)
    assert e.value.code == PolicyError.INVALID and "rules/0/severity" in e.value.message
    assert load_policy("default_vendor_v1", policy_dir).version == "1.0.0"
    assert not (policy_dir / "history").exists()


def test_save_rejects_duplicate_ids(policy_dir):
    data = json.loads((policy_dir / "default_vendor_v1.json").read_text())
    data["rules"][1]["id"] = "R01"
    with pytest.raises(PolicyError, match="Duplicate"):
        save_policy("default_vendor_v1", data, policy_dir)


def test_save_rejects_id_mismatch(policy_dir):
    data = json.loads((policy_dir / "default_vendor_v1.json").read_text())
    data["policy_id"] = "other"
    with pytest.raises(PolicyError, match="must match"):
        save_policy("default_vendor_v1", data, policy_dir)
