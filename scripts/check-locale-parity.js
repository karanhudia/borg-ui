#!/usr/bin/env node
/**
 * CI script: validate that en.json, es.json, and de.json have identical key sets.
 *
 * Usage:
 *   node scripts/check-locale-parity.js
 *
 * Exit codes:
 *   0 — all three locale files have identical key sets
 *   1 — key sets differ (prints which keys are missing from which files)
 */

const fs = require('fs')
const path = require('path')

const LOCALE_DIR = path.join(__dirname, '..', 'frontend', 'src', 'locales')
const FILES = ['en.json', 'es.json', 'de.json']

/**
 * Recursively collect all dot-separated key paths from a nested object.
 * E.g. { a: { b: "val" } } → ["a.b"]
 */
function collectKeys(obj, prefix = '') {
  const keys = []
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      keys.push(...collectKeys(v, fullKey))
    } else {
      keys.push(fullKey)
    }
  }
  return keys
}

// Load all locale files
const locales = {}
for (const file of FILES) {
  const filePath = path.join(LOCALE_DIR, file)
  try {
    const content = fs.readFileSync(filePath, 'utf8')
    locales[file] = JSON.parse(content)
  } catch (err) {
    console.error(`ERROR: Failed to read/parse ${file}: ${err.message}`)
    process.exit(1)
  }
}

// Collect key sets for each file
const keySets = {}
for (const [file, data] of Object.entries(locales)) {
  keySets[file] = new Set(collectKeys(data))
}

// Compare every pair against en.json as the reference
const reference = 'en.json'
const referenceKeys = keySets[reference]
let hasErrors = false

for (const file of FILES) {
  if (file === reference) continue
  const fileKeys = keySets[file]

  const missingFromFile = [...referenceKeys].filter(k => !fileKeys.has(k))
  const extraInFile = [...fileKeys].filter(k => !referenceKeys.has(k))

  if (missingFromFile.length > 0) {
    hasErrors = true
    console.error(`\n[FAIL] ${file} is missing ${missingFromFile.length} key(s) present in ${reference}:`)
    for (const key of missingFromFile.sort()) {
      console.error(`  - ${key}`)
    }
  }

  if (extraInFile.length > 0) {
    hasErrors = true
    console.error(`\n[FAIL] ${file} has ${extraInFile.length} extra key(s) not present in ${reference}:`)
    for (const key of extraInFile.sort()) {
      console.error(`  + ${key}`)
    }
  }
}

if (hasErrors) {
  console.error('\nLocale parity check FAILED. Fix the key differences above.')
  process.exit(1)
} else {
  const keyCount = referenceKeys.size
  console.log(`Locale parity check PASSED. All 3 locale files share the same ${keyCount} keys.`)
  process.exit(0)
}
