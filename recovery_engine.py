from pathlib import Path
import hashlib
from collections import defaultdict


# ============================================================
# RECON-AI GENERIC MULTI-FRAGMENT RECOVERY ENGINE (fixed)
# ============================================================
#
# Accepts ANY number of fragments:
#   2, 5, 21, 98, 500, ...
#
# It does NOT trust:
#   - filename numbers
#   - upload order
#   - ZIP order
#
# It reconstructs using exact byte relationships. The engine also
# reports when the available fragments are insufficient to establish
# a complete chain.
#
# --------------------------------------------------------------
# WHAT WAS WRONG / WHAT CHANGED
# --------------------------------------------------------------
# The previous _select_chain() only kept an edge (A -> B) if it was
# simultaneously:
#   - the single strongest outgoing edge for A, AND
#   - the single strongest incoming edge for B
#
# That "mutual best match" rule is good for rejecting ambiguous
# branches, but it is brittle: binary formats like JPEG/PNG contain
# long repeated byte runs (padding, compressed stream boilerplot),
# which occasionally produce a slightly stronger *spurious* overlap
# somewhere else. When that happened, the TRUE edge got vetoed on
# one side, the walk hit a dead end, and _select_chain() just picked
# the single longest surviving piece via:
#
#       best_chain = max(candidates, key=candidate_score)
#
# ...silently discarding every fragment not on that one piece. The
# result was a "successful" recovery that was actually missing a
# chunk of the image, with no indication anything was dropped.
#
# The fix:
#   1. Chain building is now a greedy walk (best real overlap wins,
#      not "must be mutually exclusive best"), extended in BOTH
#      directions from the strongest seed fragment.
#   2. If the walk stalls with fragments left over, we don't stop —
#      we look for the next best usable connection among whatever
#      is left and keep going, repeating until nothing more can be
#      attached.
#   3. Anything that genuinely cannot be connected is reported
#      explicitly (dropped_fragments / fragments_unresolved) instead
#      of disappearing silently.
#   4. MIN_OVERLAP is now a parameter, not just a hardcoded module
#      constant, so it can be tuned per call without editing code.
# ============================================================

MIN_OVERLAP_DEFAULT = 16
MAX_OVERLAP = 8192


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def detect_file_type(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG", ".jpg", "image/jpeg"

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG", ".png", "image/png"

    if data.startswith(b"%PDF-"):
        return "PDF", ".pdf", "application/pdf"

    if data.startswith(b"PK\x03\x04"):
        return "ZIP", ".zip", "application/zip"

    return "BINARY", ".bin", "application/octet-stream"


def _name(item):
    return Path(str(getattr(item, "name", item))).name


def _bytes(item):
    if hasattr(item, "getvalue"):
        return item.getvalue()

    if hasattr(item, "read"):
        return item.read()

    return Path(item).read_bytes()


def _overlap(a, b, max_overlap=MAX_OVERLAP, min_overlap=MIN_OVERLAP_DEFAULT):
    """Return the largest exact suffix(a)==prefix(b) overlap."""
    limit = min(len(a), len(b), max_overlap)

    if limit < min_overlap:
        return 0

    for n in range(limit, min_overlap - 1, -1):
        if a[-n:] == b[:n]:
            return n

    return 0


def _build_relationships(fragments, min_overlap, max_overlap=MAX_OVERLAP):
    """
    Build exact overlap relationships between every pair of fragments.

    A prefix index is used to avoid blindly comparing every possible
    pair for every overlap length. The final relationship is always
    verified using the actual bytes.
    """
    names = list(fragments)

    # prefix[length][bytes] -> target names
    prefix_index = defaultdict(lambda: defaultdict(list))

    for name in names:
        data = fragments[name]
        max_len = min(len(data), max_overlap)

        for n in range(min_overlap, max_len + 1):
            prefix_index[n][data[:n]].append(name)

    relationships = []

    for source in names:
        source_data = fragments[source]
        max_len = min(len(source_data), max_overlap)

        # Check longer overlaps first, keep the strongest one per
        # (source, target) pair.
        seen_targets = set()

        for n in range(max_len, min_overlap - 1, -1):
            suffix = source_data[-n:]
            targets = prefix_index[n].get(suffix, [])

            for target in targets:
                if target == source or target in seen_targets:
                    continue

                # Exact verification.
                if fragments[target][:n] != suffix:
                    continue

                confidence = round(
                    min(
                        100.0,
                        55.0
                        + (n / max(1, min(len(source_data), len(fragments[target]))))
                        * 45.0,
                    ),
                    2,
                )

                relationships.append(
                    {
                        "from": source,
                        "to": target,
                        "overlap": n,
                        "confidence": confidence,
                    }
                )
                seen_targets.add(target)

    return sorted(
        relationships,
        key=lambda r: (r["overlap"], r["confidence"]),
        reverse=True,
    )


def _known_signature(data):
    """Return a strong file signature score for a fragment."""
    if data.startswith(b"\xff\xd8\xff"):
        return ("JPEG", 10000)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("PNG", 10000)
    if data.startswith(b"%PDF-"):
        return ("PDF", 10000)
    if data.startswith(b"PK\x03\x04"):
        return ("ZIP", 10000)
    return ("BINARY", 0)


def _numeric_index(name):
    """
    Use a numeric fragment index only as a last-resort fallback.

    Exact byte relationships always have priority, so randomized
    filenames do not control normal reconstruction.
    """
    import re

    matches = re.findall(
        r"(?:fragment|frag|part|chunk|piece)[^\d]*(\d+)", str(name), re.I
    )
    if matches:
        return int(matches[-1])

    nums = re.findall(r"\d+", str(name))
    return int(nums[-1]) if len(nums) == 1 else None


def _best_edge(relationships, source=None, target=None, exclude=()):
    """Best-scoring edge matching the given source/target, excluding names."""
    best = None
    for rel in relationships:
        if source is not None and rel["from"] != source:
            continue
        if target is not None and rel["to"] != target:
            continue
        if rel["from"] in exclude or rel["to"] in exclude:
            continue
        if best is None or (rel["overlap"], rel["confidence"]) > (
            best["overlap"],
            best["confidence"],
        ):
            best = rel
    return best


def _pick_seed(names, fragments, relationships):
    """
    Choose the fragment most likely to be the true start of the file:
    prefer a recognized file signature; otherwise prefer a fragment
    that never appears as a strong target (i.e. nothing points to it).
    """
    incoming_strength = defaultdict(float)
    for rel in relationships:
        incoming_strength[rel["to"]] = max(
            incoming_strength[rel["to"]], rel["overlap"]
        )

    def score(name):
        sig, sig_score = _known_signature(fragments[name])
        # Lower incoming strength = more likely to be a true start.
        return (sig_score, -incoming_strength.get(name, 0))

    return max(names, key=score)


def _greedy_walk_forward(start, fragments, relationships, used):
    """Extend forward from `start`, always taking the best unused edge."""
    chain = [start]
    local_used = set(used) | {start}
    current = start

    while True:
        best = _best_edge(relationships, source=current, exclude=local_used)
        if best is None:
            break
        chain.append(best["to"])
        local_used.add(best["to"])
        current = best["to"]

    return chain, local_used


def _greedy_walk_backward(start, fragments, relationships, used):
    """Extend backward from `start`, always taking the best unused edge."""
    chain = [start]
    local_used = set(used) | {start}
    current = start

    while True:
        best = _best_edge(relationships, target=current, exclude=local_used)
        if best is None:
            break
        chain.insert(0, best["from"])
        local_used.add(best["from"])
        current = best["from"]

    return chain, local_used


def _select_chain(fragments, relationships):
    """
    Build the fullest possible chain without silently discarding
    fragments that fall outside a single "mutually-best" path.

    Strategy:
      1. Pick the most likely true start (signature match, or the
         fragment nothing else points into).
      2. Greedily walk forward and backward from that seed, always
         taking the strongest available unused edge.
      3. If fragments remain unused, repeat the seed+walk process on
         the leftovers to build additional segments, then attach any
         segment whose head/tail connects to the main chain.
      4. Only fragments with genuinely no discoverable connection are
         left out, and those are reported explicitly by the caller.
    """
    names = list(fragments)

    if not names:
        return [], [], [], "none"

    if not relationships:
        # No byte relationships at all — try the numeric fallback.
        indexed = []
        for name in names:
            idx = _numeric_index(name)
            if idx is None:
                indexed = []
                break
            indexed.append((idx, name))

        if indexed and len({idx for idx, _ in indexed}) == len(indexed):
            indexed.sort()
            chain = [name for _, name in indexed]
            accepted_fallback = [
                {
                    "from": a,
                    "to": b,
                    "overlap": 0,
                    "confidence": 55.0,
                    "method": "numeric-index-fallback",
                }
                for a, b in zip(chain, chain[1:])
            ]
            return chain, accepted_fallback, [], "numeric-index-fallback"

        return [names[0]], [], names[1:], "insufficient-order-evidence"

    used = set()
    segments = []

    remaining = set(names)
    while remaining:
        seed = _pick_seed(list(remaining), fragments, relationships)

        chain, used_after_fwd = _greedy_walk_forward(
            seed, fragments, relationships, used
        )
        chain, used_after_bwd = _greedy_walk_backward(
            chain[0], fragments, relationships, used_after_fwd
        )
        # The backward walk only prepends to chain[0]; re-derive full
        # chain including forward extension already captured.
        full_used = used_after_bwd
        # Rebuild the actual ordered chain: backward walk returns a
        # chain starting from chain[0] going backward only, so merge.
        back_chain, _ = _greedy_walk_backward(
            chain[0], fragments, relationships, used
        )
        # back_chain already includes chain[0]; splice with forward part
        if back_chain[-1] == chain[0]:
            merged = back_chain[:-1] + chain
        else:
            merged = chain

        used |= set(merged)
        remaining -= set(merged)
        segments.append(merged)

    # Try to stitch segments together: if one segment's tail connects
    # to another segment's head via a real (if not globally-best) edge,
    # join them rather than leaving separate pieces.
    segments.sort(key=len, reverse=True)
    main_chain = segments[0]
    leftover_segments = segments[1:]

    changed = True
    while changed and leftover_segments:
        changed = False
        for seg in list(leftover_segments):
            edge_after = _best_edge(
                relationships, source=main_chain[-1], target=seg[0]
            )
            if edge_after:
                main_chain = main_chain + seg
                leftover_segments.remove(seg)
                changed = True
                continue

            edge_before = _best_edge(
                relationships, source=seg[-1], target=main_chain[0]
            )
            if edge_before:
                main_chain = seg + main_chain
                leftover_segments.remove(seg)
                changed = True
                continue

    dropped = [name for seg in leftover_segments for name in seg]

    accepted = []
    for a, b in zip(main_chain, main_chain[1:]):
        rel = _best_edge(relationships, source=a, target=b)
        if rel:
            accepted.append(rel)

    return main_chain, accepted, dropped, "exact-byte-overlap"


def _merge(chain, fragments, min_overlap, max_overlap=MAX_OVERLAP):
    if not chain:
        return b"", 0

    output = fragments[chain[0]]
    unresolved = 0

    for previous, current in zip(chain, chain[1:]):
        data = fragments[current]
        overlap = _overlap(output, data, max_overlap=max_overlap, min_overlap=min_overlap)

        if overlap >= min_overlap:
            output += data[overlap:]
        else:
            # No confirmable overlap at the merge point — still
            # concatenate so no bytes are lost, but flag the seam.
            output += data
            unresolved += 1

    return output, unresolved


def recover_uploaded_fragments(uploaded_files, output_dir, min_overlap=MIN_OVERLAP_DEFAULT):
    """
    Recover any number of uploaded fragments.

    The function is intentionally independent of a fixed fragment
    count. It accepts every supplied fragment and determines the
    relationships dynamically. Fragments that cannot be connected to
    anything are reported explicitly rather than dropped silently.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale recovered artifacts.
    for old in output_dir.iterdir():
        try:
            if old.is_file():
                old.unlink()
        except Exception:
            pass

    fragments = {}

    for item in uploaded_files or []:
        data = _bytes(item)

        if not data:
            continue

        filename = _name(item)

        # Prevent duplicate names from replacing one another.
        if filename in fragments:
            base = Path(filename).stem
            suffix = Path(filename).suffix
            counter = 2

            while f"{base}_{counter}{suffix}" in fragments:
                counter += 1

            filename = f"{base}_{counter}{suffix}"

        fragments[filename] = data

    count = len(fragments)

    if count == 0:
        return {
            "success": False,
            "message": "No usable fragments were supplied.",
            "fragments_received": 0,
        }

    if count == 1:
        # One fragment can still be a valid complete file.
        only_name = next(iter(fragments))
        recovered = fragments[only_name]

        file_type, extension, mime = detect_file_type(recovered)
        output_path = output_dir / f"recovered_evidence{extension}"
        output_path.write_bytes(recovered)

        return {
            "success": True,
            "message": "One fragment supplied; treated as a single evidence object.",
            "chain": [only_name],
            "fragment_chain": [only_name],
            "relationships": [],
            "relationship_count": 0,
            "fragments_received": 1,
            "fragments_used": 1,
            "dropped_fragments": [],
            "unresolved_connections": 0,
            "recovered_size": len(recovered),
            "output_path": str(output_path.resolve()),
            "recovered_file": str(output_path.resolve()),
            "recovered_path": str(output_path.resolve()),
            "sha256": sha256_bytes(recovered),
            "file_type": file_type,
            "extension": extension,
            "mime_type": mime,
            "reconstruction_method": "Single evidence object",
            "ordering_method": "single-fragment",
        }

    relationships = _build_relationships(fragments, min_overlap=min_overlap)

    chain, accepted, dropped, ordering_method = _select_chain(fragments, relationships)

    if ordering_method == "insufficient-order-evidence":
        return {
            "success": False,
            "message": (
                "The fragments were received, but no reliable byte-overlap "
                "or fragment-index relationship was found. "
                "Upload the complete randomized fragment set, preferably "
                "with the simulated overlap preserved."
            ),
            "fragments_received": count,
            "fragments_used": len(chain),
            "dropped_fragments": dropped,
            "relationships": relationships,
            "relationship_count": len(relationships),
            "unresolved_connections": len(dropped),
            "ordering_method": ordering_method,
        }

    recovered, merge_unresolved = _merge(chain, fragments, min_overlap=min_overlap)

    unresolved = merge_unresolved + len(dropped)

    file_type, extension, mime = detect_file_type(recovered)
    output_path = output_dir / f"recovered_evidence{extension}"

    # NEVER re-encode the recovered JPEG/PNG/PDF.
    # The reconstructed bytes are written directly.
    output_path.write_bytes(recovered)

    all_fragments_connected = len(chain) == count and unresolved == 0

    return {
        "success": True,
        "message": (
            "Multi-fragment reconstruction completed."
            if all_fragments_connected
            else (
                f"Reconstruction completed, but {len(dropped)} fragment(s) could "
                "not be connected to the main chain and were left out. "
                "See dropped_fragments."
            )
        ),
        "fragments_received": count,
        "fragments_used": len(chain),
        "fragments_unresolved": max(0, count - len(chain)),
        "dropped_fragments": dropped,
        "relationship_count": len(relationships),
        "relationships": relationships,
        "accepted_relationships": accepted,
        "chain": chain,
        "fragment_chain": chain,
        "unresolved_connections": unresolved,
        "all_fragments_connected": all_fragments_connected,
        "recovered_size": len(recovered),
        "output_path": str(output_path.resolve()),
        "recovered_file": str(output_path.resolve()),
        "recovered_path": str(output_path.resolve()),
        "sha256": sha256_bytes(recovered),
        "file_type": file_type,
        "extension": extension,
        "mime_type": mime,
        "reconstruction_method": "Greedy bidirectional exact suffix-to-prefix byte-overlap walk",
        "ordering_method": ordering_method,
        "min_overlap": min_overlap,
        "max_overlap": MAX_OVERLAP,
    }


def repair_single_file(file_path, output_dir):
    # Corrupted-file repair intentionally disabled.
    return {
        "success": False,
        "message": "Single corrupted-file repair is disabled. Use multiple-fragment reconstruction.",
    }