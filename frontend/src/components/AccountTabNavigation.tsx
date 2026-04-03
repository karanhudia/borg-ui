import { Box, Tab, Tabs } from '@mui/material'
import { Lock, ShieldCheck, User } from 'lucide-react'

export type AccountView = 'profile' | 'security' | 'access'

interface AccountTabNavigationProps {
  value: AccountView
  onChange: (view: AccountView) => void
}

export default function AccountTabNavigation({ value, onChange }: AccountTabNavigationProps) {
  return (
    <Box sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
      <Tabs
        value={value === 'profile' ? 0 : value === 'security' ? 1 : 2}
        onChange={(_, nextValue) =>
          onChange(nextValue === 0 ? 'profile' : nextValue === 1 ? 'security' : 'access')
        }
        sx={{ px: { xs: 1, md: 2 } }}
      >
        <Tab
          icon={<User size={15} />}
          iconPosition="start"
          label="Profile"
          sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
        />
        <Tab
          icon={<Lock size={15} />}
          iconPosition="start"
          label="Security"
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
