# SỌRT RÁC - AI training

Chỉ cần quan tâm các mục sau:

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

## Khi có ảnh điện thoại mới

1. Đổi ảnh sang JPG/JPEG và đặt vào đúng folder lớp trong `dataset/train/`.
2. Không đưa hai ảnh gần giống nhau của cùng một vật thể vào cả train và test.
3. Tạo lại `classifier_dataset/` có tách theo `objectID` trước khi train.
4. Chạy kiểm tra dữ liệu, train model mới rồi đánh giá trên ảnh test chưa từng
   dùng để train.
5. Chỉ cài model mới vào website khi độ chính xác phân loại thùng và các lớp yếu
   đều tăng.

Chi tiết cách chụp và đặt tên ảnh nằm trong `PHOTO_COLLECTION_CHECKLIST.md`.

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
