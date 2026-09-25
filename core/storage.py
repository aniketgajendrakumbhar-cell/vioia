from pathlib import Path
import hashlib
import json
import shutil
import random

# ============================================================
# FORENSIC SIMULATION CONFIGURATION
# ============================================================
# High-overlap storage creates redundancy so selected missing/corrupted
# fragments can be reconstructed from neighboring copies.
FRAGMENT_SIZE = 4096
OVERLAP_SIZE = 3072
STEP_SIZE = FRAGMENT_SIZE - OVERLAP_SIZE

# Deterministic demo damage. Damage is real at the fragment level,
# but redundancy allows the original byte stream to be recovered.
DELETED_FRAGMENT_INTERVAL = 83
CORRUPTED_FRAGMENT_INTERVAL = 61
CORRUPTED_BYTES_PERCENT = 0.02

BASE_DIR = Path(__file__).resolve().parent.parent
LAB_DIR = BASE_DIR / "lab"
ACTIVE_DIR = LAB_DIR / "active"
DELETED_DIR = LAB_DIR / "deleted_storage"
RECOVERED_DIR = LAB_DIR / "recovered"
METADATA_FILE = LAB_DIR / "storage_metadata.json"

for folder in (ACTIVE_DIR, DELETED_DIR, RECOVERED_DIR):
    folder.mkdir(parents=True, exist_ok=True)


def calculate_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_active_files():
    return [p for p in ACTIVE_DIR.iterdir() if p.is_file()]


def get_deleted_files():
    return [p for p in DELETED_DIR.iterdir() if p.is_file()]


def save_metadata(filename, metadata):
    data = {}
    if METADATA_FILE.exists():
        try:
            data = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data[filename] = metadata
    METADATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_metadata(filename):
    if not METADATA_FILE.exists():
        return None
    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8")).get(filename)
    except (json.JSONDecodeError, OSError):
        return None


def register_file(file_path):
    file_path = Path(file_path)
    if not file_path.exists():
        return False
    save_metadata(file_path.name, {
        "filename": file_path.name,
        "size": file_path.stat().st_size,
        "sha256": calculate_sha256(file_path),
        "status": "active",
    })
    return True


def simulate_deletion(file_path):
    file_path = Path(file_path)
    if isinstance(file_path, str):
        file_path = ACTIVE_DIR / file_path
    if not file_path.exists():
        return {"success": False, "message": "File not found."}
    destination = DELETED_DIR / file_path.name
    shutil.move(str(file_path), str(destination))
    original_hash = calculate_sha256(destination)
    metadata = {
        "filename": destination.name,
        "size": destination.stat().st_size,
        "sha256": original_hash,
        "status": "deleted",
        "deleted_path": str(destination),
    }
    save_metadata(destination.name, metadata)
    return {
        "success": True,
        "message": f"{destination.name} moved to simulated deleted storage.",
        "filename": destination.name,
        "size": destination.stat().st_size,
        "sha256": original_hash,
    }


def _corrupt_bytes(data, seed):
    rng = random.Random(seed)
    arr = bytearray(data)
    changes = max(1, int(len(arr) * CORRUPTED_BYTES_PERCENT / 100))
    for _ in range(changes):
        pos = rng.randrange(len(arr))
        old = arr[pos]
        new = rng.randrange(256)
        while new == old:
            new = rng.randrange(256)
        arr[pos] = new
    return bytes(arr), changes


def create_damaged_fragments(file_path):
    """
    Split the original into heavily overlapping fragments.

    A small number of fragments are actually removed or byte-corrupted.
    The 75% overlap provides redundant copies of the same byte ranges,
    allowing the reconstruction engine to repair the damaged fragments.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return {"success": False, "message": "File not found."}

    data = file_path.read_bytes()
    filename = file_path.name
    original_size = len(data)
    original_hash = hashlib.sha256(data).hexdigest()

    for old in DELETED_DIR.glob(f"{filename}.fragment_*.bin"):
        try:
            old.unlink()
        except OSError:
            pass

    fragments = []
    for original_index, start in enumerate(range(0, len(data), STEP_SIZE)):
        chunk = data[start:start + FRAGMENT_SIZE]
        if not chunk:
            continue
        fragments.append({
            "original_index": original_index,
            "start_position": start,
            "data": chunk,
        })

    total = len(fragments)
    records = []
    deleted = []
    corrupted = []

    # Keep boundary fragments intact: their edge bytes have less redundancy.
    for fragment in fragments:
        idx = fragment["original_index"]
        is_boundary = idx == 0 or idx == total - 1

        status = "INTACT"
        output_data = fragment["data"]
        corruption_changes = 0

        if not is_boundary and idx % DELETED_FRAGMENT_INTERVAL == 0:
            status = "DELETED"
            deleted.append(idx)
        elif not is_boundary and idx % CORRUPTED_FRAGMENT_INTERVAL == 0:
            status = "CORRUPTED"
            output_data, corruption_changes = _corrupt_bytes(
                fragment["data"], seed=idx + 9173
            )
            corrupted.append(idx)

        record = {
            "fragment_name": f"{filename}.fragment_{idx:04d}.bin",
            "original_index": idx,
            "start_position": fragment["start_position"],
            "size": len(fragment["data"]),
            "status": status,
            "corrupted": status == "CORRUPTED",
            "deleted": status == "DELETED",
            "missing": status in {"DELETED", "MISSING"},
            "corruption_changes": corruption_changes,
            "original_sha256": hashlib.sha256(fragment["data"]).hexdigest(),
            "stored_sha256": (
                hashlib.sha256(output_data).hexdigest()
                if status != "DELETED" else None
            ),
        }
        records.append(record)

        if status != "DELETED":
            # Storage filename follows original index so the dashboard is easy to read.
            (DELETED_DIR / record["fragment_name"]).write_bytes(output_data)

    status_summary = {
        "INTACT": sum(r["status"] == "INTACT" for r in records),
        "CORRUPTED": sum(r["status"] == "CORRUPTED" for r in records),
        "DELETED": sum(r["status"] == "DELETED" for r in records),
        "MISSING": 0,
        "SUSPICIOUS": 0,
    }

    metadata = {
        "filename": filename,
        "size": original_size,
        "sha256": original_hash,
        "status": "deleted_and_fragmented",
        "simulation_mode": "redundant_forensic_recovery",
        "fragment_size": FRAGMENT_SIZE,
        "overlap_size": OVERLAP_SIZE,
        "step_size": STEP_SIZE,
        "total_fragments": total,
        "available_fragments": total - len(deleted),
        "missing_fragments": deleted,
        "deleted_fragments": deleted,
        "corrupted_fragments": corrupted,
        "fragment_status_summary": status_summary,
        "fragment_records": records,
    }
    save_metadata(filename, metadata)

    file_path.unlink()

    return {
        "success": True,
        "filename": filename,
        "original_size": original_size,
        "total_fragments": total,
        "available_fragments": total - len(deleted),
        "missing_fragments": deleted,
        "deleted_fragments": deleted,
        "corrupted_fragments": corrupted,
        "fragment_records": records,
        "simulation_mode": "redundant_forensic_recovery",
    }


def restore_file(filename):
    source = DELETED_DIR / filename
    if not source.exists():
        return {"success": False, "message": "Deleted file not found."}
    destination = RECOVERED_DIR / filename
    shutil.copy2(source, destination)
    recovered_hash = calculate_sha256(destination)
    metadata = get_metadata(filename) or {}
    return {
        "success": True,
        "filename": filename,
        "recovered_path": str(destination),
        "sha256": recovered_hash,
        "integrity": metadata.get("sha256") == recovered_hash,
    }
