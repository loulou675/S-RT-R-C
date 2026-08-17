"""Create portable ZIP64 handoff bundles for ignored AI training assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT.parent / "SORT_RAC_TEAMMATE_HANDOFF"
SKIP_NAMES = {".DS_Store", ".cache", "__pycache__"}

CORE_PATHS = [
    "training/classifier_dataset",
    "training/condition_dataset",
    "training/checkpoints/waste_classifier.pt",
    "training/checkpoints/waste_classifier_36_seed.pt",
    "training/classes.json",
    "training/requirements-training.txt",
    "training/source_manifests",
    "training/README.md",
    "training/PHOTO_COLLECTION_CHECKLIST.md",
    "training/train_and_export.py",
    "training/evaluate_per_class.py",
    "training/evaluate_acceptance.py",
    "training/validate_dataset.py",
    "training/verify_teammate_setup.py",
    "public/models/waste_classifier.onnx",
    "public/models/labels.json",
    "public/models/MODEL_CARD.md",
    "yolo26n-cls.pt",
]

COMPONENT_PATHS = [
    "training/component_dataset",
    "training/checkpoints/component_detector.pt",
    "training/component_classes.json",
    "training/real_component_annotations.json",
    "training/train_component_detector.py",
    "training/import_real_component_images.py",
    "training/oversample_component_class.py",
    "training/verify_teammate_setup.py",
    "public/models/waste_components.onnx",
    "public/models/component_labels.json",
    "public/models/COMPONENT_MODEL_CARD.md",
    "yolo26n.pt",
]


def included_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    missing: list[str] = []
    for relative in paths:
        path = ROOT / relative
        if not path.exists():
            missing.append(relative)
            continue
        if path.is_file():
            files.append(path)
            continue
        files.extend(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file() and not any(part in SKIP_NAMES for part in candidate.parts)
        )
    if missing:
        raise SystemExit("Missing required bundle paths:\n- " + "\n- ".join(missing))
    return sorted(set(files))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_bundle(output: Path, label: str, paths: list[str]) -> dict[str, object]:
    files = included_files(paths)
    total_bytes = sum(path.stat().st_size for path in files)
    info = {
        "bundle": label,
        "files": len(files),
        "uncompressedBytes": total_bytes,
        "extractAt": "Repository root (the folder containing package.json)",
        "verify": "python3 training/verify_teammate_setup.py"
        + (" --with-components" if label == "parts" else ""),
    }
    print(f"Creating {output.name}: {len(files)} files, {total_bytes / 1024 / 1024:.1f} MiB")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.writestr("TEAMMATE_BUNDLE_INFO.json", json.dumps(info, indent=2) + "\n")
        for index, path in enumerate(files, start=1):
            archive.write(path, path.relative_to(ROOT).as_posix())
            if index % 500 == 0 or index == len(files):
                print(f"  {index}/{len(files)} files")
    info["archive"] = output.name
    info["archiveBytes"] = output.stat().st_size
    info["sha256"] = sha256(output)
    return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args()

    output_dir = args.output.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    guide = ROOT / "training" / "TEAMMATE_SETUP.md"
    (output_dir / "START_HERE.md").write_text(guide.read_text(encoding="utf-8"), encoding="utf-8")
    bundles = [
        create_bundle(output_dir / "SORT_RAC_AI_CORE_36CLASS.zip", "core-36-class", CORE_PATHS)
    ]
    if not args.core_only:
        bundles.append(
            create_bundle(output_dir / "SORT_RAC_AI_PARTS.zip", "parts", COMPONENT_PATHS)
        )

    manifest = {
        "project": "SORT RAC",
        "guide": "START_HERE.md",
        "instructions": "Extract the ZIP files at the repository root, then run the verify command.",
        "bundles": bundles,
    }
    manifest_path = output_dir / "SHA256SUMS.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nHandoff ready: {output_dir}")
    print(f"Checksums: {manifest_path}")


if __name__ == "__main__":
    main()
