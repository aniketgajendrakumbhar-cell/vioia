from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer, util

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_MODEL = None


def get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def entropy(data):
    if not data:
        return 0.0

    values = np.frombuffer(data, dtype=np.uint8)
    counts = np.bincount(values, minlength=256)
    p = counts[counts > 0] / len(values)

    return float(-np.sum(p * np.log2(p)))


def printable_ratio(data):
    if not data:
        return 0.0

    return sum(
        32 <= b <= 126 or b in (9, 10, 13)
        for b in data
    ) / len(data)


def boundary_overlap(a, b, maximum=256):
    """
    Find suffix(a) == prefix(b).

    The search is deliberately capped because the simulator uses a known
    overlap size. This prevents expensive large-byte comparisons.
    """
    if not a or not b:
        return 0

    limit = min(maximum, len(a), len(b))

    for n in range(limit, 0, -1):
        if a[-n:] == b[:n]:
            return n

    return 0


def structural_similarity(a, b):
    if not a or not b:
        return 0.0

    ea = entropy(a)
    eb = entropy(b)

    entropy_score = max(
        0.0,
        1.0 - abs(ea - eb) / 8.0,
    )

    pa = printable_ratio(a)
    pb = printable_ratio(b)

    printable_score = max(
        0.0,
        1.0 - abs(pa - pb),
    )

    # Compare compact byte histograms rather than raw buffers.
    ha = np.bincount(
        np.frombuffer(a, dtype=np.uint8),
        minlength=256,
    ).astype(np.float32)

    hb = np.bincount(
        np.frombuffer(b, dtype=np.uint8),
        minlength=256,
    ).astype(np.float32)

    ha /= max(1, len(a))
    hb /= max(1, len(b))

    denom = np.linalg.norm(ha) * np.linalg.norm(hb)

    histogram_score = (
        float(np.dot(ha, hb) / denom)
        if denom
        else 0.0
    )

    return (
        entropy_score * 0.35
        + printable_score * 0.15
        + histogram_score * 0.50
    )


def bytes_to_embedding_text(data):
    """
    Small forensic fingerprint for the general-purpose Transformer.

    We intentionally do not convert the whole binary fragment to hex.
    A 1024-byte binary fragment would otherwise become a very long token
    sequence and slow inference without giving useful semantic information.
    """
    arr = np.frombuffer(data, dtype=np.uint8)

    if len(arr):
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        minimum = int(np.min(arr))
        maximum = int(np.max(arr))
    else:
        mean = std = 0.0
        minimum = maximum = 0

    # Keep only short boundary signatures.
    head = data[:48].hex()
    tail = data[-48:].hex()

    return (
        "digital evidence binary fragment "
        f"size={len(data)} "
        f"entropy={entropy(data):.3f} "
        f"printable={printable_ratio(data):.3f} "
        f"mean={mean:.2f} "
        f"std={std:.2f} "
        f"min={minimum} "
        f"max={maximum} "
        f"head={head} "
        f"tail={tail}"
    )


def load_fragments(storage_directory):
    storage_directory = Path(storage_directory)

    fragments = []

    for path in storage_directory.glob("*.bin"):
        try:
            data = path.read_bytes()
        except OSError:
            continue

        fragments.append({
            "filename": path.name,
            "data": data,
        })

    # Stable order only. Reconstruction uses relationship edges, not
    # directory order.
    fragments.sort(key=lambda item: item["filename"])

    return fragments


def create_embeddings(fragments):
    model = get_model()

    texts = [
        bytes_to_embedding_text(fragment["data"])
        for fragment in fragments
    ]

    print(f"       Generating embeddings for {len(texts)} fragments...")

    return model.encode(
        texts,
        batch_size=64,
        normalize_embeddings=True,
        convert_to_tensor=True,
        show_progress_bar=True,
    )


def _candidate_relationships(embeddings, top_k=4):
    """
    Chunked semantic search.

    Unlike a full NxN NumPy matrix, this does not permanently allocate an
    NxN similarity matrix. sentence-transformers performs the search in
    manageable chunks and returns only the top-k matches.
    """
    n = embeddings.shape[0]

    if n < 2:
        return []

    k = min(top_k + 1, n)

    print(
        f"       Finding top-{top_k} AI candidates per fragment..."
    )

    hits = util.semantic_search(
        embeddings,
        embeddings,
        query_chunk_size=256,
        corpus_chunk_size=2048,
        top_k=k,
        score_function=util.cos_sim,
    )

    candidates = []

    for i, row in enumerate(hits):
        for hit in row:
            j = int(hit["corpus_id"])

            if i == j:
                continue

            # AI cosine similarity is [-1,1]. Convert to [0,1].
            similarity = float(hit["score"])
            ai_score = np.clip(
                (similarity + 1.0) / 2.0,
                0.0,
                1.0,
            )

            candidates.append((i, j, ai_score))

    return candidates


def analyze_fragment_relationships(storage_directory, top_k=4):
    """
    Real Transformer-based relationship analysis optimized for the hackathon.

    Pipeline:
      binary fragments
        -> compact forensic fingerprints
        -> MiniLM Transformer embeddings
        -> chunked top-k semantic search
        -> byte-boundary verification
        -> structural verification
        -> final relationship confidence

    The Transformer is still the AI component. Deterministic byte analysis
    validates and strengthens the AI candidates before reconstruction.
    """
    fragments = load_fragments(storage_directory)

    if len(fragments) < 2:
        return {
            "model": MODEL_NAME,
            "embedding_dimension": 0,
            "fragment_count": len(fragments),
            "candidate_limit_per_fragment": 0,
            "relationships": [],
        }

    embeddings = create_embeddings(fragments)

    dimension = int(embeddings.shape[1])

    candidates = _candidate_relationships(
        embeddings,
        top_k=top_k,
    )

    relationships = []

    # De-duplicate directed pairs.
    seen = set()

    print(
        f"       Validating {len(candidates)} AI candidates..."
    )

    for i, j, ai_score in candidates:
        key = (i, j)

        if key in seen:
            continue

        seen.add(key)

        a = fragments[i]["data"]
        b = fragments[j]["data"]

        overlap = boundary_overlap(
            a,
            b,
            maximum=256,
        )

        structural = structural_similarity(
            a,
            b,
        )

        overlap_ratio = (
            overlap / min(len(a), len(b))
            if min(len(a), len(b)) > 0
            else 0.0
        )

        # AI is the primary signal.
        confidence = (
            ai_score * 0.65
            + structural * 0.20
            + overlap_ratio * 0.15
        )

        # For binary fragments, keep strong AI relationships or actual
        # boundary evidence. This avoids producing thousands of weak edges.
        if (
            ai_score >= 0.55
            or overlap >= 8
        ):
            relationships.append({
                "from": fragments[i]["filename"],
                "to": fragments[j]["filename"],
                "overlap": overlap,
                "ai_similarity": round(ai_score * 100, 2),
                "structural_similarity": round(
                    structural * 100,
                    2,
                ),
                "overlap_score": round(
                    overlap_ratio * 100,
                    2,
                ),
                "confidence": round(
                    confidence * 100,
                    2,
                ),
            })

    relationships.sort(
        key=lambda item: item["confidence"],
        reverse=True,
    )

    return {
        "model": MODEL_NAME,
        "embedding_dimension": dimension,
        "fragment_count": len(fragments),
        "candidate_limit_per_fragment": top_k,
        "relationships": relationships,
    }


def print_ai_report(result):
    print("=" * 90)
    print("             RECON-AI REAL TRANSFORMER RELATIONSHIP ANALYSIS")
    print("=" * 90)

    print(f"Model: {result['model']}")
    print(f"Embedding dimension: {result['embedding_dimension']}")
    print(f"Fragments analyzed: {result['fragment_count']}")
    print(
        "AI candidates per fragment: "
        f"{result.get('candidate_limit_per_fragment', '-')}"
    )
    print()

    print(
        f"{'FROM':40} {'TO':40} "
        f"{'AI':>8} {'OVERLAP':>8} {'FINAL':>8}"
    )
    print("-" * 110)

    for relationship in result["relationships"][:20]:
        print(
            f"{relationship['from'][:40]:40} "
            f"{relationship['to'][:40]:40} "
            f"{relationship['ai_similarity']:7.2f}% "
            f"{relationship['overlap']:8} "
            f"{relationship['confidence']:7.2f}%"
        )

    print()
    print(
        "Candidate relationships: "
        f"{len(result['relationships'])}"
    )
    print("=" * 90)


if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent

    result = analyze_fragment_relationships(
        BASE_DIR / "lab" / "deleted_storage",
        top_k=4,
    )

    print_ai_report(result)
