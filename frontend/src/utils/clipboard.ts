// navigator.clipboard only exists in secure contexts, so plain http on a LAN
// address needs the legacy execCommand path. Resolves false when nothing worked.
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Permission denied or similar; try the fallback below.
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  // Sit next to the focused control so a focus trap (MUI Dialog, Drawer, Menu)
  // does not pull focus away and drop the selection before the copy.
  const host = document.activeElement?.parentElement ?? document.body
  host.appendChild(textarea)
  textarea.focus()
  textarea.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    textarea.remove()
  }
}
