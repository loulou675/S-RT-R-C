"""Collect a review batch of real, single-item photos from Wikimedia Commons.

This is intentionally a *candidate* collector: the files land in the normal
training folders so they can be manually reviewed before the next curation and
training run. Every download is accompanied by a source/license record.
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
SOURCES_PATH = ROOT / "training" / "field-photo-sources.jsonl"
API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "sort-rac-local-field-photo-collector/1.0 (single-item research prototype)"

# These terms favor photographs of an object in an ordinary setting. The
# search API still returns occasional near misses, so the user is expected to
# review the candidates before training.
TARGETS: dict[str, list[str]] = {
    "fruit_peel": [
        "intitle:banana peel",
        "intitle:banana skin",
        "banana peel on the ground",
        "intitle:orange peel",
        "intitle:fruit peel",
    ],
    "battery": [
        "intitle:single battery",
        "intitle:AA battery",
        "intitle:AAA battery",
        "intitle:9V battery",
        "battery on the ground",
        "battery litter",
    ],
    "paper_cup": [
        "intitle:paper coffee cup",
        "intitle:paper cup",
        "disposable paper cup on table",
        "paper cup litter",
        "coffee cup in hand",
    ],
    "plastic_takeaway_cup": [
        "intitle:plastic cup",
        "intitle:disposable plastic cup",
        "single plastic takeaway cup",
        "plastic cup on table",
        "plastic cup litter",
        "red solo cup",
    ],
}

BAD_TITLE_TOKENS = (
    "pile", "collection", "group", "set of", "various", "multiple",
    "comparison", "assortment", "stack", "batteries", "cups", "peels",
    "diagram", "schematic", "svg", "icon", "clip art", "illustration",
    "model", "3d", "render", "drawing", "artwork", "texture", "chart",
    "holder", "adapter", "charger", "flashlight", "camera", "cat",
    "shutterstock", "alamy", "istock", "depositphotos", "stock photo",
)


def request_json(params: dict) -> dict:
    for attempt in range(5):
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
            "iiurlwidth": 900,
        }
    )
    return list(payload.get("query", {}).get("pages", {}).values())


def existing_page_ids() -> set[int]:
    ids: set[int] = set()
    for path in (ROOT / "training").glob("*-sources.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                page_id = json.loads(line).get("pageid")
                if isinstance(page_id, int):
                    ids.add(page_id)
            except json.JSONDecodeError:
                continue
    return ids


def metadata(page: dict) -> tuple[str, dict] | None:
    title = str(page.get("title", ""))
    lowered = title.lower()
    if any(token in lowered for token in BAD_TITLE_TOKENS):
        return None
    info = (page.get("imageinfo") or [{}])[0]
    mime = info.get("mime", "")
    thumb_url = info.get("thumburl")
    if not mime.startswith("image/") or not thumb_url or mime in {"image/svg+xml", "image/gif"}:
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
    existing = {p.name for p in destination.iterdir() if p.is_file()}
    added = 0
    for term in terms:
        if added >= target:
            break
        print(f"Searching {class_name}: {term}")
        for page in search_commons(term):
            if added >= target:
                break
            page_id = page.get("pageid")
            if not isinstance(page_id, int) or page_id in known_ids:
                continue
            found = metadata(page)
            if not found:
                continue
            thumb_url, record = found
            output = destination / f"commons_field_{page_id}.jpg"
            if output.name in existing:
                continue
            try:
                response = requests.get(thumb_url, headers={"User-Agent": USER_AGENT}, timeout=30)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content)).convert("RGB")
                if min(image.size) < 224:
                    continue
                image.save(output, format="JPEG", quality=92, optimize=True)
            except Exception as error:  # noqa: BLE001 - skip an unusable remote file
                print(f"  skip {page.get('title')}: {error}")
                continue
            record.update({"class": class_name, "local_file": str(output.relative_to(ROOT))})
            source_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            source_file.flush()
            known_ids.add(page_id)
            existing.add(output.name)
            added += 1
            print(f"  added {output.name} ({record['license']})")
            time.sleep(0.35)
    return added


def main() -> None:
    known_ids = existing_page_ids()
    with SOURCES_PATH.open("a", encoding="utf-8") as source_file:
        for class_name, terms in TARGETS.items():
            added = collect_class(class_name, terms, target=25, known_ids=known_ids, source_file=source_file)
            print(f"{class_name}: added {added} candidate field photos")


if __name__ == "__main__":
    main()
