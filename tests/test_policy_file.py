import json

import jsonschema
import pytest

from contractguard.config import REPO_ROOT

POLICIES = REPO_ROOT / "policies"


@pytest.fixture(scope="module")
def schema():
    return json.loads((POLICIES / "policy.schema.json").read_text())


@pytest.fixture(scope="module")
def policy():
    return json.loads((POLICIES / "default_vendor_v1.json").read_text())


def test_default_policy_is_valid(schema, policy):
    jsonschema.validate(policy, schema)
    assert [r["id"] for r in policy["rules"]] == [f"R{i:02d}" for i in range(1, 11)]


def test_schema_requires_threshold_for_numeric(schema, policy):
    bad = json.loads(json.dumps(policy))
    del bad["rules"][2]["threshold"]  # R03 NUMERIC_MIN
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_schema_rejects_unknown_category(schema, policy):
    bad = json.loads(json.dumps(policy))
    bad["rules"][0]["category"] = "WARRANTY"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
