/** Operation statuses that mean the work ran to an end it counts as done. */
export const SUCCESS_OPERATION_STATUSES: ReadonlySet<string> = new Set([
  'completed',
  'completed_with_warnings',
])
