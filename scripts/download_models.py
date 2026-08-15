import json
import urllib.request
import zipfile
from pathlib import Path

from huggingface_hub import hf_hub_download

from dictate import config


def download_cleanup_model() -> None:
    print(f"Downloading {config.CLEANUP_MODEL_FILENAME} from {config.CLEANUP_MODEL_REPO}...")
    path = hf_hub_download(
        repo_id=config.CLEANUP_MODEL_REPO,
        filename=config.CLEANUP_MODEL_FILENAME,
        local_dir=config.CLEANUP_MODEL_PATH.parent,
    )
    print(f"Saved to {path}")


def download_llamacpp_binaries() -> None:
    if config.LLAMACPP_SERVER_EXE.exists():
        print(f"{config.LLAMACPP_SERVER_EXE} already present, skipping.")
        return

    print(f"Looking up latest release for {config.LLAMACPP_RELEASE_REPO}...")
    api_url = f"https://api.github.com/repos/{config.LLAMACPP_RELEASE_REPO}/releases/latest"
    with urllib.request.urlopen(api_url) as resp:
        release = json.loads(resp.read())

    asset = next(
        (a for a in release["assets"] if a["name"].endswith(config.LLAMACPP_ASSET_PATTERN)),
        None,
    )
    if asset is None:
        raise RuntimeError(
            f"No release asset matching '{config.LLAMACPP_ASSET_PATTERN}' found in "
            f"{config.LLAMACPP_RELEASE_REPO} release {release.get('tag_name')}"
        )

    print(f"Downloading {asset['name']} ({asset['size'] / 1_000_000:.1f} MB)...")
    config.LLAMACPP_BIN_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = config.LLAMACPP_BIN_DIR / asset["name"]
    urllib.request.urlretrieve(asset["browser_download_url"], zip_path)

    print("Extracting...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(config.LLAMACPP_BIN_DIR)
    zip_path.unlink()
    print(f"Saved to {config.LLAMACPP_BIN_DIR}")


def main() -> None:
    download_cleanup_model()
    download_llamacpp_binaries()
    print("(faster-whisper's model downloads automatically on first use -- nothing to do there.)")


if __name__ == "__main__":
    main()
