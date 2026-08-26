import { Link } from 'react-router-dom'

export function AboutPage() {
  return (
    <section className="flow-layout about-layout">
      <div className="page-heading about-heading">
        <h1>
          <span>AI identifies the item.<span className="vi-note">AI nhận diện vật thể.</span></span>
          <span>Sorting guidance decides the bin.<span className="vi-note">Hướng dẫn phân loại xác định đúng thùng.</span></span>
        </h1>
        <p>
          The app processes one still image in the browser, maps it to a known waste item, then checks curated disposal guidance. Images are retained only when a user chooses to submit post-scan feedback for review.
          <span className="vi-note">Ứng dụng xử lý một ảnh tĩnh trong trình duyệt, đối chiếu với vật thể đã biết rồi kiểm tra hướng dẫn phân loại. Ảnh chỉ được lưu khi người dùng chủ động gửi phản hồi sau khi quét.</span>
        </p>
      </div>
      <div className="about-card-grid">
        <section className="about-card">
          <h2>Local data disclaimer</h2>
          <p>
            This guidance applies to the selected waste station and should be updated when signage or local sorting policy changes.
            <span className="vi-note">Hướng dẫn áp dụng cho điểm thu gom đã chọn và cần được cập nhật khi biển chỉ dẫn hoặc quy định phân loại thay đổi.</span>
          </p>
        </section>
        <section className="about-card">
          <h2>Anonymous usage analytics</h2>
          <p>
            We count visits, visible time, pages, feature actions, and broad device type using random browser and session identifiers. We do not include names, scanned images, or full referral URLs, and browser Do Not Track is respected.
            <span className="vi-note">Chúng mình ghi nhận lượt truy cập, thời gian hiển thị, trang, thao tác tính năng và loại thiết bị chung bằng mã trình duyệt và phiên ngẫu nhiên. Dữ liệu không gồm tên, ảnh quét hay toàn bộ đường dẫn giới thiệu và tôn trọng cài đặt Do Not Track.</span>
          </p>
        </section>
        <section className="about-card">
          <h2>Model requirement</h2>
          <p>
            The repository includes the application and AI integration layer. Accurate custom recognition requires a trained ONNX model and labels that match the intended sorting environment.
            <span className="vi-note">Kho mã nguồn gồm ứng dụng và lớp tích hợp AI. Nhận diện chính xác cần mô hình ONNX đã được huấn luyện cùng bộ nhãn phù hợp với môi trường phân loại.</span>
          </p>
        </section>
      </div>
      <Link className="primary-action large about-cta" to="/">
        <span>Start scanning</span>
      </Link>
    </section>
  )
}
