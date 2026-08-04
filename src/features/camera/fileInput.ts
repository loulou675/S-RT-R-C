import { validateImageFile } from '../../lib/validation/imageValidation'

export async function fileToDataUrl(file: File) {
  await validateImageFile(file)

  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}
