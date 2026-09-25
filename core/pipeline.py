from pathlib import Path
import json

from core.scanner import scan_storage
from core.storage import get_metadata
from core.ai_engine import analyze_fragment_relationships
from core.damage_detector import analyze_damage
from core.reconstruction import reconstruct_file
from core.classifier import classify_file
from core.integrity import assess_integrity
from core.prioritizer import calculate_priority
from core.evidence import (
    create_evidence_report,
    save_json_report,
    save_text_report,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "lab" / "deleted_storage"
RECOVERED_DIR = BASE_DIR / "lab" / "recovered"
REPORTS_DIR = BASE_DIR / "reports"


def _metadata_list(metadata, primary, fallback):
    value = metadata.get(primary)
    if value is None:
        value = metadata.get(fallback, [])
    return value if isinstance(value, list) else []


def run_pipeline():
    print("\n" + "=" * 82)
    print("             RECON-AI INTEGRATED RECOVERY PIPELINE")
    print("=" * 82)

    # ---------------------------------------------------------
    # 1. SCAN
    # ---------------------------------------------------------
    print("\n[1/8] Scanning damaged storage...")

    fragments = scan_storage(STORAGE_DIR)

    if not fragments:
        print("       No recoverable fragments found.")
        return None

    print(f"       Fragments detected: {len(fragments)}")

    first_filename = fragments[0]["filename"]
    original_filename = first_filename.split(".fragment_")[0]

    metadata = get_metadata(original_filename)

    if not metadata:
        print(f"       Storage metadata not found for: {original_filename}")
        return None

    original_size = metadata.get(
        "size",
        metadata.get("original_size"),
    )

    if original_size is None:
        print("       Original file size missing from metadata.")
        return None

    # Support both metadata naming schemes.
    missing_fragments = _metadata_list(
        metadata,
        "missing_fragments",
        "missing",
    )

    corrupted_fragments = _metadata_list(
        metadata,
        "corrupted_fragments",
        "corrupted",
    )

    # ---------------------------------------------------------
    # 2. DAMAGE ANALYSIS
    # ---------------------------------------------------------
    print("\n[2/8] Detecting damage and corruption...")

    damage = analyze_damage()

    if not damage.get("success"):
        print(f"       Damage analysis failed: {damage.get('message')}")
        return None

    # Prefer detector's normalized values.
    missing_fragments = damage.get(
        "missing_fragments",
        missing_fragments,
    )

    corrupted_fragments = damage.get(
        "corrupted_fragments",
        corrupted_fragments,
    )

    print(f"       Damage types: {', '.join(damage['damage_types'])}")
    print(f"       Expected: {damage['expected_fragments']}")
    print(f"       Available: {damage['available_fragments']}")
    print(f"       Missing: {damage['missing_count']}")
    print(f"       Corrupted: {damage['corrupted_count']}")
    print(f"       Severity: {damage['damage_severity']}")

    # ---------------------------------------------------------
    # 3. REAL TRANSFORMER AI
    # ---------------------------------------------------------
    print("\n[3/8] AI-analyzing fragment relationships...")

    ai_result = analyze_fragment_relationships(STORAGE_DIR)
    relationships = ai_result.get("relationships", [])

    print(f"       Model: {ai_result.get('model')}")
    print(
        f"       Embedding dimension: "
        f"{ai_result.get('embedding_dimension')}"
    )
    print(f"       Candidate relationships: {len(relationships)}")

    if relationships:
        best = relationships[0]
        print(
            f"       Best: "
            f"{best.get('from')} -> {best.get('to')}"
        )
        print(
            f"       AI similarity: "
            f"{float(best.get('ai_similarity', 0)):.2f}%"
        )
        print(
            f"       Final confidence: "
            f"{float(best.get('confidence', 0)):.2f}%"
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    (REPORTS_DIR / "ai_relationship_analysis.json").write_text(
        json.dumps(ai_result, indent=4),
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # 4. RECONSTRUCTION
    # ---------------------------------------------------------
    print("\n[4/8] Reconstructing evidence...")

    recovered_filename = f"reconstructed_{original_filename}"
    recovered_path = RECOVERED_DIR / recovered_filename

    reconstruction = reconstruct_file(
        STORAGE_DIR,
        relationships,
        recovered_path,
    )

    if not reconstruction.get("success"):
        print(
            "       Reconstruction failed: "
            f"{reconstruction.get('message', '')}"
        )
        return None

    # Accept both current and legacy result names.
    chain = reconstruction.get(
        "chain",
        reconstruction.get("fragment_chain", []),
    )

    recovered_size = reconstruction.get(
        "recovered_size",
        recovered_path.stat().st_size,
    )

    print(
        f"       Fragments used: "
        f"{reconstruction.get('fragments_used', len(chain))}"
    )
    print(f"       Recovered size: {recovered_size} bytes")
    print(f"       Chain: {' -> '.join(chain)}")

    # ---------------------------------------------------------
    # 5. CLASSIFICATION
    # ---------------------------------------------------------
    print("\n[5/8] Classifying recovered evidence...")

    classification = classify_file(recovered_path)

    print(f"       File type: {classification['file_type']}")
    print(
        f"       Confidence: "
        f"{classification['confidence']:.2f}%"
    )

    # ---------------------------------------------------------
    # 6. INTEGRITY
    # ---------------------------------------------------------
    print("\n[6/8] Assessing recovery integrity...")

    relationship_confidence = max(
        (
            float(r.get("confidence", 0))
            for r in relationships
        ),
        default=0.0,
    )

    # Current AI engine stores confidence as a percentage.
    # Protect against older 0-1 relationship formats.
    if 0 < relationship_confidence <= 1:
        relationship_confidence *= 100.0

    integrity = assess_integrity(
        original_size=original_size,
        recovered_size=recovered_size,
        missing_fragments=missing_fragments,
        corrupted_fragments=corrupted_fragments,
        relationship_confidence=relationship_confidence,
    )

    print(
        f"       Recovery: "
        f"{integrity['recovery_percentage']:.2f}%"
    )
    print(
        f"       Integrity: "
        f"{integrity['integrity_score']:.2f}%"
    )
    print(
        f"       AI recovery confidence: "
        f"{integrity['confidence']:.2f}%"
    )

    # ---------------------------------------------------------
    # 7. PRIORITY
    # ---------------------------------------------------------
    print("\n[7/8] Calculating evidence priority...")

    priority = calculate_priority(
        recovery_percentage=integrity["recovery_percentage"],
        integrity_score=integrity["integrity_score"],
        recovery_confidence=integrity["confidence"],
        classification_confidence=classification["confidence"],
        missing_fragments=missing_fragments,
        corrupted_fragments=corrupted_fragments,
    )

    print(
        f"       Priority: "
        f"{priority['priority_score']:.2f}/100 "
        f"({priority['priority']})"
    )

    # ---------------------------------------------------------
    # 8. REPORTS
    # ---------------------------------------------------------
    print("\n[8/8] Generating forensic evidence reports...")

    report = create_evidence_report(
        evidence_id="RECON-2026-001",
        original_filename=original_filename,
        original_size=original_size,
        detected_fragments=len(fragments),
        missing_fragments=missing_fragments,
        corrupted_fragments=corrupted_fragments,
        reconstruction_chain=chain,
        recovered_file=recovered_path,
        recovery_percentage=integrity["recovery_percentage"],
        integrity_score=integrity["integrity_score"],
        recovery_confidence=integrity["confidence"],
        file_type=classification["file_type"],
        classification_confidence=classification["confidence"],
        priority_score=priority["priority_score"],
        priority_level=priority["priority"],
    )

    if isinstance(report, dict):
        report["damage_analysis"] = damage

        report["ai_analysis"] = {
            "model": ai_result.get("model"),
            "embedding_dimension": ai_result.get(
                "embedding_dimension"
            ),
            "relationship_count": len(relationships),
            "relationships": relationships,
        }

        report["reconstruction"] = reconstruction

    json_report = save_json_report(
        report,
        "pipeline_evidence_report.json",
    )

    text_report = save_text_report(
        report,
        "pipeline_evidence_report.txt",
    )

    print(f"       JSON report: {json_report}")
    print(f"       Text report: {text_report}")

    print("\n" + "=" * 82)
    print("                    RECOVERY SUMMARY")
    print("=" * 82)
    print(f"Evidence        : {original_filename}")
    print(f"Damage          : {', '.join(damage['damage_types'])}")
    print(f"Severity        : {damage['damage_severity']}")
    print(f"AI model        : {ai_result.get('model')}")
    print(f"Relationships    : {len(relationships)}")
    print(
        f"Recovery        : "
        f"{integrity['recovery_percentage']:.2f}%"
    )
    print(
        f"Integrity       : "
        f"{integrity['integrity_score']:.2f}%"
    )
    print(
        f"Priority        : "
        f"{priority['priority']} "
        f"({priority['priority_score']:.2f}/100)"
    )
    print("=" * 82)

    return report


if __name__ == "__main__":
    run_pipeline()
