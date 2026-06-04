import { Box, Tab, Tabs } from '@mui/material'
import { KeyRound, ShieldCheck, User } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export type AccountView = 'profile' | 'security' | 'access'

interface AccountTabNavigationProps {
  value: AccountView
  onChange: (view: AccountView) => void
  showSecurityTab?: boolean
}

export default function AccountTabNavigation({
  value,
  onChange,
  showSecurityTab = true,
}: AccountTabNavigationProps) {
  const { t } = useTranslation()
  const tabs = showSecurityTab
    ? [
        { value: 'profile' as const, label: t('settings.account.profile.title'), icon: User },
        { value: 'security' as const, label: t('settings.account.security.title'), icon: KeyRound },
        { value: 'access' as const, label: t('settings.account.access.title'), icon: ShieldCheck },
      ]
    : [
        { value: 'profile' as const, label: t('settings.account.profile.title'), icon: User },
        { value: 'access' as const, label: t('settings.account.access.title'), icon: ShieldCheck },
      ]

  return (
    <Box sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
      <Tabs
        value={tabs.findIndex((tab) => tab.value === value)}
        onChange={(_, nextValue) => onChange(tabs[nextValue].value)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        sx={{ px: { xs: 1, md: 2 } }}
      >
        {tabs.map((tab) => {
          const Icon = tab.icon

          return (
            <Tab
              key={tab.value}
              icon={<Icon size={15} />}
              iconPosition="start"
              label={tab.label}
              sx={{ minHeight: 48, gap: 0.5, textTransform: 'none', fontWeight: 600 }}
            />
          )
        })}
      </Tabs>
    </Box>
  )
}
