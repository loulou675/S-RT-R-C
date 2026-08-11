"""Collect license-traceable object photos from Wikimedia Commons.

The downloaded images are training candidates, not automatically approved
ground truth. Review them before creating the curated train/val/test split.
Every accepted image has a corresponding source and license record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "training" / "dataset" / "train"
SOURCES_PATH = ROOT / "training" / "commons-training-sources.jsonl"
API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "sort-rac-training-collector/2.1 (https://github.com/loulou675/S-RT-R-C)"

# Search phrases intentionally describe visible objects, not disposal bins.
# Near-identical products that share one disposal route use one class.
TARGETS: dict[str, list[str]] = {
    "aerosol_can": [
        "intitle:aerosol can",
        "intitle:spray paint can",
        "deodorant aerosol can isolated",
    ],
    "aluminium_drink_can": ["aluminium beverage can", "soda can", "beer can"],
    "battery": ["AA battery", "AAA battery", "9 volt battery", "button cell battery"],
    "cardboard_box": ["cardboard shipping box", "corrugated cardboard box", "open cardboard box"],
    "chemical_container": [
        "intitle:household chemical bottle",
        "intitle:pesticide bottle",
        "weed killer bottle",
        "bleach bottle",
        "paint can isolated",
    ],
    "disposable_diaper": ["disposable diaper", "used diaper waste", "nappy disposable"],
    "drink_carton": ["milk carton", "juice carton", "tetra pak carton"],
    "electronic_cable": ["USB cable", "electrical cable", "phone charging cable"],
    "food_waste": ["leftover food waste", "food scraps plate", "kitchen food waste"],
    "fruit_peel": ["banana peel", "orange peel", "mango peel"],
    "glass_drink_bottle": ["glass beverage bottle", "glass beer bottle", "glass water bottle"],
    "light_bulb": ["LED light bulb", "incandescent light bulb", "fluorescent bulb"],
    "medical_mask": ["disposable medical mask", "surgical face mask", "used face mask litter"],
    "medicine_blister_pack": ["medicine blister pack", "empty pill blister", "tablet blister packaging"],
    "mobile_phone": ["mobile phone isolated", "smartphone on table", "old mobile phone"],
    "newspaper": ["folded newspaper", "newspaper on table", "old newspaper"],
    "paper_bag": ["brown paper bag", "paper shopping bag", "paper grocery bag"],
    "paper_cup": ["paper coffee cup", "disposable paper cup", "paper cup on table"],
    "paper_plate": ["disposable paper plate", "white paper plate", "used paper plate"],
    "paperboard_packaging": ["paperboard food box", "cereal box packaging", "paperboard carton packaging"],
    "plastic_bag": ["single plastic shopping bag", "transparent plastic bag", "plastic carrier bag"],
    "plastic_food_container": ["plastic food container", "plastic takeaway container", "plastic food tray"],
    "plastic_takeaway_cup": ["plastic drink cup", "disposable plastic cup", "clear plastic takeaway cup"],
    "plastic_water_bottle": ["PET water bottle", "plastic beverage bottle", "plastic water bottle"],
    "power_bank": ["portable power bank", "phone power bank", "USB power bank"],
    "printing_paper": ["sheet of white paper", "printing paper on table", "office paper sheet"],
    "sanitary_pad": ["sanitary pad", "menstrual pad", "wrapped sanitary napkin"],
    "snack_wrapper": ["snack wrapper", "potato chip packet", "candy wrapper"],
    "steel_food_can": ["tin food can", "steel canned food container", "empty food tin"],
    "styrofoam_container": ["styrofoam food container", "foam takeaway box", "polystyrene food tray"],
    "tissue": ["used tissue paper", "facial tissue", "paper napkin"],
    "vegetable_scraps": ["vegetable scraps", "vegetable peel waste", "kitchen vegetable waste"],
    "unknown": [
        "ceramic mug on table",
        "wooden spoon",
        "house keys",
        "computer keyboard",
        "indoor plant pot",
        "empty desk",
        "human hand",
        "shoe isolated",
    ],
}

ALLOWED_LICENSE_PREFIXES = ("cc0", "cc by", "public domain", "pdm", "no restrictions")
BLOCKED_TITLE_TOKENS = (
    "diagram",
    "drawing",
    "icon",
    "logo",
    "map",
    "poster",
    "render",
    "schema",
    "svg",
)


def request_json(params: dict) -> dict:
    for attempt in range(6):
        response = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=45)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        delay = min(30, int(response.headers.get("Retry-After", "5")) + attempt)
        print(f"Commons rate limit; waiting {delay}s", flush=True)
        time.sleep(delay)
    raise RuntimeError("Wikimedia Commons kept returning HTTP 429")


def search(term: str, limit: int = 80) -> list[dict]:
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
            # 640 is a standard Commons thumbnail width and is considerably
            # friendlier to the image servers than requesting arbitrary sizes.
            "iiurlwidth": 640,
        }
    )
    return list(payload.get("query", {}).get("pages", {}).values())


def usable_metadata(page: dict) -> tuple[str, dict] | None:
    title = str(page.get("title", ""))
    if any(token in title.lower() for token in BLOCKED_TITLE_TOKENS):
        return None
    info = (page.get("imageinfo") or [{}])[0]
    mime = str(info.get("mime", ""))
    thumb_url = info.get("thumburl")
    if not mime.startswith("image/") or mime in {"image/svg+xml", "image/gif"} or not thumb_url:
        return None
    metadata = info.get("extmetadata", {})
    license_name = metadata.get("LicenseShortName", {}).get("value", "").strip()
    license_url = metadata.get("LicenseUrl", {}).get("value", "").strip()
    if not license_name or not license_url:
        return None
    if not license_name.lower().startswith(ALLOWED_LICENSE_PREFIXES):
        return None
    return thumb_url, {
        "pageid": page.get("pageid"),
        "title": title,
        "file_page": info.get("descriptionurl"),
        "source_url": info.get("url"),
        "license": license_name,
        "license_url": license_url,
        "artist": metadata.get("Artist", {}).get("value", "").strip(),
    }


def load_existing_records() -> tuple[set[int], set[str]]:
    page_ids: set[int] = set()
    hashes: set[str] = set()
    for manifest in (ROOT / "training").glob("*-sources.jsonl"):
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Keep reviewed/quarantined page IDs blocked as well. Otherwise a
            # later collection run would download the same rejected image
            # again just because it was moved out of its original folder.
            if isinstance(row.get("pageid"), int):
                page_ids.add(row["pageid"])
            if row.get("sha256"):
                hashes.add(row["sha256"])
    return page_ids, hashes


def image_count(folder: Path) -> int:
    return sum(path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} for path in folder.iterdir())


def download_candidate(url: str) -> bytes | None:
    for attempt in range(5):
        # Commons explicitly asks automated clients to avoid burst traffic.
        time.sleep(1.1 + attempt * 0.4)
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=45)
        if response.status_code == 429:
            delay = min(30, int(response.headers.get("Retry-After", "6")) + attempt * 2)
            print(f"  image rate limit; waiting {delay}s", flush=True)
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response.content
    return None


def collect_class(
    class_name: str,
    terms: list[str],
    target: int,
    known_ids: set[int],
    known_hashes: set[str],
    manifest,
) -> int:
    destination = DATASET_ROOT / class_name
    destination.mkdir(parents=True, exist_ok=True)
    current = image_count(destination)
    added = 0
    for term in terms:
        if current + added >= target:
            break
        print(f"[{class_name}] search: {term}", flush=True)
        for page in search(term):
            if current + added >= target:
                break
            page_id = page.get("pageid")
            if not isinstance(page_id, int) or page_id in known_ids:
                continue
            result = usable_metadata(page)
            if result is None:
                continue
            thumb_url, record = result
            try:
                raw = download_candidate(thumb_url)
                if raw is None:
                    continue
                content_hash = hashlib.sha256(raw).hexdigest()
                if content_hash in known_hashes:
                    continue
                with Image.open(BytesIO(raw)) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                if min(image.size) < 224 or max(image.size) / min(image.size) > 4:
                    continue
                output = destination / f"commons_train_{page_id}.jpg"
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                image.save(output, format="JPEG", quality=90, optimize=True)
            except Exception as error:  # noqa: BLE001 - a bad candidate should not stop a collection run
                print(f"  skip unusable candidate: {page.get('title')} ({type(error).__name__})", flush=True)
                continue
            record.update(
                {
                    "class": class_name,
                    "query": term,
                    "local_file": str(output.relative_to(ROOT)),
                    "sha256": content_hash,
                }
            )
            manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
            manifest.flush()
            known_ids.add(page_id)
            known_hashes.add(content_hash)
            added += 1
            print(f"  added {output.name} ({record['license']})", flush=True)
    return added


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=40, help="Desired total candidates per class")
    parser.add_argument("--class", dest="class_names", action="append", choices=sorted(TARGETS))
    args = parser.parse_args()

    selected = args.class_names or list(TARGETS)
    known_ids, known_hashes = load_existing_records()
    with SOURCES_PATH.open("a", encoding="utf-8") as manifest:
        for class_name in selected:
            added = collect_class(
                class_name,
                TARGETS[class_name],
                args.target,
                known_ids,
                known_hashes,
                manifest,
            )
            print(f"{class_name}: added {added}; total {image_count(DATASET_ROOT / class_name)}", flush=True)


if __name__ == "__main__":
    main()
