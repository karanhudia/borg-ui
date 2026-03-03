# Testing Patterns

**Analysis Date:** 2026-03-03

## Test Framework

**Runner:**
- Vitest 4.0.18
- Config: `vitest.config.ts`
- Environment: `happy-dom` (lightweight DOM implementation)

**Assertion Library:**
- Vitest's native expect with `@testing-library/jest-dom` matchers extended
- Setup in `src/test/setup.ts`: `expect.extend(matchers)` for DOM matchers

**Run Commands:**
```bash
npm test              # Run all tests
npm run test:ui       # Watch mode with UI
npm run test:coverage # Generate coverage report
```

## Test File Organization

**Location:**
- Co-located pattern with source files OR separate `__tests__` directories
- Both patterns used in codebase:
  - Co-located: `dateUtils.ts` + `dateUtils.test.ts` in same directory
  - Separate: Components have `src/components/__tests__/ComponentName.test.tsx`

**Naming:**
- `.test.tsx` for component tests
- `.test.ts` for utility/hook tests
- Must match pattern in `eslint.config.mjs` to disable `react-refresh/only-export-components`

**Structure:**
```
src/
├── components/
│   ├── StatusBadge.tsx
│   └── __tests__/
│       └── StatusBadge.test.tsx
├── utils/
│   ├── dateUtils.ts
│   └── dateUtils.test.ts  # Same directory
└── test/
    ├── setup.ts           # Global setup
    ├── test-utils.tsx     # Custom render + helpers
    ├── helpers.tsx        # Additional utilities
    └── factories.ts       # Mock data factories
```

## Test Structure

**Suite Organization:**
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/test-utils'
import ComponentName from '../ComponentName'

describe('ComponentName', () => {
  beforeEach(() => {
    // Setup for each test
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)
  })

  afterEach(() => {
    // Cleanup after each test
    vi.restoreAllMocks()
  })

  it('does something specific', () => {
    const { getByRole } = renderWithProviders(<ComponentName />)
    expect(getByRole('button')).toBeInTheDocument()
  })
})
```

**Patterns:**
- Setup: `beforeEach` hooks for mocking and initialization
- Teardown: `afterEach` hooks for cleanup with `vi.restoreAllMocks()` and `cleanup()` (auto-called)
- Assertion: Vitest `expect()` with jest-dom matchers like `toBeInTheDocument()`, `toContain()`

## Mocking

**Framework:** Vitest's `vi` object

**Patterns:**
```typescript
// Mock modules
vi.mock('../../hooks/useMaintenanceJobs')
vi.mock('../../hooks/useMatomo')

// Mock functions
const handleClick = vi.fn()
const mockApi = vi.fn().mockResolvedValue({ data: {} })
const mockError = vi.fn().mockRejectedValue(new Error('API Error'))

// Mock objects/timers
vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)
vi.spyOn(console, 'error').mockImplementation(() => {})

// Restore after test
vi.restoreAllMocks()
```

**What to Mock:**
- External API calls and network requests
- Browser APIs that aren't available in test environment (`matchMedia`, `IntersectionObserver`, `ResizeObserver`)
- Date/time for timezone-dependent logic
- Custom hooks and context providers
- Third-party services (analytics, etc.)

**What NOT to Mock:**
- Core rendering logic you're testing
- User event handlers and interactions
- React hooks like `useState`, `useEffect` (test their behavior, don't mock)
- Built-in DOM methods unless unavailable in test environment

## Fixtures and Factories

**Test Data:**
```typescript
// From src/test/factories.ts
const mockRepository = {
  id: 1,
  name: 'Test Repository',
  path: '/path/to/repo',
  encryption: 'repokey',
  compression: 'lz4',
  source_directories: ['/source/path1', '/source/path2'],
  exclude_patterns: ['*.tmp', '*.log'],
  last_backup: '2024-01-20T10:30:00Z',
  last_check: '2024-01-19T09:00:00Z',
  last_compact: '2024-01-18T08:00:00Z',
  total_size: '10.5 GB',
  archive_count: 25,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-20T10:30:00Z',
  mode: 'full' as const,
  has_running_maintenance: false,
}

const mockCallbacks = {
  onViewInfo: vi.fn(),
  onCheck: vi.fn(),
  onCompact: vi.fn(),
  onPrune: vi.fn(),
  // ... other callbacks
}
```

**Location:**
- `src/test/factories.ts` - Centralized mock data factories for reuse across tests
- `src/test/test-utils.tsx` - Custom render function and helpers
- `src/test/helpers.tsx` - Additional test utilities

**Usage Pattern:**
```typescript
const mockData = { ...mockRepository, name: 'Custom Name' }
renderWithProviders(<Component repository={mockData} />)
```

## Coverage

**Requirements:**
- Lines: 60% minimum
- Functions: 34% minimum (lower to focus on critical logic)
- Branches: 70% minimum
- Statements: 60% minimum

**Configuration:** `vitest.config.ts` with philosophy: "Focus on critical business logic, not arbitrary percentages"

**Excluded from Coverage:**
- `node_modules/`
- `src/test/` (test utilities themselves)
- `**/*.d.ts` (type definitions)
- `**/*.config.*` (config files)
- `**/mockData` (mock data directories)
- `src/vite-env.d.ts` (Vite env types)
- `src/services/api.ts` (API wrappers - low value to unit test)

**View Coverage:**
```bash
npm run test:coverage
# Generates: text, json, html, lcov reports
```

## Test Types

**Unit Tests:**
- Scope: Individual utility functions and small components
- Approach: Test pure functions with known inputs/outputs
- Example: `dateUtils.test.ts` tests functions like `formatBytes`, `parseBytes`, `convertCronToUTC`
- Focus on edge cases and boundary conditions
- Files: `src/utils/**/*.test.ts`, `src/hooks/**/*.test.ts`

**Integration Tests:**
- Scope: Components with their dependencies (providers, hooks, etc.)
- Approach: Use `renderWithProviders` to include real context, routing, theme
- Test user interactions and state management
- Files: `src/components/__tests__/**/*.test.tsx`

**E2E Tests:**
- Framework: Not used in current codebase
- Would cover full user workflows if added

## Common Patterns

**Async Testing:**
```typescript
it('handles async operations', async () => {
  const user = userEvent.setup()
  renderWithProviders(<Component />)

  await user.click(screen.getByRole('button'))
  await waitFor(() => {
    expect(screen.getByText('Loaded')).toBeInTheDocument()
  })
})
```

**Error Testing:**
```typescript
it('handles errors gracefully', async () => {
  const mockError = vi.fn().mockRejectedValue(new Error('API Error'))
  vi.mock('../../services/api', () => ({
    api: mockError,
  }))

  renderWithProviders(<Component />)

  await waitFor(() => {
    expect(screen.getByText(/error/i)).toBeInTheDocument()
  })
})
```

**Testing with Timezone:**
```typescript
beforeEach(() => {
  // Mock timezone offset to UTC+5:30 (IST)
  vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-330)
})

it('converts time correctly', () => {
  const result = convertCronToUTC('0 2 * * *')
  expect(result).toBe('30 20 * * *')
})

afterEach(() => {
  vi.restoreAllMocks()
})
```

## Test Setup & Global Configuration

**Setup File:** `src/test/setup.ts`

Configures:
- Extends `expect` with jest-dom matchers
- Auto-cleanup after each test with `afterEach(() => cleanup())`
- Mocks browser APIs:
  - `window.matchMedia()` - for responsive design testing
  - `IntersectionObserver` - for visibility detection
  - `ResizeObserver` - for layout observation
  - `Element.prototype.scrollIntoView` - for scroll testing
- Suppresses React Testing Library warnings
- Fails tests on console errors (except known React warnings)

**Custom Render Utilities:** `src/test/test-utils.tsx`

Provides:
- `renderWithProviders()` - Wraps components with all required providers
  - Includes: I18next, React Query, Router, Theme, Toast
  - Accepts `queryClient` and `initialRoute` options
- `AllProviders` - Reusable wrapper component for tests
- `waitFor()` - Custom async wait utility (3s timeout)
- `mockApiResponse()` - Creates resolved mock API promises
- `mockApiError()` - Creates rejected mock API promises
- Re-exports all `@testing-library/react` utilities

**Example:**
```typescript
import { renderWithProviders, screen, userEvent } from '@/test/test-utils'

it('renders with providers', () => {
  renderWithProviders(<Component />)
  expect(screen.getByText('Hello')).toBeInTheDocument()
})
```

## Vitest Configuration

**Key Settings:** From `vitest.config.ts`
```typescript
{
  globals: true,           // Global test functions (describe, it, expect)
  environment: 'happy-dom', // Lightweight DOM
  setupFiles: ['./src/test/setup.ts'],
  isolate: true,           // Test isolation for stability
  slowTestThreshold: 300,  // Log tests slower than 300ms
  onConsoleLog(log, type) {
    // Fail on stderr errors containing 'Error:'
    if (type === 'stderr' && log.includes('Error:')) {
      return false
    }
  },
}
```

## Test Philosophy

From vitest config comments:
- "Philosophy: Focus on critical business logic, not arbitrary percentages"
- Coverage thresholds serve as guardrails, not targets
- Unit test utilities that fail silently (like `dateUtils`)
- Integration test components with complex UX (dialogs, forms)
- Mock external dependencies (API, browser APIs)

---

*Testing analysis: 2026-03-03*
