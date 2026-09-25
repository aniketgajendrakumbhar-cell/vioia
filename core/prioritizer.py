# ============================================================
# RECON-AI RECOVERY PRIORITIZATION ENGINE
# ============================================================


def calculate_priority(
    recovery_percentage,
    integrity_score,
    recovery_confidence,
    classification_confidence,
    missing_fragments,
    corrupted_fragments
):

    # --------------------------------------------------------
    # Base recovery evidence
    # --------------------------------------------------------

    score = (

        recovery_percentage * 0.35

        + integrity_score * 0.25

        + recovery_confidence * 0.20

        + classification_confidence * 0.20

    )

    # --------------------------------------------------------
    # Missing fragment penalty
    # --------------------------------------------------------

    score -= (
        len(missing_fragments) * 5
    )

    # --------------------------------------------------------
    # Corruption penalty
    # --------------------------------------------------------

    score -= (
        len(corrupted_fragments) * 8
    )

    score = max(
        0.0,
        min(100.0, score)
    )

    # --------------------------------------------------------
    # Priority category
    # --------------------------------------------------------

    if score >= 80:

        priority = "HIGH"

    elif score >= 50:

        priority = "MEDIUM"

    else:

        priority = "LOW"

    return {
        "priority_score":
            round(score, 2),

        "priority":
            priority
    }


# ============================================================
# DISPLAY RESULT
# ============================================================

def print_priority(result):

    print()

    print("=" * 80)

    print(
        "              RECON-AI RECOVERY PRIORITIZATION"
    )

    print("=" * 80)

    print(
        f"Priority score : "
        f"{result['priority_score']:.2f}/100"
    )

    print(
        f"Priority level : "
        f"{result['priority']}"
    )

    print("=" * 80)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    result = calculate_priority(

        recovery_percentage=72.97,

        integrity_score=72.97,

        recovery_confidence=51.25,

        classification_confidence=100.0,

        missing_fragments=[0],

        corrupted_fragments=[]

    )

    print_priority(
        result
    )