"""The settings page dies completely on a single JS syntax error (nothing is clickable),
so every script the UI ships gets parsed here. Needs Node; skipped without it."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "touff" / "ui" / "web"
NODE = shutil.which("node")


def _scripts():
    for js in sorted(WEB.glob("*.js")):
        yield js.name, js.read_text(encoding="utf-8")
    for html in sorted(WEB.glob("*.html")):
        for i, body in enumerate(re.findall(r"<script>(.*?)</script>", html.read_text(encoding="utf-8"), re.S)):
            yield f"{html.name} <script #{i}>", body


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("name,source", list(_scripts()), ids=lambda v: v if isinstance(v, str) and len(v) < 40 else "")
def test_ui_script_parses(tmp_path, name, source):
    f = tmp_path / "check.js"
    f.write_text(source, encoding="utf-8")
    result = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True)
    assert result.returncode == 0, f"{name} has a syntax error:\n{result.stderr}"
