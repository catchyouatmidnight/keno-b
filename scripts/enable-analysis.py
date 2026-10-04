"""Switch model configuration without replacing credentials, ports or personal data."""
import os
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
path = root / ".env"
if not path.exists():
    raise SystemExit("Run bash scripts/setup.sh first")
required = ["Qwen3.5-2B-Q4_K_M.gguf", "Qwen3.5-2B-mmproj-F16.gguf", "laya/keno-manifest.json"]
if any(not (root / "models" / name).is_file() for name in required):
    raise SystemExit("Download the complete profile first: python3 scripts/download-model.py --model 2b --vision --laya")
settings = {"MODEL_FILE": "Qwen3.5-2B-Q4_K_M.gguf", "MMPROJ_FILE": "Qwen3.5-2B-mmproj-F16.gguf", "VISION_ENABLED": "true", "CONTEXT_SIZE": "8192"}
text = path.read_text()
for key, value in settings.items():
    if re.search(r"^" + key + r"=", text, re.M):
        text = re.sub(r"^" + key + r"=.*$", key + "=" + value, text, flags=re.M)
    else:
        text = text.rstrip() + "\n" + key + "=" + value + "\n"
temporary = path.with_name(".env.analysis.tmp")
with open(temporary, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
    file.write(text)
os.replace(temporary, path)
print("Configured Qwen 2B vision and automatic Laya routing. Credentials, port and data preserved.")
