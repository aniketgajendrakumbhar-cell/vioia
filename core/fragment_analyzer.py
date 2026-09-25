from pathlib import Path
import hashlib
import math


# ============================================================
# FRAGMENT ANALYZER
# ============================================================

def calculate_sha256(data):

    return hashlib.sha256(data).hexdigest()


def calculate_entropy(data):

    if not data:
        return 0.0

    frequency = {}

    for byte in data:
        frequency[byte] = frequency.get(byte, 0) + 1

    entropy = 0.0

    data_length = len(data)

    for count in frequency.values():

        probability = count / data_length

        entropy -= probability * math.log2(
            probability
        )

    return entropy


def printable_ratio(data):

    if not data:
        return 0.0

    printable = sum(
        1
        for byte in data
        if 32 <= byte <= 126
        or byte in (9, 10, 13)
    )

    return printable / len(data)


def detect_file_signature(data):

    signatures = {

        b"%PDF":
            "PDF",

        b"\xFF\xD8\xFF":
            "JPEG",

        b"\x89PNG\r\n\x1a\n":
            "PNG",

        b"GIF87a":
            "GIF",

        b"GIF89a":
            "GIF",

        b"PK\x03\x04":
            "ZIP",

        b"RIFF":
            "RIFF"

    }

    for signature, file_type in signatures.items():

        if data.startswith(signature):

            return file_type

    return "Unknown"


def analyze_fragment(file_path):
    
    file_path = Path(file_path)

    data = file_path.read_bytes()

    return {

        "filename":
            file_path.name,

        "size":
            len(data),

        "sha256":
            calculate_sha256(data),

        "entropy":
            round(
                calculate_entropy(data),
                4
            ),

        "printable_ratio":
            round(
                printable_ratio(data),
                4
            ),

        "file_signature":
            detect_file_signature(data)

    }


def analyze_directory(directory):

    directory = Path(directory)

    results = []

    for file in directory.iterdir():

        if not file.is_file():
            continue

        results.append(
            analyze_fragment(file)
        )

    return results