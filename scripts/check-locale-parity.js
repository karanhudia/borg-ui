#!/usr/bin/env node
/**
 * CI script: validate that all locale JSON files have identical key sets.
 * New locale files are picked up automatically — no changes needed here.
 *
 * Usage:
 *   node scripts/check-locale-parity.js
 *
 * Exit codes:
 *   0 — all locale files have identical key sets
 *   1 — key sets differ (prints which keys are missing from which files)
 */

const fs = require('fs')
const path = require('path')

const LOCALE_DIR = path.join(__dirname, '..', 'frontend', 'src', 'locales')
const FILES = fs.readdirSync(LOCALE_DIR).filter(f => f.endsWith('.json')).sort()

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
  console.log(`Locale parity check PASSED. All ${FILES.length} locale files share the same ${keyCount} keys.`)
}

// --- Soft check: values still identical to English (warn-only, never fails CI) ---
// Key parity doesn't mean translation parity — a locale file can carry the same
// keys as en.json while a feature shipped with untranslated English placeholders
// (see issue #1099). This flags those without blocking merges, since some strings
// (brand names, cognates, format-only text) are legitimately identical across
// locales. Add a key here once you've confirmed it's a real, deliberate match —
// scoped to the specific locale file(s) where it's legitimate, since a word that's
// a genuine loanword in one language (e.g. "Repository" in German) is often a real
// untranslated gap in another (e.g. Spanish, which normally uses "Repositorio").
const IDENTICAL_TO_ENGLISH_ALLOWLIST = {
  'activity.umbrella.plan': ['de.json', 'es.json'],
  'backupPlans.runsPanel.columns.plan': ['de.json'],
  'backupPlans.sort.nameAZ': ['de.json'],
  'backupPlans.sort.nameZA': ['de.json'],
  'backupPlans.sourceChooser.inPrefix': ['de.json', 'it.json'],
  'cache.cacheUsageDetail': ['de.json', 'es.json', 'it.json'],
  'cloudStorage.sort.nameAZ': ['de.json'],
  'cloudStorage.sort.nameZA': ['de.json'],
  'common.no': ['es.json', 'it.json'],
  'exportImport.title': ['de.json'],
  'layout.logoAlt': ['de.json'],
  'login.ssoDefaultProvider': ['it.json'],
  'notifications.chip.repositoryCount': ['de.json'],
  'remoteClients.switcher.versionHelper': ['de.json', 'es.json', 'it.json'],
  'remoteClients.version': ['de.json', 'es.json', 'it.json'],
  'repositories.sort.nameAZ': ['de.json'],
  'repositories.sort.nameZA': ['de.json'],
  'repositoryCard.nextBackupWithName': ['de.json', 'es.json', 'it.json'],
  'repositoryCard.rcloneNextSyncBadge': ['it.json'],
  'sshConnections.deployDialog.presetHetzner': ['de.json', 'es.json', 'it.json'],
  'sshConnections.diagnostics.transferredIn': ['de.json', 'it.json'],
  'wizard.location.directRclonePathPlaceholder': ['de.json', 'es.json', 'it.json'],
}

// "Identical to English AND (contains an English function word OR is 3+ words)" —
// lets short, legitimately-identical strings (Backup, Server, Status, Repository)
// through without an allowlist entry, at the cost of a few format-string false
// positives that are cheap to allowlist by hand.
const ENGLISH_FUNCTION_WORDS =
  /\b(the|and|or|to|a|of|is|are|for|with|from|this|that|will|can|not|when|all|your|you|be|has|have|in|on|at|it|no|yes|by|as|if|only|each|per|more|less|new|use|used|may|must|should)\b/i

function findUntranslated(file, fileKeys, fileData) {
  return [...referenceKeys]
    .filter(k => fileKeys.has(k) && !(IDENTICAL_TO_ENGLISH_ALLOWLIST[k] || []).includes(file))
    .filter(k => {
      const enValue = getByPath(referenceData, k)
      const value = getByPath(fileData, k)
      return (
        typeof enValue === 'string' &&
        enValue === value &&
        (ENGLISH_FUNCTION_WORDS.test(enValue) || enValue.trim().split(/\s+/).length >= 3)
      )
    })
}

function getByPath(obj, keyPath) {
  return keyPath.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj)
}

const referenceData = locales[reference]
let warnCount = 0
for (const file of FILES) {
  if (file === reference) continue
  const untranslated = findUntranslated(file, keySets[file], locales[file])
  if (untranslated.length > 0) {
    warnCount += untranslated.length
    console.warn(`\n[WARN] ${file} has ${untranslated.length} value(s) still identical to English:`)
    for (const key of untranslated.sort()) {
      console.warn(`  ~ ${key}`)
    }
  }
}
if (warnCount > 0) {
  console.warn(
    `\n${warnCount} untranslated value(s) found (warn-only, does not fail CI). ` +
      'Translate them, or if identical is correct, add the key to IDENTICAL_TO_ENGLISH_ALLOWLIST above.'
  )
} else {
  console.log('Translation soft check: no untranslated values found outside the allowlist.')
}

process.exit(hasErrors ? 1 : 0)
