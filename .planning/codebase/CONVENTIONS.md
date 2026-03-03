# Coding Conventions

**Analysis Date:** 2026-03-03

## Naming Patterns

**Files:**
- Components: PascalCase with `.tsx` extension (e.g., `StatusBadge.tsx`, `RepositoryCard.tsx`)
- Utilities: camelCase with `.ts` extension (e.g., `dateUtils.ts`, `compressionUtils.ts`)
- Hooks: camelCase with `.ts` or `.tsx` extension (e.g., `useAuth.tsx`, `useMaintenanceJobs.ts`)
- Test files: Either `[filename].test.tsx` or `[filename].spec.tsx` or separate `__tests__` directory with same naming
- Types/Interfaces: PascalCase in dedicated `types/` directory or co-located (e.g., `types/jobs.ts`)

**Functions:**
- camelCase for all functions (e.g., `formatDate`, `convertCronToUTC`, `getStatusColor`)
- Private/internal functions within components use camelCase with leading underscore if needed
- Helper/utility functions are exported without underscore: `export const formatBytes`

**Variables:**
- camelCase for all variables and properties (e.g., `mockData`, `isLoading`, `hasRunningMaintenance`)
- Boolean variables use `is`, `has`, `can` prefixes (e.g., `isAuthenticated`, `hasWarnings`, `canModify`)
- Constants use UPPER_SNAKE_CASE (e.g., `API_BASE_URL`)

**Types/Interfaces:**
- PascalCase with `Props` suffix for component props (e.g., `StatusBadgeProps`, `RepositoryCellProps`)
- PascalCase for types and interfaces (e.g., `User`, `Repository`, `ActivityItem`)
- Context types with `Type` suffix (e.g., `AuthContextType`)

## Code Style

**Formatting:**
- Tool: Prettier 3.6.2
- Config: `.prettierrc.json`
- Settings:
  - `semi: false` - No semicolons
  - `singleQuote: true` - Single quotes
  - `tabWidth: 2` - 2 spaces
  - `trailingComma: "es5"` - Trailing commas in ES5 syntax
  - `printWidth: 100` - Line length limit
  - `arrowParens: "always"` - Parentheses around single arrow function parameters
  - `endOfLine: "lf"` - Unix line endings
- Run format: `npm run format` or `npm run format:check`
- Husky pre-commit hook runs Prettier on staged files in `src/**/*.{ts,tsx,js,jsx,json,css,md}`

**Linting:**
- Tool: ESLint with TypeScript support (9.39.1)
- Config: `eslint.config.mjs` (flat config format)
- Key rules:
  - `@typescript-eslint/no-unused-vars` with `argsIgnorePattern: '^_'` (allows unused params starting with `_`)
  - `react-refresh/only-export-components: warn` for fast refresh (disabled in test files)
  - `react-hooks/set-state-in-effect: off` - Allows setState in effects (custom exemption)
  - Max warnings: 0 (all warnings treated as errors)
- Run lint: `npm run lint` with `--max-warnings 0` flag
- Type checking: `npm run typecheck` (tsc --noEmit)

## Import Organization

**Order:**
1. External dependencies (React, third-party libraries)
2. Internal dependencies (services, hooks, utils)
3. Components (relative imports from sibling/parent dirs)
4. Types/interfaces (relative imports)
5. Styles/assets (if any)

**Examples:**
```typescript
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Box, Card, Typography } from '@mui/material'
import { History, RefreshCw } from 'lucide-react'
import { activityAPI } from '../services/api'
import { useMatomo } from '../hooks/useMatomo'
import BackupJobsTable from '../components/BackupJobsTable'
```

**Path Aliases:**
- `@` - Points to `src/` directory
- Used for absolute imports: `import { formatDate } from '@/utils/dateUtils'`
- Configured in `vitest.config.ts`: `alias: { '@': path.resolve(__dirname, './src') }`

## Error Handling

**Patterns:**
- Context/hook invariant errors use `throw new Error()` for impossible states
  - Example in `ThemeContext.tsx`: `throw new Error('useTheme must be used within a ThemeProvider')`
- API errors caught with try-catch blocks in async operations
- Error messages logged to console with `console.error()` for tracking
- User-facing errors wrapped in try-catch with translation keys

**In Components:**
```typescript
try {
  const result = await apiCall()
  // process result
} catch (error) {
  console.error('Error description:', error)
  throw new Error(t('translation.key.for.error'))
  // or handle silently with fallback
}
```

**Utility Functions:**
- Validate inputs at function start
- Return sensible defaults or `undefined` on error (e.g., `parseBytes` returns `undefined`)
- Log errors to console for debugging: `console.error('Error formatting date:', error)`
- Return original input or 'Never'/'N/A' as fallback

## Logging

**Framework:** `console` object directly (no custom logger)

**Patterns:**
- Errors logged with `console.error('Description:', error)`
- Only error logs used in production code
- Console output typically caught during test setup with suppression of React warnings
- Matomo tracking used for user analytics, not console logging

**Example:**
```typescript
try {
  // do something
} catch (error) {
  console.error('Error converting cron to UTC:', error)
  return cronExpression // fallback
}
```

## Comments

**When to Comment:**
- JSDoc comments for exported functions explaining purpose and usage
- Inline comments for complex logic or non-obvious decisions
- Block comments explaining "why" not "what"
- Comments on public APIs and utilities, not on simple implementations

**JSDoc/TSDoc:**
- Used on exported functions in utils
- Includes description, parameters (if any), and return type
- Example from `dateUtils.ts`:
```typescript
/**
 * Format a date string to a human-readable format
 * Example: "16th October 2025, 2:40:55 PM"
 */
export const formatDate = (dateString: string | null | undefined): string => {
```

## Function Design

**Size:** Functions kept relatively small (<40 lines for most utilities, <50 for components)

**Parameters:**
- Explicit parameters over config objects when 2-3 params
- Use interfaces for component props with optional fields having defaults
- Optional parameters with defaults at end of list
- Example: `formatDate(dateString: string | null | undefined): string`

**Return Values:**
- Explicit return type annotations required for exported functions
- Handle `null` and `undefined` inputs gracefully
- Return same type consistently (don't mix `undefined` and `null`)
- Type-safe: Use union types like `string | undefined` not just `any`

## Module Design

**Exports:**
- Named exports preferred for utilities and hooks
- Default exports for React components
- Example from `StatusBadge.tsx`:
```typescript
export const StatusBadge: React.FC<StatusBadgeProps> = ({ ... }) => { }
export default StatusBadge
```

**Barrel Files (Index Files):**
- Used in modular directories like `components/wizard/`
- Example: `src/components/wizard/schedule/index.ts` exports from submodules
- Simplifies imports: `import { ... } from '@/components/wizard'`

## React-Specific Patterns

**Component Definition:**
- Functional components with `React.FC<Props>` type annotation
- Props interface defined above component with `Props` suffix
- Component wrapped with `export const ComponentName: React.FC<Props> = ({ ... }) => {}`
- Default export at bottom: `export default ComponentName`

**Hooks:**
- Custom hooks follow `useXxx` naming convention
- Context hooks throw error if used outside provider
- Example from `useAuth.tsx`:
```typescript
const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
```

**Testing Library Conventions:**
- Use `screen` queries (getByRole, getByText) over container queries
- Use `userEvent` for user interactions over `fireEvent`
- Query elements by semantic roles when possible
- Use `data-testid` only when role/text queries aren't practical

---

*Convention analysis: 2026-03-03*
