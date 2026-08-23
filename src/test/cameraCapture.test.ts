import { averagePixelDifference, measureFrameQuality } from '../features/camera/frameQuality'

const SIZE = 64

function solidFrame(value: number) {
  const pixels = new Uint8ClampedArray(SIZE * SIZE * 4)
  for (let index = 0; index < pixels.length; index += 4) {
    pixels[index] = value
    pixels[index + 1] = value
    pixels[index + 2] = value
    pixels[index + 3] = 255
  }
  return pixels
}

function setPixel(pixels: Uint8ClampedArray, x: number, y: number, value: number) {
  const index = (y * SIZE + x) * 4
  pixels[index] = value
  pixels[index + 1] = value
  pixels[index + 2] = value
}

describe('automatic camera frame checks', () => {
  it('keeps a blank frame in the adjusting state', () => {
    const result = measureFrameQuality(solidFrame(150), SIZE)

    expect(result.good).toBe(false)
    expect(result.message).toContain('Move one item')
  })

  it('accepts a centered, contrasted, sharp object', () => {
    const pixels = solidFrame(205)
    for (let y = 17; y < 47; y += 1) {
      for (let x = 17; x < 47; x += 1) {
        setPixel(pixels, x, y, (x + y) % 6 < 3 ? 55 : 95)
      }
    }

    expect(measureFrameQuality(pixels, SIZE).good).toBe(true)
  })

  it('rejects an item that fills almost the entire focus zone', () => {
    const pixels = solidFrame(205)
    for (let y = 8; y < 56; y += 1) {
      for (let x = 8; x < 56; x += 1) setPixel(pixels, x, y, 55)
    }

    const result = measureFrameQuality(pixels, SIZE)
    expect(result.good).toBe(false)
    expect(result.message).toContain('farther away')
  })

  it('measures movement independently from overall brightness', () => {
    const previous = solidFrame(120)
    const current = solidFrame(120)
    for (let y = 20; y < 44; y += 1) {
      for (let x = 20; x < 44; x += 1) setPixel(current, x, y, 180)
    }

    expect(averagePixelDifference(previous, previous)).toBe(0)
    expect(averagePixelDifference(previous, current)).toBeGreaterThan(5)
  })
})
