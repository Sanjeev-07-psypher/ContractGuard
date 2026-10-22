import re
from pathlib import Path

import pytest

from contractguard.config import (
    REPO_ROOT,
    Settings,
    get_contract_types,
    get_label_map,
    get_patterns,
    get_settings,
)
from contractguard.models import CATEGORIES, CONTRACT_TYPES


def test_defaults_load_from_yaml():
    s = get_settings()
    assert s.limits.max_file_mb == 20
    assert s.ocr.min_chars_per_page == 50
    assert s.segmentation.max_chars == 3000
    assert s.policy.tau_missing == pytest.approx(0.55)
    assert s.llm.provider == "gemini"
    assert s.org.date_order == "DMY"
    assert "not legal advice" in s.disclaimer


def test_nested_env_override(monkeypatch):
    monkeypatch.setenv("CG_LLM__RPM", "4")
    monkeypatch.setenv("CG_OCR__TESSERACT_CMD", "C:/tess/tesseract.exe")
    s = Settings()
    assert s.llm.rpm == 4
    assert s.ocr.tesseract_cmd == "C:/tess/tesseract.exe"
    assert s.llm.max_findings == 15  # untouched YAML values survive the merge


def test_short_env_names(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value")
    s = Settings()
    assert s.llm.provider == "ollama"
    assert s.llm.model == "qwen2.5:7b"
    assert s.gemini_api_key.get_secret_value() == "secret-value"
    assert "secret-value" not in repr(s)


def test_invalid_provider_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gpt")
    with pytest.raises(ValueError):
        Settings()


def test_resolve_path_is_repo_relative():
    s = get_settings()
    assert s.resolve_path("models/x.joblib") == REPO_ROOT / "models/x.joblib"
    assert s.resolve_path("/abs/x") == Path("/abs/x")


def test_missing_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("CG_CONFIG_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        Settings()


def _all_regex_strings(node, skip_keys=("aliases", "our_org_aliases", "counterparty_aliases")):
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for x in node:
            yield from _all_regex_strings(x, skip_keys)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k not in skip_keys:
                yield from _all_regex_strings(v, skip_keys)


def test_patterns_compile():
    patterns = get_patterns()
    for key in ("cleaning", "segmentation", "sla_keywords", "parties", "governing_law", "facts"):
        assert key in patterns
    compiled = [re.compile(p) for p in _all_regex_strings(patterns)]
    assert len(compiled) > 30


def test_label_map_targets_are_categories():
    lm = get_label_map()
    for source in ("ledgar", "cuad"):
        for category in lm[source]:
            assert category in CATEGORIES
    assert "SLA" not in lm["ledgar"] and "SLA" not in lm["cuad"]


def test_contract_types_config():
    ct = get_contract_types()
    assert set(ct["types"]) | {"OTHER"} == set(CONTRACT_TYPES)
