"""Report missing, undersized and duplicate classification data before training."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "training" / "dataset")
    parser.add_argument("--minimum", type=int, default=300, help="Recommended minimum images per class across all splits")
    args = parser.parse_args()

    classes = json.loads((ROOT / "training" / "classes.json").read_text(encoding="utf-8"))["classes"]
    hashes: dict[str, list[tuple[str, str, Path]]] = defaultdict(list)
    has_problem = False

    print(f"Dataset: {args.data}")
    print(f"Classes: {len(classes)}\n")
    for class_name in classes:
        counts = {}
        for split in ("train", "val", "test"):
            folder = args.data / split / class_name
            files = sorted(path for path in folder.glob("**/*") if path.suffix.lower() in IMAGE_EXTENSIONS) if folder.exists() else []
            counts[split] = len(files)
            for path in files:
                hashes[file_hash(path)].append((split, class_name, path))

        total = sum(counts.values())
        marker = "OK" if total >= args.minimum and counts["val"] and counts["test"] else "CHECK"
        if marker == "CHECK":
            has_problem = True
        print(f"{marker:5} {class_name:28} train={counts['train']:4} val={counts['val']:3} test={counts['test']:3} total={total:4}")

    leaked = [locations for locations in hashes.values() if len({split for split, _, _ in locations}) > 1]
    if leaked:
        has_problem = True
        print(f"\nCHECK: {len(leaked)} exact duplicate images appear in more than one split.")
        for locations in leaked[:10]:
            print("  " + " | ".join(str(path.relative_to(args.data)) for _, _, path in locations))

    if has_problem:
        raise SystemExit("\nDataset is not ready. Fix CHECK rows and split leakage before training.")
    print("\nDataset checks passed.")


if __name__ == "__main__":
    main()
