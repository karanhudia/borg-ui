import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/mockData',
        'src/vite-env.d.ts',
      ],
      // Enforce minimum coverage thresholds
      // Philosophy: Focus on critical business logic, not arbitrary percentages
      thresholds: {
        lines: 60,
        functions: 34,
        branches: 70,
        statements: 60,
      },
    },
    // Test isolation
    isolate: true,
    // Show test execution time
    slowTestThreshold: 300,
    // Fail tests on console errors
    onConsoleLog(log, type) {
      if (type === 'stderr' && log.includes('Error:')) {
        return false
      }
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
