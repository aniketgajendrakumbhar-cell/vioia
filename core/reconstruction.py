from pathlib import Path
import json


def _load_fragment_bytes(storage_dir):
    storage_dir = Path(storage_dir)
    fragments = {}

    for path in storage_dir.glob("*.bin"):
        try:
            fragments[path.name] = path.read_bytes()
        except OSError:
            pass

    return fragments


def _load_metadata(storage_dir):
    storage_dir = Path(storage_dir)
    metadata_path = storage_dir.parent / "storage_metadata.json"

    if not metadata_path.exists():
        return {}

    try:
        data = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
    except Exception:
        return {}

    if isinstance(data, dict) and isinstance(data.get("files"), dict):
        return data["files"]

    return data if isinstance(data, dict) else {}


def _get_record(metadata, original_filename):
    if original_filename in metadata:
        record = metadata[original_filename]
        return record if isinstance(record, dict) else {}

    for value in metadata.values():
        if isinstance(value, dict):
            if value.get("original_filename") == original_filename:
                return value

    return {}


def _get_records(record):
    records = (
        record.get("fragment_records")
        or record.get("fragments")
        or []
    )

    return records if isinstance(records, list) else []


def _normalise_relationships(relationships):
    result = []

    for rel in relationships or []:
        if not isinstance(rel, dict):
            continue

        source = (
            rel.get("from")
            or rel.get("source")
        )

        target = (
            rel.get("to")
            or rel.get("target")
        )

        if not source or not target or source == target:
            continue

        try:
            confidence = float(
                rel.get(
                    "confidence",
                    rel.get(
                        "combined_confidence",
                        0,
                    ),
                )
            )
        except (TypeError, ValueError):
            confidence = 0.0

        if 0 < confidence <= 1:
            confidence *= 100.0

        try:
            overlap = int(
                rel.get("overlap", 0)
            )
        except (TypeError, ValueError):
            overlap = 0

        result.append(
            {
                "from": str(source),
                "to": str(target),
                "confidence": max(
                    0.0,
                    min(100.0, confidence),
                ),
                "overlap": max(0, overlap),
            }
        )

    return sorted(
        result,
        key=lambda x: x["confidence"],
        reverse=True,
    )


def _exact_overlap(left, right, maximum=4096):
    """
    Find the largest suffix(left) == prefix(right).

    4096 is deliberately used because the project can work with
    fragments larger than 256 bytes.
    """

    if not left or not right:
        return 0

    limit = min(
        maximum,
        len(left),
        len(right),
    )

    for size in range(limit, 0, -1):
        if left[-size:] == right[:size]:
            return size

    return 0


def _build_chain(fragment_names, relationships, records):
    available = set(fragment_names)

    outgoing = {}
    incoming = {}

    for rel in relationships:
        source = rel["from"]
        target = rel["to"]

        if source not in available or target not in available:
            continue

        outgoing.setdefault(
            source,
            [],
        ).append(rel)

        incoming.setdefault(
            target,
            [],
        ).append(rel)

    for edges in outgoing.values():
        edges.sort(
            key=lambda x: (
                x["confidence"],
                x["overlap"],
            ),
            reverse=True,
        )

    # Metadata provides the logical order when available.
    positions = {}

    for fallback, record in enumerate(records):
        if not isinstance(record, dict):
            continue

        name = (
            record.get("filename")
            or record.get("fragment_name")
        )

        if name is None:
            continue

        try:
            index = int(
                record.get(
                    "original_index",
                    fallback,
                )
            )
        except (TypeError, ValueError):
            index = fallback

        positions[str(name)] = index

    # Find a fragment that has no incoming relationship.
    starts = [
        name
        for name in fragment_names
        if name not in incoming
    ]

    if starts:
        starts.sort(
            key=lambda name: positions.get(
                name,
                10**9,
            )
        )

        current = starts[0]

    elif fragment_names:
        current = min(
            fragment_names,
            key=lambda name: positions.get(
                name,
                10**9,
            ),
        )

    else:
        return []

    chain = []
    used = set()

    while (
        current
        and current not in used
    ):
        used.add(current)
        chain.append(current)

        candidates = [
            edge
            for edge in outgoing.get(
                current,
                [],
            )
            if edge["to"] not in used
        ]

        if not candidates:
            break

        current = candidates[0]["to"]

    # Add disconnected fragments using their metadata order.
    remaining = [
        name
        for name in fragment_names
        if name not in used
    ]

    remaining.sort(
        key=lambda name: positions.get(
            name,
            10**9,
        )
    )

    chain.extend(remaining)

    return chain


def _merge_chain(
    chain,
    fragment_bytes,
    relationships,
):
    if not chain:
        return b""

    relationship_map = {
        (
            rel["from"],
            rel["to"],
        ): rel
        for rel in relationships
    }

    recovered = fragment_bytes[chain[0]]

    for previous, current in zip(
        chain,
        chain[1:],
    ):
        current_data = fragment_bytes[current]

        # First use actual byte overlap.
        exact = _exact_overlap(
            recovered,
            current_data,
            maximum=4096,
        )

        relationship = relationship_map.get(
            (previous, current),
            {},
        )

        try:
            claimed = int(
                relationship.get(
                    "overlap",
                    0,
                )
            )
        except (TypeError, ValueError):
            claimed = 0

        overlap = exact

        # If exact overlap wasn't found, use the AI/metadata
        # relationship's claimed overlap.
        if overlap == 0:
            if (
                0 < claimed
                <= min(
                    len(recovered),
                    len(current_data),
                )
            ):
                overlap = claimed

        # Append only the new bytes.
        recovered += current_data[overlap:]

    return recovered


def reconstruct_file(
    storage_dir,
    relationships,
    output_path,
):
    """
    Reconstruct evidence from fragments.

    This function is intentionally exposed because the dashboard
    imports it directly.

    Returned keys include both modern and legacy names so the
    existing dashboard does not fail with KeyError.
    """

    storage_dir = Path(storage_dir)
    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fragments = _load_fragment_bytes(
        storage_dir
    )

    if not fragments:
        return {
            "success": False,
            "message": "No fragment files found.",
            "chain": [],
            "fragment_chain": [],
            "fragments_used": 0,
            "recovered_size": 0,
            "output_path": None,
            "recovered_file": None,
        }

    first_name = next(
        iter(fragments)
    )

    if ".fragment_" in first_name:
        original_filename = first_name.split(
            ".fragment_",
            1,
        )[0]
    else:
        original_filename = first_name

    metadata = _load_metadata(
        storage_dir
    )

    record = _get_record(
        metadata,
        original_filename,
    )

    records = _get_records(record)

    relationships = _normalise_relationships(
        relationships
    )

    chain = _build_chain(
        list(fragments.keys()),
        relationships,
        records,
    )

    if not chain:
        return {
            "success": False,
            "message": "Could not build a reconstruction chain.",
            "chain": [],
            "fragment_chain": [],
            "fragments_used": 0,
            "recovered_size": 0,
            "output_path": None,
            "recovered_file": None,
        }

    try:
        recovered = _merge_chain(
            chain,
            fragments,
            relationships,
        )

        output_path.write_bytes(
            recovered
        )

    except Exception as exc:
        return {
            "success": False,
            "message": (
                f"Reconstruction failed: {exc}"
            ),
            "chain": chain,
            "fragment_chain": chain,
            "fragments_used": len(chain),
            "recovered_size": 0,
            "output_path": None,
            "recovered_file": None,
        }

    output_string = str(
        output_path.resolve()
    )

    return {
        "success": True,
        "message": (
            "Evidence reconstructed successfully."
        ),

        "chain": chain,

        "fragment_chain": chain,

        "fragments_used": len(chain),

        "recovered_size": len(recovered),

        "output_path": output_string,

        "recovered_file": output_string,
    }


if __name__ == "__main__":
    print(
        "reconstruction.py loaded successfully."
    )