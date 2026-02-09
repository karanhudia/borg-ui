import React from 'react'
import { Card, CardContent, Typography, Box } from '@mui/material'
import { Clock } from 'lucide-react'
import DataTable, { Column, ActionButton } from './DataTable'

interface ScheduledJobsTableProps<T = unknown> {
  jobs: T[]
  columns: Column<T>[]
  actions: ActionButton<T>[]
  isLoading: boolean
}

const ScheduledJobsTable = <T extends { id: number | string }>({
  jobs,
  columns,
  actions,
  isLoading,
}: ScheduledJobsTableProps<T>) => {
  return (
    <Card>
      <CardContent>
        <Typography variant="h6" fontWeight={600} gutterBottom>
          All Scheduled Jobs
        </Typography>

        <Box sx={{ mt: 2 }}>
          <DataTable
            data={jobs}
            columns={columns}
            actions={actions}
            getRowKey={(job) => job.id}
            loading={isLoading}
            enableHover={true}
            headerBgColor="background.default"
            emptyState={{
              icon: <Clock size={48} />,
              title: 'No scheduled jobs found',
              description: 'Create your first scheduled backup job',
            }}
          />
        </Box>
      </CardContent>
    </Card>
  )
}

export default ScheduledJobsTable as <T extends { id: number | string }>(
  props: ScheduledJobsTableProps<T>
) => React.JSX.Element
