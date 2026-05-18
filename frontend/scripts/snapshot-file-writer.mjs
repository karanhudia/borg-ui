import { mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

import pngjs from 'pngjs'

const { PNG } = pngjs

export function pngBuffersHaveSamePixels(existingBuffer, nextBuffer) {
  let existingPng
  let nextPng

  try {
    existingPng = PNG.sync.read(existingBuffer)
    nextPng = PNG.sync.read(nextBuffer)
  } catch {
    return false
  }

  if (existingPng.width !== nextPng.width || existingPng.height !== nextPng.height) {
    return false
  }

  return Buffer.compare(existingPng.data, nextPng.data) === 0
}

async function writeSnapshot(outputPath, snapshotBuffer, reason) {
  await mkdir(path.dirname(outputPath), { recursive: true })
  await writeFile(outputPath, snapshotBuffer)
  return { changed: true, reason }
}

export async function writeSnapshotIfChanged(outputPath, snapshotBuffer) {
  let existingBuffer

  try {
    existingBuffer = await readFile(outputPath)
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      return writeSnapshot(outputPath, snapshotBuffer, 'missing')
    }

    throw error
  }

  if (Buffer.compare(existingBuffer, snapshotBuffer) === 0) {
    return { changed: false, reason: 'matching-bytes' }
  }

  if (pngBuffersHaveSamePixels(existingBuffer, snapshotBuffer)) {
    return { changed: false, reason: 'matching-pixels' }
  }

  return writeSnapshot(outputPath, snapshotBuffer, 'different-pixels')
}
