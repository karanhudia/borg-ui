/**
 * Schedule Functional Updaters Test
 *
 * This test verifies that the Schedule component uses functional updaters
 * for all state updates, preventing stale closure bugs.
 *
 * The stale closure bug occurred when using:
 *   setForm({ ...form, field: value })
 *
 * Fixed by using:
 *   setForm(prev => ({ ...prev, field: value }))
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

describe('Schedule - Functional Updater Pattern Verification', () => {
  const scheduleFilePath = join(__dirname, '../Schedule.tsx')
  const scheduleCode = readFileSync(scheduleFilePath, 'utf-8')

  it('should use functional updaters for createForm state updates', () => {
    // Check that we're using (prev) => pattern for updates
    const functionalUpdaterPattern = /setCreateForm\(\s*\(?(?:prev|p)\s*\)?\s*=>/g

    // Check for the BAD pattern: setCreateForm({ ...createForm, field: value })
    // This is the stale closure anti-pattern
    const staleClosurePattern = /setCreateForm\(\s*{\s*\.\.\.createForm\s*,/g

    const functionalMatches = scheduleCode.match(functionalUpdaterPattern) || []
    const staleMatches = scheduleCode.match(staleClosurePattern) || []

    // We should have many functional updaters (one for each field)
    expect(functionalMatches.length).toBeGreaterThan(10)

    // We should have ZERO stale closure patterns
    // Note: resetCreateForm() uses setCreateForm({ name: '', ... }) which is fine
    // because it's not spreading old state
    expect(staleMatches.length).toBe(0)
  })

  it('should use functional updaters for editForm state updates', () => {
    const functionalUpdaterPattern = /setEditForm\(\s*\(?(?:prev|p)\s*\)?\s*=>/g
    const staleClosurePattern = /setEditForm\(\s*{\s*\.\.\.editForm\s*,/g

    const functionalMatches = scheduleCode.match(functionalUpdaterPattern) || []
    const staleMatches = scheduleCode.match(staleClosurePattern) || []

    // We should have many functional updaters (one for each field)
    expect(functionalMatches.length).toBeGreaterThan(10)

    // We should have ZERO stale closure patterns
    expect(staleMatches.length).toBe(0)
  })

  it('should use functional updaters for repository_ids changes', () => {
    // Specifically check the critical repository_ids field
    const repositoryIdsPattern = /repository_ids:\s*ids\s*\}\)/g
    const matches = scheduleCode.match(repositoryIdsPattern) || []

    // We should have at least 2 (one in create form, one in edit form)
    expect(matches.length).toBeGreaterThanOrEqual(2)

    // Check that all repository_ids updates use functional updater
    const repositoryUpdatesWithPrev = /setCreateForm\(\s*\(?prev\s*\)?\s*=>[^}]*repository_ids:\s*ids/g
    const createFormMatches = scheduleCode.match(repositoryUpdatesWithPrev) || []
    expect(createFormMatches.length).toBeGreaterThanOrEqual(1)

    const editFormUpdatesWithPrev = /setEditForm\(\s*\(?prev\s*\)?\s*=>[^}]*repository_ids:\s*ids/g
    const editFormMatches = scheduleCode.match(editFormUpdatesWithPrev) || []
    expect(editFormMatches.length).toBeGreaterThanOrEqual(1)
  })

  it('should NOT use stale closure pattern anywhere', () => {
    // These are the BAD patterns that cause stale closures:
    const badPatterns = [
      /setCreateForm\(\s*{\s*\.\.\.createForm,/,
      /setEditForm\(\s*{\s*\.\.\.editForm,/,
    ]

    for (const badPattern of badPatterns) {
      const matches = scheduleCode.match(badPattern)
      if (matches) {
        console.error('Found stale closure pattern:', matches[0])
      }
      expect(matches).toBeNull()
    }
  })

  it('should use functional updaters for all form field types', () => {
    // Verify that various field types use functional updaters
    const fieldPatterns = [
      /setCreateForm\(\s*\(?prev\s*\)?\s*=>[^}]*name:/,           // text field
      /setCreateForm\(\s*\(?prev\s*\)?\s*=>[^}]*repository_ids:/, // array field
      /setCreateForm\(\s*\(?prev\s*\)?\s*=>[^}]*enabled:/,        // boolean field
      /setCreateForm\(\s*\(?prev\s*\)?\s*=>[^}]*run_prune_after:/, // switch field
      /setCreateForm\(\s*\(?prev\s*\)?\s*=>[^}]*prune_keep_daily:/, // number field
    ]

    for (const pattern of fieldPatterns) {
      const matches = scheduleCode.match(pattern)
      expect(matches).not.toBeNull()
      expect(matches!.length).toBeGreaterThan(0)
    }
  })
})
