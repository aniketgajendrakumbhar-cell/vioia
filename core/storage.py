
from pathlib import Path
import hashlib
import json
import random

FRAGMENT_SIZE = 8192
OVERLAP_SIZE = 6144
MISSING_PROBABILITY = 0.0
CORRUPTION_PROBABILITY = 0.0

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


def save_metadata(filename, metadata):
    data = {}
    if METADATA_FILE.exists():
        try:
            data = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[filename] = metadata
    METADATA_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_metadata(filename):
    if not METADATA_FILE.exists():
        return None
    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8")).get(filename)
    except Exception:
        return None


def get_active_files():
    return [p for p in ACTIVE_DIR.iterdir() if p.is_file()]


def get_deleted_files():
    return [p for p in DELETED_DIR.iterdir() if p.is_file()]


def _choose_damage_indices(fragments, target_missing, target_corrupted):
    """Choose as many visible damage points as possible while preserving coverage."""
    n = len(fragments)
    if n < 8:
        return [], []

    rng = random.Random(20260926 + n)
    candidates = list(range(1, n - 1))
    rng.shuffle(candidates)

    missing, corrupted = [], []

    def covered_with(extra):
        for f in fragments:
            f["missing"] = False
            f["corrupted"] = False
        for idx in extra:
            fragments[idx]["missing"] = idx in missing
            fragments[idx]["corrupted"] = idx in corrupted
        return _coverage_is_complete(fragments)

    # Alternate states so the dashboard visibly contains different evidence
    # conditions. Every accepted damage point is coverage-safe.
    targets = [("missing", target_missing), ("corrupted", target_corrupted)]
    accepted = []
    for kind, target in targets:
        count = 0
        for idx in candidates:
            if idx in accepted or count >= target:
                continue
            trial = accepted + [idx]
            # Temporarily mark the trial as the requested state.
            for f in fragments:
                f["missing"] = False
                f["corrupted"] = False
            for j in accepted:
                if j in missing:
                    fragments[j]["missing"] = True
                elif j in corrupted:
                    fragments[j]["corrupted"] = True
            if kind == "missing":
                fragments[idx]["missing"] = True
            else:
                fragments[idx]["corrupted"] = True

            if _coverage_is_complete(fragments):
                accepted.append(idx)
                if kind == "missing":
                    missing.append(idx)
                else:
                    corrupted.append(idx)
                count += 1

    # Restore clean state; caller applies the final statuses.
    for f in fragments:
        f["missing"] = False
        f["corrupted"] = False

    return sorted(missing), sorted(corrupted)


def _coverage_is_complete(fragments):
    """Check whether every original byte has at least one intact fragment."""
    total = max((f["start_position"] + f["size"] for f in fragments), default=0)
    covered = bytearray(total)
    for f in fragments:
        if f["missing"] or f["corrupted"]:
            continue
        start = f["start_position"]
        end = min(total, start + f["size"])
        if end > start:
            covered[start:end] = b"\x01" * (end - start)
    return all(covered)


def create_damaged_fragments(file_path):
    """Create a highly redundant forensic storage set with visible damage.

    The demo intentionally creates multiple missing/deleted and corrupted
    fragments while preserving enough redundant byte coverage for exact
    reconstruction. The original file is never used as the recovered output;
    it is only used to create the simulated storage evidence.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return {"success": False, "message": "File not found."}

    data = file_path.read_bytes()
    filename = file_path.name
    original_hash = hashlib.sha256(data).hexdigest()

    for folder in (DELETED_DIR, RECOVERED_DIR):
        for old in folder.glob(f"{filename}.fragment_*.bin"):
            old.unlink()

    step = max(1, FRAGMENT_SIZE - OVERLAP_SIZE)
    fragments = []
    for start in range(0, len(data), step):
        chunk = data[start:start + FRAGMENT_SIZE]
        if not chunk:
            continue
        fragments.append({
            "original_index": len(fragments),
            "start_position": start,
            "size": len(chunk),
            "data": chunk,
            "corrupted": False,
            "missing": False,
            "deleted": False,
        })

    # Scale damage with the number of fragments, with a useful minimum for
    # hackathon demonstrations.
    n = len(fragments)
    target_missing = max(3, round(n * 0.06))
    target_corrupted = max(4, round(n * 0.07))

    missing_indices, corrupted_indices = _choose_damage_indices(
        fragments, target_missing, target_corrupted
    )

    for idx in missing_indices:
        fragments[idx]["missing"] = True
        fragments[idx]["deleted"] = True

    for idx in corrupted_indices:
        frag = fragments[idx]
        buf = bytearray(frag["data"])
        if buf:
            # Multiple damaged byte regions make corruption visible in analysis.
            changes = max(12, min(96, len(buf) // 30))
            rng = random.Random(7000 + idx + len(data))
            for _ in range(changes):
                pos = rng.randrange(len(buf))
                width = rng.randint(1, min(8, len(buf) - pos))
                for p in range(pos, pos + width):
                    buf[p] = (buf[p] ^ rng.randint(1, 255)) & 0xFF
        frag["data"] = bytes(buf)
        frag["corrupted"] = True

    # If the selected damage leaves any byte without an intact copy, remove
    # the most recent damage targets until coverage is complete.
    while not _coverage_is_complete(fragments):
        active = [
            i for i, f in enumerate(fragments)
            if f["missing"] or f["corrupted"]
        ]
        if not active:
            break
        idx = active[-1]
        f = fragments[idx]
        f["missing"] = False
        f["deleted"] = False
        f["corrupted"] = False
        start = f["start_position"]
        f["data"] = data[start:start + f["size"]]

    present = [f for f in fragments if not f["missing"]]
    rng = random.Random(9001 + len(data))
    rng.shuffle(present)

    records = []
    for frag in fragments:
        name = f"{filename}.fragment_{frag['original_index']:04d}.bin"
        status = (
            "DELETED" if frag["deleted"]
            else "CORRUPTED" if frag["corrupted"]
            else "INTACT"
        )
        if frag["deleted"]:
            damage_type = "DELETED FROM STORAGE"
        elif frag["corrupted"]:
            damage_type = "BYTE MUTATION"
        else:
            damage_type = "NONE"
        records.append({
            "fragment_name": name,
            "filename": name,
            "original_index": frag["original_index"],
            "start_position": frag["start_position"],
            "size": frag["size"],
            "corrupted": bool(frag["corrupted"]),
            "missing": bool(frag["missing"]),
            "deleted": bool(frag["deleted"]),
            "status": status,
            "damage_type": damage_type,
            "corruption_regions": (8 if frag["corrupted"] else 0),
        })

    for frag in present:
        name = f"{filename}.fragment_{frag['original_index']:04d}.bin"
        (DELETED_DIR / name).write_bytes(frag["data"])

    missing = [f["original_index"] for f in fragments if f["missing"]]
    deleted = [f["original_index"] for f in fragments if f["deleted"]]
    corrupted = [f["original_index"] for f in fragments if f["corrupted"]]

    metadata = {
        "filename": filename,
        "original_filename": filename,
        "size": len(data),
        "original_size": len(data),
        "sha256": original_hash,
        "status": "damaged_storage",
        "fragment_size": FRAGMENT_SIZE,
        "overlap_size": OVERLAP_SIZE,
        "total_fragments": len(fragments),
        "available_fragments": len(present),
        "missing_fragments": missing,
        "deleted_fragments": deleted,
        "corrupted_fragments": corrupted,
        "fragment_records": records,
        "damage_profile": {
            "missing_target_percent": 6.0,
            "corrupted_target_percent": 7.0,
            "redundancy": f"{OVERLAP_SIZE / FRAGMENT_SIZE:.0%}",
            "reconstructable": True,
            "coverage_verified": True,
        },
    }
    save_metadata(filename, metadata)

    file_path.unlink()

    return {
        "success": True,
        "filename": filename,
        "original_size": len(data),
        "total_fragments": len(fragments),
        "available_fragments": len(present),
        "missing_fragments": missing,
        "deleted_fragments": deleted,
        "corrupted_fragments": corrupted,
        "fragment_records": records,
    }
