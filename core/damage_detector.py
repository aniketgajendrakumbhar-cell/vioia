from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent
LAB_DIR = BASE_DIR / "lab"
DELETED_DIR = LAB_DIR / "deleted_storage"
ACTIVE_DIR = LAB_DIR / "active"
METADATA_FILE = LAB_DIR / "storage_metadata.json"


def _load_metadata():
    if not METADATA_FILE.exists():
        return None
    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_current_record(metadata):
    if not isinstance(metadata, dict):
        return {}

    if isinstance(metadata.get("files"), dict) and metadata["files"]:
        return next(iter(metadata["files"].values()))

    # Normal storage format: {original_filename: record}
    for key, value in metadata.items():
        if isinstance(value, dict) and (
            "fragment_records" in value
            or "fragments" in value
            or "total_fragments" in value
        ):
            return value

    return metadata


def _normalize_names(values):
    if not values:
        return []
    if isinstance(values, str):
        values = [values]

    result = []
    for value in values:
        if isinstance(value, dict):
            value = (
                value.get("filename")
                or value.get("name")
                or value.get("fragment")
            )
        if value is not None:
            result.append(str(value))
    return result


def _record_name(record, fallback_index):
    return str(
        record.get("filename")
        or record.get("name")
        or f"fragment_{fallback_index:04d}.bin"
    )


def _record_index(record, fallback):
    try:
        return int(record.get("original_index", fallback))
    except (TypeError, ValueError):
        return fallback


def _record_start(record):
    try:
        return int(record.get("start", 0))
    except (TypeError, ValueError):
        return 0


def _record_size(record):
    for key in ("size", "length", "fragment_size"):
        if key in record:
            try:
                return int(record[key])
            except (TypeError, ValueError):
                pass
    return None


def _find_fragment(name, index):
    direct = DELETED_DIR / name
    if direct.exists():
        return direct

    matches = list(DELETED_DIR.glob(f"*fragment_{index:04d}.bin"))
    return matches[0] if matches else None


def _severity(missing, corrupted, size_errors, overlap, out_of_order):
    score = (
        missing * 25
        + corrupted * 30
        + size_errors * 20
        + (5 if overlap else 0)
        + (5 if out_of_order else 0)
    )

    if score >= 50:
        return "HIGH"
    if score >= 20:
        return "MODERATE"
    if score > 0:
        return "LOW"
    return "NONE"


def _detect_overlaps_fast(normalized):
    """
    Detect logical range overlaps in O(n log n) instead of O(n²).

    The old detector compared every fragment against every other fragment.
    With ~4,490 fragments that is ~10 million Python comparisons.
    """
    ranges = []

    for item in normalized:
        if not item["exists"]:
            continue

        size = item["expected_size"]
        if size is None:
            size = item["actual_size"]

        if size <= 0:
            continue

        start = item["start"]
        end = start + size
        ranges.append((start, end, item["name"]))

    ranges.sort(key=lambda x: (x[0], x[1]))

    overlaps = []
    active = []

    for start, end, name in ranges:
        # Remove ranges that cannot overlap this one.
        active = [
            item for item in active
            if item[1] > start
        ]

        for other_start, other_end, other_name in active:
            overlap_start = max(start, other_start)
            overlap_end = min(end, other_end)

            if overlap_start < overlap_end:
                overlaps.append({
                    "fragment_a": other_name,
                    "fragment_b": name,
                    "overlap_bytes": overlap_end - overlap_start,
                })

        active.append((start, end, name))

    return overlaps


def analyze_damage():
    metadata = _load_metadata()

    if metadata is None:
        return {
            "success": False,
            "message": "Storage metadata not found. Run damage simulation first.",
        }

    record = _get_current_record(metadata)

    records = (
        record.get("fragment_records")
        or record.get("fragments")
        or []
    )

    if not isinstance(records, list):
        records = []

    expected = record.get("total_fragments")
    if expected is None:
        expected = len(records)

    try:
        expected = int(expected)
    except (TypeError, ValueError):
        expected = len(records)

    explicit_missing = _normalize_names(
        record.get("missing_fragments", record.get("missing", []))
    )

    explicit_corrupted = _normalize_names(
        record.get("corrupted_fragments", record.get("corrupted", []))
    )

    normalized = []

    for i, item in enumerate(records):
        if not isinstance(item, dict):
            continue

        name = _record_name(item, i)
        index = _record_index(item, i)
        start = _record_start(item)
        expected_size = _record_size(item)

        path = _find_fragment(name, index)

        normalized.append({
            "name": name,
            "original_index": index,
            "start": start,
            "expected_size": expected_size,
            "actual_size": path.stat().st_size if path else 0,
            "path": str(path) if path else None,
            "exists": path is not None,
        })

    actual_names = {item["name"] for item in normalized}

    missing = set(explicit_missing)

    for item in normalized:
        if not item["exists"]:
            missing.add(item["name"])

    # If metadata says more fragments were expected than records present,
    # account for those as missing without creating thousands of objects.
    if len(normalized) < expected:
        for i in range(len(normalized), expected):
            missing.add(f"fragment_{i:04d}")

    corrupted = set()

    for value in explicit_corrupted:
        if value in actual_names:
            corrupted.add(value)
            continue

        for item in normalized:
            if value in item["name"] or item["name"].endswith(value):
                corrupted.add(item["name"])

    size_errors = []

    for item in normalized:
        if (
            item["exists"]
            and item["expected_size"] is not None
            and item["actual_size"] != item["expected_size"]
        ):
            size_errors.append({
                "fragment": item["name"],
                "expected_size": item["expected_size"],
                "actual_size": item["actual_size"],
            })

    # Use the original logical index, not directory order.
    available_order = [
        item["original_index"]
        for item in normalized
        if item["exists"] and item["name"] not in missing
    ]

    out_of_order = available_order != sorted(available_order)

    # FAST O(n log n) overlap detection.
    overlaps = _detect_overlaps_fast(normalized)

    original_file = (
        record.get("original_file")
        or record.get("source_file")
        or record.get("original_path")
    )

    if original_file:
        original_path = Path(str(original_file))
        if not original_path.is_absolute():
            original_path = BASE_DIR / original_path
        original_deleted = not original_path.exists()
    else:
        original_name = (
            record.get("filename")
            or record.get("original_filename")
            or record.get("name")
        )
        original_deleted = (
            bool(original_name)
            and not (ACTIVE_DIR / str(original_name)).exists()
        )

    missing_count = len(missing)
    corrupted_count = len(corrupted)

    damage_types = []

    if original_deleted:
        damage_types.append("Deletion")
    if expected > 1:
        damage_types.append("Fragmentation")
    if missing_count:
        damage_types.append("Missing Data")
    if corrupted_count:
        damage_types.append("Corruption")
    if out_of_order:
        damage_types.append("Fragment Disorder")
    if overlaps:
        damage_types.append("Overlapping Fragments")
    if size_errors:
        damage_types.append("Size Inconsistency")

    if not damage_types:
        damage_types.append("No damage detected")

    return {
        "success": True,
        "original_file": original_file,
        "deletion_detected": original_deleted,
        "fragmentation_detected": expected > 1,
        "expected_fragments": expected,
        "available_fragments": max(0, expected - missing_count),
        "missing_fragments": sorted(missing),
        "missing_count": missing_count,
        "corrupted_fragments": sorted(corrupted),
        "corrupted_count": corrupted_count,
        "size_inconsistencies": size_errors,
        "out_of_order": out_of_order,
        "logical_fragment_order": available_order,
        "overlap_detected": bool(overlaps),
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
        "damage_types": damage_types,
        "damage_severity": _severity(
            missing_count,
            corrupted_count,
            len(size_errors),
            bool(overlaps),
            out_of_order,
        ),
        "fragments": normalized,
    }


if __name__ == "__main__":
    report = analyze_damage()

    print("=" * 82)
    print("                 RECON-AI DAMAGE & CORRUPTION ANALYSIS")
    print("=" * 82)

    if not report.get("success"):
        print(report.get("message"))
    else:
        print(f"Expected fragments  : {report['expected_fragments']}")
        print(f"Available fragments : {report['available_fragments']}")
        print(f"Missing fragments   : {report['missing_count']}")
        print(f"Corrupted fragments : {report['corrupted_count']}")
        print(f"Out-of-order        : {'DETECTED' if report['out_of_order'] else 'NOT DETECTED'}")
        print(f"Overlap             : {'DETECTED' if report['overlap_detected'] else 'NOT DETECTED'}")
        print(f"Damage severity     : {report['damage_severity']}")
        print(f"Damage types        : {', '.join(report['damage_types'])}")

    print("=" * 82)
