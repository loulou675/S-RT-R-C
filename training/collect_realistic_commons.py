"""Collect single-item, reuse-traceable images from Wikimedia Commons.

This collector intentionally favors ordinary scenes (tables, hands, kitchens,
and outdoor litter) and skips titles that strongly suggest a set, pile, stock
photo, or multiple objects. Every accepted file is logged with its license.
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
SOURCES_PATH = ROOT / "training" / "realistic-commons-sources.jsonl"
API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "sort-rac-local-dataset-collector/2.0 (single-item research prototype)"

TARGETS = {
    "aluminium_drink_can": ["single soda can on table", "used aluminium can outdoors", "single beverage can"],
    "battery": ["single AA battery", "single household battery on table", "single 9v battery"],
    "cardboard_box": ["single cardboard box on floor", "open cardboard box", "single shipping box"],
    "fruit_peel": ["single banana peel", "single orange peel", "single fruit peel on table"],
    "paper_cup": ["single paper cup on table", "single coffee paper cup", "paper takeaway cup"],
    "plastic_takeaway_cup": ["single plastic cup on table", "single disposable plastic cup", "plastic takeaway cup"],
    "plastic_water_bottle": ["single plastic water bottle on table", "single PET bottle outdoors", "used plastic bottle"],
    "unknown": ["single glass bottle", "single newspaper", "single wooden spoon"],
}

BAD_TITLE_TOKENS = (
    "pile",
    "collection",
    "group",
    "set of",
    "various",
    "multiple",
    "comparison",
    "assortment",
    "stack",
    "boxes",
    "bottles",
    "cups",
    "cans",
    "batteries",
    "peels",
    "shutterstock",
    "alamy",
    "istock",
    "depositphotos",
    "stock photo",
)


def request_json(params: dict) -> dict:
    for attempt in range(4):
        response = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        wait_seconds = int(response.headers.get("Retry-After", "5"))
        print(f"Commons rate limit; waiting {wait_seconds}s")
        time.sleep(min(wait_seconds, 30))
    raise RuntimeError("Commons API kept returning HTTP 429")


def search_commons(term: str, limit: int = 80) -> list[dict]:
    payload = request_json(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": term,
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": 800,
        }
    )
    return list(payload.get("query", {}).get("pages", {}).values())


def existing_page_ids() -> set[int]:
    if not SOURCES_PATH.exists():
        return set()
    return {
        int(json.loads(line)["pageid"])
        for line in SOURCES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def metadata(page: dict) -> tuple[str, dict] | None:
    title = str(page.get("title", "")).lower()
    if any(token in title for token in BAD_TITLE_TOKENS):
        return None

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

    return thumb_url, {
        "pageid": page.get("pageid"),
        "title": page.get("title"),
        "file_page": info.get("descriptionurl"),
        "source_url": info.get("url"),
        "license": license_name,
        "license_url": license_url,
        "artist": extra.get("Artist", {}).get("value", "").strip(),
    }


def collect_class(class_name: str, terms: list[str], target: int, known_ids: set[int], source_file) -> int:
    destination = DATASET_ROOT / class_name
    destination.mkdir(parents=True, exist_ok=True)
    current = len([path for path in destination.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}])
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
                response = requests.get(thumb_url, headers={"User-Agent": USER_AGENT}, timeout=30)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content)).convert("RGB")
                if min(image.size) < 224:
                    continue
                output = destination / f"commons_real_{page_id}.jpg"
                if output.exists():
                    continue
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
            time.sleep(0.35)

    return added


def main() -> None:
    known_ids = existing_page_ids()
    with SOURCES_PATH.open("a", encoding="utf-8") as source_file:
        for class_name, terms in TARGETS.items():
            added = collect_class(class_name, terms, target=12, known_ids=known_ids, source_file=source_file)
            print(f"{class_name}: added {added} new single-item images")


if __name__ == "__main__":
    main()
