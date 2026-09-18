import type { Meta, StoryObj } from '@storybook/react-vite'
import { PruneComparedPolicies } from './PruneComparedPolicies'
import type { PruneComparison } from '../../types/archives'

const retention = (keep_daily: number) => ({
  keep_hourly: 0,
  keep_daily,
  keep_weekly: 4,
  keep_monthly: 6,
  keep_quarterly: 0,
  keep_yearly: 1,
  keep_within: null,
})

const comparison: PruneComparison = {
  computed_at: '2026-09-18T01:00:00Z',
  archive_count_at: 12,
  stale: false,
  candidates: [
    {
      key: 'current',
      label: 'Current',
      retention: retention(30),
      kept_count: 12,
      deleted_count: 0,
      freed_at_least: 0,
      partial_measure: false,
      operation_id: 1,
    },
    {
      key: 'standard',
      label: 'Standard',
      retention: retention(7),
      kept_count: 8,
      deleted_count: 4,
      freed_at_least: 40 * 1024 ** 3,
      partial_measure: false,
      operation_id: 2,
    },
    {
      key: 'longer',
      label: 'Longer',
      retention: retention(14),
      kept_count: 10,
      deleted_count: 2,
      freed_at_least: 15 * 1024 ** 3,
      partial_measure: false,
      operation_id: 3,
    },
  ],
}

const meta = {
  title: 'Components/Prune/PruneComparedPolicies',
  component: PruneComparedPolicies,
} satisfies Meta<typeof PruneComparedPolicies>

export default meta
type Story = StoryObj<typeof meta>

export const Stored: Story = {
  args: {
    comparison,
    editing: null,
    selectedKey: 'standard',
    pending: false,
    refreshDisabled: false,
    onSelect: () => {},
    onRefresh: () => {},
  },
}

export const WithEditingRowStale: Story = {
  args: {
    comparison: { ...comparison, stale: true },
    editing: {
      retention: retention(3),
      kept_count: 4,
      deleted_count: 8,
      freed_at_least: 5 * 1024 ** 3,
    },
    selectedKey: null,
    pending: false,
    refreshDisabled: false,
    onSelect: () => {},
    onRefresh: () => {},
  },
}

export const Empty: Story = {
  args: {
    comparison: { computed_at: null, archive_count_at: null, stale: true, candidates: [] },
    editing: null,
    selectedKey: null,
    pending: false,
    refreshDisabled: false,
    onSelect: () => {},
    onRefresh: () => {},
  },
}
