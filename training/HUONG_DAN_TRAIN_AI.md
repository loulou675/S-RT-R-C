# Hướng dẫn train AI cho SỌRT RÁC

## Model đang làm gì?

SỌRT RÁC dùng image classification: người dùng đặt **một vật thể** vào ô giữa
camera, app tự cắt đúng vùng đó thành ảnh 224 x 224 và model trả về một mã vật
thể. Rule engine của app mới là phần đổi mã vật thể thành một trong sáu nhóm
rác và checklist xử lý.

Không train trực tiếp tên thùng nếu hai vật thể nhìn khác nhau. Không tạo lớp
`dirty_plastic`, `wet_paper` hay `full_bottle`: sạch/bẩn, khô/ướt và rỗng/còn
chất lỏng là điều kiện xử lý, không phải hình dạng ổn định để classifier học.

Danh sách 33 lớp chính thức nằm trong `training/classes.json`. Ví dụ:

- beer can, soft-drink can -> `aluminium_drink_can`;
- fruit, bread, leftover meal -> `food_waste`;
- book, notebook và sheet paper có thể tìm kiếm trong app, nhưng model chỉ tách
  các lớp có đủ ảnh và khác biệt hình ảnh rõ;
- đồ ngoài danh sách, tay, mặt người, nền trống và cảnh lộn xộn -> `unknown`.

## Chuẩn bị môi trường

Khuyến nghị Python 3.11 hoặc 3.12. Tạo môi trường riêng trong project:

```bash
python3 -m venv training/.venv
source training/.venv/bin/activate
python -m pip install -U pip
python -m pip install -r training/requirements-training.txt
```

Mac Apple Silicon dùng MPS. Máy Windows/Linux có NVIDIA GPU dùng CUDA. Google
Colab cũng chạy được: upload repository và dataset vào Drive, cài requirements,
sau đó dùng `--device 0`.

## Bổ sung ảnh đúng cách

Mỗi lớp nên có tối thiểu 300 ảnh gốc đã review; 800-1.500 ảnh/lớp tốt hơn cho
bao bì có nhiều kiểu dáng. Đặt ảnh vào:

```text
training/dataset/train/<class_code>/
```

Một ảnh tốt cần:

1. Có đúng vật thể của lớp và không bị watermark.
2. Vật thể chiếm khoảng 55-85% khung hình.
3. Có nhiều nhãn hiệu, màu, góc xoay, vật thể bị móp và mức ánh sáng khác nhau.
4. Có ảnh từ điện thoại, webcam, bàn, sàn và tay cầm vật thể.
5. Không phải ảnh gần như giống hệt nhau từ cùng một video/burst.

Mọi ảnh tải từ internet phải có manifest ghi URL, tác giả và license. Xem các
nguồn đã duyệt trong `training/DATA_SOURCES.md`. Không dùng TrashBox khi chưa có
giấy phép rõ ràng.

## Kiểm duyệt và chia dữ liệu

Tạo contact sheet:

```bash
python training/make_review_contact_sheets.py --samples 40
```

Mở `training/review_sheets/` và loại mọi ảnh sai nhãn. Sau đó xóa bản curated
cũ nếu đây là một lần train mới, rồi tạo split cố định:

```bash
python training/prepare_curated_splits.py
python training/augment_minority_classes.py --target 60
python training/validate_dataset.py --data training/dataset_curated --minimum 300
```

Ở bản thử nghiệm ít dữ liệu, có thể hạ `--minimum` để chạy kỹ thuật, nhưng không
được gọi model đó là production-ready. Chỉ augment thư mục train; tuyệt đối
không augment hoặc dùng lại ảnh validation/test.

## Train và xuất ONNX

Mac Apple Silicon:

```bash
python training/train_and_export.py \
  --data training/dataset_curated \
  --epochs 100 \
  --batch 32 \
  --device mps
```

NVIDIA/Colab đổi thành `--device 0`. Nếu hết bộ nhớ, giảm batch xuống 16 hoặc 8.
Script sẽ chọn checkpoint tốt nhất, đánh giá test split, xuất ONNX và thay hai
file mà web sử dụng:

```text
public/models/waste_classifier.onnx
public/models/labels.json
```

Không sửa thứ tự index trong `labels.json` bằng tay vì index phải khớp chính
xác với output của ONNX.

## Tiêu chí chấp nhận

Checkpoint hiện tại (vòng train thứ hai) đạt 58,2% top-1, 85,0% top-5, 58,0%
macro recall, 59,1% macro recall cho nhóm hazardous và 67,4% chọn đúng một
trong sáu thùng cho vật phẩm đã biết trên 153 ảnh test chưa qua augmentation.
Đây là checkpoint MVP để kiểm thử luồng web, chưa đạt tiêu chí phát hành. Xem
chi tiết trong `public/models/MODEL_CARD.md`.

Không chỉ nhìn train accuracy. Cần xem confusion matrix và test bằng ảnh mới
qua camera thật. Mục tiêu trước khi phát hành:

- macro top-1 test >= 85%;
- recall từng lớp thường >= 80%;
- recall các lớp hazardous >= 90%;
- ảnh không thuộc danh sách phải về `unknown` hoặc bị từ chối vì confidence thấp;
- mỗi lớp được thử ít nhất 30 ảnh mới, ba nền và ba điều kiện sáng khác nhau.

Nếu hai lớp liên tục nhầm nhau, ưu tiên sửa nhãn và thêm hard examples. Nếu hai
vật thể nhìn gần như giống nhau và cùng cách xử lý, hãy gộp lớp. Không hạ ngưỡng
confidence chỉ để demo trông như nhận được nhiều vật hơn.

## Đưa model mới lên web

1. Bảo đảm `.env` có `VITE_USE_MOCK_VISION=false`.
2. Build lại app và bản GitHub Pages.
3. Commit model, labels và thư mục `docs` mới.
4. Mở website bằng cửa sổ ẩn danh để tránh cache model cũ.
5. Thử upload và camera với cả ảnh đúng lớp lẫn ảnh `unknown`.

Nếu model chỉ chạy tốt trên ảnh đã crop đẹp nhưng kém trên camera, cần bổ sung
ảnh chụp theo đúng ô giữa camera của app, không thêm bước crop cho người dùng.
