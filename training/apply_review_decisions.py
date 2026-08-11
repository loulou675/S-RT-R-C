#!/usr/bin/env python3
"""Apply the manual contact-sheet review without deleting source images."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TRAIN_ROOT = ROOT / "dataset" / "train"
REJECTED_ROOT = ROOT / "review_rejected"

# For noisy search terms, an allow-list is safer than trying to enumerate every
# false positive. Values are filename stems from the generated contact sheets.
KEEP_ONLY = {
    "drink_carton": {
        "commons_train_106318273", "commons_train_112878826",
        "commons_train_115193922", "commons_train_11804926",
        "commons_train_133525822", "commons_train_133981856",
        "commons_train_151468120", "commons_train_164432481",
        "commons_train_17711329", "commons_train_181917358",
        "commons_train_185968890", "commons_train_196191111",
        "commons_train_38351046", "commons_train_49211429",
        "commons_train_61738003", "commons_train_75285385",
        "commons_train_78625371",
    },
    "mobile_phone": {
        "commons_train_110866514", "commons_train_11204649",
        "commons_train_115613009", "commons_train_124720293",
        "commons_train_138016622", "commons_train_152695043",
        "commons_train_165164441", "commons_train_25942907",
        "commons_train_27889312", "commons_train_57217996",
        "commons_train_60726439", "commons_train_7609303",
        "commons_train_9303488", "commons_train_94919792",
        "commons_train_94919793",
    },
    "tissue": {
        "commons_train_100015809", "commons_train_109417620",
        "commons_train_115309467", "commons_train_126356293",
        "commons_train_127262881", "commons_train_132022992",
        "commons_train_138176959", "commons_train_138633177",
        "commons_train_1393300", "commons_train_140970650",
        "commons_train_148998529", "commons_train_3359242",
        "commons_train_36679859", "commons_train_37641344",
        "commons_train_37641345", "commons_train_37641346",
        "commons_train_37641347", "commons_train_52439163",
        "commons_train_92387900", "commons_train_98922949",
        "commons_train_99843239",
    },
}

REJECT = {
    "chemical_container": {
        "commons_train_121698293", "commons_train_121698298",
        "commons_train_121698513", "commons_train_121698517",
        "commons_train_121698522", "commons_train_121698526",
        "commons_train_121699695", "commons_train_13551552",
        "commons_train_181291562", "commons_train_24528882",
        "commons_train_42117423", "commons_train_42152873",
        "commons_train_43203455", "commons_train_43695208",
        "commons_train_43829946", "commons_train_43844528",
        "commons_train_43933715", "commons_train_44522075",
        "commons_train_6774260", "commons_train_76001410",
        "commons_train_77164161", "commons_train_77632915",
    },
    "disposable_diaper": {
        "commons_train_105610924", "commons_train_108028653",
        "commons_train_33030195", "commons_train_33030197",
        "commons_train_34965742", "commons_train_3750538",
        "commons_train_41885373", "commons_train_4267879",
        "commons_train_4308523", "commons_train_5785042",
        "commons_train_60450322", "commons_train_76735285",
        "commons_train_87584469", "commons_train_87584477",
    },
    "paper_bag": {
        "commons_train_144717914", "commons_train_151684313",
        "commons_train_17564242", "commons_train_17564806",
        "commons_train_18439983", "commons_train_40440493",
        "commons_train_40440496", "commons_train_40440497",
        "commons_train_40440498", "commons_train_40440502",
        "commons_train_40440503", "commons_train_40440504",
        "commons_train_70547635",
        "taco_field_v2_332_1082", "taco_field_v2_533_1751",
        "taco_field_v2_611_1917", "taco_field_v2_679_2184",
        "taco_field_v2_679_2185", "taco_field_v2_679_2186",
    },
    "power_bank": {
        "commons_train_111294058", "commons_train_112481680",
        "commons_train_114424118", "commons_train_129299280",
        "commons_train_129756194", "commons_train_151542757",
        "commons_train_164111743", "commons_train_165099229",
        "commons_train_173430095", "commons_train_186116641",
        "commons_train_186220254", "commons_train_28920965",
        "commons_train_43031680", "commons_train_50012175",
        "commons_train_50750154", "commons_train_72184381",
        "commons_train_80293147", "commons_train_95712951",
    },
    "aluminium_drink_can": {
        "taco_field_v2_29_83", "taco_field_v2_242_784",
        "taco_field_v2_335_1099", "taco_field_v2_345_1135",
        "taco_field_v2_385_1345", "taco_field_v2_522_1730",
        "taco_field_v2_580_1817", "taco_field_v2_580_1818",
        "taco_field_v2_582_1824", "taco_field_v2_601_1882",
        "taco_field_v2_601_1883", "taco_field_v2_601_1885",
        "taco_field_v2_601_1886", "taco_field_v2_614_1924",
    },
    "cardboard_box": {
        "taco_field_v2_132_443", "taco_field_v2_186_623",
        "taco_field_v2_199_683", "taco_field_v2_201_687",
        "taco_field_v2_209_709", "taco_field_v2_1003_2991",
        "taco_field_v2_1064_3159",
    },
    "drink_carton": {
        "taco_field_v2_297_901", "taco_field_v2_298_905",
        "taco_field_v2_334_1091",
    },
    "paperboard_packaging": {
        "taco_field_v2_1_3", "taco_field_v2_336_1104",
        "taco_field_v2_359_1214", "taco_field_v2_359_1215",
        "taco_field_v2_416_1478", "taco_field_v2_521_1729",
        "taco_field_v2_522_1732", "taco_field_v2_560_1790",
        "taco_field_v2_563_1794", "taco_field_v2_572_1806",
        "taco_field_v2_572_1807", "taco_field_v2_610_1906",
        "taco_field_v2_1029_3056",
    },
    "plastic_bag": {
        "taco_field_v2_34_92", "taco_field_v2_229_758",
        "taco_field_v2_229_759", "taco_field_v2_229_760",
        "taco_field_v2_229_761", "taco_field_v2_229_762",
        "taco_field_v2_229_763", "taco_field_v2_229_764",
        "taco_field_v2_359_1210", "taco_field_v2_385_1338",
        "taco_field_v2_606_1895", "taco_field_v2_1239_3839",
    },
    "plastic_takeaway_cup": {
        "taco_field_v2_353_1194", "taco_field_v2_375_1323",
    },
    "snack_wrapper": {
        "taco_field_v2_241_781", "taco_field_v2_301_923",
        "taco_field_v2_310_938", "taco_field_v2_329_1057",
        "taco_field_v2_331_1075", "taco_field_v2_332_1083",
        "taco_field_v2_334_1090", "taco_field_v2_335_1103",
        "taco_field_v2_340_1121", "taco_field_v2_356_1103",
        "taco_field_v2_356_1197", "taco_field_v2_359_1212",
        "taco_field_v2_359_1213", "taco_field_v2_360_1218",
        "taco_field_v2_360_1219", "taco_field_v2_360_1221",
        "taco_field_v2_360_1222", "taco_field_v2_362_1225",
        "taco_field_v2_362_1226", "taco_field_v2_362_1228",
        "taco_field_v2_362_1245", "taco_field_v2_362_1247",
        "taco_field_v2_362_1248", "taco_field_v2_362_1250",
        "taco_field_v2_362_1252", "taco_field_v2_362_1253",
        "taco_field_v2_362_1255", "taco_field_v2_362_1256",
        "taco_field_v2_362_1257", "taco_field_v2_362_1261",
        "taco_field_v2_363_1291",
    },
    "styrofoam_container": {
        "taco_field_v2_320_960", "taco_field_v2_460_1627",
        "taco_field_v2_460_1628", "taco_field_v2_601_1880",
        "taco_field_v2_601_1881",
    },
    "tissue": {
        "taco_field_v2_234_771", "taco_field_v2_310_939",
        "taco_field_v2_329_1061", "taco_field_v2_457_1617",
        "taco_field_v2_608_1902", "taco_field_v2_630_2040",
    },
}


def decisions() -> dict[str, set[str]]:
    result = {name: set(values) for name, values in REJECT.items()}
    for class_name, keep in KEEP_ONLY.items():
        all_stems = {
            path.stem
            for path in (TRAIN_ROOT / class_name).iterdir()
            if path.is_file() and path.name != ".gitkeep" and path.stem.startswith("commons_train_")
        }
        result.setdefault(class_name, set()).update(all_stems - keep)
    return result


def update_manifests(moved: dict[tuple[str, str], Path]) -> int:
    updated = 0
    for manifest in sorted(ROOT.glob("*-sources.jsonl")):
        rows = []
        changed = False
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            local_file = Path(str(row.get("local_file", "")))
            class_name = str(
                row.get("target_class", row.get("class_name", row.get("class", "")))
            )
            destination = moved.get((class_name, local_file.stem))
            if destination:
                row["local_file"] = str(destination.relative_to(ROOT.parent))
                row["review_status"] = "rejected_wrong_or_cluttered"
                changed = True
                updated += 1
            rows.append(row)
        if changed:
            manifest.write_text(
                "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows),
                encoding="utf-8",
            )
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Move rejected files and update manifests")
    args = parser.parse_args()

    review = decisions()
    total = sum(len(stems) for stems in review.values())
    for class_name in sorted(review):
        print(f"{class_name}: reject {len(review[class_name])}")
    print(f"total: reject {total}")
    if not args.apply:
        print("Dry run only. Add --apply to make changes.")
        return

    moved: dict[tuple[str, str], Path] = {}
    for class_name, stems in review.items():
        destination_dir = REJECTED_ROOT / class_name
        destination_dir.mkdir(parents=True, exist_ok=True)
        for stem in sorted(stems):
            matches = list((TRAIN_ROOT / class_name).glob(f"{stem}.*"))
            for source in matches:
                destination = destination_dir / source.name
                if destination.exists():
                    source.unlink()
                else:
                    shutil.move(str(source), destination)
                moved[(class_name, stem)] = destination

    # Include files quarantined by an earlier run so manifest repair is
    # idempotent even if the images have already moved out of the train folder.
    for class_dir in REJECTED_ROOT.iterdir():
        if not class_dir.is_dir():
            continue
        for rejected in class_dir.iterdir():
            if rejected.is_file():
                moved[(class_dir.name, rejected.stem)] = rejected

    manifest_updates = update_manifests(moved)
    print(f"Moved {len(moved)} files; updated {manifest_updates} manifest rows.")


if __name__ == "__main__":
    main()
