"""When the UI starts the API itself (Streamlit Community Cloud) and when it does not."""

from __future__ import annotations

import pytest

from frontend import embedded_backend


@pytest.mark.parametrize(("flag", "expected"), [("1", True), ("0", False)])
def test_flag_overrides_detection(
    monkeypatch: pytest.MonkeyPatch, flag: str, expected: bool
) -> None:
    monkeypatch.setenv("CG_EMBED_BACKEND", flag)
    assert embedded_backend._wanted() is expected


def test_off_by_default_outside_streamlit_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CG_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(
        embedded_backend, "Path", lambda _p: type("P", (), {"exists": lambda s: False})()
    )
    assert embedded_backend._wanted() is False


def test_ensure_backend_does_nothing_when_not_wanted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CG_EMBED_BACKEND", "0")
    monkeypatch.delenv("CG_API_URL", raising=False)
    embedded_backend.ensure_backend()
    import os

    assert "CG_API_URL" not in os.environ
