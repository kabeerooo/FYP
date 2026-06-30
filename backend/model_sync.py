# model_sync.py
#
# Railway's container filesystem is ephemeral — anything the auto-retrain
# scheduler writes to ml_models/ is lost on the next deploy/restart.
# This module mirrors model files to Firebase Storage so retrained models
# survive restarts, and pulls the latest copy back down on startup.

from pathlib import Path
from firebase_admin import storage

_STORAGE_PREFIX = "ml_models"


def upload_model_files(ticker: str, file_paths: list[Path]) -> None:
    """Push a retrained model's files to Firebase Storage so they survive a container restart."""
    try:
        bucket = storage.bucket()
        for path in file_paths:
            blob = bucket.blob(f"{_STORAGE_PREFIX}/{ticker}/{path.name}")
            blob.upload_from_filename(str(path))
        print(f"☁️  Uploaded {len(file_paths)} model files for {ticker} to Firebase Storage")
    except Exception as exc:
        print(f"⚠️  Could not upload {ticker} models to Firebase Storage: {exc}")


def download_latest_models(models_dir: Path, asset_config: dict) -> None:
    """On startup, overwrite the bundled models with the latest retrained versions from
    Firebase Storage, if any exist. Falls back silently to the bundled models otherwise."""
    try:
        bucket = storage.bucket()
    except Exception as exc:
        print(f"⚠️  Firebase Storage unavailable, using bundled models: {exc}")
        return

    synced = 0
    for ticker, cfg in asset_config.items():
        for filename in (cfg["model_file"], cfg["scaler_feat"], cfg["scaler_tgt"]):
            blob = bucket.blob(f"{_STORAGE_PREFIX}/{ticker}/{filename}")
            try:
                if not blob.exists():
                    continue
                blob.download_to_filename(str(models_dir / filename))
                synced += 1
            except Exception as exc:
                print(f"⚠️  Could not download {filename} for {ticker}: {exc}")

    if synced:
        print(f"☁️  Synced {synced} model files from Firebase Storage")
    else:
        print("ℹ️  No retrained models in Firebase Storage yet — using bundled models")
