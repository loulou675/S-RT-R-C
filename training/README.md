# SỌRT RÁC - AI training

Chỉ cần quan tâm các mục sau:

- `TEAMMATE_SETUP.md`: cách khôi phục dataset/checkpoint trên một máy mới.
- `PHOTO_COLLECTION_CHECKLIST.md`: danh sách và cách chụp ảnh mới.
- `dataset/`: ảnh gốc đã thu thập. Thêm ảnh mới vào đúng lớp trong
  `dataset/train/<class_code>/`.
- `classifier_dataset/`: dữ liệu đã chia sẵn để train model nhận diện vật thể.
- `component_dataset/`: ảnh và nhãn khung của model nhận diện nắp và phần thức
  ăn nhìn thấy được.
- `checkpoints/`: hai checkpoint tốt nhất hiện tại để đánh giá hoặc train tiếp.
- `classes.json` và `component_classes.json`: tên lớp chính thức, không tự đổi
  thứ tự.
- `source_manifests/`: nguồn gốc dữ liệu. Không cần đọc thường xuyên nhưng phải
  giữ lại.

Model website đang sử dụng nằm tại `public/models/`. Không thay các file ở đó
cho đến khi model mới được kiểm tra tốt hơn model hiện tại.

## Lấy feedback đã duyệt từ Supabase

Tạo file `.env.reviewer` ở thư mục gốc. Key này chỉ dùng ở máy reviewer, không
đặt tên bắt đầu bằng `VITE_` và không commit lên Git:

```dotenv
SUPABASE_REVIEWER_KEY=your_secret_or_service_role_key
```

Sau đó chạy:

```bash
python3 training/import_supabase_feedback.py
```

Ảnh `pending` chỉ được tải vào `training/feedback_review/` để duyệt. Chỉ ảnh có
trạng thái `accepted` hoặc `relabeled` mới được sao chép vào đúng class trong
`training/dataset/train/`. Script không đưa ghi chú của người dùng vào manifest.

## Khi có ảnh điện thoại mới

1. Đổi ảnh sang JPG/JPEG và đặt vào đúng folder lớp trong `dataset/train/`.
2. Không đưa hai ảnh gần giống nhau của cùng một vật thể vào cả train và test.
3. Tạo lại `classifier_dataset/` có tách theo `objectID` trước khi train.
4. Chạy kiểm tra dữ liệu, train model mới rồi đánh giá trên ảnh test chưa từng
   dùng để train.
5. Chỉ cài model mới vào website khi độ chính xác phân loại thùng và các lớp yếu
   đều tăng.

Chi tiết cách chụp và đặt tên ảnh nằm trong `PHOTO_COLLECTION_CHECKLIST.md`.

Tên nhóm ảnh thật có thể bắt đầu bằng `clean_`, `dirty_` hoặc `used_`. Script
`import_real_images.py` ghi trạng thái nhìn thấy này vào trường
`visibleCondition` của manifest nhưng vẫn train theo loại vật thể. Muốn nhận
diện sạch/bẩn như một kết quả riêng cần một dataset cân bằng, trong đó cùng một
loại vật thể có đủ cả ảnh sạch và bẩn chụp trong nhiều bối cảnh.

Với ảnh paired của cùng một vật thể, dùng một `objectID` chung trước dấu `__`
và đặt trạng thái ở token tiếp theo, ví dụ
`obj_paper_cup_pair_a__clean_empty__IMG_0001.heic` và
`obj_paper_cup_pair_a__dirty_residue__IMG_0002.heic`. Importer giữ toàn bộ pair
trong cùng split, đồng thời tạo ảnh chuẩn hóa tại
`condition_dataset/<split>/<condition>/` để chuẩn bị cho model condition riêng.

## Nhập nhãn parts từ ảnh thật

Các box đã duyệt nằm trong `real_component_annotations.json`. Nhập chúng vào
dataset detector bằng lệnh:

```bash
.training-venv/bin/python training/import_real_component_images.py
```

Script chỉ thay các file có tiền tố `real_component_`, giữ nguyên dữ liệu cũ và
ghi lại danh sách nguồn tại `source_manifests/real-component-import.json`.
Bộ nhãn hiện tại có 70 ảnh: 23 box `closure`, 26 box `food` và 21 ảnh
hard-negative. Tất cả nằm trong train vì nhiều ảnh chụp lặp cùng một vật thể;
không dùng chúng để báo cáo điểm test.

## Bổ sung lớp Unknown

Chạy collector Open Images để tạo crop các vật thể không thuộc hệ thống
phân loại:

```bash
.training-venv/bin/python training/collect_openimages_unknown.py
```

Mặc định script tạo tối đa 660 ảnh cân bằng theo 10 nhóm, loại nhãn rác
mục tiêu, crop quanh vật thể và loại ảnh gần trùng. Script chỉ thay các file
có tiền tố `openimages_unknown_`.

## Tái tạo phần Organic

1. Chạy `collect_openimages_organic.py` để bổ sung crop cho classifier và box
   `food` cho component detector. Script có thể chạy lại an toàn.
2. Train classifier bằng `train_and_export.py`, sau đó dùng
   `evaluate_per_class.py` để kiểm tra riêng ba lớp Organic.
3. Nếu box component mất cân bằng, chạy
   `oversample_component_class.py --class-id 0 --copies 3`. Chỉ train được nhân
   bản; validation và test phải giữ nguyên.
4. Fine-tune component detector bằng `train_component_detector.py`. Với model
   đã học food, dùng learning rate thấp để tránh quên lớp cũ.
