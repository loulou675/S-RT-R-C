type NavigatorWithMemory = Navigator & { deviceMemory?: number }

export function isMemoryConstrainedDevice() {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return false

  const navigatorWithMemory = navigator as NavigatorWithMemory
  const isIos = /iPad|iPhone|iPod/i.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  const isMobileViewport = window.matchMedia('(max-width: 860px)').matches
  const hasLowReportedMemory = typeof navigatorWithMemory.deviceMemory === 'number'
    && navigatorWithMemory.deviceMemory <= 4

  return isIos || isMobileViewport || hasLowReportedMemory
}

export function preferredCameraSize() {
  return isMemoryConstrainedDevice()
    ? { width: 640, height: 480 }
    : { width: 1280, height: 720 }
}
