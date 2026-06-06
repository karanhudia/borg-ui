import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Divider } from '@mui/material'
import { ThemeProvider } from '@mui/material/styles'
import { SidebarUpdateNoticeView } from './SidebarUpdateNotice'
import { darkTheme } from '../theme'

const meta = {
  title: 'Components/SidebarUpdateNotice',
  parameters: {
    layout: 'centered',
  },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

const sidebarFrame = (children: React.ReactNode, dark = false) => (
  <Box
    sx={{
      width: 240,
      px: 2,
      pt: 1.5,
      pb: 1.5,
      borderRadius: 2,
      bgcolor: 'background.paper',
      border: 1,
      borderColor: 'divider',
    }}
  >
    <Divider sx={{ mb: 1.5 }} />
    {children}
    <Box
      sx={{
        mt: 1,
        height: 16,
        borderRadius: 0.75,
        bgcolor: dark ? 'rgba(255,255,255,0.05)' : 'rgba(15,23,42,0.05)',
      }}
    />
    <Box sx={{ mt: 1, display: 'flex', gap: 0.5 }}>
      <Box
        sx={{
          flex: 1,
          height: 14,
          borderRadius: 0.5,
          bgcolor: dark ? 'rgba(255,255,255,0.04)' : 'rgba(15,23,42,0.04)',
        }}
      />
      <Box
        sx={{
          flex: 0.6,
          height: 14,
          borderRadius: 0.5,
          bgcolor: dark ? 'rgba(255,255,255,0.04)' : 'rgba(15,23,42,0.04)',
        }}
      />
    </Box>
  </Box>
)

export const Light: Story = {
  render: () =>
    sidebarFrame(
      <SidebarUpdateNoticeView
        notice={{
          id: 'update-2.3.0-available',
          version: '2.3.0',
          title: 'Borg UI 2.3.0 is available',
          ctaUrl: 'https://github.com/karanhudia/borg-ui/releases/tag/v2.3.0',
        }}
        onDismiss={() => {}}
        onCtaClick={() => {}}
      />
    ),
}

export const Dark: Story = {
  render: () => (
    <ThemeProvider theme={darkTheme}>
      <Box sx={{ p: 2, bgcolor: 'background.default' }}>
        {sidebarFrame(
          <SidebarUpdateNoticeView
            notice={{
              id: 'update-2.3.0-available',
              version: '2.3.0',
              title: 'Borg UI 2.3.0 is available',
              ctaUrl: 'https://github.com/karanhudia/borg-ui/releases/tag/v2.3.0',
            }}
            onDismiss={() => {}}
            onCtaClick={() => {}}
          />,
          true
        )}
      </Box>
    </ThemeProvider>
  ),
}

export const WithoutVersion: Story = {
  render: () =>
    sidebarFrame(
      <SidebarUpdateNoticeView
        notice={{
          id: 'update-future-available',
          version: null,
          title: 'A new version is available',
          ctaUrl: 'https://github.com/karanhudia/borg-ui/releases',
        }}
        onDismiss={() => {}}
        onCtaClick={() => {}}
      />
    ),
}

export const WithoutCta: Story = {
  render: () =>
    sidebarFrame(
      <SidebarUpdateNoticeView
        notice={{
          id: 'update-2.3.0-available',
          version: '2.3.0',
          title: 'Borg UI 2.3.0 is available',
          ctaUrl: null,
        }}
        onDismiss={() => {}}
        onCtaClick={() => {}}
      />
    ),
}

export const StackedAbovePlanBadge: Story = {
  parameters: { layout: 'centered' },
  render: () =>
    sidebarFrame(
      <>
        <SidebarUpdateNoticeView
          notice={{
            id: 'update-2.3.0-available',
            version: '2.3.0',
            title: 'Borg UI 2.3.0 is available',
            ctaUrl: 'https://github.com/karanhudia/borg-ui/releases/tag/v2.3.0',
          }}
          onDismiss={() => {}}
          onCtaClick={() => {}}
        />
        <Box
          sx={{
            mb: 1,
            px: 1,
            py: 0.625,
            borderRadius: 1.5,
            bgcolor: 'rgba(91, 33, 182, 0.08)',
            border: '1px solid rgba(91, 33, 182, 0.22)',
            color: '#5b21b6',
            fontWeight: 700,
            fontSize: '0.7rem',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            display: 'inline-block',
          }}
        >
          ✦ Pro Plan
        </Box>
      </>
    ),
}
