"""Add curated single-object examples from the TrashNet dataset.

TrashNet photographs one item per image on a simple background. We use only
the unambiguous source folders here: cardboard -> cardboard_box, metal ->
aluminium_drink_can, and glass/paper/trash -> unknown. Plastic is intentionally
not copied because its broad material label cannot reliably distinguish the
app's bottle and takeaway-cup classes.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "training" / "dataset" / "train"
SOURCES_PATH = ROOT / "training" / "trashnet-sources.jsonl"
DATASET_URL = "https://huggingface.co/datasets/garythung/trashnet/resolve/main/dataset-resized.zip?download=true"
USER_AGENT = "sort-rac-local-dataset-collector/1.0"

SOURCE_TO_APP = {
    "cardboard": "cardboard_box",
    "metal": "aluminium_drink_can",
    "glass": "unknown",
    "paper": "unknown",
    "trash": "unknown",
}
IMAGES_PER_SOURCE_CLASS = 30


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sort-rac-trashnet-") as temp_dir:
        archive = Path(temp_dir) / "dataset-resized.zip"
        print("downloading TrashNet single-item archive...")
        with requests.get(DATASET_URL, headers={"User-Agent": USER_AGENT}, stream=True, timeout=120) as response:
            response.raise_for_status()
            with archive.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)

        with zipfile.ZipFile(archive) as zipped, SOURCES_PATH.open("a", encoding="utf-8") as source_file:
            names = sorted(
                name
                for name in zipped.namelist()
                if name.lower().endswith(('.jpg', '.jpeg', '.png'))
                and "__MACOSX" not in name
                and not Path(name).name.startswith("._")
            )
            counts: dict[str, int] = {}

            for name in names:
                parts = Path(name).parts
                source_class = next((part for part in parts if part in SOURCE_TO_APP), None)
                if source_class is None or counts.get(source_class, 0) >= IMAGES_PER_SOURCE_CLASS:
                    continue

                app_class = SOURCE_TO_APP[source_class]
                destination = DATASET_ROOT / app_class
                destination.mkdir(parents=True, exist_ok=True)
                output = destination / f"trashnet_{source_class}_{counts.get(source_class, 0):03d}.jpg"
                if output.exists():
                    counts[source_class] = counts.get(source_class, 0) + 1
                    continue

                with zipped.open(name) as source_file_handle:
                    image = Image.open(source_file_handle).convert("RGB")
                if min(image.size) < 128:
                    continue
                image.save(output, format="JPEG", quality=92, optimize=True)

                source_file.write(
                    json.dumps(
                        {
                            "source_class": source_class,
                            "class": app_class,
                            "local_file": str(output.relative_to(ROOT)),
                            "source_repository": "https://github.com/garythung/trashnet",
                            "dataset_page": "https://huggingface.co/datasets/garythung/trashnet",
                            "license": "MIT",
                            "license_note": "Single-item source images; retain the upstream copyright notice for redistribution.",
                        }
                    )
                    + "\n"
                )
                counts[source_class] = counts.get(source_class, 0) + 1

            print("added:", counts)


if __name__ == "__main__":
    main()
