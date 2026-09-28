import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { I18nextProvider } from 'react-i18next'
import i18n from '../../i18n'
import { SuccessDonutLegend } from './SuccessDonutLegend'
import { makeT, TokenContext } from './tokens'

// Follows the Storybook theme toolbar, so each story renders both modes.
const useStoryT = () => makeT(useTheme().palette.mode === 'dark')

// Same 200px rail the dashboard renders the donut card in.
function Rail({ passed, failed }: { passed: number; failed: number }) {
  const T = useStoryT()
  return (
    <TokenContext.Provider value={T}>
      <Box
        sx={{
          width: 200,
          bgcolor: T.bgCard,
          border: `1px solid ${T.border}`,
          borderRadius: T.radius,
          p: 2,
        }}
      >
        <Box sx={{ px: 0.5 }}>
          <SuccessDonutLegend passed={passed} failed={failed} />
        </Box>
      </Box>
    </TokenContext.Provider>
  )
}

const meta = {
  title: 'Pages/DashboardV3/SuccessDonutLegend',
  component: SuccessDonutLegend,
  parameters: { layout: 'centered' },
  args: { passed: 349, failed: 5 },
} satisfies Meta<typeof SuccessDonutLegend>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: (args) => (
    <I18nextProvider i18n={i18n.cloneInstance({ lng: 'en' })}>
      <Rail {...args} />
    </I18nextProvider>
  ),
}

// Regression for #1214: "fehlgeschlagen" used to run past the card edge.
export const GermanLongLabels: Story = {
  render: (args) => (
    <I18nextProvider i18n={i18n.cloneInstance({ lng: 'de' })}>
      <Rail {...args} />
    </I18nextProvider>
  ),
}
