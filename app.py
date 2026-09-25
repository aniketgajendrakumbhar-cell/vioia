from pathlib import Path
import atexit
import contextlib
import io
import json
import hashlib
import mimetypes
import re

import streamlit as st

from core.storage import (
    ACTIVE_DIR,
    DELETED_DIR,
    RECOVERED_DIR,
    create_damaged_fragments,
)
from core.scanner import scan_storage
from recovery_engine import recover_uploaded_fragments, repair_single_file


# ============================================================
# RECON-AI STREAMLIT DASHBOARD
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
LAB_DIR = BASE_DIR / "lab"
REPORTS_DIR = BASE_DIR / "reports"
METADATA_FILE = LAB_DIR / "storage_metadata.json"

AI_REPORT = REPORTS_DIR / "ai_relationship_analysis.json"
EVIDENCE_JSON = REPORTS_DIR / "pipeline_evidence_report.json"
EVIDENCE_TXT = REPORTS_DIR / "pipeline_evidence_report.txt"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# AUTOMATIC CLEANUP
# ============================================================

def clear_folder(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for item in list(folder.iterdir()):
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)
        except Exception:
            pass


def cleanup_lab():
    """Delete temporary forensic simulation data when Streamlit exits."""
    for folder in (ACTIVE_DIR, DELETED_DIR, RECOVERED_DIR):
        clear_folder(folder)

    try:
        if METADATA_FILE.exists():
            METADATA_FILE.unlink()
    except Exception:
        pass

    # Reports contain temporary demo results, so remove them too.
    clear_folder(REPORTS_DIR)


# Register cleanup when the Streamlit/Python process actually stops.
atexit.register(cleanup_lab)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="RECON-AI | Digital Evidence Recovery",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ============================================================
# CUSTOM UI
# ============================================================

st.markdown(
    """
    <style>
    /* Navy forensic command-center theme */
    :root {
        --navy-950: #061326;
        --navy-900: #0a1b33;
        --navy-800: #0e2747;
        --navy-700: #12365f;
        --blue: #2f80ed;
        --cyan: #38bdf8;
        --green: #22c55e;
        --red: #ef4444;
        --amber: #f59e0b;
    }

    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 10% 0%, rgba(47,128,237,0.13), transparent 32%),
            radial-gradient(circle at 90% 10%, rgba(56,189,248,0.09), transparent 28%),
            #061326;
    }

    [data-testid="stHeader"] {
        background: rgba(6,19,38,0.82);
    }

    [data-testid="stAppViewContainer"] * {
        color: #586179;
    }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stCaptionContainer"] {
        color: #586179;
    }

    .block-container {
    .block-container {
        max-width: 1120px;
        padding-top: 2rem;
        padding-bottom: 3rem;
        margin: 0 auto;
    }

    /* Header */
    .hero {
        text-align: center;
        padding: 1.8rem 1rem 1.4rem 1rem;
        margin-bottom: 1rem;
    }

    .hero-title {
        font-size: 3rem;
        font-weight: 900;
        letter-spacing: -0.05em;
        margin: 0;
        background: none;
        -webkit-background-clip: text;
        -webkit-text-fill-color: #586179;
        text-shadow: 0 0 30px rgba(56,189,248,0.12);
    }

    .hero-subtitle {
        font-size: 1.05rem;
        opacity: 0.72;
        margin-top: 0.45rem;
    }

    .hero-badge {
        display: inline-block;
        margin-top: 0.9rem;
        padding: 0.4rem 1rem;
        border-radius: 999px;
        border: 1px solid rgba(56,189,248,0.35);
        background: rgba(14,39,71,0.72);
        color: #586179 !important;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.04em;
    }

    /* Main cards */
    .card {
        border: 1px solid rgba(56,189,248,0.18);
        border-radius: 18px;
        padding: 1.35rem;
        margin: 0.8rem 0;
        background: linear-gradient(145deg, rgba(14,39,71,0.78), rgba(7,24,47,0.82));
        box-shadow: 0 14px 40px rgba(0,0,0,0.22);
    }

    .step-title {
        font-size: 1.15rem;
        font-weight: 750;
        margin-bottom: 0.35rem;
    }

    .muted {
        opacity: 0.68;
        font-size: 0.92rem;
    }

    .result-banner {
        border-radius: 16px;
        padding: 1rem 1.1rem;
        margin: 0.8rem 0 1rem 0;
        border: 1px solid rgba(56,189,248,0.22);
        background: linear-gradient(135deg, rgba(14,39,71,0.75), rgba(9,29,53,0.72));
        box-shadow: 0 10px 30px rgba(0,0,0,0.18);
    }

    .download-card {
        border: 1px solid rgba(56,189,248,0.30);
        border-radius: 18px;
        padding: 1.2rem;
        margin-top: 0.8rem;
        background: linear-gradient(135deg, rgba(18,54,95,0.78), rgba(8,27,50,0.9));
        box-shadow: 0 14px 36px rgba(0,0,0,0.25);
    }

    /* Make buttons feel like primary actions */
    .stButton > button,
    .stDownloadButton > button {
        border-radius: 12px;
        min-height: 2.9rem;
        font-weight: 750;
        border: 1px solid rgba(56,189,248,0.25);
        background: linear-gradient(135deg, #12365f, #0d294b);
        color: white !important;
        box-shadow: 0 8px 22px rgba(0,0,0,0.18);
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        border-color: #38bdf8;
        box-shadow: 0 0 22px rgba(56,189,248,0.18);
    }

    [data-testid="stDataFrame"] {
        border: 1px solid rgba(56,189,248,0.16);
        border-radius: 14px;
        overflow: hidden;
    }

    [data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(14,39,71,0.8), rgba(7,24,47,0.72));
        border: 1px solid rgba(56,189,248,0.15);
        border-radius: 14px;
        padding: 0.8rem;
    }

    /* Metric spacing */
    [data-testid="stMetric"] {
        padding: 0.5rem 0.25rem;
    }

    /* Hide the sidebar completely for the centered workflow */
    [data-testid="stSidebar"] {
        display: none;
    }

    /* Cleaner tabs */
    button[data-baseweb="tab"] {
        font-weight: 650;
    }

    /* High contrast for navy forensic UI */
    .download-card {
        border: 1px solid #2f80ed !important;
        border-radius: 18px;
        padding: 1.35rem;
        margin-top: 0.8rem;
        background: #102d50 !important;
        color: #586179 !important;
        box-shadow: 0 14px 36px rgba(0,0,0,0.30);
    }

    .download-card b {
        color: #586179 !important;
    }

    .download-card code {
        display: inline-block;
        background: #061326 !important;
        color: #586179 !important;
        border: 1px solid #2f80ed !important;
        border-radius: 7px;
        padding: 4px 8px;
        word-break: break-all;
    }

    .stDownloadButton > button {
        background: #1f6fd1 !important;
        color: #586179 !important;
        border: 1px solid #55b8ff !important;
        font-weight: 800 !important;
    }

    .stDownloadButton > button:hover {
        background: #2f80ed !important;
        color: #586179 !important;
        border-color: #586179 !important;
    }

    [data-testid="stAlert"] {
        color: #586179 !important;
    }

    [data-testid="stCodeBlock"] {
        background: #071a30 !important;
        border: 1px solid rgba(56,189,248,0.22);
    }

    button[data-baseweb="tab"] {
        color: #9fb6d1 !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        color: #586179 !important;
    }


    /* High-contrast execution logs */
    [data-testid="stCodeBlock"] {
        background: #071a30 !important;
        border: 1px solid #21466d !important;
        border-radius: 14px !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.28);
    }

    [data-testid="stCodeBlock"] pre,
    [data-testid="stCodeBlock"] code {
        background: #071a30 !important;
        color: #586179 !important;
        -webkit-text-fill-color: #586179 !important;
        font-family: "Consolas", "Cascadia Mono", monospace !important;
        font-size: 0.88rem !important;
        line-height: 1.65 !important;
        text-shadow: none !important;
    }

    [data-testid="stCodeBlock"] button {
        background: #12365f !important;
        color: #586179 !important;
        border: 1px solid #2f80ed !important;
    }

    [data-testid="stCodeBlock"] button svg {
        color: #586179 !important;
        fill: #586179 !important;
    }

    /* Prevent the global text rule from washing out code/log text. */
    [data-testid="stCodeBlock"] * {
        color: #586179 !important;
        -webkit-text-fill-color: #586179 !important;
    }


    /* ============================================================
       LIGHT SURFACES = DARK TEXT
       Never use white text on white Streamlit surfaces.
       ============================================================ */

    /* Streamlit cards / expanders / popovers that render light */
    [data-testid="stExpander"],
    [data-testid="stExpander"] > details,
    [data-testid="stPopover"],
    [data-testid="stFileUploader"],
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stAlert"],
    [data-testid="stDataFrame"],
    [data-testid="stTable"] {
        color: #10243d !important;
    }

    [data-testid="stExpander"] *,
    [data-testid="stPopover"] *,
    [data-testid="stFileUploader"] *,
    [data-testid="stFileUploaderDropzone"] *,
    [data-testid="stAlert"] *,
    [data-testid="stDataFrame"] *,
    [data-testid="stTable"] * {
        color: #10243d !important;
        -webkit-text-fill-color: #10243d !important;
    }

    /* File uploader: white/light background -> navy text */
    [data-testid="stFileUploaderDropzone"] {
        background: #f8fbff !important;
        border: 1px dashed #7aa7d8 !important;
        border-radius: 14px !important;
    }

    [data-testid="stFileUploaderDropzone"] button {
        background: #586179 !important;
        color: #12365f !important;
        border: 1px solid #7aa7d8 !important;
    }

    [data-testid="stFileUploaderDropzone"] button * {
        color: #12365f !important;
        -webkit-text-fill-color: #12365f !important;
    }

    /* White/light alerts */
    [data-testid="stAlert"] {
        background: #f4f8fc !important;
        border: 1px solid #c8d8e8 !important;
    }

    /* Metrics */
    [data-testid="stMetric"] {
        color: #10243d !important;
    }

    [data-testid="stMetric"] *,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] {
        color: #10243d !important;
        -webkit-text-fill-color: #10243d !important;
    }

    /* Dataframes: force readable dark text on light cells */
    [data-testid="stDataFrame"] {
        background: #586179 !important;
        color: #10243d !important;
    }

    /* Native selectbox / input surfaces */
    [data-baseweb="select"] > div,
    [data-baseweb="input"],
    [data-baseweb="textarea"] {
        background: #586179 !important;
        color: #10243d !important;
        border-color: #9ab5d1 !important;
    }

    [data-baseweb="select"] *,
    [data-baseweb="input"] *,
    [data-baseweb="textarea"] * {
        color: #10243d !important;
        -webkit-text-fill-color: #10243d !important;
    }

    /* Dropdown menu */
    [role="listbox"],
    [role="option"] {
        background: #586179 !important;
        color: #10243d !important;
    }

    [role="option"] * {
        color: #10243d !important;
        -webkit-text-fill-color: #10243d !important;
    }

    /* Main page headings remain light because the page is navy */
    [data-testid="stAppViewContainer"] .hero-title,
    [data-testid="stAppViewContainer"] .hero-title *,
    [data-testid="stAppViewContainer"] .step-title {
        color: #586179 !important;
        -webkit-text-fill-color: #586179 !important;
    }

    /* Captions on navy background */
    [data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] {
        color: #586179 !important;
        -webkit-text-fill-color: #586179 !important;
    }


    /* Requested global text color */
    [data-testid="stAppViewContainer"] {
        color: #586179 !important;
    }

    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] span,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] h4,
    [data-testid="stAppViewContainer"] h5,
    [data-testid="stAppViewContainer"] h6,
    [data-testid="stAppViewContainer"] li,
    [data-testid="stAppViewContainer"] td,
    [data-testid="stAppViewContainer"] th {
        color: #586179 !important;
        -webkit-text-fill-color: #586179 !important;
    }

    /* Buttons also use the requested text color */
    .stButton > button,
    .stDownloadButton > button {
        color: #586179 !important;
        -webkit-text-fill-color: #586179 !important;
    }

    /* Code/log text */
    [data-testid="stCodeBlock"],
    [data-testid="stCodeBlock"] pre,
    [data-testid="stCodeBlock"] code,
    [data-testid="stCodeBlock"] * {
        color: #586179 !important;
        -webkit-text-fill-color: #586179 !important;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HELPERS
# ============================================================

# Heavy visualization/data packages are imported only when needed.
def get_pandas():
    import pandas as pd
    return pd


def get_plotly_go():
    import plotly.graph_objects as go
    return go



def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def format_bytes(value):
    if value is None:
        return "—"
    try:
        value = float(value)
    except Exception:
        return "—"

    if value < 1024:
        return f"{int(value)} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.2f} MB"
    return f"{value / (1024 * 1024 * 1024):.2f} GB"


def clear_previous_demo():
    """Clear old demo data before starting a new recovery case."""
    for folder in (ACTIVE_DIR, DELETED_DIR, RECOVERED_DIR):
        clear_folder(folder)

    try:
        if METADATA_FILE.exists():
            METADATA_FILE.unlink()
    except Exception:
        pass

    clear_folder(REPORTS_DIR)


def run_recovery():
    buffer = io.StringIO()
    try:
        # Lazy import: sentence-transformers and the AI pipeline are loaded
        # only when recovery is actually requested, not when Streamlit starts.
        from core.pipeline import run_pipeline

        with contextlib.redirect_stdout(buffer):
            result = run_pipeline()

        return result, buffer.getvalue(), None
    except Exception as exc:
        return None, buffer.getvalue(), exc



def _numeric_fragment_index(name):
    """Extract a fragment sequence number from common forensic filenames."""
    m = re.search(r"(?:fragment|frag|part|chunk|piece)[^\d]*(\d+)", str(name), re.I)
    if m:
        return int(m.group(1))
    # Fallback: use the last numeric group only when there is one.
    nums = re.findall(r"\d+", str(name))
    return int(nums[-1]) if len(nums) == 1 else None


def _external_fragment_statistics(uploaded_files, external):
    """Derive fragment counts from actual uploaded evidence, not guessed percentages."""
    names = [getattr(f, "name", str(f)) for f in (uploaded_files or [])]
    indexes = [_numeric_fragment_index(n) for n in names]
    indexes = [i for i in indexes if i is not None]

    relationships = external.get("relationships", []) or []
    used = int(external.get("fragments_used", 0) or 0)
    received = len(names)

    # If the filenames expose a sequence, identify actual gaps.
    missing_indices = []
    if indexes:
        lo, hi = min(indexes), max(indexes)
        expected = set(range(lo, hi + 1))
        missing_indices = sorted(expected - set(indexes))

    unresolved = int(external.get("unresolved_connections", 0) or 0)

    # Relationship graph gives an evidence-based connection rate.
    possible_connections = max(0, received - 1)
    connected = min(possible_connections, len(relationships))
    connection_rate = (
        connected / possible_connections * 100.0
        if possible_connections else 100.0
    )

    # Do not call missing fragments "corrupted". They are separate forensic states.
    corrupted = int(external.get("corrupted_fragments", 0) or 0)

    return {
        "fragments_received": received,
        "fragments_used": used,
        "missing_count": len(missing_indices),
        "missing_indices": missing_indices,
        "corrupted_count": corrupted,
        "relationship_count": len(relationships),
        "unresolved_connections": unresolved,
        "connection_rate": connection_rate,
    }


def analyze_external_recovery(mode, uploaded_files, external):
    """Build a forensic report from measurable recovery evidence."""
    original = uploaded_files[0].getvalue() if uploaded_files else b""
    output_path = Path(str(external.get("output_path", "")))
    recovered = output_path.read_bytes() if output_path.exists() else b""

    stats = _external_fragment_statistics(uploaded_files, external)

    report = {
        "original_filename": uploaded_files[0].name if uploaded_files else "Unknown",
        "file_type": "BINARY",
        "original_size": len(original),
        "recovered_size": len(recovered),
        "recovery_percentage": min(100.0, len(recovered) / max(1, len(original)) * 100.0),
        "integrity_score": 0.0,
        "recovery_confidence": 0.0,
        "priority_score": 0.0,
        "priority_level": "UNKNOWN",
        "missing_fragments": stats["missing_indices"],
        "missing_fragment_count": stats["missing_count"],
        "corrupted_fragments": stats["corrupted_count"],
        "corrupted_fragment_count": stats["corrupted_count"],
        "reconstruction_chain": external.get("chain", []),
        "recovered_file": external.get("output_path"),
        "recovered_path": external.get("output_path"),
        "output_path": external.get("output_path"),
        "external_recovery": external,
    }

    if mode == "Repair Corrupted File":
        report["file_type"] = (
            "JPEG" if original.startswith(b"\xff\xd8\xff")
            else mimetypes.guess_type(uploaded_files[0].name)[0] if uploaded_files else "BINARY"
        ) or "BINARY"

        report["valid_header"] = (
            original.startswith(b"\xff\xd8\xff")
            if report["file_type"] == "JPEG" else True
        )
        report["valid_eoi"] = (
            original.endswith(b"\xff\xd9")
            if report["file_type"] == "JPEG" else True
        )
        report["sha256_before"] = hashlib.sha256(original).hexdigest()
        report["sha256_after"] = hashlib.sha256(recovered).hexdigest() if recovered else "—"
        report["changed"] = recovered != original
        report["repair_status"] = external.get("repair_status", "UNKNOWN")
        report["repair_method"] = report["repair_status"]

        indicators = []
        report["pil_verified"] = False

        if report["file_type"] == "JPEG":
            if not report["valid_header"]:
                indicators.append("JPEG header is missing or invalid.")
            if not report["valid_eoi"]:
                indicators.append("JPEG end-of-image marker (FF D9) is missing.")

            try:
                from PIL import Image
                with Image.open(io.BytesIO(original)) as im:
                    im.verify()
                report["pil_verified"] = True
            except Exception as exc:
                indicators.append(f"JPEG decoder validation failed: {type(exc).__name__}")

        report["corruption_indicators"] = indicators
        report["damaged_regions"] = []

        if recovered:
            try:
                if report["file_type"] == "JPEG":
                    from PIL import Image
                    with Image.open(io.BytesIO(recovered)) as im:
                        im.verify()
                    report["recovered_validation"] = "VALID JPEG"
                else:
                    report["recovered_validation"] = "OUTPUT CREATED"
            except Exception as exc:
                report["recovered_validation"] = f"Validation failed: {type(exc).__name__}"
        else:
            report["recovered_validation"] = "OUTPUT NOT FOUND"

        # Honest integrity: a changed hash is not treated as 0%, but also not as 100%.
        if not recovered:
            integrity = 0.0
        elif report["file_type"] == "JPEG" and report["recovered_validation"] == "VALID JPEG":
            integrity = 100.0 if not indicators else 90.0
        else:
            integrity = 85.0

        report["integrity_score"] = integrity
        report["recovery_confidence"] = (
            95.0 if report["recovered_validation"] == "VALID JPEG" and not indicators
            else 80.0 if recovered else 0.0
        )
        report["priority_score"] = round(
            report["recovery_percentage"] * 0.35
            + report["integrity_score"] * 0.25
            + report["recovery_confidence"] * 0.40,
            2,
        )
        report["priority_level"] = (
            "HIGH" if report["priority_score"] >= 80
            else "MEDIUM" if report["priority_score"] >= 50
            else "LOW"
        )
        report["ai_analysis"] = {
            "status": "completed",
            "method": "Structural forensic analysis",
            "file_type": report["file_type"],
            "indicators": len(indicators),
        }

    else:
        relationships = external.get("relationships", []) or []
        report["file_type"] = (
            "JPEG" if recovered.startswith(b"\xff\xd8\xff") else
            mimetypes.guess_type(uploaded_files[0].name)[0] if uploaded_files else "BINARY"
        ) or "BINARY"

        report["relationships"] = relationships
        report["ai_analysis"] = {
            "model": external.get(
                "model",
                "sentence-transformers/all-MiniLM-L6-v2"
            ),
            "status": "completed",
            "relationships": len(relationships),
        }

        report["unresolved_connections"] = stats["unresolved_connections"]
        report["relationship_count"] = stats["relationship_count"]
        report["connection_rate"] = stats["connection_rate"]
        report["fragments_received"] = stats["fragments_received"]
        report["fragments_used"] = stats["fragments_used"]

        # Explicit fragment records for the UI.
        report["fragment_summary"] = {
            "total": stats["fragments_received"],
            "intact": max(0, stats["fragments_received"] - stats["missing_count"] - stats["corrupted_count"]),
            "corrupted": stats["corrupted_count"],
            "missing": stats["missing_count"],
            "suspicious": 0,
        }

        # For arbitrary uploaded fragments, missing count is only known when
        # a numeric sequence in the filenames exposes a gap.
        report["missing_fragment_details"] = [
            {"original_index": i, "status": "MISSING"}
            for i in stats["missing_indices"]
        ]

        # Integrity is based on measurable reconstruction evidence.
        if recovered and stats["missing_count"] == 0 and stats["unresolved_connections"] == 0:
            integrity = 100.0
        elif recovered:
            integrity = max(
                0.0,
                min(
                    99.0,
                    stats["connection_rate"]
                    - stats["missing_count"] * 10.0
                    - stats["corrupted_count"] * 12.0,
                ),
            )
        else:
            integrity = 0.0

        report["integrity_score"] = round(integrity, 2)

        # Confidence combines AI relationship evidence and reconstruction completeness.
        confidence = (
            stats["connection_rate"] * 0.55
            + (100.0 if stats["unresolved_connections"] == 0 else 50.0) * 0.25
            + (100.0 if stats["missing_count"] == 0 else max(0.0, 100.0 - stats["missing_count"] * 20.0)) * 0.20
        )
        report["recovery_confidence"] = round(max(0.0, min(100.0, confidence)), 2)

        report["repair_status"] = external.get("repair_status", "—")

        report["priority_score"] = round(
            report["recovery_percentage"] * 0.35
            + report["integrity_score"] * 0.25
            + report["recovery_confidence"] * 0.40,
            2,
        )
        report["priority_level"] = (
            "HIGH" if report["priority_score"] >= 80
            else "MEDIUM" if report["priority_score"] >= 50
            else "LOW"
        )

    return report

def get_recovered_path(report):
    if not report:
        return None

    recovered_file = (
        report.get("recovered_file")
        or report.get("recovered_path")
        or report.get("output_path")
    )

    if not recovered_file:
        reconstruction = report.get("reconstruction", {})
        if isinstance(reconstruction, dict):
            recovered_file = (
                reconstruction.get("recovered_file")
                or reconstruction.get("recovered_path")
                or reconstruction.get("output_path")
            )

    if not recovered_file:
        return None

    path = Path(str(recovered_file))
    if not path.is_absolute():
        path = BASE_DIR / path

    return path


def get_fragment_records(report=None):
    """Read fragment records from simulation metadata and normalize the schema."""
    metadata = load_json(METADATA_FILE)

    if not metadata:
        return []

    candidates = []

    def collect(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("fragment_records"), list):
                candidates.extend(obj["fragment_records"])
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    collect(value)
        elif isinstance(obj, list):
            for value in obj:
                collect(value)

    collect(metadata)

    normalized = []
    for i, record in enumerate(candidates):
        if not isinstance(record, dict):
            continue

        r = dict(record)
        name = (
            r.get("fragment_name")
            or r.get("filename")
            or r.get("name")
            or f"fragment_{i:04d}.bin"
        )
        r["fragment_name"] = str(name)

        if r.get("original_index") is None:
            idx = _numeric_fragment_index(name)
            r["original_index"] = idx if idx is not None else i

        status = str(r.get("status", "")).upper().strip()
        if not status:
            if r.get("missing") or r.get("deleted"):
                status = "MISSING" if r.get("missing") else "DELETED"
            elif r.get("corrupted"):
                status = "CORRUPTED"
            else:
                status = "INTACT"

        r["status"] = status
        r["corrupted"] = bool(r.get("corrupted")) or status == "CORRUPTED"
        r["missing"] = bool(r.get("missing")) or status == "MISSING"
        r["deleted"] = bool(r.get("deleted")) or status == "DELETED"
        normalized.append(r)

    normalized.sort(
        key=lambda x: (
            int(x.get("original_index"))
            if str(x.get("original_index", "")).isdigit()
            else 10**9
        )
    )
    return normalized

def fragment_status_table(report=None):
    pd = get_pandas()
    records = get_fragment_records(report)

    if not records:
        return None

    rows = []
    for record in records:
        status = str(record.get("status", "INTACT")).upper()

        rows.append({
            "Fragment": record.get("fragment_name", "Unknown"),
            "Original Position": record.get("original_index", "—"),
            "Byte Offset": record.get("start_position", record.get("offset", "—")),
            "Size": f"{record.get('size', 0)} B",
            "Status": status,
            "Corrupted": "YES" if record.get("corrupted") else "NO",
            "Deleted": "YES" if record.get("deleted") else "NO",
            "Missing": "YES" if record.get("missing") else "NO",
            "SHA-256": str(record.get("sha256", ""))[:16] + "…",
        })

    return pd.DataFrame(rows)

def threat_analysis(report=None):
    """
    Conservative demo-level threat assessment.

    A normal JPEG's high entropy is NOT treated as ransomware evidence.
    Ransomware is reported only when there are explicit indicators in
    the simulated evidence/metadata such as ransom-note files or
    suspicious encrypted extensions.
    """
    metadata = load_json(METADATA_FILE) or {}

    filename = str(report.get("original_filename", "") if report else "")
    lower_name = filename.lower()

    ransomware_extensions = {
        ".encrypted", ".locked", ".crypt", ".enc", ".wncry",
        ".locky", ".zepto", ".cerber", ".ryk", ".akira",
    }

    indicators = []
    ransomware_detected = False

    if any(lower_name.endswith(ext) for ext in ransomware_extensions):
        ransomware_detected = True
        indicators.append("Suspicious encrypted/locked file extension")

    for value in metadata.values() if isinstance(metadata, dict) else []:
        if not isinstance(value, dict):
            continue

        status = str(value.get("status", "")).lower()

        if status in {"ransomware", "encrypted_by_ransomware"}:
            ransomware_detected = True
            indicators.append("Simulation metadata marks ransomware activity")

    if ransomware_detected:
        verdict = "RANSOMWARE INDICATORS DETECTED"
    else:
        verdict = "NO RANSOMWARE INDICATORS DETECTED"

    return {
        "verdict": verdict,
        "indicators": indicators,
        "note": (
            "This prototype does not classify ordinary high-entropy JPEG "
            "data as ransomware. A real ransomware detector would require "
            "filesystem/process telemetry, ransom-note detection, and "
            "encrypted-file behavior analysis."
        ),
    }


def make_relationship_graph(relationships):
    if not relationships:
        return None

    go = get_plotly_go()
    nodes = []
    seen = set()

    for rel in relationships:
        for name in (rel.get("from"), rel.get("to")):
            if name and name not in seen:
                seen.add(name)
                nodes.append(name)

    if not nodes:
        return None

    positions = {name: i for i, name in enumerate(nodes)}

    fig = go.Figure()

    for rel in relationships[:150]:
        src = rel.get("from")
        dst = rel.get("to")

        if src not in positions or dst not in positions:
            continue

        confidence = float(rel.get("confidence", 0) or 0)

        fig.add_trace(
            go.Scatter(
                x=[positions[src], positions[dst]],
                y=[0, 0],
                mode="lines",
                line=dict(width=max(1, min(4, confidence / 30))),
                hoverinfo="text",
                text=[f"{src} → {dst}", f"Confidence: {confidence:.2f}%"],
                showlegend=False,
            )
        )

    labels = [name.replace(".bin", "") for name in nodes]

    fig.add_trace(
        go.Scatter(
            x=list(range(len(nodes))),
            y=[0] * len(nodes),
            mode="markers+text",
            marker=dict(size=28),
            text=labels,
            textposition="bottom center",
            hovertext=nodes,
            hoverinfo="text",
            showlegend=False,
        )
    )

    fig.update_layout(
        height=280,
        margin=dict(l=20, r=20, t=20, b=100),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">
        <div class="hero-title">🔐 RECON-AI</div>
        <div class="hero-subtitle">
            AI-Assisted Intelligent Data Recovery & Digital Evidence Reconstruction
        </div>
        <div class="hero-badge">CYBERSECURITY • AI • DIGITAL FORENSICS</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# MAIN WORKFLOW
# ============================================================

st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown('<div class="step-title">1. Select Evidence</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="muted">Analyze a damaged file or reconstruct an uploaded set of fragments.</div>',
    unsafe_allow_html=True,
)

recovery_mode = st.selectbox(
    "Recovery mode",
    [
        "Simulate Storage Damage",
        "Recover Multiple Fragments",
        "Repair Corrupted File",
    ],
    label_visibility="visible",
)

uploaded_files = st.file_uploader(
    "Evidence files / fragments",
    type=None,
    accept_multiple_files=True,
    label_visibility="collapsed",
    help="Upload one file for simulation/repair, or multiple fragments for reconstruction.",
)

if uploaded_files:
    st.success(
        f"Selected **{len(uploaded_files)} file(s)** • "
        + ", ".join(f.name for f in uploaded_files[:4])
        + (" …" if len(uploaded_files) > 4 else "")
    )

st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# ACTIONS
# ============================================================

col1, col2, col3 = st.columns([1, 1.15, 1])

with col1:
    simulate_clicked = st.button(
        "⚡ Prepare Evidence",
        use_container_width=True,
        disabled=not uploaded_files,
    )

with col2:
    recover_clicked = st.button(
        "🚀 Run AI Recovery",
        type="primary",
        use_container_width=True,
        disabled=not st.session_state.get("damage_ready", False),
    )

with col3:
    if st.button("🧹 Clear Current Case", use_container_width=True):
        clear_previous_demo()
        for key in (
            "damage_ready",
            "last_fragmentation",
            "last_report",
            "pipeline_logs",
        ):
            st.session_state.pop(key, None)
        st.rerun()


# ============================================================
# PREPARE EVIDENCE
# ============================================================

if simulate_clicked and uploaded_files:
    try:
        clear_previous_demo()

        if recovery_mode == "Simulate Storage Damage":
            uploaded = uploaded_files[0]
            destination = ACTIVE_DIR / Path(uploaded.name).name
            destination.write_bytes(uploaded.getvalue())

            result = create_damaged_fragments(destination)

            if result.get("success"):
                st.session_state["damage_ready"] = True
                st.session_state["recovery_mode"] = recovery_mode
                st.session_state["last_fragmentation"] = result
                st.session_state.pop("last_report", None)
                st.session_state.pop("external_recovery", None)
                st.session_state.pop("pipeline_logs", None)

                st.success(
                    f"Fragmentation complete — "
                    f"{result.get('total_fragments', result.get('available_fragments', 0))} "
                    f"fragments created and stored out-of-order."
                )
            else:
                st.session_state["damage_ready"] = False
                st.error(result.get("message", "Preparation failed."))

        elif recovery_mode == "Recover Multiple Fragments":
            # Copy uploaded fragments into a temporary forensic set.
            # The generalized recovery engine does not require simulation metadata.
            result = recover_uploaded_fragments(
                uploaded_files,
                RECOVERED_DIR,
            )

            st.session_state["damage_ready"] = bool(result.get("success"))
            st.session_state["recovery_mode"] = recovery_mode
            st.session_state["external_recovery"] = result
            st.session_state.pop("last_report", None)
            st.session_state.pop("pipeline_logs", None)

            if result.get("success"):
                st.success(
                    f"Fragment recovery prepared — "
                    f"{result.get('fragments_received', 0)} fragment(s) analyzed."
                )
            else:
                st.error(result.get("message", "Fragment recovery failed."))

        else:
            if len(uploaded_files) != 1:
                st.error("Corrupted-file repair requires exactly one file.")
                st.session_state["damage_ready"] = False
            else:
                temp_input = ACTIVE_DIR / Path(uploaded_files[0].name).name
                temp_input.write_bytes(uploaded_files[0].getvalue())

                result = repair_single_file(
                    temp_input,
                    RECOVERED_DIR,
                )

                st.session_state["damage_ready"] = bool(result.get("success"))
                st.session_state["recovery_mode"] = recovery_mode
                st.session_state["external_recovery"] = result
                st.session_state.pop("last_report", None)
                st.session_state.pop("pipeline_logs", None)

                if result.get("success"):
                    st.success("Best-effort corrupted-file repair completed.")
                else:
                    st.error(result.get("message", "File repair failed."))

    except Exception as exc:
        st.session_state["damage_ready"] = False
        st.error(f"Evidence preparation failed: {exc}")


# ============================================================
# RUN RECOVERY
# ============================================================

if recover_clicked:
    mode = st.session_state.get("recovery_mode", recovery_mode)

    if mode == "Simulate Storage Damage":
        with st.spinner("AI is analyzing fragments and reconstructing the evidence..."):
            result, logs, error = run_recovery()

        st.session_state["pipeline_logs"] = logs

        if error:
            st.session_state.pop("last_report", None)
            st.error(f"Recovery failed: {error}")
        elif result:
            st.session_state["last_report"] = result
            st.success("Recovery completed successfully.")
        else:
            st.warning("No recoverable fragments were found.")

    else:
        external = st.session_state.get("external_recovery")

        if external and external.get("success"):
            recovered_path = Path(external["output_path"])

            # Normalize the complete generalized-recovery result.
            report = analyze_external_recovery(
                mode,
                uploaded_files,
                external,
            )

            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            EVIDENCE_JSON.write_text(
                json.dumps(report, indent=2, default=str),
                encoding="utf-8",
            )

            st.session_state["last_report"] = report
            st.session_state["pipeline_logs"] = (
                "GENERALIZED RECOVERY ENGINE\n"
                "===========================\n"
                f"Mode: {mode}\n"
                f"Fragments received: {external.get('fragments_received', 1)}\n"
                f"Fragments used: {external.get('fragments_used', 1)}\n"
                f"Recovered size: {external.get('recovered_size', 0)} bytes\n"
                f"Repair: {external.get('repair_status', '—')}\n"
                f"SHA-256: {external.get('sha256', '—')}\n"
            )
            st.success("Recovery completed successfully.")
        else:
            st.error("No recovery data is available. Prepare the evidence first.")


# ============================================================
# LOAD RESULTS
# ============================================================

report = load_json(EVIDENCE_JSON)
ai_report = load_json(AI_REPORT)

if ai_report is None and report and report.get("relationships"):
    ai_report = {
        "model": report.get("ai_analysis", {}).get("model", "Exact-overlap forensic analysis"),
        "relationships": report.get("relationships", []),
    }

if report is None:
    report = st.session_state.get("last_report")

fragmentation = st.session_state.get("last_fragmentation")


# ============================================================
# RESULTS
# ============================================================

if report:

    st.markdown("---")
    st.subheader("📊 Recovery Results")

    recovery = float(report.get("recovery_percentage", 0) or 0)
    integrity = float(report.get("integrity_score", 0) or 0)
    confidence = float(report.get("recovery_confidence", 0) or 0)
    priority_score = float(report.get("priority_score", 0) or 0)
    priority_level = report.get("priority_level", "UNKNOWN")

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Recovery", f"{recovery:.2f}%")
    c2.metric("Integrity", f"{integrity:.2f}%")
    c3.metric("AI Confidence", f"{confidence:.2f}%")
    c4.metric("Priority Score", f"{priority_score:.2f}")
    c5.metric("Priority", str(priority_level))

    st.progress(min(max(recovery / 100, 0), 1))

    st.markdown(
        f"""
        <div class="result-banner">
            <b>Evidence:</b> {report.get('original_filename', 'Unknown')}
            &nbsp; • &nbsp;
            <b>Type:</b> {report.get('file_type', 'Unknown')}
            &nbsp; • &nbsp;
            <b>Original:</b> {format_bytes(report.get('original_size'))}
            &nbsp; • &nbsp;
            <b>Recovered:</b> {format_bytes(report.get('recovered_size'))}
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_results, tab_fragments, tab_ai, tab_damage, tab_threats, tab_evidence, tab_logs = st.tabs(
        [
            "Overview",
            "🧩 Fragments",
            "🤖 AI Analysis",
            "🛡️ Damage",
            "🚨 Threats",
            "📥 Recovered Evidence",
            "📋 Logs",
        ]
    )

    # --------------------------------------------------------
    # OVERVIEW
    # --------------------------------------------------------
    with tab_results:
        pd = get_pandas()
        st.markdown("### Reconstruction Summary")

        reconstruction = report.get("reconstruction", {})
        if isinstance(reconstruction, dict):
            chain = (
                report.get("reconstruction_chain")
                or reconstruction.get("chain")
                or reconstruction.get("fragment_chain")
                or []
            )
        else:
            chain = report.get("reconstruction_chain", [])

        if chain:
            st.write(f"**Fragments used:** {len(chain)}")

            # Do not create hundreds of Streamlit columns.
            preview_chain = chain[:12]
            chain_text = "  →  ".join(Path(str(x)).stem for x in preview_chain)

            if len(chain) > 12:
                chain_text += f"  →  …  →  {Path(str(chain[-1])).stem}"

            st.code(chain_text, language="text")
        else:
            st.info("No reconstruction chain available.")

        st.markdown("### Evidence Details")

        details = {
            "Original filename": report.get("original_filename", "Unknown"),
            "File type": report.get("file_type", "Unknown"),
            "Original size": format_bytes(report.get("original_size")),
            "Recovered size": format_bytes(report.get("recovered_size")),
            "Missing fragments": report.get("missing_fragments", 0),
            "Corrupted fragments": report.get("corrupted_fragments", 0),
        }

        st.dataframe(
            pd.DataFrame(
                {"Property": list(details.keys()), "Value": list(details.values())}
            ),
            use_container_width=True,
            hide_index=True,
        )

        if mode == "Repair Corrupted File":
            st.markdown("### 🔬 Corrupted File Forensic Analysis")
            validation = pd.DataFrame([
                {"Check": "JPEG Header", "Result": "VALID" if report.get("valid_header") else "INVALID"},
                {"Check": "EOI Marker", "Result": "VALID" if report.get("valid_eoi") else "MISSING"},
                {"Check": "Decoder Validation", "Result": "PASSED" if report.get("pil_verified") else "FAILED"},
                {"Check": "Recovered Output", "Result": report.get("recovered_validation", "UNKNOWN")},
                {"Check": "Bytes Changed", "Result": "YES" if report.get("changed") else "NO"},
                {"Check": "Repair Method", "Result": report.get("repair_method", "—")},
            ])
            st.dataframe(validation, use_container_width=True, hide_index=True)

            indicators = report.get("corruption_indicators", [])
            if indicators:
                for indicator in indicators:
                    st.warning(str(indicator))
            else:
                st.success("No structural corruption indicators were detected.")

            st.write(f"**Input SHA-256:** `{report.get('sha256_before', '—')}`")
            st.write(f"**Recovered SHA-256:** `{report.get('sha256_after', '—')}`")

    # --------------------------------------------------------
    # FRAGMENT BREAKDOWN
    # --------------------------------------------------------
    with tab_fragments:
        st.markdown("### 🧩 Original File → Storage Fragments")

        fragment_df = fragment_status_table(report)

        if fragment_df is not None and not fragment_df.empty:
            records = get_fragment_records(report)

            total = len(records)
            intact = sum(1 for r in records if str(r.get("status", "")).upper() == "INTACT")
            corrupted = sum(
                1 for r in records
                if bool(r.get("corrupted")) or str(r.get("status", "")).upper() == "CORRUPTED"
            )
            deleted = sum(
                1 for r in records
                if str(r.get("status", "")).upper() in {"DELETED", "MISSING"}
                or bool(r.get("deleted")) or bool(r.get("missing"))
            )
            suspicious = sum(
                1 for r in records
                if str(r.get("status", "")).upper() == "SUSPICIOUS"
            )

            # Use the report's explicit counts when metadata contains only
            # currently present fragments.
            summary = report.get("fragment_summary", {}) if isinstance(report, dict) else {}
            if total == 0 and summary:
                total = int(summary.get("total", 0) or 0)
                intact = int(summary.get("intact", 0) or 0)
                corrupted = int(summary.get("corrupted", 0) or 0)
                deleted = int(summary.get("missing", 0) or 0)
                suspicious = int(summary.get("suspicious", 0) or 0)

            f1, f2, f3, f4, f5 = st.columns(5)
            f1.metric("Total", total)
            f2.metric("Intact", intact)
            f3.metric("Corrupted", corrupted)
            f4.metric("Deleted / Missing", deleted)
            f5.metric("Suspicious", suspicious)

            st.progress(intact / total if total else 0)

            st.caption(
                "The original file is split into overlapping fragments. "
                "The table below shows where each fragment belongs in the original file."
            )

            # Visual fragment map
            st.markdown("#### Fragment Map")
            status_colors = {
                "INTACT": "#22c55e",
                "CORRUPTED": "#ef4444",
                "DELETED": "#f59e0b",
                "MISSING": "#f59e0b",
                "SUSPICIOUS": "#a855f7",
            }

            blocks = []
            for record in records:
                status = str(record.get("status", "INTACT")).upper()
                color = status_colors.get(status, "#64748b")
                idx = record.get("original_index", "?")
                blocks.append(
                    f'<span title="Fragment {idx}: {status}" '
                    f'style="display:inline-block;width:10px;height:28px;'
                    f'margin:2px;border-radius:3px;background:{color};"></span>'
                )

            st.markdown(
                '<div style="padding:10px;border-radius:12px;'
                'background:rgba(2,12,27,.55);border:1px solid rgba(56,189,248,.12);'
                'line-height:34px;">' + ''.join(blocks) + '</div>',
                unsafe_allow_html=True,
            )

            st.dataframe(
                fragment_df,
                use_container_width=True,
                hide_index=True,
                height=460,
            )

            st.markdown("#### Fragment status legend")
            st.markdown(
                """
                - 🟢 **INTACT** — fragment bytes are unchanged
                - 🔴 **CORRUPTED** — fragment bytes are known/simulated as altered
                - 🟠 **MISSING** — expected fragment is absent
                - ⚫ **DELETED** — fragment was removed from simulated storage
                - 🟡 **SUSPICIOUS** — fragment requires additional forensic review
                """
            )
        elif report.get("external_recovery", {}).get("fragments_received"):
            ext = report.get("external_recovery", {})
            st.markdown("### Uploaded Fragment Analysis")
            summary = report.get("fragment_summary", {}) if isinstance(report, dict) else {}
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total", summary.get("total", ext.get("fragments_received", 0)))
            c2.metric("Intact", summary.get("intact", 0))
            c3.metric("Corrupted", summary.get("corrupted", 0))
            c4.metric("Missing", summary.get("missing", 0))
            c5.metric("Relationships", len(ext.get("relationships", [])))

            st.caption(
                f"Used: {ext.get('fragments_used', 0)} • "
                f"Unresolved connections: {ext.get('unresolved_connections', 0)} • "
                f"Connection rate: {report.get('connection_rate', 0):.1f}%"
            )

            if ext.get("relationships"):
                st.dataframe(
                    pd.DataFrame(ext["relationships"]),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.warning("No fragment overlap relationships were detected.")
        else:
            st.info(
                "Fragment details will appear after you simulate damage or upload fragments."
            )

    # --------------------------------------------------------
    # AI ANALYSIS
    # --------------------------------------------------------
    with tab_ai:
        pd = get_pandas()
        st.markdown("### 🤖 AI Fragment Relationship Analysis")

        if ai_report:
            relationships = (
                ai_report.get("relationships")
                if isinstance(ai_report, dict)
                else ai_report
            )

            if relationships:
                st.caption(
                    f"Transformer model: "
                    f"{ai_report.get('model', 'sentence-transformers/all-MiniLM-L6-v2')}"
                    if isinstance(ai_report, dict)
                    else "Transformer-based fragment analysis"
                )

                df = pd.DataFrame(relationships)

                display_columns = [
                    c
                    for c in [
                        "from",
                        "to",
                        "overlap",
                        "ml_confidence",
                        "heuristic_confidence",
                        "confidence",
                    ]
                    if c in df.columns
                ]

                if display_columns:
                    shown = df[display_columns].copy()

                    rename = {
                        "from": "Fragment A",
                        "to": "Fragment B",
                        "overlap": "Overlap (bytes)",
                        "ml_confidence": "AI Confidence",
                        "heuristic_confidence": "Structural Confidence",
                        "confidence": "Combined Confidence",
                    }

                    shown = shown.rename(columns=rename)

                    for col in [
                        "AI Confidence",
                        "Structural Confidence",
                        "Combined Confidence",
                    ]:
                        if col in shown.columns:
                            shown[col] = shown[col].map(
                                lambda x: f"{float(x):.2f}%"
                            )

                    st.dataframe(
                        shown.head(100),
                        use_container_width=True,
                        hide_index=True,
                    )

                graph = make_relationship_graph(relationships)

                if graph:
                    st.plotly_chart(graph, use_container_width=True)
            else:
                st.info("No AI relationships detected.")
        else:
            st.info("AI results will appear here after recovery.")

    # --------------------------------------------------------
    # DAMAGE
    # --------------------------------------------------------
    with tab_damage:
        pd = get_pandas()
        st.markdown("### 🛡️ Damage & Corruption Analysis")

        damage = report.get("damage_analysis", {})

        if isinstance(damage, dict) and damage:
            damage_types = damage.get("damage_types", [])
            severity = damage.get("severity", damage.get("damage_severity", "UNKNOWN"))

            if isinstance(damage_types, list):
                damage_text = ", ".join(map(str, damage_types)) or "No damage types reported"
            else:
                damage_text = str(damage_types)

            st.markdown(
                f"""
                <div class="result-banner">
                    <b>Severity:</b> {severity}<br>
                    <b>Detected damage:</b> {damage_text}
                </div>
                """,
                unsafe_allow_html=True,
            )

            damage_rows = []
            for key, value in damage.items():
                if key in ("damage_types",):
                    continue
                if isinstance(value, (str, int, float, bool)):
                    damage_rows.append({"Metric": key, "Value": value})

            if damage_rows:
                st.dataframe(
                    pd.DataFrame(damage_rows),
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.info("No damage analysis was included in the evidence report.")

        try:
            fragments = scan_storage(DELETED_DIR)

            if fragments:
                st.markdown("### Fragment Storage")

                fragment_df = pd.DataFrame(
                    [
                        {
                            "Fragment": f.get("filename"),
                            "Size": f"{f.get('size', 0)} B",
                            "Entropy": round(
                                float(f.get("entropy", 0) or 0), 3
                            ),
                            "Printable": (
                                f"{float(f.get('printable_ratio', 0) or 0) * 100:.1f}%"
                            ),
                            "Signature": f.get("signature", "UNKNOWN"),
                        }
                        for f in fragments
                    ]
                )

                st.dataframe(
                    fragment_df,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No damaged fragments currently present.")
        except Exception as exc:
            st.warning(f"Could not scan damaged storage: {exc}")

    # --------------------------------------------------------
    # THREAT ANALYSIS
    # --------------------------------------------------------
    with tab_threats:
        st.markdown("### 🚨 Malware & Ransomware Indicators")

        threat = threat_analysis(report)

        if threat["verdict"] == "RANSOMWARE INDICATORS DETECTED":
            st.error("🔴 " + threat["verdict"])
        else:
            st.success("🟢 " + threat["verdict"])

        if threat["indicators"]:
            st.markdown("**Indicators:**")
            for indicator in threat["indicators"]:
                st.write(f"• {indicator}")
        else:
            st.write("No explicit ransomware indicators were found in this simulation.")


        st.markdown("### Other forensic indicators")

        records = get_fragment_records(report)
        if records:
            suspicious = [
                r for r in records
                if str(r.get("status", "")).upper() == "SUSPICIOUS"
            ]
            corrupted = [
                r for r in records
                if bool(r.get("corrupted"))
                or str(r.get("status", "")).upper() == "CORRUPTED"
            ]

            a, b, c = st.columns(3)
            a.metric("Suspicious fragments", len(suspicious))
            b.metric("Corrupted fragments", len(corrupted))
            c.metric("Missing fragments", report.get("missing_fragment_count", report.get("missing_fragments", 0) if isinstance(report.get("missing_fragments", 0), int) else len(report.get("missing_fragments", []) or [])))


    # --------------------------------------------------------
    # RECOVERED EVIDENCE
    # --------------------------------------------------------
    with tab_evidence:
        st.markdown("### 📥 Recovered Evidence")

        recovered_path = get_recovered_path(report)

        if recovered_path and recovered_path.exists():
            file_bytes = recovered_path.read_bytes()
            recovered_hash = sha256_file(recovered_path)
            mime = mimetypes.guess_type(recovered_path.name)[0] or "application/octet-stream"

            st.markdown(
                f"""
                <div class="download-card">
                    <div style="font-size:1.08rem;margin-bottom:8px;color:#586179;font-weight:800;">
                        RESTORED EVIDENCE
                    </div>
                    <div style="margin:7px 0;">
                        <span style="color:#586179;">File:</span>
                        <span style="color:#586179;font-weight:750;"> {recovered_path.name}</span>
                    </div>
                    <div style="margin:7px 0;">
                        <span style="color:#586179;">Size:</span>
                        <span style="color:#586179;font-weight:750;"> {format_bytes(len(file_bytes))}</span>
                    </div>
                    <div style="margin:7px 0;">
                        <span style="color:#586179;">SHA-256:</span><br>
                        <code>{recovered_hash}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.download_button(
                "⬇️ DOWNLOAD RESTORED FILE",
                data=file_bytes,
                file_name=recovered_path.name,
                mime=mime,
                type="primary",
                use_container_width=True,
            )

            st.success(
                "The restored evidence is ready. Click the button above to save it directly."
            )

            # Preview images only if the recovered bytes are actually
            # a valid image. A damaged/reconstructed JPEG may still have
            # a .jpg extension but contain incomplete or corrupted bytes.
            if mime.startswith("image/"):
                try:
                    from PIL import Image, UnidentifiedImageError
                    from io import BytesIO

                    with Image.open(BytesIO(file_bytes)) as preview_image:
                        preview_image.verify()

                    # Re-open after verify because verify() consumes the stream.
                    with Image.open(BytesIO(file_bytes)) as preview_image:
                        st.image(
                            preview_image,
                            caption="Recovered image preview",
                            use_container_width=True,
                        )

                except (UnidentifiedImageError, OSError, ValueError):
                    st.warning(
                        "The recovered file is classified as an image, "
                        "but the reconstructed bytes are incomplete or corrupted, "
                        "so an image preview is not available."
                    )
                    st.info(
                        "You can still download the restored file below for "
                        "further forensic inspection."
                    )

            # Preview text files.
            elif mime.startswith("text/"):
                try:
                    text_preview = file_bytes.decode("utf-8", errors="replace")
                    st.text_area(
                        "Recovered content preview",
                        value=text_preview,
                        height=300,
                    )
                except Exception:
                    pass

        else:
            st.warning("Recovered file was not found on disk.")

        st.markdown("### Evidence Reports")

        r1, r2 = st.columns(2)

        with r1:
            if EVIDENCE_JSON.exists():
                st.download_button(
                    "⬇️ JSON Evidence Report",
                    data=EVIDENCE_JSON.read_bytes(),
                    file_name=EVIDENCE_JSON.name,
                    mime="application/json",
                    use_container_width=True,
                )

        with r2:
            if EVIDENCE_TXT.exists():
                st.download_button(
                    "⬇️ Text Evidence Report",
                    data=EVIDENCE_TXT.read_bytes(),
                    file_name=EVIDENCE_TXT.name,
                    mime="text/plain",
                    use_container_width=True,
                )

    # --------------------------------------------------------
    # LOGS
    # --------------------------------------------------------
    with tab_logs:
        st.markdown("### 📋 Pipeline Execution Log")

        logs = st.session_state.get("pipeline_logs", "")

        if logs:
            st.code(logs, language="text")
        else:
            st.caption("No execution log available.")


# ============================================================
# EMPTY STATE
# ============================================================

else:
    st.markdown("---")

    st.markdown(
        """
        <div class="card">
            <div class="step-title">How it works</div>
            <ol>
                <li>Upload an evidence file.</li>
                <li>Simulate deletion, fragmentation and corruption.</li>
                <li>Run the AI-assisted recovery pipeline.</li>
                <li>Inspect damage, AI relationships and reconstruction.</li>
                <li>Download the restored file directly.</li>
            </ol>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.markdown(
    """
    <div style="
        text-align:center;
        padding:18px 10px 8px 10px;
        color:#7891b0;
        font-size:0.82rem;
        letter-spacing:0.02em;
    ">
        <span style="color:#38bdf8;font-weight:700;">RECON-AI</span>
        &nbsp;•&nbsp; Intelligent Digital Evidence Recovery
    </div>
    """,
    unsafe_allow_html=True,
)
