import json
import subprocess
import sys

from contractguard.cli import main


def test_help_via_module():
    out = subprocess.run(
        [sys.executable, "-m", "contractguard.cli", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "analyze" in out.stdout and "Not legal advice" in out.stdout


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out


def test_config_hides_secret(capsys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "top-secret")
    assert main(["config"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["gemini_api_key_set"] is True
    assert "top-secret" not in json.dumps(data)


def test_analyze_missing_file(tmp_path):
    assert main(["analyze", str(tmp_path / "nope.pdf")]) == 2
