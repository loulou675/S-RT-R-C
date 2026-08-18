"""Collect candidate images for newly requested waste-item classes.

The candidates stay outside the production classifier until a human reviews
them. Wikimedia Commons is used because the API exposes the original file
page and image metadata alongside the downloadable thumbnail.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from PIL import Image
from io import BytesIO


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOT = ROOT / "training" / "candidate_dataset" / "new_items"
MANIFEST = ROOT / "training" / "source_manifests" / "new-item-candidates.jsonl"
API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "SORT-RAC-training/1.0 (educational waste-classification dataset)"


TARGETS: dict[str, dict[str, Any]] = {
    "hair_clip": {"bin": "landfill", "queries": ["hair clip", "barrette", "hair claw"], "target": 45},
    "phone_case": {"bin": "landfill", "queries": ["phone case", "mobile phone case", "smartphone case"], "target": 45},
    "clothing_fabric": {"bin": "landfill", "queries": ["old clothing", "torn clothing", "textile waste", "fabric scraps"], "target": 55},
    "hair_tie": {"bin": "landfill", "queries": ["hair tie", "hair elastic", "hair band"], "target": 40},
    "comb": {"bin": "landfill", "queries": ["hair comb", "comb hair"], "target": 40},
    "broken_toy": {"bin": "landfill", "queries": ["broken toy", "damaged toy", "discarded toy"], "target": 45},
    "keychain": {"bin": "landfill", "queries": ["keychain", "key ring"], "target": 40},
    "cosmetic_sponge": {"bin": "landfill", "queries": ["makeup sponge", "cosmetic sponge"], "target": 40},
    "broken_ceramic": {"bin": "landfill", "queries": ["broken ceramic", "broken pottery", "broken plate"], "target": 45},
    "birthday_candle": {"bin": "landfill", "queries": ["birthday candle", "used candle"], "target": 35},
    "phone_charger": {"bin": "special_handling", "queries": ["phone charger", "power adapter", "charging cable"], "target": 45},
    "pen_marker": {"bin": "landfill", "queries": ["ballpoint pen", "marker pen", "highlighter pen"], "target": 45},
    "pencil_crayon": {"bin": "landfill", "queries": ["colored pencil", "colour pencil", "crayon"], "target": 45},
    "eraser": {"bin": "landfill", "queries": ["rubber eraser", "pencil eraser"], "target": 35},
    "ruler": {"bin": "landfill", "queries": ["plastic ruler", "school ruler"], "target": 35},
    "glue_tape": {"bin": "landfill", "queries": ["glue stick", "correction tape", "sticky tape"], "target": 35},
    "notebook": {"bin": "paper_cardboard", "queries": ["school notebook", "exercise book", "spiral notebook"], "target": 45},
}

CATEGORY_TARGETS: dict[str, list[str]] = {
    "hair_clip": ["Hair_clips"],
    "phone_case": ["Mobile_phone_covers", "Smartphone_covers"],
    "hair_tie": ["Hair_ties", "Scrunchies"],
    "comb": ["Modern_haircombs", "Combs_(hair_ornaments)"],
    "broken_ceramic": ["Broken_ceramics"],
    "pencil_crayon": ["Colored_pencils", "Crayons"],
    "eraser": ["Erasers"],
    "ruler": ["Rulers"],
}


def api_search(query: str, limit: int = 80) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,
        "gsrlimit": min(limit, 500),
        "prop": "imageinfo|info",
        "iiprop": "url|mime|size|width|height",
        "iiurlwidth": 1400,
        "inprop": "url",
    }
    response = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {}).values()
    return list(pages)


def commons_category_search(category: str, limit: int = 100) -> list[dict[str, Any]]:
    """Read file thumbnails from a focused Commons category page."""
    response = requests.get(
        f"https://commons.wikimedia.org/wiki/Category:{category}",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    raw_urls = re.findall(r"https://upload.wikimedia.org/[^\"' ]+", response.text)
    pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_url in enumerate(raw_urls):
        source_image = html.unescape(raw_url).split("?", 1)[0]
        if "/thumb/" not in source_image or source_image.lower().endswith((".svg", ".svg.png")):
            continue
        if any(token in source_image.lower() for token in ("wikipedia-logo", "wikidata-logo", "blue_pencil")):
            continue
        # Commons only creates a fixed set of thumbnail widths for many files;
        # 1280px is widely available while arbitrary widths can return 400.
        source_image = re.sub(r"/\d+px-", "/1280px-", source_image)
        if source_image in seen:
            continue
        seen.add(source_image)
        pages.append(
            {
                "pageid": f"commons-category-{hashlib.sha1(source_image.encode()).hexdigest()}",
                "title": Path(source_image).name,
                "fullurl": f"https://commons.wikimedia.org/wiki/Category:{category}",
                "sourceName": "Wikimedia Commons",
                "license": "per_file_review_required",
                "imageinfo": [{"url": source_image, "thumburl": source_image, "mime": "image/jpeg", "width": 0, "height": 0}],
            }
        )
        if len(pages) >= limit:
            break
    return pages


def openverse_search(query: str, limit: int = 100) -> list[dict[str, Any]]:
    """Return Openverse results in the same shape as the Commons records."""
    response = requests.get(
        "https://api.openverse.org/v1/images/",
        params={"q": query, "page_size": min(limit, 100)},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    pages: list[dict[str, Any]] = []
    for index, result in enumerate(response.json().get("results", [])):
        image_url = result.get("url")
        thumbnail = result.get("thumbnail") or image_url
        if not image_url or not thumbnail:
            continue
        pages.append(
            {
                "pageid": f"openverse-{result.get('id', index)}",
                "title": result.get("title") or query,
                "fullurl": result.get("detail_url") or result.get("foreign_landing_url"),
                "sourceName": "Openverse",
                "license": result.get("license"),
                "creator": result.get("creator"),
                "imageinfo": [
                    {
                        "url": image_url,
                        "thumburl": thumbnail,
                        "mime": result.get("filetype") or "image/jpeg",
                        "width": result.get("width") or 0,
                        "height": result.get("height") or 0,
                    }
                ],
            }
        )
    return pages


def bing_image_search(query: str, limit: int = 70) -> list[dict[str, Any]]:
    """Read image URLs from Bing's public image-search result markup.

    Bing does not provide a reliable license field here, so every result is
    marked for manual review instead of being treated as cleared training data.
    """
    response = requests.get(
        "https://www.bing.com/images/search",
        params={"q": query, "form": "HDRSC2"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    matches = re.findall(r'class="iusc"[^>]*\sm="(.*?)"', response.text)
    pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_payload in enumerate(matches):
        try:
            metadata = json.loads(html.unescape(raw_payload))
        except json.JSONDecodeError:
            continue
        image_url = str(metadata.get("murl", "")).replace("\\/", "/")
        if not image_url.startswith(("http://", "https://")) or image_url in seen:
            continue
        seen.add(image_url)
        pages.append(
            {
                "pageid": f"bing-{hashlib.sha1(image_url.encode()).hexdigest()}",
                "title": metadata.get("t") or query,
                "fullurl": metadata.get("purl") or f"https://www.bing.com/images/search?q={requests.utils.quote(query)}",
                "sourceName": "Bing Images",
                "license": "unknown_review_needed",
                "imageinfo": [{"url": image_url, "thumburl": image_url, "mime": "image/jpeg", "width": 0, "height": 0}],
            }
        )
        if len(pages) >= limit:
            break
    return pages


def title_matches(class_code: str, title: str) -> bool:
    """Remove obvious semantic mismatches before downloading an image."""
    text = title.casefold()
    rules = {
        "hair_clip": (r"clip|barrette|hair claw|hair accessory", r"video|paper clip|film clip|cat|dog"),
        "phone_case": (r"phone case|phone cover|mobile case|smartphone case", r"phone in hand|telephone|calculator|screen protector"),
        "clothing_fabric": (r"clothing|clothes|textile|fabric|garment|torn shirt|old clothes|scrap", r"torn paper|paper tear|newspaper|poster"),
        "hair_tie": (r"hair tie|hair elastic|hair band|scrunchie", r"hand gesture|ok sign|bracelet"),
        "comb": (r"hair comb|comb", r"cat|kitten|dog|animal|combustion"),
        "broken_toy": (r"broken toy|damaged toy|discarded toy|toy", r"broken heart|injury|leg cast|glass|relationship"),
        "keychain": (r"keychain|key chain|key ring|keyring", r"ring light|ring finger|wedding ring"),
        "cosmetic_sponge": (r"sponge|makeup|cosmetic|beauty blender", r"sponge cake|dish sponge|sea sponge"),
        "broken_ceramic": (r"broken ceramic|broken pottery|broken plate|ceramic shard|pottery", r"periodic table|chart|table of elements"),
        "birthday_candle": (r"birthday candle|candle", r"cat|dog|balloon|candlelight concert"),
        "phone_charger": (r"phone charger|power adapter|charging cable|usb charger|charger", r"phone only|battery charger review"),
        "pen_marker": (r"ballpoint pen|marker pen|highlighter|felt.?tip pen", r"pencil|penalty|peninsula|person"),
        "pencil_crayon": (r"colored pencil|colour pencil|crayon|pencil crayon", r"pencil sketch|pencil drawing|pencil sharpener"),
        "eraser": (r"eraser|rubber eraser", r"eraserhead|eraser tool software"),
        "ruler": (r"school ruler|plastic ruler|ruler", r"ruler of|ruler portrait|ruler person"),
        "glue_tape": (r"glue stick|correction tape|sticky tape|adhesive tape", r"tape measure|tape recording|tape drive"),
        "notebook": (r"school notebook|exercise book|spiral notebook|notebook", r"laptop|computer|notebook computer"),
    }
    include, exclude = rules[class_code]
    return bool(re.search(include, text)) and not re.search(exclude, text)


def safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._")
    return value[:120] or "commons_image"


def fetch_candidate(item: tuple[str, dict[str, Any], int]) -> dict[str, Any] | None:
    class_code, page, index = item
    info = (page.get("imageinfo") or [{}])[0]
    url = info.get("thumburl") or info.get("url")
    mime = info.get("mime", "")
    width = int(info.get("thumbwidth") or info.get("width") or 0)
    height = int(info.get("thumbheight") or info.get("height") or 0)
    if not url or not mime.startswith("image/") or (width and width < 200) or (height and height < 200):
        return None

    try:
        download_urls = [url]
        if "/thumb/" in url:
            parts = url.split("/")
            thumb_index = parts.index("thumb")
            original = "/".join(parts[:thumb_index] + parts[thumb_index + 1 : -1])
            download_urls.append(original)
        response = None
        for download_url in download_urls:
            candidate_response = requests.get(download_url, headers={"User-Agent": USER_AGENT}, timeout=45)
            if candidate_response.ok and candidate_response.headers.get("content-type", "").startswith("image/"):
                response = candidate_response
                break
        if response is None:
            return None
        image = Image.open(BytesIO(response.content)).convert("RGB")
        if min(image.size) < 200:
            return None
        buffer = BytesIO()
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        image.save(buffer, format="JPEG", quality=90, optimize=True)
        payload = buffer.getvalue()
    except Exception:
        return None

    digest = hashlib.sha256(payload).hexdigest()
    destination = CANDIDATE_ROOT / class_code / f"commons_{class_code}_{digest[:16]}.jpg"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(payload)
    return {
        "class": class_code,
        "bin": TARGETS[class_code]["bin"],
        "path": destination.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "source": page.get("sourceName", "Wikimedia Commons"),
        "sourcePage": page.get("fullurl") or f"https://commons.wikimedia.org/?curid={page.get('pageid')}",
        "sourceFile": page.get("title"),
        "sourceImage": url,
        "license": page.get("license"),
        "creator": page.get("creator"),
        "width": image.width,
        "height": image.height,
        "review": "candidate_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit-query", type=int, default=80)
    parser.add_argument("--classes", nargs="*", help="Only collect selected class codes")
    args = parser.parse_args()

    existing: dict[str, dict[str, Any]] = {}
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[record.get("sha256", "")] = record

    all_records = dict(existing)
    for class_code, config in TARGETS.items():
        if args.classes and class_code not in args.classes:
            continue
        target = args.per_class or config["target"]
        current = [record for record in all_records.values() if record.get("class") == class_code]
        if len(current) >= target:
            print(f"{class_code}: already has {len(current)} candidates")
            continue

        pages: dict[str, dict[str, Any]] = {}
        for category in CATEGORY_TARGETS.get(class_code, []):
            try:
                for page in commons_category_search(category, args.limit_query):
                    if page.get("pageid"):
                        pages[str(page["pageid"])] = page
            except requests.RequestException as error:
                print(f"{class_code}: category search failed for {category!r}: {error}")
        for query in config["queries"]:
            try:
                for page in api_search(query, args.limit_query):
                    if page.get("pageid") and title_matches(class_code, str(page.get("title", ""))):
                        page["sourceName"] = "Wikimedia Commons"
                        page["license"] = "per_file_review_required"
                        pages[f"commons-api-{page['pageid']}"] = page
            except requests.RequestException as error:
                print(f"{class_code}: Commons search failed for {query!r}: {error}")
            try:
                for page in openverse_search(query, args.limit_query):
                    if page.get("pageid") and title_matches(class_code, str(page.get("title", ""))):
                        pages[str(page["pageid"])] = page
            except requests.RequestException as error:
                print(f"{class_code}: Openverse search failed for {query!r}: {error}")
            try:
                for page in bing_image_search(query, args.limit_query):
                    if page.get("pageid") and title_matches(class_code, str(page.get("title", ""))):
                        pages[str(page["pageid"])] = page
            except requests.RequestException as error:
                print(f"{class_code}: search failed for {query!r}: {error}")
            time.sleep(0.6)

        work = [(class_code, page, index) for index, page in enumerate(pages.values())]
        added = 0
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(fetch_candidate, item) for item in work]
            for future in as_completed(futures):
                record = future.result()
                if not record or record["sha256"] in all_records:
                    continue
                all_records[record["sha256"]] = record
                added += 1
                if len([row for row in all_records.values() if row.get("class") == class_code]) >= target:
                    break
        print(f"{class_code}: added {added}, total {len([row for row in all_records.values() if row.get('class') == class_code])}")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(all_records.values(), key=lambda record: (record.get("class", ""), record.get("path", "")))
    MANIFEST.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    print(f"\nCandidate dataset: {CANDIDATE_ROOT}")
    print(f"Manifest: {MANIFEST}")
    print(f"Total candidates: {len(records)}")


if __name__ == "__main__":
    main()
