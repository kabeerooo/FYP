import math
from datetime import datetime
from pathlib import Path
from firebase_admin import firestore

_COLLECTION = "ml_model_files"
_CHUNK_SIZE = 950 * 1024  # stay under Firestore's 1 MB document limit


def _chunk_id(ticker: str, filename: str, index: int) -> str:
    return f"{ticker}__{filename}__{index}"


def _meta_id(ticker: str, filename: str) -> str:
    return f"{ticker}__{filename}__meta"


def upload_model_files(ticker: str, file_paths: list[Path]) -> None:
    """Store retrained model files in Firestore so they survive a Railway container restart."""
    try:
        db = firestore.client()
        col = db.collection(_COLLECTION)
        uploaded = 0
        for path in file_paths:
            raw = path.read_bytes()
            total_chunks = math.ceil(len(raw) / _CHUNK_SIZE) or 1
            for i in range(total_chunks):
                col.document(_chunk_id(ticker, path.name, i)).set({
                    "data": raw[i * _CHUNK_SIZE : (i + 1) * _CHUNK_SIZE],
                    "chunk_index": i,
                })
            col.document(_meta_id(ticker, path.name)).set({
                "total_chunks": total_chunks,
                "size": len(raw),
                "updated_at": datetime.utcnow(),
            })
            uploaded += 1
        print(f"Saved {uploaded} model files for {ticker} to Firestore")
    except Exception as exc:
        print(f"Could not save {ticker} models to Firestore: {exc}")


def download_latest_models(models_dir: Path, asset_config: dict) -> None:
    """On startup, overwrite bundled models with the latest retrained versions from Firestore."""
    try:
        db = firestore.client()
        col = db.collection(_COLLECTION)
    except Exception as exc:
        print(f"Firestore unavailable, using bundled models: {exc}")
        return

    synced = 0
    for ticker, cfg in asset_config.items():
        for filename in (cfg["model_file"], cfg["scaler_feat"], cfg["scaler_tgt"]):
            meta = col.document(_meta_id(ticker, filename)).get()
            if not meta.exists:
                continue
            total_chunks = meta.to_dict()["total_chunks"]
            try:
                chunks = []
                for i in range(total_chunks):
                    doc = col.document(_chunk_id(ticker, filename, i)).get()
                    chunks.append(bytes(doc.to_dict()["data"]))
                (models_dir / filename).write_bytes(b"".join(chunks))
                synced += 1
            except Exception as exc:
                print(f"Could not restore {filename} for {ticker}: {exc}")

    if synced:
        print(f"Restored {synced} model files from Firestore")
    else:
        print("No retrained models in Firestore yet — using bundled models")
