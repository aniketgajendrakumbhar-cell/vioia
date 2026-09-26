
from pathlib import Path
import json

from core.storage import get_metadata
from core.ai_engine import analyze_fragment_relationships
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


def _direct_scan():
    """
    Direct forensic scan used by the integrated simulation pipeline.

    We intentionally do not depend on the generic scanner here. The
    simulation already creates .bin fragment files and metadata, so a
    direct filesystem enumeration is the reliable source of truth.
    """
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    fragments = []

    for path in sorted(STORAGE_DIR.glob("*.bin")):
        try:
            size = path.stat().st_size
            if size <= 0:
                continue

            fragments.append({
                "filename": path.name,
                "path": str(path),
                "size": size,
            })
        except OSError:
            continue

    return fragments


def _fallback_damage(metadata, fragments):
    """Build damage information directly from simulation metadata."""
    missing = _metadata_list(
        metadata,
        "missing_fragments",
        "missing",
    )

    corrupted = _metadata_list(
        metadata,
        "corrupted_fragments",
        "corrupted",
    )

    expected = int(
        metadata.get(
            "total_fragments",
            len(fragments) + len(missing),
        ) or 0
    )

    available = len(fragments)

    damage_types = []

    if missing:
        damage_types.append("FRAGMENT LOSS")

    if corrupted:
        damage_types.append("DATA CORRUPTION")

    if not damage_types:
        damage_types.append("NONE DETECTED")

    damage_count = len(missing) + len(corrupted)

    if expected <= 0:
        severity = "UNKNOWN"
    else:
        ratio = damage_count / expected

        if ratio >= 0.20:
            severity = "HIGH"
        elif ratio >= 0.08:
            severity = "MEDIUM"
        elif ratio > 0:
            severity = "LOW"
        else:
            severity = "NONE"

    return {
        "success": True,
        "damage_types": damage_types,
        "damage_severity": severity,
        "severity": severity,
        "expected_fragments": expected,
        "available_fragments": available,
        "missing_count": len(missing),
        "corrupted_count": len(corrupted),
        "missing_fragments": missing,
        "corrupted_fragments": corrupted,
    }


def run_pipeline():
    print("\n" + "=" * 82)
    print("             RECON-AI INTEGRATED RECOVERY PIPELINE")
    print("=" * 82)

    # ---------------------------------------------------------
    # 1. DIRECT FORENSIC SCAN
    # ---------------------------------------------------------
    print("\n[1/8] Scanning damaged storage...")

    fragments = _direct_scan()

    if not fragments:
        print("       No .bin fragment files found in damaged storage.")
        print(f"       Storage path: {STORAGE_DIR}")
        return None

    print(f"       Fragments detected: {len(fragments)}")

    first_filename = fragments[0]["filename"]

    if ".fragment_" in first_filename:
        original_filename = first_filename.split(
            ".fragment_",
            1,
        )[0]
    else:
        original_filename = first_filename

    metadata = get_metadata(original_filename)

    if not metadata:
        print(
            f"       Storage metadata not found for: "
            f"{original_filename}"
        )
        return None

    original_size = metadata.get(
        "original_size",
        metadata.get("size"),
    )

    if original_size is None:
        print("       Original file size missing from metadata.")
        return None

    original_size = int(original_size)

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

    damage = _fallback_damage(
        metadata,
        fragments,
    )

    print(
        f"       Damage types: "
        f"{', '.join(damage['damage_types'])}"
    )
    print(
        f"       Expected: "
        f"{damage['expected_fragments']}"
    )
    print(
        f"       Available: "
        f"{damage['available_fragments']}"
    )
    print(
        f"       Missing: "
        f"{damage['missing_count']}"
    )
    print(
        f"       Corrupted: "
        f"{damage['corrupted_count']}"
    )
    print(
        f"       Severity: "
        f"{damage['damage_severity']}"
    )

    # ---------------------------------------------------------
    # 3. REAL TRANSFORMER AI
    # ---------------------------------------------------------
    print("\n[3/8] AI-analyzing fragment relationships...")

    ai_result = analyze_fragment_relationships(
        STORAGE_DIR
    )

    relationships = ai_result.get(
        "relationships",
        [],
    )

    print(
        f"       Model: "
        f"{ai_result.get('model')}"
    )
    print(
        f"       Embedding dimension: "
        f"{ai_result.get('embedding_dimension')}"
    )
    print(
        f"       Candidate relationships: "
        f"{len(relationships)}"
    )

    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        REPORTS_DIR /
        "ai_relationship_analysis.json"
    ).write_text(
        json.dumps(
            ai_result,
            indent=4,
        ),
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # 4. RECONSTRUCTION
    # ---------------------------------------------------------
    print("\n[4/8] Reconstructing evidence...")

    recovered_filename = (
        f"reconstructed_{original_filename}"
    )

    recovered_path = (
        RECOVERED_DIR /
        recovered_filename
    )

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

    chain = reconstruction.get(
        "chain",
        reconstruction.get(
            "fragment_chain",
            [],
        ),
    )

    if recovered_path.exists():
        recovered_size = recovered_path.stat().st_size
    else:
        recovered_size = int(
            reconstruction.get(
                "recovered_size",
                0,
            )
        )

    print(
        f"       Fragments used: "
        f"{reconstruction.get('fragments_used', len(chain))}"
    )
    print(
        f"       Recovered size: "
        f"{recovered_size} bytes"
    )

    if recovered_size <= 0:
        print("       Reconstruction produced zero bytes.")
        return None

    # ---------------------------------------------------------
    # 5. CLASSIFICATION
    # ---------------------------------------------------------
    print("\n[5/8] Classifying recovered evidence...")

    classification = classify_file(
        recovered_path
    )

    print(
        f"       File type: "
        f"{classification['file_type']}"
    )
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
            float(
                r.get(
                    "confidence",
                    0,
                )
            )
            for r in relationships
        ),
        default=0.0,
    )

    if (
        0 <
        relationship_confidence
        <= 1
    ):
        relationship_confidence *= 100.0

    integrity = assess_integrity(
        original_size=original_size,
        recovered_size=recovered_size,
        missing_fragments=missing_fragments,
        corrupted_fragments=corrupted_fragments,
        relationship_confidence=relationship_confidence,
    )

    # IMPORTANT:
    # The recovered artifact already exists, so recovery percentage must
    # describe actual byte coverage. Some older integrity implementations
    # returned 0 when relationship confidence was unavailable even though
    # reconstruction succeeded.
    size_recovery = min(
        100.0,
        (recovered_size / max(1, original_size)) * 100.0,
    )

    original_sha = str(
        metadata.get(
            "original_sha256",
            metadata.get("sha256", ""),
        ) or ""
    ).strip().lower()

    recovered_sha = ""
    try:
        import hashlib
        recovered_sha = hashlib.sha256(
            recovered_path.read_bytes()
        ).hexdigest().lower()
    except Exception:
        pass

    exact_hash_match = bool(
        original_sha
        and recovered_sha
        and original_sha == recovered_sha
    )

    # Use measured byte coverage as the recovery metric.
    integrity["recovery_percentage"] = round(
        100.0 if exact_hash_match else size_recovery,
        2,
    )

    # A cryptographic match is definitive evidence of exact recovery.
    if exact_hash_match:
        integrity["integrity_score"] = 100.0
        integrity["confidence"] = 100.0

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
        recovery_percentage=integrity[
            "recovery_percentage"
        ],
        integrity_score=integrity[
            "integrity_score"
        ],
        recovery_confidence=integrity[
            "confidence"
        ],
        classification_confidence=classification[
            "confidence"
        ],
        missing_fragments=missing_fragments,
        corrupted_fragments=corrupted_fragments,
    )

    print(
        f"       Priority: "
        f"{priority['priority_score']:.2f}/100 "
        f"({priority['priority']})"
    )

    # ---------------------------------------------------------
    # 8. REPORT
    # ---------------------------------------------------------
    print(
        "\n[8/8] Generating forensic evidence reports..."
    )

    report = create_evidence_report(
        evidence_id="RECON-2026-001",
        original_filename=original_filename,
        original_size=original_size,
        detected_fragments=len(fragments),
        missing_fragments=missing_fragments,
        corrupted_fragments=corrupted_fragments,
        reconstruction_chain=chain,
        recovered_file=recovered_path,
        recovery_percentage=integrity[
            "recovery_percentage"
        ],
        integrity_score=integrity[
            "integrity_score"
        ],
        recovery_confidence=integrity[
            "confidence"
        ],
        file_type=classification[
            "file_type"
        ],
        classification_confidence=classification[
            "confidence"
        ],
        priority_score=priority[
            "priority_score"
        ],
        priority_level=priority[
            "priority"
        ],
    )

    if isinstance(report, dict):
        report["damage_analysis"] = damage

        report["ai_analysis"] = {
            "model": ai_result.get(
                "model"
            ),
            "embedding_dimension": ai_result.get(
                "embedding_dimension"
            ),
            "relationship_count": len(
                relationships
            ),
            "relationships": relationships,
        }

        report["reconstruction"] = (
            reconstruction
        )

        # Explicit source-of-truth fields for the dashboard.
        report["original_filename"] = (
            original_filename
        )
        report["original_size"] = (
            original_size
        )
        report["recovered_size"] = (
            recovered_size
        )
        report["recovered_file"] = (
            str(recovered_path)
        )
        report["recovered_path"] = (
            str(recovered_path)
        )
        report["output_path"] = (
            str(recovered_path)
        )
        report["original_sha256"] = (
            metadata.get(
                "original_sha256",
                metadata.get(
                    "sha256",
                    "",
                ),
            )
        )
        report["recovered_sha256"] = recovered_sha
        report["exact_sha256_match"] = exact_hash_match
        report["exact_reconstruction"] = exact_hash_match
        report["recovery_percentage"] = integrity[
            "recovery_percentage"
        ]
        report["integrity_score"] = integrity[
            "integrity_score"
        ]
        report["recovery_confidence"] = integrity[
            "confidence"
        ]

    json_report = save_json_report(
        report,
        "pipeline_evidence_report.json",
    )

    text_report = save_text_report(
        report,
        "pipeline_evidence_report.txt",
    )

    print(
        f"       JSON report: {json_report}"
    )
    print(
        f"       Text report: {text_report}"
    )

    print("\n" + "=" * 82)
    print("                    RECOVERY SUMMARY")
    print("=" * 82)
    print(
        f"Evidence        : "
        f"{original_filename}"
    )
    print(
        f"Damage          : "
        f"{', '.join(damage['damage_types'])}"
    )
    print(
        f"Severity        : "
        f"{damage['damage_severity']}"
    )
    print(
        f"AI model        : "
        f"{ai_result.get('model')}"
    )
    print(
        f"Relationships   : "
        f"{len(relationships)}"
    )
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
