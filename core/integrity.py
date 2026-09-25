from pathlib import Path
import hashlib


# ============================================================
# RECON-AI INTEGRITY ASSESSMENT ENGINE
# ============================================================


def calculate_sha256(file_path):

    file_path = Path(file_path)

    if not file_path.exists():
        return None

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:

        while True:

            chunk = file.read(8192)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


# ============================================================
# RECOVERY PERCENTAGE
# ============================================================

def calculate_recovery_percentage(
    original_size,
    recovered_size
):

    if original_size <= 0:
        return 0.0

    percentage = (
        recovered_size /
        original_size
    ) * 100

    return min(
        100.0,
        percentage
    )


# ============================================================
# INTEGRITY ASSESSMENT
# ============================================================

def assess_integrity(
    original_size,
    recovered_size,
    missing_fragments,
    corrupted_fragments,
    relationship_confidence
):

    recovery_percentage = (
        calculate_recovery_percentage(
            original_size,
            recovered_size
        )
    )

    # --------------------------------------------------------
    # Determine recovery status
    # --------------------------------------------------------

    if (
        not missing_fragments
        and not corrupted_fragments
        and recovery_percentage >= 99
    ):

        status = "FULLY RECOVERED"

    elif recovery_percentage >= 70:

        status = "PARTIALLY RECOVERED"

    elif recovery_percentage > 0:

        status = "LOW RECOVERY"

    else:

        status = "NOT RECOVERABLE"

    # --------------------------------------------------------
    # Integrity score
    # --------------------------------------------------------

    integrity_score = recovery_percentage

    if corrupted_fragments:

        integrity_score -= (
            len(corrupted_fragments) * 10
        )

    integrity_score = max(
        0.0,
        min(100.0, integrity_score)
    )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidence = (
        relationship_confidence * 100
    )

    if missing_fragments:

        confidence *= 0.85

    if corrupted_fragments:

        confidence *= 0.75

    confidence = max(
        0.0,
        min(100.0, confidence)
    )

    # --------------------------------------------------------
    # Restoration assessment
    # --------------------------------------------------------

    if status == "FULLY RECOVERED":

        restoration = (
            "File appears completely recoverable."
        )

    elif status == "PARTIALLY RECOVERED":

        restoration = (
            "File is partially recoverable. "
            "Missing or damaged sections remain."
        )

    elif status == "LOW RECOVERY":

        restoration = (
            "Only a limited portion of the "
            "original information could be reconstructed."
        )

    else:

        restoration = (
            "Insufficient recoverable information "
            "was found."
        )

    return {

        "status":
            status,

        "recovery_percentage":
            round(
                recovery_percentage,
                2
            ),

        "integrity_score":
            round(
                integrity_score,
                2
            ),

        "confidence":
            round(
                confidence,
                2
            ),

        "restoration_assessment":
            restoration

    }


# ============================================================
# DISPLAY RESULT
# ============================================================

def print_integrity_report(
    result
):

    print()

    print("=" * 80)

    print(
        "              RECON-AI INTEGRITY ASSESSMENT"
    )

    print("=" * 80)

    print(
        f"Recovery status       : "
        f"{result['status']}"
    )

    print(
        f"Recovery percentage   : "
        f"{result['recovery_percentage']:.2f}%"
    )

    print(
        f"Integrity score       : "
        f"{result['integrity_score']:.2f}%"
    )

    print(
        f"Recovery confidence   : "
        f"{result['confidence']:.2f}%"
    )

    print()

    print(
        "Assessment:"
    )

    print(
        result["restoration_assessment"]
    )

    print("=" * 80)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    from core.storage import get_metadata

    original_filename = "test_evidence.txt"

    recovered_file = Path(
        "lab/recovered/reconstructed_test_evidence.txt"
    )

    # Read latest fragmentation metadata
    metadata = get_metadata(original_filename)

    if not metadata:
        print("No metadata found for:", original_filename)
        raise SystemExit(1)

    if not recovered_file.exists():
        print("Recovered file not found:", recovered_file)
        raise SystemExit(1)

    original_size = metadata.get("size", 0)
    recovered_size = recovered_file.stat().st_size

    missing_fragments = metadata.get(
        "missing_fragments",
        []
    )

    corrupted_fragments = metadata.get(
        "corrupted_fragments",
        []
    )

    # Highest relationship confidence from current analysis.
    # Later the pipeline will supply this automatically.
    relationship_confidence = 0.603

    result = assess_integrity(
        original_size=original_size,
        recovered_size=recovered_size,
        missing_fragments=missing_fragments,
        corrupted_fragments=corrupted_fragments,
        relationship_confidence=relationship_confidence
    )

    print_integrity_report(result)