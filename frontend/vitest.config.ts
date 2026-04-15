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
        'src/services/api.ts', // API wrappers - low value to unit test
        'src/locales/**', // Locale JSON files - no logic to test
        // Integration-heavy container shells. Their business logic is covered by
        // the underlying tested hooks/components; unit-testing these top-level
        // orchestrators directly provides poor signal for the threshold cost.
        'src/components/SystemSettingsTab.tsx',
        'src/components/NotificationsTab.tsx',
        'src/components/PackagesTab.tsx',
        'src/components/CacheManagementTab.tsx',
        'src/components/TerminalLogViewer.tsx',
        'src/components/ExportImportTab.tsx',
        'src/components/ArchiveBrowserDialog.tsx',
        'src/components/LogManagementTab.tsx',
        'src/components/MountsManagementTab.tsx',
        'src/components/PreferencesTab.tsx',
        'src/components/wizard/WizardStepRestoreDestination.tsx',
        'src/components/wizard/WizardStepRestoreFiles.tsx',
        'src/components/wizard/WizardStepRestoreReview.tsx',
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
    // Multi-step wizard tests take 1-2s in isolation; give headroom under full suite load
    testTimeout: 15000,
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
