import { afterEach, describe, expect, it, vi } from 'vitest'
import { isMemoryConstrainedDevice, preferredCameraSize } from './deviceCapabilities'

const originalUserAgent = navigator.userAgent
const originalPlatform = navigator.platform
const originalMaxTouchPoints = navigator.maxTouchPoints
const originalMatchMedia = window.matchMedia

afterEach(() => {
  Object.defineProperty(navigator, 'userAgent', { configurable: true, value: originalUserAgent })
  Object.defineProperty(navigator, 'platform', { configurable: true, value: originalPlatform })
  Object.defineProperty(navigator, 'deviceMemory', { configurable: true, value: undefined })
  Object.defineProperty(navigator, 'maxTouchPoints', { configurable: true, value: originalMaxTouchPoints })
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: originalMatchMedia })
  vi.restoreAllMocks()
})

describe('device capabilities', () => {
  it('uses the mobile inference path and 640x480 camera request on iPhone', () => {
    Object.defineProperty(navigator, 'userAgent', { configurable: true, value: 'Mozilla/5.0 (iPhone)' })
    Object.defineProperty(navigator, 'platform', { configurable: true, value: 'iPhone' })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: true } as MediaQueryList)),
    })

    expect(isMemoryConstrainedDevice()).toBe(true)
    expect(preferredCameraSize()).toEqual({ width: 640, height: 480 })
  })

  it('keeps the larger camera request on a desktop with sufficient memory', () => {
    Object.defineProperty(navigator, 'userAgent', { configurable: true, value: 'Mozilla/5.0 (Macintosh)' })
    Object.defineProperty(navigator, 'platform', { configurable: true, value: 'MacIntel' })
    Object.defineProperty(navigator, 'deviceMemory', { configurable: true, value: 8 })
    Object.defineProperty(navigator, 'maxTouchPoints', { configurable: true, value: 0 })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: false } as MediaQueryList)),
    })

    expect(isMemoryConstrainedDevice()).toBe(false)
    expect(preferredCameraSize()).toEqual({ width: 1280, height: 720 })
  })
})
