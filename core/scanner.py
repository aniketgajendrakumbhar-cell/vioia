from pathlib import Path
from core.fragment_analyzer import analyze_fragment


def scan_storage(storage_directory):

    storage_directory = Path(storage_directory)

    if not storage_directory.exists():
        return []

    fragments = []

    for file_path in storage_directory.iterdir():

        if not file_path.is_file():
            continue

        analysis = analyze_fragment(file_path)

        fragments.append(analysis)

    return fragments


def print_scan_results(results):

    print()
    print("=" * 80)
    print("              RECON-AI STORAGE SCAN")
    print("=" * 80)

    if not results:

        print("No recoverable fragments found.")

        return

    print(
        f"{'Fragment':<45}"
        f"{'Size':>8}"
        f"{'Entropy':>12}"
        f"{'Printable':>14}"
    )

    print("-" * 80)

    for fragment in results:

        print(
            f"{fragment['filename']:<45}"
            f"{fragment['size']:>8}"
            f"{fragment['entropy']:>12.2f}"
            f"{fragment['printable_ratio'] * 100:>12.1f}%"
        )

    print("-" * 80)

    print(
        f"Fragments detected: {len(results)}"
    )


if __name__ == "__main__":

    storage_path = Path(
        "lab/deleted_storage"
    )

    results = scan_storage(
        storage_path
    )

    print_scan_results(results)