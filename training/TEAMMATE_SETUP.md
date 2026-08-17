# Khoi phuc AI tren may cong su

Dataset va checkpoint huan luyen khong nam tren GitHub vi dung luong hon 2 GB.
GitHub chi chua source code, model ONNX dang chay tren website, labels va cac
script huan luyen. Hai goi handoff bo sung du lieu bi `.gitignore` loai ra.

## 1. Lay dung branch

Trong GitHub Desktop, chon repository `SORT RAC`, fetch/pull branch `chi-lou`.
Khong copy rieng folder `src`; can lay toan bo repository.

## 2. Nhan hai file ZIP

- `SORT_RAC_AI_CORE_36CLASS.zip`: dataset classifier 36 lop, checkpoint co the
  train tiep, condition samples va model dang dung.
- `SORT_RAC_AI_PARTS.zip`: dataset box cho `food`/`closure`, checkpoint detector
  va model parts dang dung.

Hai file qua lon de commit GitHub thong thuong. Gui chung qua Google Drive,
OneDrive, AirDrop hoac o cung. Giai nen **tai repository root**, la folder co
`package.json`. Sau khi giai nen phai co:

```text
training/classifier_dataset/train/
training/checkpoints/waste_classifier.pt
training/component_dataset/data.yaml
training/checkpoints/component_detector.pt
```

## 3. Kiem tra tu dong

```bash
python3 training/verify_teammate_setup.py --with-components
```

Ket qua dung phai ket thuc bang `PASS`. Canh bao mot lop test it anh khong ngan
app chay; dong `Setup is incomplete` moi la loi can sua.

## 4. Chay website

```bash
pnpm install
pnpm dev
```

Neu may chua co `pnpm`, cai Node.js LTS, sau do chay `corepack enable`. Co the
nhờ Codex tren may do cai dependency va chay hai lenh tren.

## 5. Tao moi truong train

```bash
python3 -m venv .training-venv
source .training-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r training/requirements-training.txt
```

## 6. Train candidate, khong ghi de model dang chay

Mac Apple Silicon:

```bash
.training-venv/bin/python training/train_and_export.py \
  --model training/checkpoints/waste_classifier.pt \
  --epochs 30 --batch 16 --device mps --name teammate-candidate-v1
```

Windows/NVIDIA thay `--device mps` bang `--device 0`. May khong co GPU dung
`--device cpu` va giam `--batch` xuong 8.

Khong them `--install` o lan train dau. Model candidate nam trong
`training/runs/teammate-candidate-v1/`. Danh gia truoc khi thay model website:

```bash
.training-venv/bin/python training/evaluate_per_class.py \
  --model training/runs/teammate-candidate-v1/weights/best.pt
```

Chi copy model moi vao `public/models/` khi no tot hon baseline ghi trong
`public/models/MODEL_CARD.md`, dac biet o bin accuracy, unknown rejection va
hazardous recall.

## Tao lai goi handoff tren may chinh

```bash
python3 training/create_teammate_bundles.py
```

Script tao hai file ZIP va checksum tai folder
`../SORT_RAC_TEAMMATE_HANDOFF/`. Folder nay nam ngoai repository nen khong bi
push nham len GitHub.
