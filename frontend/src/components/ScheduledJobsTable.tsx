import React from 'react'
import { Card, CardContent, Typography, Box } from '@mui/material'
import { Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
  return (
    <Card>
      <CardContent>
        <Typography variant="h6" fontWeight={600} gutterBottom>
          {t('scheduledJobsTableSection.title')}
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
              title: t('scheduledJobsTableSection.noJobsFound'),
              description: t('scheduledJobsTableSection.noJobsDesc'),
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
