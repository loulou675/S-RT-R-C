#!/usr/bin/env python3
"""Download private Supabase feedback and promote only reviewed images."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_DIR = ROOT / "training" / "feedback_review"
DEFAULT_DATASET_DIR = ROOT / "training" / "dataset" / "train"
APPROVED_STATUSES = {"accepted", "relabeled"}
KNOWN_STATUSES = {"pending", "accepted", "relabeled", "unknown", "rejected"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / ".env.reviewer",
        help="File containing SUPABASE_REVIEWER_KEY or SUPABASE_SERVICE_ROLE_KEY.",
    )
    parser.add_argument(
        "--statuses",
        default="pending,accepted,relabeled",
        help="Comma-separated review statuses to download.",
    )
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Download approved images without copying them into the training set.",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def get_configuration(env_file: Path) -> tuple[str, str]:
    load_env_file(ROOT / ".env.local")
    load_env_file(ROOT / ".env")
    load_env_file(env_file)
    url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
    key = os.getenv("SUPABASE_REVIEWER_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url:
        raise SystemExit("Missing SUPABASE_URL or VITE_SUPABASE_URL.")
    if not key:
        raise SystemExit(
            "Missing reviewer key. Put SUPABASE_REVIEWER_KEY=... in .env.reviewer."
        )
    if key.startswith("sb_publishable_"):
        raise SystemExit(
            "The publishable key can submit feedback but cannot read the private queue. "
            "Use a secret/service-role reviewer key in .env.reviewer instead."
        )
    return url.rstrip("/"), key


def api_request(url: str, key: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Supabase returned HTTP {error.code}: {detail}") from error


def fetch_rows(base_url: str, key: str, statuses: set[str]) -> list[dict]:
    columns = ",".join(
        [
            "id",
            "image_path",
            "predicted_item_code",
            "corrected_item_code",
            "input_method",
            "error_code",
            "review_status",
            "client_created_at",
            "created_at",
            "reviewed_at",
        ]
    )
    status_filter = "(" + ",".join(sorted(statuses)) + ")"
    query = urllib.parse.urlencode(
        {
            "select": columns,
            "review_status": f"in.{status_filter}",
            "order": "created_at.asc",
        },
        safe=",().",
    )
    payload = api_request(f"{base_url}/rest/v1/training_feedback?{query}", key)
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected response while reading training_feedback.")
    return rows


def download_image(base_url: str, key: str, image_path: str) -> bytes:
    encoded_path = urllib.parse.quote(image_path, safe="/")
    return api_request(
        f"{base_url}/storage/v1/object/authenticated/training-feedback/{encoded_path}",
        key,
    )


def validate_jpeg(data: bytes) -> None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("Downloaded object is not a complete JPEG image.")


def write_if_missing(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)


def main() -> int:
    args = parse_args()
    statuses = {value.strip() for value in args.statuses.split(",") if value.strip()}
    invalid_statuses = statuses - KNOWN_STATUSES
    if invalid_statuses:
        raise SystemExit(f"Unknown review statuses: {', '.join(sorted(invalid_statuses))}")

    base_url, key = get_configuration(args.env_file)
    rows = fetch_rows(base_url, key, statuses)
    valid_classes = {path.name for path in args.dataset_dir.iterdir() if path.is_dir()}
    manifest_entries: list[dict] = []
    downloaded = 0
    promoted = 0
    skipped = 0

    for row in rows:
        status = row.get("review_status")
        corrected_code = row.get("corrected_item_code")
        image_path = row.get("image_path")
        if not isinstance(image_path, str) or not isinstance(corrected_code, str):
            skipped += 1
            continue

        try:
            data = download_image(base_url, key, image_path)
            validate_jpeg(data)
        except (RuntimeError, ValueError) as error:
            print(f"Skip {row.get('id')}: {error}", file=sys.stderr)
            skipped += 1
            continue

        digest = hashlib.sha256(data).hexdigest()
        review_class = corrected_code if corrected_code in valid_classes else "_unknown_class"
        review_path = args.review_dir / str(status) / review_class / f"{digest[:16]}.jpg"
        write_if_missing(review_path, data)
        downloaded += 1

        promoted_path: Path | None = None
        if (
            not args.no_promote
            and status in APPROVED_STATUSES
            and corrected_code in valid_classes
        ):
            promoted_path = args.dataset_dir / corrected_code / f"feedback_{digest[:16]}.jpg"
            if not promoted_path.exists():
                promoted_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(review_path, promoted_path)
                promoted += 1

        manifest_entries.append(
            {
                "feedback_id": row.get("id"),
                "review_status": status,
                "predicted_item_code": row.get("predicted_item_code"),
                "corrected_item_code": corrected_code,
                "input_method": row.get("input_method"),
                "error_code": row.get("error_code"),
                "created_at": row.get("created_at"),
                "reviewed_at": row.get("reviewed_at"),
                "sha256": digest,
                "review_file": str(review_path.relative_to(ROOT)),
                "training_file": str(promoted_path.relative_to(ROOT)) if promoted_path else None,
            }
        )

    args.review_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.review_dir / "feedback_manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for entry in manifest_entries:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")

    counts: dict[str, int] = {}
    for entry in manifest_entries:
        count_key = f"{entry['review_status']}:{entry['corrected_item_code']}"
        counts[count_key] = counts.get(count_key, 0) + 1

    print(f"Rows matched: {len(rows)}")
    print(f"Images downloaded: {downloaded}")
    print(f"Approved images added to training: {promoted}")
    print(f"Rows skipped: {skipped}")
    print(f"Manifest: {manifest_path}")
    for count_key, count in sorted(counts.items()):
        print(f"  {count_key}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
