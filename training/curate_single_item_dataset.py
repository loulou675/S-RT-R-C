"""Quarantine images that do not match the one-item training contract.

The operation is reversible: files are moved under ``training/quarantine`` and
their original paths are recorded in a manifest. Nothing is deleted.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRAIN_ROOT = ROOT / "training" / "dataset" / "train"
QUARANTINE_ROOT = ROOT / "training" / "quarantine"
MANIFEST_PATH = QUARANTINE_ROOT / "manifest.jsonl"

# These downloaded images are visibly cluttered, contain multiple objects, or
# carry stock-photo watermarks. They should not teach the classifier a class.
EXPLICIT_BAD = {
    "aerosol_can": {
        "commons_train_62418368.jpg",
        "commons_train_62418373.jpg",
        "commons_train_43607362.jpg",
        "commons_train_62418400.jpg",
        "commons_train_62418383.jpg",
        "commons_train_62418380.jpg",
        "commons_train_62418387.jpg",
        "commons_train_62418376.jpg",
        "commons_train_62418395.jpg",
        "commons_train_62418367.jpg",
        "commons_train_62418371.jpg",
    },
    "aluminium_drink_can": {
        "crumpled-empty-blank-aluminium-can-600w-2703908305.webp",
        "images.jpeg",
    },
    "battery": {
        "XMS24BATAA8_1024x1024.webp",
        "commons_15359691.jpg",
        "commons_15852351.jpg",
        "commons_282602.jpg",
        "commons_52898.jpg",
    },
    "cardboard_box": {
        "commons_72384486.jpg",
        "commons_87745811.jpg",
        "images.jpeg",
    },
    "chemical_container": {
        "commons_train_94643181.jpg",
        "commons_train_87485653.jpg",
        "commons_train_41889642.jpg",
        "commons_train_41863551.jpg",
        "commons_train_190550726.jpg",
        "commons_train_69621593.jpg",
        "commons_train_92473844.jpg",
        "commons_train_190550409.jpg",
        "commons_train_41873714.jpg",
        "commons_train_128890890.jpg",
    },
    "disposable_diaper": {
        "commons_train_73017602.jpg",
        "commons_train_73017601.jpg",
        "commons_train_73017598.jpg",
        "commons_train_73017586.jpg",
        "commons_train_101772088.jpg",
        "commons_train_37308717.jpg",
        "commons_train_27465941.jpg",
        "commons_train_60365179.jpg",
        "commons_train_73017596.jpg",
        "commons_train_73017604.jpg",
        "commons_train_73017590.jpg",
        "commons_train_27465949.jpg",
        "commons_train_73017603.jpg",
        "commons_train_73017593.jpg",
        "commons_train_104998437.jpg",
        "commons_train_101242213.jpg",
        "commons_train_60365114.jpg",
        "commons_train_122583126.jpg",
    },
    "drink_carton": {
        "commons_train_106342192.jpg",
        "commons_train_163379167.jpg",
        "commons_train_162732413.jpg",
        "commons_train_134232761.jpg",
        "commons_train_69281738.jpg",
        "commons_train_101291506.jpg",
        "commons_train_25195586.jpg",
        "commons_train_106342196.jpg",
        "commons_train_101317219.jpg",
        "commons_train_163974023.jpg",
        "commons_train_49283780.jpg",
        "commons_train_142362800.jpg",
        "commons_train_28952217.jpg",
        "commons_train_101317202.jpg",
        "commons_train_163023128.jpg",
        "commons_train_35426036.jpg",
        "commons_train_74765455.jpg",
        "commons_train_2064996.jpg",
        "commons_train_2458724.jpg",
        "commons_train_152430669.jpg",
    },
    "fruit_peel": {"images (2).jpeg"},
    "food_waste": {
        "commons_train_29745785.jpg",
        "commons_train_164150233.jpg",
    },
    "mobile_phone": {
        "commons_train_46063742.jpg",
        "commons_train_63475150.jpg",
        "commons_train_116757415.jpg",
        "commons_train_60538322.jpg",
        "commons_train_41451300.jpg",
        "commons_train_46063622.jpg",
        "commons_train_79409250.jpg",
        "commons_train_148900077.jpg",
        "commons_train_98330841.jpg",
        "commons_train_154089661.jpg",
        "commons_train_162791137.jpg",
        "commons_train_22661293.jpg",
        "commons_train_64034524.jpg",
        "commons_train_189032526.jpg",
        "commons_train_136446950.jpg",
        "commons_train_196834609.jpg",
        "commons_train_144343373.jpg",
        "commons_train_13165765.jpg",
        "commons_train_95198090.jpg",
        "commons_train_30411508.jpg",
        "commons_train_112673444.jpg",
        "commons_train_62413311.jpg",
        "commons_train_150891054.jpg",
        "commons_train_9287539.jpg",
        "commons_train_176945738.jpg",
        "commons_train_62049347.jpg",
        "commons_train_103569827.jpg",
        "commons_train_12331020.jpg",
        "commons_train_196292985.jpg",
        "commons_train_186467420.jpg",
    },
    "newspaper": {
        "commons_train_65959591.jpg",
        "commons_train_65959460.jpg",
        "commons_train_52158551.jpg",
        "commons_train_65959569.jpg",
        "commons_train_65959454.jpg",
        "commons_train_1325624.jpg",
        "commons_train_165513692.jpg",
        "commons_train_135474125.jpg",
        "commons_train_65959445.jpg",
        "commons_train_65959575.jpg",
        "commons_train_65959556.jpg",
        "commons_train_65959503.jpg",
        "commons_train_36632696.jpg",
        "commons_train_38609922.jpg",
        "commons_train_65959436.jpg",
        "commons_train_65959458.jpg",
        "commons_train_65959437.jpg",
        "commons_train_65959510.jpg",
        "commons_train_65959607.jpg",
        "commons_train_52981120.jpg",
        "commons_train_65959490.jpg",
        "commons_train_44099316.jpg",
    },
    "paper_bag": {
        "commons_train_40440507.jpg",
        "commons_train_38644576.jpg",
        "commons_train_40440515.jpg",
        "commons_train_40440495.jpg",
        "commons_train_40440511.jpg",
        "commons_train_41095106.jpg",
        "commons_train_40394143.jpg",
        "commons_train_40440514.jpg",
        "commons_train_40440517.jpg",
        "commons_train_38644578.jpg",
        "commons_train_40063201.jpg",
        "commons_train_40532828.jpg",
        "commons_train_40440494.jpg",
        "commons_train_65501406.jpg",
        "commons_train_65501385.jpg",
        "commons_train_74384964.jpg",
        "commons_train_40440508.jpg",
        "commons_train_40440516.jpg",
        "commons_train_19741646.jpg",
        "commons_train_38644577.jpg",
        "commons_train_52516985.jpg",
        "commons_train_38644573.jpg",
        "commons_train_40440513.jpg",
        "commons_train_40440506.jpg",
        "commons_train_40440505.jpg",
        "commons_train_40063200.jpg",
        "commons_train_74384963.jpg",
        "commons_train_38644575.jpg",
    },
    "paper_cup": {"logo-printed-paper-cup.jpg"},
    "paperboard_packaging": {
        "commons_train_163653894.jpg",
        "commons_train_163368730.jpg",
        "commons_train_188883094.jpg",
        "commons_train_162941568.jpg",
        "commons_train_162622480.jpg",
        "commons_train_163037371.jpg",
        "commons_train_162589379.jpg",
        "commons_train_162623076.jpg",
        "commons_train_116745164.jpg",
        "commons_train_147861454.jpg",
        "commons_train_163035281.jpg",
        "commons_train_163388857.jpg",
        "commons_train_162355498.jpg",
        "commons_train_163379164.jpg",
        "commons_train_163271603.jpg",
        "commons_train_163202372.jpg",
        "commons_train_161871220.jpg",
        "commons_train_51405857.jpg",
        "commons_train_162941567.jpg",
        "commons_train_164339457.jpg",
        "commons_train_163654418.jpg",
        "commons_train_163295573.jpg",
        "commons_train_147472446.jpg",
        "commons_train_116855577.jpg",
        "commons_train_163921711.jpg",
        "commons_train_146095444.jpg",
        "commons_train_163653819.jpg",
    },
    "plastic_food_container": {
        "commons_train_176020433.jpg",
        "commons_train_98244256.jpg",
        "commons_train_45246779.jpg",
        "commons_train_97976654.jpg",
        "commons_train_70023245.jpg",
        "commons_train_131889979.jpg",
        "commons_train_97976643.jpg",
        "commons_train_20989309.jpg",
        "commons_train_163315180.jpg",
        "commons_train_70023244.jpg",
        "commons_train_30245836.jpg",
        "commons_train_67271591.jpg",
        "commons_train_26508927.jpg",
        "commons_train_162822433.jpg",
        "commons_train_17160795.jpg",
        "commons_train_132036399.jpg",
        "commons_train_98244260.jpg",
        "commons_train_47340270.jpg",
        "commons_train_26508926.jpg",
        "commons_train_131889981.jpg",
        "commons_train_89315345.jpg",
        "commons_train_29717701.jpg",
        "commons_train_84014169.jpg",
        "commons_train_23712836.jpg",
        "commons_train_36238585.jpg",
        "commons_train_17160791.jpg",
        "commons_train_74981335.jpg",
    },
    "plastic_takeaway_cup": {
        "set-realistic-plastic-disposable-food-glasses-various-size-white-isolated_1284-28031.avif",
    },
    "plastic_water_bottle": {
        "images.jpeg",
        "commons_train_38424947.jpg",
        "commons_train_38424949.jpg",
        "commons_train_38424945.jpg",
        "commons_train_38424948.jpg",
        "commons_train_107691926.jpg",
        "commons_train_44972629.jpg",
        "commons_train_36739193.jpg",
        "commons_train_70925390.jpg",
        "commons_train_52635345.jpg",
        "commons_train_52635346.jpg",
        "commons_train_52635351.jpg",
        "commons_train_37983326.jpg",
        "commons_train_115912451.jpg",
        "commons_train_2776101.jpg",
        "commons_train_53181561.jpg",
        "commons_train_69124951.jpg",
        "commons_train_79498059.jpg",
        "commons_train_44633366.jpg",
        "commons_train_44974550.jpg",
        "commons_train_143721050.jpg",
        "commons_train_45236832.jpg",
        "commons_train_66969472.jpg",
        "commons_train_92028448.jpg",
        "commons_train_13306588.jpg",
        "commons_train_38227687.jpg",
    },
    "power_bank": {
        "commons_train_187617093.jpg",
        "commons_train_163446152.jpg",
        "commons_train_161137834.jpg",
        "commons_train_187982492.jpg",
        "commons_train_190753243.jpg",
        "commons_train_186469493.jpg",
        "commons_train_156776584.jpg",
        "commons_train_151542755.jpg",
        "commons_train_173430099.jpg",
        "commons_train_190766795.jpg",
        "commons_train_80349510.jpg",
        "commons_train_190126496.jpg",
    },
    "printing_paper": {
        "commons_train_151489390.jpg",
        "commons_train_63652452.jpg",
        "commons_train_124111888.jpg",
        "commons_train_11995021.jpg",
        "commons_train_133234283.jpg",
        "commons_train_69957968.jpg",
        "commons_train_69957967.jpg",
        "commons_train_71044954.jpg",
        "commons_train_12626596.jpg",
        "commons_train_73982618.jpg",
    },
    "tissue": {
        "commons_train_38608852.jpg",
        "commons_train_150681438.jpg",
        "commons_train_88894738.jpg",
        "commons_train_32137425.jpg",
        "commons_train_150681432.jpg",
        "commons_train_150681423.jpg",
        "commons_train_87666282.jpg",
        "commons_train_150681417.jpg",
        "commons_train_36274305.jpg",
        "commons_train_63205462.jpg",
        "commons_train_87466685.jpg",
        "commons_train_150681416.jpg",
        "commons_train_138633178.jpg",
        "commons_train_150681442.jpg",
        "commons_train_150681434.jpg",
        "commons_train_36739002.jpg",
        "commons_train_74476872.jpg",
        "commons_train_196397529.jpg",
        "commons_train_96181342.jpg",
        "commons_train_150681439.jpg",
    },
}

MISCLASSIFIED_TO_UNKNOWN = {
    "aerosol_can": {
        "commons_train_135067533.jpg",
        "commons_train_190156612.jpg",
        "commons_train_164542505.jpg",
        "commons_train_5347770.jpg",
        "commons_train_45225356.jpg",
        "commons_train_55412969.jpg",
        "commons_train_146355142.jpg",
        "commons_train_30250559.jpg",
        "commons_train_192767763.jpg",
        "commons_train_113129508.jpg",
    },
    "chemical_container": {
        "commons_train_44737414.jpg",
        "commons_train_126595154.jpg",
        "commons_train_108383707.jpg",
        "commons_train_126595058.jpg",
        "commons_train_53796974.jpg",
        "commons_train_94643211.jpg",
        "commons_train_108383681.jpg",
        "commons_train_19268685.jpg",
        "commons_train_84473303.jpg",
        "commons_train_85616358.jpg",
        "commons_train_99056673.jpg",
        "commons_train_190549124.jpg",
        "commons_train_127409148.jpg",
        "commons_train_190549880.jpg",
        "commons_train_190549254.jpg",
    },
    "aluminium_drink_can": {
        "trashnet_metal_006.jpg",
        "trashnet_metal_012.jpg",
        "trashnet_metal_014.jpg",
        "trashnet_metal_017.jpg",
        "trashnet_metal_018.jpg",
        "trashnet_metal_020.jpg",
        "trashnet_metal_021.jpg",
        "trashnet_metal_024.jpg",
        "trashnet_metal_026.jpg",
        "commons_train_130854491.jpg",
        "commons_train_130854493.jpg",
        "commons_train_43844691.jpg",
        "commons_train_16161509.jpg",
        "commons_train_16161513.jpg",
        "commons_train_163119832.jpg",
        "commons_train_81793439.jpg",
    },
    "battery": {
        "commons_real_129248138.jpg",
        "commons_real_94332223.jpg",
        "commons_real_97449028.jpg",
    },
    "cardboard_box": {
        "commons_real_94851437.jpg",
        "commons_real_110049916.jpg",
    },
    "plastic_takeaway_cup": {"commons_real_35562638.jpg"},
    "food_waste": {
        "commons_train_79919470.jpg",
        "commons_train_23467496.jpg",
    },
    "printing_paper": {
        "commons_train_162511272.jpg",
        "commons_train_10383803.jpg",
        "commons_train_142101349.jpg",
        "commons_train_83077057.jpg",
        "commons_train_71333565.jpg",
        "commons_train_129502292.jpg",
        "commons_train_10383800.jpg",
        "commons_train_123933520.jpg",
        "commons_train_2547632.jpg",
        "commons_train_90514936.jpg",
        "commons_train_70023731.jpg",
        "commons_train_30298485.jpg",
        "commons_train_149539640.jpg",
        "commons_train_83189396.jpg",
        "commons_train_90697628.jpg",
        "commons_train_129077490.jpg",
        "commons_train_29327403.jpg",
        "commons_train_116396931.jpg",
        "commons_train_162511269.jpg",
        "commons_train_17896734.jpg",
    },
    "vegetable_scraps": {
        "commons_train_55450591.jpg",
        "commons_train_43775303.jpg",
        "commons_train_43422862.jpg",
        "commons_train_55893150.jpg",
        "commons_train_43917368.jpg",
        "commons_train_105181640.jpg",
        "commons_train_41855911.jpg",
        "commons_train_43253165.jpg",
        "commons_train_43355525.jpg",
        "commons_train_44192505.jpg",
        "commons_train_158642785.jpg",
        "commons_train_69104499.jpg",
        "commons_train_43419380.jpg",
        "commons_train_55502664.jpg",
        "commons_train_42121070.jpg",
    },
    "styrofoam_container": {
        "commons_train_24660833.jpg",
        "commons_train_149391532.jpg",
        "commons_train_74847076.jpg",
    },
    "tissue": {
        "commons_train_99843833.jpg",
        "commons_train_148029116.jpg",
        "commons_train_196397533.jpg",
        "commons_train_83250836.jpg",
        "commons_train_148029114.jpg",
        "commons_train_138671705.jpg",
        "commons_train_73830281.jpg",
        "commons_train_148029118.jpg",
        "commons_train_117002368.jpg",
        "commons_train_117002367.jpg",
    },
    "glass_drink_bottle": {
        "commons_train_52649006.jpg",
        "commons_train_154090604.jpg",
        "hf_glass_0004.jpg",
        "hf_glass_0007.jpg",
        "hf_glass_0008.jpg",
        "hf_glass_0014.jpg",
        "hf_glass_0015.jpg",
        "hf_glass_0016.jpg",
        "hf_glass_0018.jpg",
        "hf_glass_0020.jpg",
        "hf_glass_0025.jpg",
        "hf_glass_0027.jpg",
        "hf_glass_0029.jpg",
        "hf_glass_0030.jpg",
        "hf_glass_0033.jpg",
        "hf_glass_0036.jpg",
        "hf_glass_0038.jpg",
        "hf_glass_0039.jpg",
        "hf_glass_0042.jpg",
        "hf_glass_0043.jpg",
        "hf_glass_0044.jpg",
        "hf_glass_0048.jpg",
        "hf_glass_0052.jpg",
        "hf_glass_0053.jpg",
        "hf_glass_0055.jpg",
        "hf_glass_0056.jpg",
        "hf_glass_0059.jpg",
    },
}

RECLASSIFIED = {
    ("aluminium_drink_can", "steel_food_can"): {
        "trashnet_metal_000.jpg",
        "trashnet_metal_007.jpg",
        "trashnet_metal_008.jpg",
        "trashnet_metal_009.jpg",
        "trashnet_metal_010.jpg",
        "trashnet_metal_015.jpg",
        "trashnet_metal_016.jpg",
        "trashnet_metal_019.jpg",
        "trashnet_metal_022.jpg",
    },
    ("food_waste", "vegetable_scraps"): {
        "hf_biological_0005.jpg",
        "hf_biological_0006.jpg",
        "hf_biological_0008.jpg",
        "hf_biological_0010.jpg",
        "hf_biological_0013.jpg",
        "hf_biological_0015.jpg",
        "hf_biological_0018.jpg",
        "hf_biological_0020.jpg",
        "hf_biological_0022.jpg",
        "hf_biological_0026.jpg",
        "hf_biological_0033.jpg",
        "hf_biological_0038.jpg",
        "hf_biological_0047.jpg",
        "hf_biological_0048.jpg",
        "hf_biological_0059.jpg",
    },
    ("unknown", "printing_paper"): {
        "trashnet_paper_009.jpg",
        "trashnet_paper_012.jpg",
        "trashnet_paper_013.jpg",
        "trashnet_paper_019.jpg",
        "trashnet_paper_020.jpg",
        "trashnet_paper_021.jpg",
        "trashnet_paper_022.jpg",
        "trashnet_paper_023.jpg",
        "trashnet_paper_028.jpg",
        "trashnet_paper_029.jpg",
    },
    ("unknown", "newspaper"): {
        "trashnet_paper_000.jpg",
        "trashnet_paper_002.jpg",
        "trashnet_paper_003.jpg",
        "trashnet_paper_005.jpg",
        "trashnet_paper_006.jpg",
        "trashnet_paper_007.jpg",
        "trashnet_paper_008.jpg",
        "trashnet_paper_010.jpg",
        "trashnet_paper_011.jpg",
        "trashnet_paper_014.jpg",
        "trashnet_paper_015.jpg",
        "trashnet_paper_017.jpg",
        "trashnet_paper_025.jpg",
        "trashnet_paper_027.jpg",
    },
    ("styrofoam_container", "plastic_food_container"): {
        "commons_train_124243920.jpg",
    },
}


def quarantine(path: Path, reason: str) -> None:
    relative = path.relative_to(TRAIN_ROOT)
    destination = QUARANTINE_ROOT / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    shutil.move(str(path), str(destination))
    with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
        manifest.write(
            json.dumps(
                {
                    "original": str((TRAIN_ROOT / relative).relative_to(ROOT)),
                    "quarantined": str(destination.relative_to(ROOT)),
                    "reason": reason,
                }
            )
            + "\n"
        )
    print(f"quarantined {relative} ({reason})")


def main() -> None:
    QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)

    for class_name, filenames in EXPLICIT_BAD.items():
        for filename in filenames:
            path = TRAIN_ROOT / class_name / filename
            if path.exists():
                quarantine(path, "multiple items, cluttered scene, or visible stock watermark")

    # Preserve single-item negatives, but do not leave them in a target class.
    unknown_destination = TRAIN_ROOT / "unknown"
    unknown_destination.mkdir(parents=True, exist_ok=True)
    for class_name, filenames in MISCLASSIFIED_TO_UNKNOWN.items():
        for filename in filenames:
            path = TRAIN_ROOT / class_name / filename
            if not path.exists():
                continue
            destination = unknown_destination / f"from_{class_name}_{filename}"
            shutil.move(str(path), str(destination))
            with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
                manifest.write(
                    json.dumps(
                        {
                            "original": str(path.relative_to(ROOT)),
                            "moved_to": str(destination.relative_to(ROOT)),
                            "reason": "single object, but not the target class",
                        }
                    )
                    + "\n"
                )
            print(f"moved {path.relative_to(ROOT)} to unknown/")

    for (source_class, target_class), filenames in RECLASSIFIED.items():
        destination_folder = TRAIN_ROOT / target_class
        destination_folder.mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            path = TRAIN_ROOT / source_class / filename
            if not path.exists():
                continue
            destination = destination_folder / f"from_{source_class}_{filename}"
            shutil.move(str(path), str(destination))
            with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
                manifest.write(
                    json.dumps(
                        {
                            "original": str(path.relative_to(ROOT)),
                            "moved_to": str(destination.relative_to(ROOT)),
                            "reason": f"manual visual review reclassified the item as {target_class}",
                        }
                    )
                    + "\n"
                )
            print(f"moved {path.relative_to(ROOT)} to {target_class}/")

    # The file is a single car battery, so it is more useful as a battery
    # example than as an unknown example. Move it without discarding it.
    misplaced = TRAIN_ROOT / "unknown" / "images (1).jpeg"
    if misplaced.exists():
        destination = TRAIN_ROOT / "battery" / misplaced.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(misplaced), str(destination))
        with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
            manifest.write(
                json.dumps(
                    {
                        "original": "training/dataset/train/unknown/images (1).jpeg",
                        "moved_to": "training/dataset/train/battery/images (1).jpeg",
                        "reason": "single battery item was in the unknown folder",
                    }
                )
                + "\n"
            )
        print("moved unknown/images (1).jpeg to battery/")

    # TrashBox samples are held separately until their reuse terms and visual
    # composition are confirmed; the reviewed samples contain clutter or piles.
    for path in sorted(TRAIN_ROOT.glob("*/trashbox_*.jpg")):
        quarantine(path, "unverified source and reviewed samples contain multiple items or clutter")


if __name__ == "__main__":
    main()
