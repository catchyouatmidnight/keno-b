import hashlib
import os
import runpy
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_fast_switch_preserves_data_and_rejects_unverified_model(tmp_path, monkeypatch):
    script = runpy.run_path(str(ROOT / "scripts" / "enable-fast.py"))
    env = tmp_path / ".env"
    original = "# installation\nKENO_API_KEY=keep-local-key\nPORT=18081\nCPU_THREADS=4\nMODEL_FILE=old\nMODEL_FILE=duplicate\nVISION_ENABLED=true\nCONTEXT_SIZE=8192\n"
    env.write_text(original)
    models = tmp_path / "models"
    (models / "laya").mkdir(parents=True)
    (models / "laya" / "keno-manifest.json").write_text("{}")
    model = models / "Qwen3-0.6B-Q4_K_M.gguf"
    model.write_bytes(b"fixture")
    data = tmp_path / "data"
    data.mkdir()
    (data / "keno.db").write_bytes(b"personal database")
    with pytest.raises(SystemExit, match="checksum"):
        script["configure"](tmp_path)
    assert env.read_text() == original
    real_run = runpy.run_path
    def fixture_assets(path):
        assets = real_run(path)
        assets["FAST_SHA256"] = hashlib.sha256(b"fixture").hexdigest()
        return assets
    monkeypatch.setattr(runpy, "run_path", fixture_assets)
    script["configure"](tmp_path)
    text = env.read_text()
    assert text.count("MODEL_FILE=") == 1
    assert "MODEL_FILE=Qwen3-0.6B-Q4_K_M.gguf" in text
    assert "VISION_ENABLED=false" in text
    assert "CONTEXT_SIZE=4096" in text
    assert "KENO_API_KEY=keep-local-key" in text and "PORT=18081" in text
    assert "CPU_THREADS=4" in text
    assert env.stat().st_mode & 0o777 == 0o600
    assert (data / "keno.db").read_bytes() == b"personal database"


def test_entrypoint_removes_projector_for_text_and_preserves_quoted_arguments(tmp_path):
    # Replace only the executable path with a recorder; exercise the real shell branches.
    recorder = tmp_path / "record.sh"
    recorder.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    recorder.chmod(0o700)
    wrapper = tmp_path / "entrypoint.sh"
    wrapper.write_text((ROOT / "scripts" / "llm-entrypoint.sh").read_text().replace("exec /app/llama-server", f'exec "{recorder}"'))
    env = {**os.environ, "VISION_ENABLED": "false", "MMPROJ_FILE": "projector with spaces.gguf"}
    args = ["sh", str(wrapper), "--model", "/models/model with spaces.gguf"]
    text = subprocess.run(args, env=env, capture_output=True, text=True, check=True).stdout.splitlines()
    assert text == ["--model", "/models/model with spaces.gguf"]
    env["VISION_ENABLED"] = "true"
    vision = subprocess.run(args, env=env, capture_output=True, text=True, check=True).stdout.splitlines()
    assert vision == text + ["--mmproj", "/models/projector with spaces.gguf", "--no-mmproj-offload", "--image-max-tokens", "1024"]
    env["VISION_ENABLED"] = "invalid"
    assert subprocess.run(args, env=env, capture_output=True).returncode == 1
