import { keyframes } from '@mui/system'

/** Emoji entrance and idle wobble, shared by the sidebar badge and the modal. */
export const festivePop = keyframes`
  0% { transform: scale(0) rotate(-40deg); }
  70% { transform: scale(1.15) rotate(-8deg); }
  100% { transform: scale(1) rotate(-14deg); }
`
export const festiveWobble = keyframes`
  0%, 88%, 100% { transform: rotate(-14deg); }
  92% { transform: rotate(-24deg); }
  96% { transform: rotate(-4deg); }
`
export const festiveEmojiAnimation = `${festivePop} 420ms cubic-bezier(0.34, 1.56, 0.64, 1) both, ${festiveWobble} 7s ease-in-out 1.5s infinite`
