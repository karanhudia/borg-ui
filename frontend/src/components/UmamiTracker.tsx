import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { trackPageView } from '../utils/analytics'

/**
 * Tracks page views on route changes.
 * Umami's auto-track is disabled so this fires only when the user has opted in.
 */
export const UmamiTracker = () => {
  const location = useLocation()

  useEffect(() => {
    trackPageView(`${location.pathname}${location.search}`)
  }, [location])

  return null
}
