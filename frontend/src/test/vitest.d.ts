import 'vitest'
import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers'

// Vitest 5 no longer reads matcher types from the global `jest.Matchers`
// interface that `@testing-library/jest-dom` declares, and jest-dom's own
// `vitest` typings still augment the old one-parameter `Assertion<T>`
// (testing-library/jest-dom#738). Declare the matchers on `Matchers<R, T>`,
// the interface Vitest 5 merges into `expect()` results.
declare module 'vitest' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface Matchers<R, T> extends TestingLibraryMatchers<unknown, R> {}
}
