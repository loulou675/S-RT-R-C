"""Collect a larger review batch of CC-licensed real-world waste photos.

Openverse indexes multiple openly licensed photo sources. This script puts
candidate photos directly in the four requested class folders and records the
original page, creator, and license. It deliberately does not claim that every
candidate is perfect; manually review them before rebuilding the curated split.
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
SOURCES_PATH = ROOT / "training" / "openverse-field-sources.jsonl"
API_URL = "https://api.openverse.org/v1/images/"
USER_AGENT = "sort-rac-local-openverse-collector/1.0 (single-item research prototype)"

TARGETS: dict[str, list[str]] = {
    "fruit_peel": ["single banana peel", "banana peel on ground", "orange peel", "fruit peel"],
    "battery": ["single AA battery", "single AAA battery", "single 9V battery", "battery litter"],
    "paper_cup": ["single paper coffee cup", "paper cup on table", "paper cup litter", "disposable paper cup"],
    "plastic_takeaway_cup": ["single plastic cup", "disposable plastic cup", "plastic takeaway cup", "plastic cup litter"],
}

BAD_TITLE_TOKENS = (
    "pile", "collection", "group", "set", "various", "multiple", "comparison",
    "assortment", "stack", "batteries", "cups", "peels", "diagram", "schematic",
    "icon", "clip art", "illustration", "model", "render", "drawing", "artwork",
    "texture", "chart", "holder", "adapter", "charger", "flashlight", "camera",
    "cat", "service area", "building", "landscape", "logo", "advertisement",
)


def existing_ids() -> set[str]:
    ids: set[str] = set()
    for path in (ROOT / "training").glob("*-sources.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line).get("id")
                if isinstance(value, str):
                    ids.add(value)
            except json.JSONDecodeError:
                continue
    return ids


def search(query: str) -> list[dict]:
    response = requests.get(
        API_URL,
        # The public endpoint accepts the query without a license_type filter;
        # each result still includes its exact license and license URL.
        params={"q": query, "page_size": 50},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def suitable(result: dict) -> bool:
    title = str(result.get("title", "")).lower()
    tags = " ".join(str(tag.get("name", "")) for tag in result.get("tags", [])).lower()
    text = f"{title} {tags}"
    return not any(token in text for token in BAD_TITLE_TOKENS)


def collect_class(class_name: str, queries: list[str], target: int, seen: set[str], session: requests.Session, log) -> int:
    destination = DATASET_ROOT / class_name
    destination.mkdir(parents=True, exist_ok=True)
    added = 0
    for query in queries:
        if added >= target:
            break
        print(f"Searching {class_name}: {query}", flush=True)
        try:
            results = search(query)
        except Exception as error:  # noqa: BLE001 - continue to the next query
            print(f"  search skipped: {error}", flush=True)
            continue
        for result in results:
            if added >= target:
                break
            result_id = result.get("id")
            url = result.get("url")
            if not isinstance(result_id, str) or not isinstance(url, str) or result_id in seen:
                continue
            if not suitable(result) or result.get("mature"):
                continue
            try:
                response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content)).convert("RGB")
                if min(image.size) < 224:
                    continue
            except Exception as error:  # noqa: BLE001 - skip broken/blocked media
                print(f"  skip {result.get('title')}: {error}", flush=True)
                continue
            output = destination / f"openverse_field_{result_id[:12]}.jpg"
            if output.exists():
                seen.add(result_id)
                continue
            image.save(output, format="JPEG", quality=92, optimize=True)
            record = {
                "id": result_id,
                "class": class_name,
                "title": result.get("title"),
                "creator": result.get("creator"),
                "creator_url": result.get("creator_url"),
                "source": result.get("source"),
                "provider": result.get("provider"),
                "foreign_landing_url": result.get("foreign_landing_url"),
                "license": result.get("license"),
                "license_version": result.get("license_version"),
                "license_url": result.get("license_url"),
                "local_file": str(output.relative_to(ROOT)),
            }
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            log.flush()
            seen.add(result_id)
            added += 1
            print(f"  added {output.name} ({result.get('license')} {result.get('license_version')})", flush=True)
            time.sleep(0.15)
    return added


def main() -> None:
    seen = existing_ids()
    with requests.Session() as session, SOURCES_PATH.open("a", encoding="utf-8") as log:
        for class_name, queries in TARGETS.items():
            added = collect_class(class_name, queries, target=20, seen=seen, session=session, log=log)
            print(f"{class_name}: added {added} candidate photos", flush=True)


if __name__ == "__main__":
    main()
