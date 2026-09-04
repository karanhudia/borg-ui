/** Show the remaining-days countdown in the plan badge once the trial is inside this window. */
export const FULL_ACCESS_COUNTDOWN_THRESHOLD_DAYS = 14

export function fullAccessDaysLeft(
  expiresAt: string | null | undefined,
  now: number = Date.now()
): number | null {
  if (!expiresAt) return null
  const ms = new Date(expiresAt).getTime() - now
  if (!Number.isFinite(ms)) return null
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)))
}
