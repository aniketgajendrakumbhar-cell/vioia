from pathlib import Path
import json
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def create_evidence_report(
    evidence_id,
    original_filename,
    original_size,
    detected_fragments,
    missing_fragments,
    corrupted_fragments,
    reconstruction_chain,
    recovered_file,
    recovery_percentage,
    integrity_score,
    recovery_confidence,
    file_type,
    classification_confidence,
    priority_score,
    priority_level,
):
    """
    Build one consistent report structure used by both JSON and TXT reports.

    Important:
    All recovery metrics live at the top level AND inside reconstruction.
    This keeps compatibility with older dashboard/report code.
    """

    original_size = int(_number(original_size))
    recovery_percentage = _number(recovery_percentage)
    integrity_score = _number(integrity_score)
    recovery_confidence = _number(recovery_confidence)
    classification_confidence = _number(
        classification_confidence
    )
    priority_score = _number(priority_score)

    missing = _list(missing_fragments)
    corrupted = _list(corrupted_fragments)
    chain = _list(reconstruction_chain)

    recovered_path = (
        str(Path(recovered_file).resolve())
        if recovered_file
        else None
    )

    recovered_size = 0

    if recovered_path:
        path = Path(recovered_path)
        if path.exists():
            try:
                recovered_size = path.stat().st_size
            except OSError:
                recovered_size = 0

    now = datetime.now().isoformat(timespec="seconds")

    reconstruction = {
        "chain": chain,
        "fragment_chain": chain,
        "fragments_used": len(chain),

        "recovered_file": recovered_path,
        "output_path": recovered_path,
        "recovered_path": recovered_path,

        "recovered_size": recovered_size,
        "recovered_size_bytes": recovered_size,
        "recovered_file_size": recovered_size,

        "recovery_percentage": recovery_percentage,
        "integrity_score": integrity_score,
        "recovery_confidence": recovery_confidence,

        "file_type": file_type,
        "classification_confidence": classification_confidence,

        "priority_score": priority_score,
        "priority_level": priority_level,
    }

    report = {
        "report_version": "2.0",
        "generated_at": now,

        "evidence_id": evidence_id,
        "original_filename": original_filename,
        "original_size": original_size,

        "detected_fragments": int(
            _number(detected_fragments)
        ),

        "missing_fragments": missing,
        "missing_count": len(missing),

        "corrupted_fragments": corrupted,
        "corrupted_count": len(corrupted),

        "recovery_percentage": recovery_percentage,
        "integrity_score": integrity_score,
        "recovery_confidence": recovery_confidence,

        "file_type": file_type,
        "classification_confidence": (
            classification_confidence
        ),

        "priority_score": priority_score,
        "priority_level": priority_level,

        "recovered_file": recovered_path,
        "recovered_size": recovered_size,

        "reconstruction_chain": chain,

        # Compatibility section expected by the current pipeline.
        "reconstruction": reconstruction,

        "damage_analysis": {},
        "ai_analysis": {},
    }

    return report


def save_json_report(report, filename="pipeline_evidence_report.json"):
    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = REPORTS_DIR / filename

    output.write_text(
        json.dumps(
            report,
            indent=4,
            default=str,
        ),
        encoding="utf-8",
    )

    return str(output)


def save_text_report(
    report,
    filename="pipeline_evidence_report.txt",
):
    """
    Generate a human-readable forensic report.

    This function deliberately reads recovery metrics from the top-level
    report first and falls back to reconstruction for compatibility.
    """

    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = REPORTS_DIR / filename

    reconstruction = report.get(
        "reconstruction",
        {},
    )

    # Robust compatibility: old reports may store values at either level.
    recovery_percentage = _number(
        report.get(
            "recovery_percentage",
            reconstruction.get(
                "recovery_percentage",
                0,
            ),
        )
    )

    integrity_score = _number(
        report.get(
            "integrity_score",
            reconstruction.get(
                "integrity_score",
                0,
            ),
        )
    )

    recovery_confidence = _number(
        report.get(
            "recovery_confidence",
            reconstruction.get(
                "recovery_confidence",
                0,
            ),
        )
    )

    priority_score = _number(
        report.get(
            "priority_score",
            reconstruction.get(
                "priority_score",
                0,
            ),
        )
    )

    priority_level = report.get(
        "priority_level",
        reconstruction.get(
            "priority_level",
            "UNKNOWN",
        ),
    )

    file_type = report.get(
        "file_type",
        reconstruction.get(
            "file_type",
            "UNKNOWN",
        ),
    )

    classification_confidence = _number(
        report.get(
            "classification_confidence",
            reconstruction.get(
                "classification_confidence",
                0,
            ),
        )
    )

    chain = report.get(
        "reconstruction_chain",
        reconstruction.get(
            "chain",
            reconstruction.get(
                "fragment_chain",
                [],
            ),
        ),
    )

    missing = _list(
        report.get(
            "missing_fragments",
            [],
        )
    )

    corrupted = _list(
        report.get(
            "corrupted_fragments",
            [],
        )
    )

    damage = report.get(
        "damage_analysis",
        {},
    )

    ai = report.get(
        "ai_analysis",
        {},
    )

    lines = []

    lines.append("=" * 82)
    lines.append(
        "                 RECON-AI FORENSIC EVIDENCE REPORT"
    )
    lines.append("=" * 82)

    lines.append("")
    lines.append(
        f"Evidence ID             : "
        f"{report.get('evidence_id', 'N/A')}"
    )
    lines.append(
        f"Original file           : "
        f"{report.get('original_filename', 'N/A')}"
    )
    lines.append(
        f"Original size           : "
        f"{report.get('original_size', 0)} bytes"
    )
    lines.append(
        f"Generated               : "
        f"{report.get('generated_at', 'N/A')}"
    )

    lines.append("")
    lines.append("-" * 82)
    lines.append("DAMAGE ANALYSIS")
    lines.append("-" * 82)

    damage_types = damage.get(
        "damage_types",
        [],
    )

    if damage_types:
        lines.append(
            "Damage types            : "
            + ", ".join(map(str, damage_types))
        )

    lines.append(
        f"Expected fragments      : "
        f"{damage.get('expected_fragments', report.get('detected_fragments', 0))}"
    )
    lines.append(
        f"Available fragments     : "
        f"{damage.get('available_fragments', 0)}"
    )
    lines.append(
        f"Missing fragments       : "
        f"{damage.get('missing_count', len(missing))}"
    )
    lines.append(
        f"Corrupted fragments     : "
        f"{damage.get('corrupted_count', len(corrupted))}"
    )
    lines.append(
        f"Damage severity         : "
        f"{damage.get('damage_severity', 'UNKNOWN')}"
    )

    lines.append("")
    lines.append("-" * 82)
    lines.append("AI ANALYSIS")
    lines.append("-" * 82)

    lines.append(
        f"AI model                : "
        f"{ai.get('model', 'N/A')}"
    )
    lines.append(
        f"Embedding dimension     : "
        f"{ai.get('embedding_dimension', 'N/A')}"
    )
    lines.append(
        f"Relationships found     : "
        f"{ai.get('relationship_count', 0)}"
    )

    lines.append("")
    lines.append("-" * 82)
    lines.append("RECONSTRUCTION")
    lines.append("-" * 82)

    lines.append(
        f"Recovered file          : "
        f"{report.get('recovered_file', reconstruction.get('recovered_file', 'N/A'))}"
    )
    lines.append(
        f"Recovered size          : "
        f"{report.get('recovered_size', reconstruction.get('recovered_size', 0))} bytes"
    )
    lines.append(
        f"Fragments used          : "
        f"{reconstruction.get('fragments_used', len(chain))}"
    )

    lines.append("")
    lines.append(
        "Reconstruction chain:"
    )

    # Avoid producing a massive single terminal line.
    if chain:
        chunk = []
        for index, item in enumerate(chain, start=1):
            chunk.append(str(item))

            if len(chunk) >= 6:
                lines.append(
                    "  " + " -> ".join(chunk)
                )
                chunk = []

        if chunk:
            lines.append(
                "  " + " -> ".join(chunk)
            )
    else:
        lines.append("  No chain available.")

    lines.append("")
    lines.append("-" * 82)
    lines.append("RECOVERY ASSESSMENT")
    lines.append("-" * 82)

    lines.append(
        f"Recovery percentage     : "
        f"{recovery_percentage:.2f}%"
    )
    lines.append(
        f"Integrity score         : "
        f"{integrity_score:.2f}%"
    )
    lines.append(
        f"AI recovery confidence  : "
        f"{recovery_confidence:.2f}%"
    )

    lines.append("")
    lines.append("-" * 82)
    lines.append("CLASSIFICATION")
    lines.append("-" * 82)

    lines.append(
        f"File type               : "
        f"{file_type}"
    )
    lines.append(
        f"Classification confidence: "
        f"{classification_confidence:.2f}%"
    )

    lines.append("")
    lines.append("-" * 82)
    lines.append("EVIDENCE PRIORITY")
    lines.append("-" * 82)

    lines.append(
        f"Priority score          : "
        f"{priority_score:.2f}/100"
    )
    lines.append(
        f"Priority level          : "
        f"{priority_level}"
    )

    lines.append("")
    lines.append("=" * 82)
    lines.append(
        "                         END OF REPORT"
    )
    lines.append("=" * 82)

    output.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return str(output)


if __name__ == "__main__":
    print(
        "RECON-AI evidence.py loaded successfully."
    )
