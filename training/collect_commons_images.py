"""Collect a small, license-traceable starter batch from Wikimedia Commons.

Images are converted to JPEG and placed only in training/dataset/train. The
source URL, author, license, and Commons file page are written to
training/commons-sources.jsonl.
"""

from __future__ import annotations

import json
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "training" / "dataset" / "train"
SOURCES_PATH = ROOT / "training" / "commons-sources.jsonl"
API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "sort-rac-local-dataset-collector/1.0 (local research prototype)"

TARGETS = {
    "aluminium_drink_can": ["aluminium beverage can", "aluminum drink can", "soda can"],
    "battery": ["AA battery", "household battery", "rechargeable battery"],
    "cardboard_box": ["cardboard box", "corrugated cardboard box", "shipping carton"],
    "fruit_peel": ["banana peel", "orange peel", "fruit peel"],
    "paper_cup": ["paper cup", "disposable paper cup", "coffee paper cup"],
    "plastic_takeaway_cup": ["plastic takeaway cup", "disposable plastic cup", "plastic drink cup"],
    "plastic_water_bottle": ["plastic water bottle", "PET water bottle", "plastic drink bottle"],
    "unknown": ["glass bottle", "newspaper", "wooden spoon", "household object"],
}


def search_commons(term: str, limit: int = 50) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": term,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": 640,
    }
    response = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("query", {}).get("pages", {}).values())


def metadata(page: dict) -> tuple[str, dict] | None:
    info = (page.get("imageinfo") or [{}])[0]
    mime = info.get("mime", "")
    thumb_url = info.get("thumburl")
    if not mime.startswith("image/") or not thumb_url:
        return None

    extra = info.get("extmetadata", {})
    license_name = extra.get("LicenseShortName", {}).get("value", "").strip()
    license_url = extra.get("LicenseUrl", {}).get("value", "").strip()
    if not license_name or not license_url:
        return None

    record = {
        "pageid": page.get("pageid"),
        "title": page.get("title"),
        "file_page": info.get("descriptionurl"),
        "source_url": info.get("url"),
        "license": license_name,
        "license_url": license_url,
        "artist": extra.get("Artist", {}).get("value", "").strip(),
    }
    return thumb_url, record


def existing_page_ids() -> set[int]:
    if not SOURCES_PATH.exists():
        return set()
    page_ids: set[int] = set()
    for line in SOURCES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            page_ids.add(int(json.loads(line)["pageid"]))
    return page_ids


def collect_class(class_name: str, terms: list[str], target: int, known_ids: set[int], source_file) -> int:
    destination = DATASET_ROOT / class_name
    destination.mkdir(parents=True, exist_ok=True)
    current = len([path for path in destination.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}])
    added = 0

    for term in terms:
        if current + added >= target:
            break
        for page in search_commons(term):
            if current + added >= target:
                break
            page_id = page.get("pageid")
            if not isinstance(page_id, int) or page_id in known_ids:
                continue
            found = metadata(page)
            if not found:
                continue
            thumb_url, record = found
            try:
                image_response = requests.get(thumb_url, headers={"User-Agent": USER_AGENT}, timeout=30)
                image_response.raise_for_status()
                image = Image.open(BytesIO(image_response.content)).convert("RGB")
                if min(image.size) < 128:
                    continue
                output = destination / f"commons_{page_id}.jpg"
                image.save(output, format="JPEG", quality=92, optimize=True)
            except Exception as error:  # noqa: BLE001 - skip a bad remote file
                print(f"skip {page.get('title')}: {error}")
                continue

            record.update({"class": class_name, "local_file": str(output.relative_to(ROOT))})
            source_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            source_file.flush()
            known_ids.add(page_id)
            added += 1
            print(f"{class_name}: added {output.name} ({record['license']})")
            time.sleep(0.15)

    return added


def main() -> None:
    known_ids = existing_page_ids()
    with SOURCES_PATH.open("a", encoding="utf-8") as source_file:
        for class_name, terms in TARGETS.items():
            added = collect_class(class_name, terms, target=12, known_ids=known_ids, source_file=source_file)
            print(f"{class_name}: added {added} new training images")


if __name__ == "__main__":
    main()
