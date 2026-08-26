export function StatusBlock({ message }: { message: string }) {
  const messageVi = translateStatus(message)
  return (
    <div className="status-block" aria-live="polite" aria-busy="true">
      <span />
      <p>{message}{messageVi ? <span className="vi-note">{messageVi}</span> : null}</p>
    </div>
  )
}

function translateStatus(message: string) {
  if (message.startsWith('Identifying item')) return 'Đang nhận diện vật thể. Lần quét đầu tiên có thể lâu hơn một chút.'
  if (message.startsWith('Checking the object framing')) return 'Đang kiểm tra vị trí vật thể trong khung.'
  if (message.startsWith('Retrying with the detected object')) return 'Đang thử lại với vật thể đã phát hiện.'
  if (message.startsWith('Checking disposal guidance')) return 'Đang kiểm tra hướng dẫn phân loại.'
  if (message.startsWith('Preparing image')) return 'Đang chuẩn bị hình ảnh.'
  return undefined
}
