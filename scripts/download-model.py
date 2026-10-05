"""Explicit setup-only download. Never reads or uploads personal data."""
import argparse
import hashlib
import json
import shutil
import os
import sys
import urllib.request
from pathlib import Path

MODEL = "Qwen3.5-4B-Q4_K_M.gguf"
SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
URL = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/720bb031aae5488eae5d6a78768e6d826662b2ae/" + MODEL
ROOT = Path(__file__).resolve().parent.parent
FAST_MODEL = "Qwen3-0.6B-Q4_K_M.gguf"
FAST_REVISION = "f2d6f9ca53a254cc379437c49e4b2eb447f779df"
FAST_SHA256 = "ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a"
FAST_URL = f"https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/{FAST_REVISION}/{FAST_MODEL}"

TEXT_MODEL = "Qwen3-1.7B-Q4_K_M.gguf"
TEXT_REVISION = "bd59ef4"  # upstream file revision; checksum pins the exact bytes
TEXT_SHA256 = "b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897"
TEXT_URL = f"https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/{TEXT_REVISION}/{TEXT_MODEL}"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def download(destination, url, expected, algorithm="sha256", maximum=4_000_000_000):
    destination.parent.mkdir(parents=True, exist_ok=True)
    def checksum(path):
        if algorithm == "sha256":
            return digest(path)
        data = path.read_bytes()
        return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if destination.exists():
        if checksum(destination) != expected:
            raise ValueError(f"Existing {destination.name} checksum differs; keeping it untouched")
        print(f"Verified: {destination.name}")
        return
    temporary = destination.with_name(destination.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "keno-model-setup/0.2"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as file:
            total = 0
            while chunk := response.read(4 * 1024 * 1024):
                file.write(chunk)
                total += len(chunk)
                if total > maximum:
                    raise ValueError("Unexpected download size")
                print(f"\r{destination.name}: {total / 1_000_000:.0f} MB downloaded", end="", flush=True)
        print("\nVerifying checksum…")
        if checksum(temporary) != expected:
            raise ValueError(f"Checksum mismatch: {destination.name}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def download_laya():
    repo = "convaiinnovations/laya-multilingual"
    revision = "e4e9ddf21a7b1903b7acffd8814ad4307bf63a67"  # upstream reviewed checkpoint
    url = f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true&limit=1000"
    with urllib.request.urlopen(url, timeout=60) as response:
        entries = json.load(response)
    required = {"model.safetensors", "rl_agent_config.json", "encoder/config.json", "tokenizer/tokenizer.json", "tokenizer/tokenizer_config.json"}
    files = [e for e in entries if e.get("type") == "file" and
             (e["path"] in {"model.safetensors", "rl_agent_config.json"} or e["path"].startswith(("encoder/", "tokenizer/")))]
    if not required <= {e["path"] for e in files}:
        raise ValueError("Laya snapshot is incomplete; no checkpoint was activated")
    manifest = {}
    for entry in files:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid checkpoint filename")
        large = entry.get("lfs")
        expected = large["oid"] if large else entry["oid"]
        algorithm = "sha256" if large else "git-sha1"
        destination = ROOT / "models" / "laya" / relative
        download(destination, f"https://huggingface.co/{repo}/resolve/{revision}/{entry['path']}", expected, algorithm,
                 maximum=800_000_000 if large else 50_000_000)
        manifest[entry["path"]] = {"checksum": expected, "algorithm": algorithm}
    (ROOT / "models" / "laya" / "keno-manifest.json").write_text(json.dumps({"repo": repo, "revision": revision, "files": manifest}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["0.6b", "1.7b", "2b", "4b"], default="2b")
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--laya", action="store_true")
    args = parser.parse_args()
    if args.vision and args.model != "2b":
        raise SystemExit("This vision profile requires the matching Qwen 2B model")
    (ROOT / "models").mkdir(exist_ok=True)
    needed = {"0.6b": 397_000_000, "1.7b": 1_110_000_000, "2b": 1_280_000_000, "4b": 2_740_000_000}[args.model]
    needed += 668_000_000 if args.vision else 0
    needed += 750_000_000 if args.laya else 0
    # Existing files can be verified with no extra space. This check is advisory;
    # each incomplete download is removed on error as before.
    print(f"Setup downloads up to {needed / 1e9:.2f} GB; free disk: {shutil.disk_usage(ROOT).free / 1e9:.2f} GB. No personal data is sent.")
    try:
        if args.model == "0.6b":
            download(ROOT / "models" / FAST_MODEL, FAST_URL, FAST_SHA256, maximum=500_000_000)
        elif args.model == "1.7b":
            download(ROOT / "models" / TEXT_MODEL, TEXT_URL, TEXT_SHA256, maximum=1_300_000_000)
        elif args.model == "4b":
            download(ROOT / "models" / MODEL, URL, SHA256)
        else:
            revision = "f6d5376be1edb4d416d56da11e5397a961aca8ae"
            base = f"https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/{revision}/"
            download(ROOT / "models" / "Qwen3.5-2B-Q4_K_M.gguf", base + "Qwen3.5-2B-Q4_K_M.gguf",
                     "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223")
            if args.vision:
                download(ROOT / "models" / "Qwen3.5-2B-mmproj-F16.gguf", base + "mmproj-F16.gguf",
                         "7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7")
        if args.laya:
            download_laya()
    except Exception as error:
        raise SystemExit(f"Download failed: {error}. Existing verified files were preserved.")
    print("Selected model assets are ready.")


if __name__ == "__main__":
    main()
