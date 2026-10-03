"""Explicit setup-only download. Never reads or uploads personal data."""
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

MODEL = "Qwen3.5-4B-Q4_K_M.gguf"
SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
URL = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/720bb031aae5488eae5d6a78768e6d826662b2ae/" + MODEL
ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main():
    destination = ROOT / "models" / MODEL
    destination.parent.mkdir(exist_ok=True)
    if destination.exists():
        if digest(destination) != SHA256:
            raise SystemExit("Existing model checksum differs; keeping file untouched. Rename it before retrying.")
        print("Model already downloaded and verified.")
        return
    temporary = destination.with_suffix(".gguf.part")
    print("Downloading approximately 2.74 GB from Hugging Face. No personal data is sent.")
    request = urllib.request.Request(URL, headers={"User-Agent": "keno-model-setup/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as file:
            total = 0
            while chunk := response.read(4 * 1024 * 1024):
                file.write(chunk)
                total += len(chunk)
                if total > 4_000_000_000:
                    raise ValueError("Unexpected download size")
                print(f"\r{total / 1_000_000:.0f} MB downloaded", end="", flush=True)
        print("\nVerifying SHA256…")
        if digest(temporary) != SHA256:
            raise ValueError("Checksum mismatch; model was not installed")
        os.replace(temporary, destination)
    except Exception as error:
        temporary.unlink(missing_ok=True)
        raise SystemExit(f"Download failed: {error}. You can import a verified GGUF manually.")
    print(f"Ready: {destination.name}")


if __name__ == "__main__":
    main()
