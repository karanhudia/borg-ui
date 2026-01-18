import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { trackPageView } from '../utils/matomo'

/**
 * Component that automatically tracks page views on route changes
 * Should be placed inside Router but outside Route components
 */
export const MatomoTracker = () => {
  const location = useLocation()

  useEffect(() => {
    // Track page view on route change
    trackPageView(`${location.pathname}${location.search}`)
  }, [location])

  return null // This component doesn't render anything
}
