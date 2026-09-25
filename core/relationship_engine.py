from pathlib import Path
import math

from core.fragment_analyzer import analyze_fragment


# ============================================================
# RECON-AI RELATIONSHIP ENGINE
# ============================================================

MIN_OVERLAP = 8


# ============================================================
# READ FRAGMENTS
# ============================================================

def read_fragments(storage_directory):

    storage_directory = Path(storage_directory)

    fragments = {}

    for file_path in storage_directory.iterdir():

        if not file_path.is_file():
            continue

        fragments[file_path.name] = {
            "data": file_path.read_bytes(),
            "analysis": analyze_fragment(file_path)
        }

    return fragments


# ============================================================
# EXACT BYTE OVERLAP
# ============================================================

def calculate_overlap(data_a, data_b):

    maximum = min(
        len(data_a),
        len(data_b)
    )

    best_overlap = 0

    for size in range(
        maximum,
        MIN_OVERLAP - 1,
        -1
    ):

        if data_a[-size:] == data_b[:size]:

            best_overlap = size

            break

    return best_overlap


# ============================================================
# ENTROPY SIMILARITY
# ============================================================

def calculate_entropy_similarity(
    entropy_a,
    entropy_b
):

    difference = abs(
        entropy_a - entropy_b
    )

    similarity = max(
        0.0,
        1.0 - (difference / 8.0)
    )

    return similarity


# ============================================================
# PRINTABLE CONTENT SIMILARITY
# ============================================================

def calculate_printable_similarity(
    printable_a,
    printable_b
):

    difference = abs(
        printable_a - printable_b
    )

    return max(
        0.0,
        1.0 - difference
    )


# ============================================================
# BYTE TRANSITION SIMILARITY
# ============================================================

def calculate_transition_similarity(
    data_a,
    data_b
):

    if not data_a or not data_b:
        return 0.0

    # Compare the final byte of A with
    # the first byte of B.

    last_byte = data_a[-1]
    first_byte = data_b[0]

    difference = abs(
        last_byte - first_byte
    )

    return max(
        0.0,
        1.0 - (difference / 255.0)
    )


# ============================================================
# RELATIONSHIP SCORE
# ============================================================

def calculate_relationship(
    fragment_a,
    fragment_b
):

    data_a = fragment_a["data"]
    data_b = fragment_b["data"]

    analysis_a = fragment_a["analysis"]
    analysis_b = fragment_b["analysis"]

    overlap = calculate_overlap(
        data_a,
        data_b
    )

    maximum_overlap = min(
        len(data_a),
        len(data_b)
    )

    if maximum_overlap == 0:
        overlap_score = 0.0
    else:
        overlap_score = (
            overlap /
            maximum_overlap
        )

    entropy_score = calculate_entropy_similarity(
        analysis_a["entropy"],
        analysis_b["entropy"]
    )

    printable_score = calculate_printable_similarity(
        analysis_a["printable_ratio"],
        analysis_b["printable_ratio"]
    )

    transition_score = calculate_transition_similarity(
        data_a,
        data_b
    )

    # --------------------------------------------------------
    # AI-assisted weighted relationship model
    # --------------------------------------------------------

    confidence = (

        overlap_score * 0.55

        + entropy_score * 0.20

        + printable_score * 0.15

        + transition_score * 0.10

    )

    return {

        "from": analysis_a["filename"],

        "to": analysis_b["filename"],

        "overlap": overlap,

        "overlap_score":
            overlap_score,

        "entropy_similarity":
            entropy_score,

        "printable_similarity":
            printable_score,

        "transition_similarity":
            transition_score,

        "confidence":
            confidence

    }


# ============================================================
# ANALYZE ALL RELATIONSHIPS
# ============================================================

def analyze_relationships(
    storage_directory
):

    fragments = read_fragments(
        storage_directory
    )

    relationships = []

    fragment_names = list(
        fragments.keys()
    )

    for source in fragment_names:

        for target in fragment_names:

            if source == target:
                continue

            relationship = calculate_relationship(
                fragments[source],
                fragments[target]
            )

            # Only keep relationships where
            # there is actual evidence of continuity.

            if relationship["overlap"] > 0:

                relationships.append(
                    relationship
                )

    relationships.sort(
        key=lambda x: x["confidence"],
        reverse=True
    )

    return relationships


# ============================================================
# DISPLAY RESULTS
# ============================================================

def print_relationships(
    relationships
):

    print()

    print("=" * 115)

    print(
        "                 RECON-AI FRAGMENT RELATIONSHIP ANALYSIS"
    )

    print("=" * 115)

    if not relationships:

        print(
            "No meaningful fragment relationships detected."
        )

        return

    print(
        f"{'FROM':<42}"
        f"{'TO':<42}"
        f"{'OVERLAP':>9}"
        f"{'CONFIDENCE':>14}"
    )

    print("-" * 115)

    for relationship in relationships:

        print(

            f"{relationship['from']:<42}"

            f"{relationship['to']:<42}"

            f"{relationship['overlap']:>9}"

            f"{relationship['confidence'] * 100:>13.1f}%"

        )

    print("-" * 115)

    print(
        f"Relationships detected: "
        f"{len(relationships)}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    storage_path = Path(
        "lab/deleted_storage"
    )

    relationships = analyze_relationships(
        storage_path
    )

    print_relationships(
        relationships
    )