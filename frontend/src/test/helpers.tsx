/**
 * Test helper functions for common testing patterns
 */

import { render, RenderOptions } from '@testing-library/react'
import { ReactElement, ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

/**
 * Create a QueryClient for testing with default options
 */
export const createTestQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // Disable retries in tests
        gcTime: 0, // Disable garbage collection
      },
      mutations: {
        retry: false,
      },
    },
  })
}

/**
 * Wrapper component that provides necessary providers for testing
 */
interface ProvidersProps {
  children: ReactNode
  queryClient?: QueryClient
}

export const AllProviders = ({ children, queryClient }: ProvidersProps) => {
  const testQueryClient = queryClient || createTestQueryClient()

  return (
    <QueryClientProvider client={testQueryClient}>
      <BrowserRouter>{children}</BrowserRouter>
    </QueryClientProvider>
  )
}

/**
 * Custom render function that includes providers
 */
export const renderWithProviders = (
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'> & { queryClient?: QueryClient }
) => {
  const { queryClient, ...renderOptions } = options || {}

  return {
    user: userEvent.setup(),
    ...render(ui, {
      wrapper: ({ children }) => <AllProviders queryClient={queryClient}>{children}</AllProviders>,
      ...renderOptions,
    }),
  }
}

/**
 * Create a wrapper for renderHook that includes QueryClient
 */
export const createQueryWrapper = (queryClient?: QueryClient) => {
  const testQueryClient = queryClient || createTestQueryClient()

  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={testQueryClient}>{children}</QueryClientProvider>
  )
}

/**
 * Advance fake timers and flush promises
 * Useful for testing polling/interval logic
 */
export const advanceTimersAndFlush = async (ms: number) => {
  vi.advanceTimersByTime(ms)
  // Flush promises to allow pending callbacks to run
  await new Promise((resolve) => setTimeout(resolve, 0))
}

/**
 * Advance polling by a number of intervals
 */
export const advancePolling = async (times: number, interval = 3000) => {
  for (let i = 0; i < times; i++) {
    await advanceTimersAndFlush(interval)
  }
}

/**
 * Wait for a condition to be true or timeout
 */
export const waitForCondition = async (
  condition: () => boolean,
  timeout = 5000,
  interval = 100
): Promise<void> => {
  const startTime = Date.now()

  return new Promise((resolve, reject) => {
    const checkCondition = () => {
      if (condition()) {
        resolve()
      } else if (Date.now() - startTime >= timeout) {
        reject(new Error('Condition not met within timeout'))
      } else {
        setTimeout(checkCondition, interval)
      }
    }

    checkCondition()
  })
}

/**
 * Mock axios error response
 */
export const mockAxiosError = (status: number, data: unknown) => ({
  response: {
    status,
    data,
  },
  isAxiosError: true,
})

/**
 * Mock lock error from API
 */
export const mockLockError = (lockPath: string) =>
  mockAxiosError(400, {
    detail: `LOCK_ERROR::${lockPath}`,
  })

/**
 * Create a mock file for testing file inputs
 */
export const createMockFile = (name: string, content: string, type = 'text/plain'): File => {
  const blob = new Blob([content], { type })
  return new File([blob], name, { type })
}
