from pathlib import Path


# ============================================================
# RECON-AI FILE CLASSIFICATION ENGINE
# ============================================================


SIGNATURES = {
    b"%PDF": "PDF",
    b"\xFF\xD8\xFF": "JPEG",
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"GIF87a": "GIF",
    b"GIF89a": "GIF",
    b"PK\x03\x04": "ZIP",
    b"RIFF": "RIFF"
}


# ============================================================
# SIGNATURE CLASSIFICATION
# ============================================================

def classify_by_signature(data):

    for signature, file_type in SIGNATURES.items():

        if data.startswith(signature):

            return file_type

    return None


# ============================================================
# TEXT DETECTION
# ============================================================

def calculate_printable_ratio(data):

    if not data:
        return 0.0

    printable = sum(
        1
        for byte in data
        if 32 <= byte <= 126
        or byte in (9, 10, 13)
    )

    return printable / len(data)


def classify_as_text(data):

    if not data:
        return False

    printable_ratio = (
        calculate_printable_ratio(data)
    )

    return printable_ratio >= 0.85


# ============================================================
# FILE CLASSIFICATION
# ============================================================

def classify_file(file_path):

    file_path = Path(file_path)

    if not file_path.exists():

        return {
            "success": False,
            "message": "File not found."
        }

    data = file_path.read_bytes()

    signature_type = classify_by_signature(
        data
    )

    if signature_type:

        file_type = signature_type
        confidence = 0.98

    elif classify_as_text(data):

        file_type = "TEXT"
        confidence = (
            calculate_printable_ratio(data)
        )

    else:

        file_type = "UNKNOWN"
        confidence = 0.30

    extension = file_path.suffix.lower()

    return {

        "success": True,

        "filename":
            file_path.name,

        "extension":
            extension,

        "file_type":
            file_type,

        "confidence":
            round(
                confidence * 100,
                2
            ),

        "size":
            len(data),

        "printable_ratio":
            round(
                calculate_printable_ratio(data) * 100,
                2
            )

    }


# ============================================================
# DISPLAY RESULT
# ============================================================

def print_classification(
    result
):

    print()

    print("=" * 80)

    print(
        "                 RECON-AI FILE CLASSIFICATION"
    )

    print("=" * 80)

    if not result["success"]:

        print(
            result["message"]
        )

        return

    print(
        f"Filename            : "
        f"{result['filename']}"
    )

    print(
        f"Detected type       : "
        f"{result['file_type']}"
    )

    print(
        f"Extension            : "
        f"{result['extension']}"
    )

    print(
        f"Classification confidence: "
        f"{result['confidence']:.2f}%"
    )

    print(
        f"Printable content   : "
        f"{result['printable_ratio']:.2f}%"
    )

    print("=" * 80)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    recovered_file = Path(
        "lab/recovered/"
        "reconstructed_test_evidence.txt"
    )

    result = classify_file(
        recovered_file
    )

    print_classification(
        result
    )
    