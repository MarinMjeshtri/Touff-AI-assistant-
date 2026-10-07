from pathlib import Path

import pytest

from touff import store, voicepack
from touff.audio import expressive


@pytest.fixture
def installed_app(tmp_path, monkeypatch):
    """Pretend to be the PyInstaller build with %LOCALAPPDATA% in tmp_path."""
    monkeypatch.setattr(store, "FROZEN", True)
    monkeypatch.setattr(voicepack, "FROZEN", True)
    monkeypatch.delenv("TOUFF_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


def test_source_checkout_uses_project_venv():
    assert voicepack.python_path() == store.PROJECT_ROOT / ".venv-voice" / "Scripts" / "python.exe"
    assert voicepack.python_dir() == store.PROJECT_ROOT / ".python"
    assert expressive.available() == voicepack.python_path().exists()


def test_installed_app_paths(installed_app):
    pack = installed_app / "Touff" / "voice-pack"
    assert voicepack.python_path() == pack / "venv" / "Scripts" / "python.exe"
    assert voicepack.python_dir() == pack / "python"
    assert store.models_dir() == installed_app / "Touff" / "models"


def test_installed_only_after_marker(installed_app):
    py = voicepack.python_path()
    py.parent.mkdir(parents=True)
    py.write_bytes(b"")
    assert not voicepack.installed()  # half-finished install
    (voicepack.venv_dir() / voicepack.MARKER).write_text("{}")
    assert voicepack.installed()
    assert expressive.available()


def test_refuses_without_nvidia_gpu(installed_app, monkeypatch):
    monkeypatch.setattr(voicepack, "gpu_name", lambda: None)
    monkeypatch.setattr(voicepack.subprocess, "Popen", lambda *a, **k: pytest.fail("ran uv"))
    with pytest.raises(voicepack.VoicePackError, match="NVIDIA"):
        voicepack.install(print)


def test_dry_run_reports_uv_steps(installed_app, monkeypatch):
    monkeypatch.setattr(voicepack, "gpu_name", lambda: "NVIDIA GeForce RTX 4050")
    monkeypatch.setattr(voicepack, "uv_path", lambda: Path("C:/app/uv.exe"))
    monkeypatch.setattr(voicepack.subprocess, "Popen", lambda *a, **k: pytest.fail("ran uv"))
    lines: list[str] = []
    py = voicepack.install(lines.append, dry_run=True)
    commands = [line for line in lines if "would run" in line]
    assert len(commands) == 5
    assert "python install 3.12" in commands[0]
    assert str(voicepack.venv_dir()) in commands[1]
    assert "torch==2.6.0" in commands[2] and voicepack.TORCH_INDEX in commands[2]
    assert "chatterbox-tts faster-whisper" in commands[3]
    assert "--download-only" in commands[4] and str(voicepack.SERVER) in commands[4]
    assert py == voicepack.python_path()
    assert not voicepack.installed()
