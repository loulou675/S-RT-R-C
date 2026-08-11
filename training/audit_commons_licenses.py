"""Quarantine downloaded Commons candidates with complex license terms."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "training" / "commons-training-sources.jsonl"
QUARANTINE = ROOT / "training" / "quarantine" / "license_review"
AUDIT_LOG = ROOT / "training" / "quarantine" / "license-review.jsonl"
ALLOWED_PREFIXES = ("cc0", "cc by", "public domain", "pdm", "no restrictions")


def main() -> None:
    if not MANIFEST.exists():
        return
    moved = 0
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        license_name = str(row.get("license", "")).lower()
        if license_name.startswith(ALLOWED_PREFIXES):
            continue
        local_file = row.get("local_file")
        if not local_file:
            continue
        source = ROOT / local_file
        if not source.exists():
            continue
        destination = QUARANTINE / source.relative_to(ROOT / "training" / "dataset" / "train")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a", encoding="utf-8") as audit:
            audit.write(
                json.dumps(
                    {
                        "local_file": local_file,
                        "quarantined_file": str(destination.relative_to(ROOT)),
                        "license": row.get("license"),
                        "reason": "manual license compliance review required",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        moved += 1
    print(f"quarantined {moved} Commons candidates for license review")


if __name__ == "__main__":
    main()
