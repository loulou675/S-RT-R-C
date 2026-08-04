export function StatusBlock({ message }: { message: string }) {
  return (
    <div className="status-block" aria-live="polite" aria-busy="true">
      <span />
      <p>{message}</p>
    </div>
  )
}
