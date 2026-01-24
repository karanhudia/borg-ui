/**
 * Utility functions for parsing and building Borg compression strings
 * These functions are critical - invalid compression strings cause backup failures
 */

export interface CompressionOptions {
  algorithm: string
  level: string
  autoDetect: boolean
  obfuscate: string
}

/**
 * Build a compression string from individual components
 * Examples:
 * - buildCompressionString('lz4', '', false, '') -> 'lz4'
 * - buildCompressionString('zstd', '6', false, '') -> 'zstd,6'
 * - buildCompressionString('lz4', '', true, '') -> 'auto,lz4'
 * - buildCompressionString('zstd', '3', true, '110') -> 'obfuscate,110,auto,zstd,3'
 */
export const buildCompressionString = (
  algorithm: string,
  level: string,
  autoDetect: boolean,
  obfuscate: string
): string => {
  let parts: string[] = []

  // Add obfuscate prefix if specified
  if (obfuscate) {
    parts.push('obfuscate', obfuscate)
  }

  // Add auto prefix if enabled (but not if algorithm is already 'auto')
  if (autoDetect && algorithm !== 'auto') {
    parts.push('auto')
  }

  // Add algorithm (unless it's 'none')
  if (algorithm !== 'none') {
    if (algorithm === 'auto') {
      parts.push('auto', 'lz4') // Default to lz4 as fallback
    } else {
      parts.push(algorithm)
      if (level) {
        parts.push(level)
      }
    }
  } else {
    parts.push('none')
  }

  return parts.join(',')
}

/**
 * Parse a compression string into individual components
 * Examples:
 * - parseCompressionString('lz4') -> { algorithm: 'lz4', level: '', autoDetect: false, obfuscate: '' }
 * - parseCompressionString('zstd,6') -> { algorithm: 'zstd', level: '6', autoDetect: false, obfuscate: '' }
 * - parseCompressionString('auto,lz4') -> { algorithm: 'lz4', level: '', autoDetect: true, obfuscate: '' }
 * - parseCompressionString('obfuscate,110,auto,zstd,3') -> { algorithm: 'zstd', level: '3', autoDetect: true, obfuscate: '110' }
 */
export const parseCompressionString = (compression: string): CompressionOptions => {
  const parts = compression.split(',')
  let algorithm = 'lz4'
  let level = ''
  let autoDetect = false
  let obfuscate = ''

  let i = 0

  // Check for obfuscate
  if (parts[i] === 'obfuscate') {
    i++
    if (i < parts.length) {
      obfuscate = parts[i]
      i++
    }
  }

  // Check for auto
  if (parts[i] === 'auto') {
    autoDetect = true
    i++
  }

  // Get algorithm
  if (i < parts.length) {
    algorithm = parts[i]
    i++
  }

  // Get level (if not 'auto' algorithm and there's another part)
  if (algorithm !== 'auto' && i < parts.length) {
    level = parts[i]
  }

  return { algorithm, level, autoDetect, obfuscate }
}
