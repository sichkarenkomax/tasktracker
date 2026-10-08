/**
 * Getting an image ready to upload, in the browser.
 *
 * The decision (stage 2.2, the user's): photographs are shrunk and cropped on the
 * client's side, so the server never runs an image library and never spends CPU
 * or memory on resizing. Nothing here asks a person to crop anything - an avatar
 * is centred and squared automatically, because a dialog that says "now drag the
 * handles" is a dialog most people cancel.
 *
 * The rules are deliberately conservative: never enlarge, keep the aspect ratio
 * unless a square was asked for, and produce a new file rather than pretending
 * the original shrank. Whatever comes out is what the server stores and serves,
 * so the sizes here are the product's real maximums rather than a nicety.
 */

export interface ImageOptions {
  /** Longest edge, in pixels, of the result. */
  maxEdge: number
  /**
   * Centre-crop to a square before scaling. What an avatar needs, and what a
   * document scan does not.
   */
  square?: boolean
  /** Encoder quality for lossy output; ignored for PNG. */
  quality?: number
}

const DEFAULTS: Required<Omit<ImageOptions, 'square'>> = { maxEdge: 1600, quality: 0.85 }

/** Image types this can decode. SVG is not one of them, and not for no reason. */
export function isProcessableImage(file: File): boolean {
  return ['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(file.type)
}

/**
 * The prepared image, or the original file when nothing needed doing.
 *
 * Returns the file itself when it is already small enough, so a 40 KB PNG
 * screenshot is not re-encoded for the sake of being re-encoded.
 */
export async function prepareImage(file: File, options: Partial<ImageOptions> = {}): Promise<File> {
  if (!isProcessableImage(file)) return file
  const maxEdge = options.maxEdge ?? DEFAULTS.maxEdge

  let bitmap: ImageBitmap
  try {
    // `imageOrientation: 'from-image'` applies the EXIF rotation, so a photo
    // taken sideways is not uploaded sideways.
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    // A file that claims to be an image but will not decode is the browser's
    // problem to report; upload the original and let the server's whitelist and
    // size limit decide, rather than failing here with a vaguer error.
    return file
  }

  try {
    const source = cropToSquare(bitmap, options.square === true)
    const scale = Math.min(1, maxEdge / Math.max(source.width, source.height))
    const width = Math.max(1, Math.round(source.width * scale))
    const height = Math.max(1, Math.round(source.height * scale))

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (context === null) return file
    // Downscaling a photo without this reads as a field of grey.
    context.imageSmoothingQuality = 'high'
    context.drawImage(bitmap, source.x, source.y, source.width, source.height, 0, 0, width, height)

    const encoded = await toBlob(canvas, file.type, options.quality ?? DEFAULTS.quality)
    if (encoded === null) return file

    const name = swapExtension(file.name, encoded.type)
    return new File([encoded], name, { type: encoded.type, lastModified: file.lastModified })
  } finally {
    bitmap.close()
  }
}

/** An avatar-sized square, cropped from the centre. */
export function prepareAvatar(file: File, size = 512): Promise<File> {
  return prepareImage(file, { maxEdge: size, square: true })
}

function cropToSquare(
  bitmap: ImageBitmap,
  square: boolean,
): { x: number; y: number; width: number; height: number } {
  if (!square) return { x: 0, y: 0, width: bitmap.width, height: bitmap.height }
  const side = Math.min(bitmap.width, bitmap.height)
  return {
    x: Math.round((bitmap.width - side) / 2),
    y: Math.round((bitmap.height - side) / 2),
    width: side,
    height: side,
  }
}

async function toBlob(
  canvas: HTMLCanvasElement,
  sourceType: string,
  quality: number,
): Promise<Blob | null> {
  // WebP first: smaller than JPEG at the same quality and it keeps an alpha
  // channel, so a logo does not get a black square behind it. JPEG is the
  // fallback for browsers without it, and PNG stays PNG because re-encoding a
  // screenshot as lossy JPEG is how text in it turns to mush.
  if (sourceType !== 'image/png' && supportsType('image/webp')) {
    return canvasToBlob(canvas, 'image/webp', quality)
  }
  if (sourceType === 'image/jpeg') return canvasToBlob(canvas, 'image/jpeg', quality)
  return canvasToBlob(canvas, 'image/png')
}

let webpSupport: boolean | null = null

function supportsType(type: string): boolean {
  if (webpSupport === null) {
    const canvas = document.createElement('canvas')
    webpSupport = canvas.toDataURL(type).startsWith(`data:${type}`)
  }
  return webpSupport
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality?: number,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), type, quality)
  })
}

function swapExtension(name: string, type: string): string {
  const extension = type === 'image/webp' ? 'webp' : type === 'image/png' ? 'png' : 'jpg'
  return `${name.replace(/\.[a-z0-9]+$/i, '')}.${extension}`
}