from pathlib import Path
import hashlib
import io
import re
from collections import defaultdict, Counter

try:
    from PIL import Image, ImageFile
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def common_base_name(names):
    if not names:
        return "recovered.bin"

    # Remove common fragment/chunk suffixes.
    cleaned = []
    for name in names:
        stem = Path(name).stem
        stem = re.sub(
            r'([._-](?:fragment|frag|part|chunk|piece)[._-]?\d+)$',
            '',
            stem,
            flags=re.I,
        )
        cleaned.append(stem)

    base = cleaned[0]
    for value in cleaned[1:]:
        while base and not value.lower().startswith(base.lower()):
            base = base[:-1]

    if not base:
        base = cleaned[0]

    return base


def exact_overlap(a, b, maximum=None):
    if not a or not b:
        return 0

    limit = min(len(a), len(b))
    if maximum:
        limit = min(limit, maximum)

    # Favor substantial overlaps to avoid accidental binary matches.
    minimum = 8 if limit >= 16 else 1

    for n in range(limit, minimum - 1, -1):
        if a[-n:] == b[:n]:
            return n

    return 0


def pairwise_overlap_graph(fragments):
    """
    Build a directed overlap graph for arbitrary uploaded fragments.
    Edge A -> B means suffix(A) matches prefix(B).
    """
    names = list(fragments)
    edges = []

    for a in names:
        for b in names:
            if a == b:
                continue

            overlap = exact_overlap(fragments[a], fragments[b], 2048)

            if overlap:
                confidence = min(
                    100.0,
                    40.0 + (overlap / max(1, min(len(fragments[a]), len(fragments[b])))) * 60.0
                )
                edges.append({
                    "from": a,
                    "to": b,
                    "overlap": overlap,
                    "confidence": confidence,
                })

    return sorted(edges, key=lambda x: x["confidence"], reverse=True)


def build_overlap_chain(fragments):
    edges = pairwise_overlap_graph(fragments)

    outgoing = defaultdict(list)
    incoming = Counter()

    for edge in edges:
        outgoing[edge["from"]].append(edge)
        incoming[edge["to"]] += 1

    for values in outgoing.values():
        values.sort(key=lambda x: (x["overlap"], x["confidence"]), reverse=True)

    starts = [n for n in fragments if incoming[n] == 0]
    if not starts:
        starts = list(fragments)

    # Try each plausible start and keep the longest coverage chain.
    best = []
    for start in starts:
        chain = []
        used = set()
        current = start

        while current not in used:
            used.add(current)
            chain.append(current)

            candidates = [
                e for e in outgoing.get(current, [])
                if e["to"] not in used
            ]

            if not candidates:
                break

            current = candidates[0]["to"]

        if len(chain) > len(best):
            best = chain

    # Add disconnected fragments at the end.
    for name in fragments:
        if name not in best:
            best.append(name)

    return best, edges


def merge_chain(chain, fragments, edges):
    if not chain:
        return b"", 0

    edge_map = {(e["from"], e["to"]): e for e in edges}
    recovered = fragments[chain[0]]
    unresolved = 0

    for previous, current in zip(chain, chain[1:]):
        data = fragments[current]

        overlap = exact_overlap(recovered, data, 4096)

        if overlap == 0:
            edge = edge_map.get((previous, current), {})
            claimed = int(edge.get("overlap", 0) or 0)

            if 0 < claimed <= min(len(recovered), len(data)):
                overlap = claimed

        if overlap == 0:
            # No relationship: preserve the fragment rather than dropping it.
            unresolved += 1
            recovered += data
        else:
            recovered += data[overlap:]

    return recovered, unresolved


def repair_jpeg(data):
    """
    Best-effort repair for truncated/corrupt JPEGs.
    Returns repaired bytes and a status string.
    """
    if not data.startswith(b"\xff\xd8\xff"):
        return None, "Not a JPEG"

    if PIL_AVAILABLE:
        try:
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=95)
                return output.getvalue(), "JPEG decoded and re-encoded"
        except Exception:
            pass

    # Simple EOI repair for a truncated JPEG.
    if not data.endswith(b"\xff\xd9"):
        return data + b"\xff\xd9", "JPEG EOI marker restored"

    return data, "JPEG structure retained"


def recover_uploaded_fragments(uploaded_files, output_dir):
    """
    Recover a user-supplied set of arbitrary fragments without relying
    on simulation metadata.

    Works best when fragments overlap. It reports missing/ambiguous
    pieces instead of silently inventing bytes.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fragments = {}
    for item in uploaded_files:
        name = Path(item.name).name
        data = item.getvalue() if hasattr(item, "getvalue") else Path(item).read_bytes()
        if data:
            fragments[name] = data

    if not fragments:
        return {
            "success": False,
            "message": "No usable fragment files were supplied.",
        }

    chain, edges = build_overlap_chain(fragments)
    recovered, unresolved = merge_chain(chain, fragments, edges)

    base = common_base_name(list(fragments))
    suffix = ".jpg" if recovered.startswith(b"\xff\xd8\xff") else ".bin"
    output_path = output_dir / f"recovered_{base}{suffix}"

    repair_status = "No image repair required"

    # If the assembled data is a JPEG, perform a best-effort decode repair.
    if recovered.startswith(b"\xff\xd8\xff"):
        repaired, repair_status = repair_jpeg(recovered)
        if repaired:
            recovered = repaired

    output_path.write_bytes(recovered)

    return {
        "success": True,
        "message": "Fragment recovery completed.",
        "chain": chain,
        "relationships": edges,
        "fragments_received": len(fragments),
        "fragments_used": len(chain),
        "unresolved_connections": unresolved,
        "recovered_size": len(recovered),
        "output_path": str(output_path),
        "sha256": sha256_bytes(recovered),
        "repair_status": repair_status,
        "exact_fragment_metadata": False,
    }


def repair_single_file(file_path, output_dir):
    file_path = Path(file_path)
    data = file_path.read_bytes()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    repaired = data
    status = "No repair performed"

    if data.startswith(b"\xff\xd8\xff"):
        repaired, status = repair_jpeg(data)
        if repaired is None:
            repaired = data

    output = output_dir / f"repaired_{file_path.name}"
    output.write_bytes(repaired)

    return {
        "success": True,
        "message": "Best-effort file repair completed.",
        "input": str(file_path),
        "output_path": str(output),
        "original_size": len(data),
        "recovered_size": len(repaired),
        "sha256": sha256_bytes(repaired),
        "repair_status": status,
    }
