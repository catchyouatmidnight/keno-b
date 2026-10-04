"""Activate the verified Qwen3 0.6B text model while preserving personal data."""
import os
import re
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def configure(root=ROOT):
    path = root / ".env"
    if not path.is_file():
        raise SystemExit("Run bash scripts/setup.sh first")
    assets = runpy.run_path(str(ROOT / "scripts" / "download-model.py"))
    model = root / "models" / assets["FAST_MODEL"]
    if not model.is_file():
        raise SystemExit("Download first: python3 scripts/download-model.py --model 0.6b")
    if model.stat().st_size > 500_000_000 or assets["digest"](model) != assets["FAST_SHA256"]:
        raise SystemExit("Model checksum differs; configuration was not changed")
    if not (root / "models" / "laya" / "keno-manifest.json").is_file():
        raise SystemExit("Download the router first: python3 scripts/download-model.py --model 0.6b --laya")
    settings = {"MODEL_FILE": assets["FAST_MODEL"], "VISION_ENABLED": "false", "CONTEXT_SIZE": "4096"}
    # Replace duplicate entries with one value, retaining unrelated settings/comments.
    lines = []
    for line in path.read_text().splitlines():
        if not any(re.match(r"^\s*" + key + r"\s*=", line) for key in settings):
            lines.append(line)
    text = "\n".join(lines).rstrip() + "\n" + "".join(f"{key}={value}\n" for key, value in settings.items())
    temporary = path.with_name(".env.fast.tmp")
    try:
        with open(temporary, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    print("Configured Qwen3 0.6B, 4096-token context, text only. Laya still decides thinking automatically.")
    print("Chats, memories, credentials, port, and previous model files were preserved.")
    print("Apply: docker compose up -d --no-deps --force-recreate llm backend")


if __name__ == "__main__":
    configure()
