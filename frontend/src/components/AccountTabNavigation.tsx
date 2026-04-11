import { Box, Tab, Tabs } from '@mui/material'
import { ShieldCheck, User } from 'lucide-react'

export type AccountView = 'profile' | 'access'

interface AccountTabNavigationProps {
  value: AccountView
  onChange: (view: AccountView) => void
}

export default function AccountTabNavigation({ value, onChange }: AccountTabNavigationProps) {
  return (
    <Box sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
      <Tabs
        value={value === 'profile' ? 0 : 1}
        onChange={(_, nextValue) => onChange(nextValue === 0 ? 'profile' : 'access')}
        sx={{ px: { xs: 1, md: 2 } }}
      >
        <Tab
          icon={<User size={15} />}
          iconPosition="start"
          label="Profile"
          sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
        />
        <Tab
          icon={<ShieldCheck size={15} />}
          iconPosition="start"
          label="Access"
          sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
        />
      </Tabs>
    </Box>
  )
}
