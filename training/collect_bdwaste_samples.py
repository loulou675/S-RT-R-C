"""Sample real field photos from the CC BY 4.0 BDWaste dataset.

Only a few images are read from each category archive; the large archives are
removed after sampling so they never become part of the project workspace.
"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "training" / "dataset" / "train"
SOURCES_PATH = ROOT / "training" / "bdwaste-sources.jsonl"
API_ROOT = "https://data.mendeley.com/public-api/datasets/96g5pgfnfw"
DOI = "https://doi.org/10.17632/96g5pgfnfw.1"
USER_AGENT = "sort-rac-local-bdwaste-sampler/1.0 (single-item research prototype)"

# Archive name -> target class. The coffee-cup archive is a review bucket:
# retain only paper/disposable cups during manual review.
ARCHIVES = {
    "Banana peel.zip": "fruit_peel",
    "Lemon Peel.zip": "fruit_peel",
    "Mango Peel.zip": "fruit_peel",
    "Coffee  cup.zip": "paper_cup",
}


def file_catalog() -> dict[str, dict]:
    folders = requests.get(f"{API_ROOT}/folders/1", headers={"User-Agent": USER_AGENT}, timeout=30).json()
    digestive = next(folder["id"] for folder in folders if folder["name"] == "Digestive")
    rows = requests.get(
        f"{API_ROOT}/files", params={"folder_id": digestive, "version": 1},
        headers={"User-Agent": USER_AGENT}, timeout=30,
    ).json()
    return {row["filename"]: row for row in rows}


def main() -> None:
    catalog = file_catalog()
    seen_names = {path.name for class_name in set(ARCHIVES.values()) for path in (DATASET_ROOT / class_name).glob("bdwaste_field_*.jpg")}
    with SOURCES_PATH.open("a", encoding="utf-8") as log:
        for archive_name, target_class in ARCHIVES.items():
            row = catalog.get(archive_name)
            if not row:
                print(f"missing archive: {archive_name}")
                continue
            download_url = row["content_details"]["download_url"]
            destination = DATASET_ROOT / target_class
            destination.mkdir(parents=True, exist_ok=True)
            existing = len(list(destination.glob("bdwaste_field_*.jpg")))
            needed = max(0, 12 - existing) if target_class == "fruit_peel" else max(0, 10 - existing)
            if not needed:
                continue
            print(f"Downloading {archive_name} ({row['content_details']['size'] / 1_000_000:.0f} MB)", flush=True)
            with tempfile.NamedTemporaryFile(suffix=".zip") as temporary:
                response = requests.get(
                    download_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=30,
                    allow_redirects=False,
                )
                if response.status_code in {301, 302, 303, 307, 308}:
                    response = requests.get(
                        response.headers["Location"],
                        headers={"User-Agent": USER_AGENT},
                        timeout=(30, 60),
                        stream=True,
                    )
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        temporary.write(chunk)
                temporary.flush()
                with zipfile.ZipFile(temporary.name) as archive:
                    added = 0
                    for member in archive.infolist():
                        if added >= needed or member.is_dir() or Path(member.filename).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                            continue
                        try:
                            image = Image.open(io.BytesIO(archive.read(member))).convert("RGB")
                            if min(image.size) < 224:
                                continue
                        except Exception:  # noqa: BLE001 - skip a damaged archive member
                            continue
                        safe = archive_name.lower().replace(" ", "_").replace(".zip", "")
                        output = destination / f"bdwaste_field_{safe}_{existing + added:03d}.jpg"
                        if output.name in seen_names:
                            continue
                        image.save(output, format="JPEG", quality=92, optimize=True)
                        log.write(json.dumps({
                            "class": target_class,
                            "local_file": str(output.relative_to(ROOT)),
                            "dataset": "BDWaste",
                            "dataset_doi": DOI,
                            "archive": archive_name,
                            "license": "CC BY 4.0",
                            "license_url": "https://creativecommons.org/licenses/by/4.0/",
                            "source_file": member.filename,
                        }, ensure_ascii=False) + "\n")
                        log.flush()
                        seen_names.add(output.name)
                        added += 1
                        print(f"  added {output.name}", flush=True)
            print(f"{archive_name}: added {added} review candidates", flush=True)


if __name__ == "__main__":
    main()
