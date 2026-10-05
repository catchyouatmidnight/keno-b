"""Activate a verified Qwen3 text model while preserving personal data."""
import argparse
import os
import re
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def configure(root=ROOT, model_size="0.6b"):
    if model_size not in {"0.6b", "1.7b"}:
        raise SystemExit("Choose --model 0.6b or --model 1.7b")
    path = root / ".env"
    if not path.is_file():
        raise SystemExit("Run bash scripts/setup.sh first")
    assets = runpy.run_path(str(ROOT / "scripts" / "download-model.py"))
    prefix = "TEXT" if model_size == "1.7b" else "FAST"
    filename, expected = assets[prefix + "_MODEL"], assets[prefix + "_SHA256"]
    maximum = 1_300_000_000 if model_size == "1.7b" else 500_000_000
    model = root / "models" / filename
    if not model.is_file():
        raise SystemExit(f"Download first: python3 scripts/download-model.py --model {model_size}")
    if model.stat().st_size > maximum or assets["digest"](model) != expected:
        raise SystemExit("Model checksum differs; configuration was not changed")
    if not (root / "models" / "laya" / "keno-manifest.json").is_file():
        raise SystemExit(f"Download the router first: python3 scripts/download-model.py --model {model_size} --laya")
    settings = {"MODEL_FILE": filename, "VISION_ENABLED": "false", "CONTEXT_SIZE": "4096"}
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
    print(f"Configured Qwen3 {model_size.upper()}, 4096-token context, text only. Laya still decides thinking automatically.")
    print("Chats, memories, credentials, port, and previous model files were preserved.")
    print("Apply: docker compose up -d --no-deps --force-recreate llm backend")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["0.6b", "1.7b"], default="0.6b")
    configure(model_size=parser.parse_args().model)
