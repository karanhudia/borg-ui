/**
 * Tests for compressionUtils.ts
 * Focus: Parse/build logic for compression strings
 * WHY: Invalid compression strings = backup fails with cryptic error
 */

import { describe, it, expect } from 'vitest'
import {
  buildCompressionString,
  parseCompressionString,
  CompressionOptions,
} from './compressionUtils'

describe('compressionUtils - Round-Trip Conversion', () => {
  it('parsing and rebuilding is identity operation for common formats', () => {
    const testCases = [
      'lz4',
      'lz4,6',
      'zstd',
      'zstd,3',
      'zlib,6',
      'lzma,6',
      'auto,lz4',
      'auto,zstd',
      'obfuscate,110,lz4',
      'obfuscate,110,auto,zstd,3',
      'none',
    ]

    testCases.forEach((input) => {
      const parsed = parseCompressionString(input)
      const rebuilt = buildCompressionString(
        parsed.algorithm,
        parsed.level,
        parsed.autoDetect,
        parsed.obfuscate
      )
      expect(rebuilt).toBe(input)
    })
  })

  it('handles edge case: auto algorithm builds correctly', () => {
    // When algorithm is 'auto', it should build as 'auto,lz4'
    const result = buildCompressionString('auto', '', false, '')
    expect(result).toBe('auto,lz4')

    // And parse back correctly
    const parsed = parseCompressionString(result)
    expect(parsed.algorithm).toBe('lz4')
    expect(parsed.autoDetect).toBe(true)
  })
})

describe('parseCompressionString', () => {
  it('parses simple algorithm', () => {
    const result = parseCompressionString('lz4')
    expect(result).toEqual({
      algorithm: 'lz4',
      level: '',
      autoDetect: false,
      obfuscate: '',
    })
  })

  it('parses algorithm with level', () => {
    const result = parseCompressionString('zstd,6')
    expect(result).toEqual({
      algorithm: 'zstd',
      level: '6',
      autoDetect: false,
      obfuscate: '',
    })
  })

  it('parses auto-detect format', () => {
    const result = parseCompressionString('auto,lz4')
    expect(result).toEqual({
      algorithm: 'lz4',
      level: '',
      autoDetect: true,
      obfuscate: '',
    })
  })

  it('parses auto-detect with level', () => {
    const result = parseCompressionString('auto,zstd,3')
    expect(result).toEqual({
      algorithm: 'zstd',
      level: '3',
      autoDetect: true,
      obfuscate: '',
    })
  })

  it('parses obfuscate format', () => {
    const result = parseCompressionString('obfuscate,110,lz4')
    expect(result).toEqual({
      algorithm: 'lz4',
      level: '',
      autoDetect: false,
      obfuscate: '110',
    })
  })

  it('parses complex format with all options', () => {
    const result = parseCompressionString('obfuscate,110,auto,zstd,3')
    expect(result).toEqual({
      algorithm: 'zstd',
      level: '3',
      autoDetect: true,
      obfuscate: '110',
    })
  })

  it('parses none algorithm', () => {
    const result = parseCompressionString('none')
    expect(result).toEqual({
      algorithm: 'none',
      level: '',
      autoDetect: false,
      obfuscate: '',
    })
  })

  it('handles empty string with default', () => {
    // parseCompressionString with empty string returns empty algorithm
    // This is expected - the component should provide a default like 'lz4' before calling parse
    const result = parseCompressionString('')
    expect(result.algorithm).toBe('') // Empty input = empty algorithm
    expect(result.level).toBe('')
    expect(result.autoDetect).toBe(false)
    expect(result.obfuscate).toBe('')
  })
})

describe('buildCompressionString', () => {
  it('builds simple algorithm', () => {
    const result = buildCompressionString('lz4', '', false, '')
    expect(result).toBe('lz4')
  })

  it('builds algorithm with level', () => {
    const result = buildCompressionString('zstd', '6', false, '')
    expect(result).toBe('zstd,6')
  })

  it('builds auto-detect format', () => {
    const result = buildCompressionString('lz4', '', true, '')
    expect(result).toBe('auto,lz4')
  })

  it('builds auto-detect with level', () => {
    const result = buildCompressionString('zstd', '3', true, '')
    expect(result).toBe('auto,zstd,3')
  })

  it('builds obfuscate format', () => {
    const result = buildCompressionString('lz4', '', false, '110')
    expect(result).toBe('obfuscate,110,lz4')
  })

  it('builds complex format with all options', () => {
    const result = buildCompressionString('zstd', '3', true, '110')
    expect(result).toBe('obfuscate,110,auto,zstd,3')
  })

  it('builds none algorithm', () => {
    const result = buildCompressionString('none', '', false, '')
    expect(result).toBe('none')
  })

  it('handles auto algorithm (special case)', () => {
    // When algorithm is 'auto', it should build as 'auto,lz4'
    const result = buildCompressionString('auto', '', false, '')
    expect(result).toBe('auto,lz4')
  })

  it('does not add auto prefix if algorithm is already auto', () => {
    // autoDetect flag should be ignored when algorithm is 'auto'
    const result = buildCompressionString('auto', '', true, '')
    expect(result).toBe('auto,lz4') // Should not be 'auto,auto,lz4'
  })

  it('ignores level when algorithm is none', () => {
    const result = buildCompressionString('none', '6', false, '')
    expect(result).toBe('none') // Level should not be included
  })

  it('handles obfuscate with auto and level', () => {
    const result = buildCompressionString('zstd', '10', true, '110')
    expect(result).toBe('obfuscate,110,auto,zstd,10')
  })
})

describe('compressionUtils - Production Scenarios', () => {
  it('handles all common Borg compression algorithms', () => {
    const algorithms = ['lz4', 'zstd', 'zlib', 'lzma', 'none']

    algorithms.forEach((algo) => {
      const built = buildCompressionString(algo, '', false, '')
      const parsed = parseCompressionString(built)
      expect(parsed.algorithm).toBe(algo)
    })
  })

  it('handles typical compression levels', () => {
    const testCases = [
      { algo: 'zstd', level: '3' },
      { algo: 'zstd', level: '6' },
      { algo: 'zstd', level: '10' },
      { algo: 'zlib', level: '6' },
      { algo: 'zlib', level: '9' },
      { algo: 'lzma', level: '6' },
    ]

    testCases.forEach(({ algo, level }) => {
      const built = buildCompressionString(algo, level, false, '')
      const parsed = parseCompressionString(built)
      expect(parsed.algorithm).toBe(algo)
      expect(parsed.level).toBe(level)
    })
  })

  it('validates obfuscate spec formats', () => {
    const obfuscateSpecs = ['110', '256', '512']

    obfuscateSpecs.forEach((spec) => {
      const built = buildCompressionString('lz4', '', false, spec)
      const parsed = parseCompressionString(built)
      expect(parsed.obfuscate).toBe(spec)
    })
  })
})

describe('compressionUtils - Error Prevention', () => {
  it('builds valid strings even with unusual inputs', () => {
    // These shouldn't crash, but may produce empty or unusual strings
    const result1 = buildCompressionString('', '', false, '')
    // Empty algorithm is handled - it goes through the else branch and adds empty string
    expect(result1).toBeDefined() // At least doesn't crash

    const result2 = buildCompressionString('unknown-algo', '999', false, '')
    expect(result2).toBe('unknown-algo,999') // Passes through unusual values
  })

  it('parses strings with extra commas gracefully', () => {
    // Shouldn't crash on malformed input
    const result = parseCompressionString('lz4,')
    expect(result.algorithm).toBeTruthy()
  })

  it('handles numeric levels as strings', () => {
    const result = buildCompressionString('zstd', '6', false, '')
    expect(result).toBe('zstd,6')
    expect(typeof result).toBe('string')
  })
})
