import { expect, test, type Page } from '@playwright/test'
import { deflateSync } from 'node:zlib'

test('successful uploaded-image flow in mock mode', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('sot-rac-mock-item', 'plastic_takeaway_cup'))
  await uploadMockImage(page)

  await expect(page.getByText(/Plastic takeaway cup/i).first()).toBeVisible()
  await expect(page.getByText(/Clean Plastic/).first()).toBeVisible()
})

test('AI failure followed by retake', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('sot-rac-mock-item', 'force_error'))
  await page.goto('/')
  await setImageFile(page)

  await expect(page.getByText(/this image matched Unknown/i)).toBeVisible()
  await expect(page).toHaveURL(/\/$/)
})

test('manual search to disposal result', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel(/Search waste item/i).fill('pizza')
  await page.getByRole('button', { name: /Pizza box/i }).click()

  await expect(page).toHaveURL(/\/\?item=pizza_box&source=search$/)
  await expect(page.getByText(/Paper & Cardboard/).first()).toBeVisible()
})

test('plastic cup condition flow', async ({ page }) => {
  await page.goto('/#/search')
  await page.getByPlaceholder(/Search for an item/i).fill('plastic cup')
  await page.getByRole('button', { name: /Plastic takeaway cup/i }).click()
  await page.getByRole('button', { name: /Cannot be cleaned/i }).click()

  await expect(page.getByText(/Landfill/).first()).toBeVisible()
})

test('special-handling item flow', async ({ page }) => {
  await page.goto('/#/search')
  await page.getByPlaceholder(/Search for an item/i).fill('battery')
  await page.getByRole('button', { name: /^Battery/i }).click()

  await expect(page.getByText(/Battery/i).first()).toBeVisible()
  await expect(page.getByText(/Special handling required/i)).toBeVisible()
})

test('camera permission denied flow', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: () => Promise.reject(new DOMException('Permission denied', 'NotAllowedError')),
      },
      configurable: true,
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: /^Start Scanning/i }).dispatchEvent('click')
  await expect(page.getByText(/Camera access was blocked/i)).toBeVisible()
})

test('history stores a searched item', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel(/Search waste item/i).fill('fruit peel')
  await page.getByRole('button', { name: /Fruit peel/i }).click()
  await page.getByRole('button', { name: /Scan history/i }).click()

  await expect(page).toHaveURL(/\/history$/)
  await expect(page.getByText(/Fruit peel/i).first()).toBeVisible()
  await expect(page.getByText(/Organic Waste/i).first()).toBeVisible()
})

async function uploadMockImage(page: Page) {
  await page.goto('/')
  await setImageFile(page)
}

async function setImageFile(page: Page) {
  await page.getByRole('button', { name: /Upload an Image/i }).click()
  await page.setInputFiles('input[type="file"]', {
    name: 'waste-item.png',
    mimeType: 'image/png',
    buffer: createPng(320, 320),
  })
}

function createPng(width: number, height: number) {
  const rows: Buffer[] = []

  for (let y = 0; y < height; y += 1) {
    const row = Buffer.alloc(1 + width * 4)
    row[0] = 0

    for (let x = 0; x < width; x += 1) {
      const offset = 1 + x * 4
      row[offset] = 235
      row[offset + 1] = 241
      row[offset + 2] = 230
      row[offset + 3] = 255
    }

    rows.push(row)
  }

  const header = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
  const ihdr = pngChunk('IHDR', Buffer.concat([uint32(width), uint32(height), Buffer.from([8, 6, 0, 0, 0])]))
  const idat = pngChunk('IDAT', deflateSync(Buffer.concat(rows)))
  const iend = pngChunk('IEND', Buffer.alloc(0))

  return Buffer.concat([header, ihdr, idat, iend])
}

function pngChunk(type: string, data: Buffer) {
  const typeBuffer = Buffer.from(type)
  return Buffer.concat([uint32(data.length), typeBuffer, data, uint32(crc32(Buffer.concat([typeBuffer, data])))])
}

function uint32(value: number) {
  const buffer = Buffer.alloc(4)
  buffer.writeUInt32BE(value >>> 0)
  return buffer
}

function crc32(buffer: Buffer) {
  let crc = 0xffffffff

  for (const byte of buffer) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
    }
  }

  return (crc ^ 0xffffffff) >>> 0
}
