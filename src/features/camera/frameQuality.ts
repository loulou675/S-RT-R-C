const DARK_LUMINANCE = 52
const GLARE_LUMINANCE = 222
const MIN_CONTRAST = 16
const MIN_SHARPNESS = 3.5
const MIN_FOREGROUND_RATIO = 0.08
const MAX_FOREGROUND_RATIO = 0.9

export function measureFrameQuality(sample: Uint8ClampedArray, width: number) {
  const luminance = averageLuminance(sample)
  if (luminance < DARK_LUMINANCE) return { good: false, message: 'Too dark. Move to brighter, even light.' }
  if (luminance > GLARE_LUMINANCE) return { good: false, message: 'Too much glare. Tilt the item or soften the light.' }

  const height = sample.length / 4 / width
  const borderSize = Math.max(2, Math.round(Math.min(width, height) * 0.12))
  let borderRed = 0
  let borderGreen = 0
  let borderBlue = 0
  let borderPixels = 0
  const luminances: number[] = []

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4
      const red = sample[index]
      const green = sample[index + 1]
      const blue = sample[index + 2]
      luminances.push(red * 0.2126 + green * 0.7152 + blue * 0.0722)
      if (x < borderSize || x >= width - borderSize || y < borderSize || y >= height - borderSize) {
        borderRed += red
        borderGreen += green
        borderBlue += blue
        borderPixels += 1
      }
    }
  }

  const mean = luminances.reduce((total, value) => total + value, 0) / luminances.length
  const contrast = Math.sqrt(
    luminances.reduce((total, value) => total + (value - mean) ** 2, 0) / luminances.length,
  )
  const borderMean = [borderRed / borderPixels, borderGreen / borderPixels, borderBlue / borderPixels]
  let foregroundPixels = 0
  let interiorPixels = 0
  let sharpness = 0
  let sharpnessComparisons = 0

  for (let y = borderSize; y < height - borderSize; y += 1) {
    for (let x = borderSize; x < width - borderSize; x += 1) {
      const index = (y * width + x) * 4
      const redDelta = sample[index] - borderMean[0]
      const greenDelta = sample[index + 1] - borderMean[1]
      const blueDelta = sample[index + 2] - borderMean[2]
      if (redDelta ** 2 + greenDelta ** 2 + blueDelta ** 2 > 28 ** 2) foregroundPixels += 1
      interiorPixels += 1

      const luminanceIndex = y * width + x
      sharpness += Math.abs(luminances[luminanceIndex] - luminances[luminanceIndex - 1])
      sharpness += Math.abs(luminances[luminanceIndex] - luminances[luminanceIndex - width])
      sharpnessComparisons += 2
    }
  }

  const foregroundRatio = foregroundPixels / interiorPixels
  const averageSharpness = sharpness / sharpnessComparisons
  if (foregroundRatio < MIN_FOREGROUND_RATIO && contrast < MIN_CONTRAST * 1.7) {
    return { good: false, message: 'Move one item into the yellow square.' }
  }
  if (foregroundRatio > MAX_FOREGROUND_RATIO) {
    return { good: false, message: 'Move the item slightly farther away so its edges fit in the square.' }
  }
  if (contrast < MIN_CONTRAST) {
    return { good: false, message: 'The item is not clear from the background yet.' }
  }
  if (averageSharpness < MIN_SHARPNESS) {
    return { good: false, message: 'Hold steady and let the camera focus.' }
  }

  return { good: true, message: 'Frame quality is good.' }
}

function averageLuminance(sample: Uint8ClampedArray) {
  let luminance = 0

  for (let index = 0; index < sample.length; index += 4) {
    luminance += sample[index] * 0.2126
    luminance += sample[index + 1] * 0.7152
    luminance += sample[index + 2] * 0.0722
  }

  return luminance / (sample.length / 4)
}
