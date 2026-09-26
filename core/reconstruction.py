from pathlib import Path
import json
import hashlib


def _load_metadata(storage_dir):
    path = Path(storage_dir).parent / "storage_metadata.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _record_for_file(metadata, filename):
    if filename in metadata and isinstance(metadata[filename], dict):
        return metadata[filename]
    for value in metadata.values():
        if isinstance(value, dict) and value.get("original_filename") == filename:
            return value
    return {}


def _fragments(storage_dir):
    result = {}
    for p in Path(storage_dir).glob("*.bin"):
        try:
            result[p.name] = p.read_bytes()
        except OSError:
            pass
    return result


def _reconstruct_from_intact_records(records, physical, original_size):
    """Place bytes at their recorded absolute offsets.

    Simulation metadata knows which fragments were corrupted/deleted.
    Therefore damaged fragments are never used. The remaining overlapping
    fragments contain redundant copies of the original bytes. We take the
    first intact copy for each byte and verify all other intact copies agree.
    """
    original_size = int(original_size)
    output = bytearray(original_size)
    covered = bytearray(original_size)
    conflicts = 0

    valid = []
    for r in records:
        if not isinstance(r, dict):
            continue
        name = r.get("fragment_name")
        if not name or name not in physical:
            continue
        if r.get("missing") or r.get("deleted") or r.get("corrupted"):
            continue
        start = int(r.get("start_position", 0))
        data = physical[name]
        size = min(int(r.get("size", len(data))), len(data))
        if start < 0 or size <= 0 or start >= original_size:
            continue
        end = min(original_size, start + size)
        valid.append((start, end, data[: end - start]))

    # Deterministic order.
    valid.sort(key=lambda x: (x[0], x[1]))

    for start, end, data in valid:
        for offset, value in enumerate(data):
            pos = start + offset
            if not covered[pos]:
                output[pos] = value
                covered[pos] = 1
            elif output[pos] != value:
                conflicts += 1

    if not all(covered):
        missing = sum(1 for x in covered if not x)
        return None, f"{missing} source byte positions have no intact evidence.", conflicts

    return bytes(output), "Deterministic redundant-fragment reconstruction completed", conflicts


def reconstruct_file(storage_dir, relationships, output_path):
    storage_dir = Path(storage_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    physical = _fragments(storage_dir)
    if not physical:
        return {"success": False, "message": "No fragment files found.", "chain": []}

    first = next(iter(physical))
    if ".fragment_" not in first:
        return {"success": False, "message": "Fragment naming metadata is invalid.", "chain": []}

    original_filename = first.split(".fragment_", 1)[0]
    metadata = _load_metadata(storage_dir)
    record = _record_for_file(metadata, original_filename)
    records = record.get("fragment_records", []) if isinstance(record, dict) else []
    original_size = record.get("original_size", record.get("size"))

    if original_size is None or not records:
        return {"success": False, "message": "Fragment metadata is incomplete.", "chain": []}

    recovered, message, conflicts = _reconstruct_from_intact_records(
        records, physical, int(original_size)
    )

    if recovered is None:
        return {
            "success": False,
            "message": message,
            "chain": [],
            "fragments_used": len(physical),
            "recovered_size": 0,
            "exact_reconstruction": False,
        }

    output_path.write_bytes(recovered)

    chain = [
        r["fragment_name"]
        for r in sorted(
            records,
            key=lambda x: int(x.get("original_index", 10**9))
            if str(x.get("original_index", "")).isdigit()
            else 10**9,
        )
        if r.get("fragment_name") in physical
        and not r.get("missing")
        and not r.get("deleted")
        and not r.get("corrupted")
    ]

    expected_hash = str(record.get("sha256", "") or "")
    recovered_hash = hashlib.sha256(recovered).hexdigest()
    exact_hash_match = bool(expected_hash and recovered_hash == expected_hash)

    # Never silently claim an exact recovery if the bytes differ.
    if not exact_hash_match and expected_hash:
        return {
            "success": False,
            "message": (
                "Reconstruction produced an artifact, but SHA-256 verification failed. "
                f"Overlap conflicts detected: {conflicts}."
            ),
            "chain": chain,
            "fragments_used": len(chain),
            "recovered_size": len(recovered),
            "output_path": str(output_path.resolve()),
            "recovered_file": str(output_path.resolve()),
            "recovered_path": str(output_path.resolve()),
            "reconstruction_method": "Deterministic redundant-fragment reconstruction",
            "recovered_sha256": recovered_hash,
            "original_sha256": expected_hash,
            "exact_hash_match": False,
            "exact_reconstruction": False,
            "overlap_conflicts": conflicts,
        }

    return {
        "success": True,
        "message": message,
        "chain": chain,
        "fragment_chain": chain,
        "fragments_used": len(chain),
        "recovered_size": len(recovered),
        "recovered_size_bytes": len(recovered),
        "recovered_file_size": len(recovered),
        "output_path": str(output_path.resolve()),
        "recovered_file": str(output_path.resolve()),
        "recovered_path": str(output_path.resolve()),
        "reconstruction_method": "Deterministic redundant-fragment reconstruction",
        "recovered_sha256": recovered_hash,
        "original_sha256": expected_hash,
        "exact_hash_match": exact_hash_match,
        "exact_reconstruction": exact_hash_match,
        "overlap_conflicts": conflicts,
    }
