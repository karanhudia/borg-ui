import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, test, type Page } from 'playwright/test'
import { SSH, api, blockAnalytics, login } from './helpers'

// The per-connection SSH key flows from PR #1498, against a real backend and a real
// sshd. The tests build on each other the way a user would, so they run in order.
test.describe.configure({ mode: 'serial' })

const KEY_A = 'e2e-generated'
const KEY_B = 'e2e-pasted'
const target = `${SSH.user}@${SSH.host}:${SSH.port}`

function makePrivateKey(passphrase: string): string {
  const dir = mkdtempSync(join(tmpdir(), 'borg-e2e-key-'))
  try {
    const path = join(dir, 'id')
    execFileSync('ssh-keygen', ['-q', '-t', 'ed25519', '-N', passphrase, '-C', 'e2e', '-f', path])
    return readFileSync(path, 'utf8')
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

async function openPage(page: Page) {
  await blockAnalytics(page)
  await page.goto('/ssh-connections')
  await expect(page.getByRole('heading', { name: 'System SSH Key' })).toBeVisible()
}

// MUI Tooltip gives these buttons the tooltip as their accessible name.
const headerButton = (page: Page, text: string) =>
  page.getByRole('button').filter({ hasText: text })

const extraKeyRow = (page: Page, name: string) =>
  page.getByRole('listitem').filter({ has: page.getByText(name, { exact: true }) })

// The smallest box holding both the status line and the card's actions is the card.
const card = (page: Page) =>
  page
    .locator('div')
    .filter({ has: page.getByText(/^(Connected|Failed|Testing|Unknown)$/) })
    .filter({ has: page.getByRole('button', { name: 'Deploy Key' }) })
    .last()

async function pickKey(page: Page, name: string) {
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('combobox', { name: 'SSH key' }).click()
  await page.getByRole('option').filter({ hasText: name }).click()
}

async function addKey(page: Page, tab: 'Generate' | 'Paste', name: string, privateKey?: string) {
  await page.getByRole('button', { name: 'Add Key', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add SSH Key' })
  await dialog.getByRole('tab', { name: tab }).click()
  await dialog.getByLabel('Key Name').fill(name)
  if (privateKey) await dialog.getByLabel('Private Key').fill(privateKey)
  await dialog.getByRole('button', { name: 'Add Key' }).click()
  return dialog
}

test.beforeAll(async ({ request }) => {
  const authed = api(request, await login(request))
  const keys = await (await authed.get('/api/ssh-keys')).json()
  if (!(keys.ssh_keys ?? keys).some((key: { is_system_key: boolean }) => key.is_system_key)) {
    const res = await authed.post('/api/ssh-keys/generate', {
      name: 'System Key',
      key_type: 'ed25519',
    })
    expect(res.ok(), await res.text()).toBeTruthy()
  }
})

test('with only the system key the deploy dialog has no key picker', async ({ page }) => {
  await openPage(page)
  await expect(headerButton(page, 'Deploy to Server')).toBeVisible()
  await expect(headerButton(page, 'Add Manual Connection')).toBeVisible()
  await expect(page.getByText('No additional keys yet.')).toBeVisible()

  await headerButton(page, 'Deploy to Server').click()
  const dialog = page.getByRole('dialog', { name: 'Deploy SSH Key to Server' })
  await expect(dialog.getByLabel('Host', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('combobox', { name: 'SSH key' })).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Cancel' }).click()
})

test('a generated key can be picked and deployed with a password', async ({ page }) => {
  await openPage(page)
  await addKey(page, 'Generate', KEY_A)
  await expect(page.getByText('SSH key added')).toBeVisible()
  await expect(extraKeyRow(page, KEY_A)).toContainText('Not used yet')

  await headerButton(page, 'Deploy to Server').click()
  const dialog = page.getByRole('dialog', { name: 'Deploy SSH Key to Server' })
  await pickKey(page, KEY_A)
  await dialog.getByLabel('Host', { exact: true }).fill(SSH.host)
  await dialog.getByLabel('Username', { exact: true }).fill(SSH.user)
  await dialog.getByRole('spinbutton', { name: 'Port' }).fill(String(SSH.port))
  await dialog.getByLabel('Password', { exact: true }).fill(SSH.password)
  await dialog.getByRole('button', { name: 'Deploy Key' }).click()

  await expect(page.getByText('SSH key deployed successfully!')).toBeVisible()
  await expect(dialog).toBeHidden()
  await expect(card(page)).toContainText('Connected')
  await expect(card(page)).toContainText(KEY_A)
  await expect(extraKeyRow(page, KEY_A)).toContainText('1 connection')
})

test('pasting a passphrase-protected key is refused', async ({ page }) => {
  await openPage(page)
  const dialog = await addKey(page, 'Paste', KEY_B, makePrivateKey('e2e-passphrase'))
  await expect(
    page.getByText('This key is protected with a passphrase.', { exact: false })
  ).toBeVisible()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(extraKeyRow(page, KEY_B)).toHaveCount(0)
})

test('switching a connection to another key and redeploying reconnects it', async ({ page }) => {
  await openPage(page)
  await addKey(page, 'Paste', KEY_B, makePrivateKey(''))
  await expect(extraKeyRow(page, KEY_B)).toContainText('Not used yet')

  await card(page).getByRole('button', { name: 'Edit' }).click()
  const edit = page.getByRole('dialog', { name: 'Edit SSH Connection' })
  await pickKey(page, KEY_B)
  await edit.getByRole('button', { name: 'Update Connection' }).click()
  await expect(edit).toBeHidden()
  // KEY_B is not in authorized_keys yet, so the automatic test fails.
  await expect(card(page)).toContainText(KEY_B)
  await expect(card(page)).toContainText('Failed')

  await card(page).getByRole('button', { name: 'Deploy Key' }).click()
  const redeploy = page.getByRole('dialog', { name: 'Deploy SSH Key to Connection' })
  await redeploy.getByLabel('Password', { exact: true }).fill(SSH.password)
  await redeploy.getByRole('button', { name: 'Deploy Key' }).click()
  await expect(redeploy).toBeHidden()
  await expect(card(page)).toContainText('Connected')
  await expect(extraKeyRow(page, KEY_B)).toContainText('1 connection')
  await expect(extraKeyRow(page, KEY_A)).toContainText('Not used yet')
})

test('an in-use key cannot be deleted, an unused one can', async ({ page }) => {
  await openPage(page)

  await page.getByRole('button', { name: `Delete key: ${KEY_B}` }).click()
  const blocked = page.getByRole('dialog', { name: 'Delete SSH Key' })
  await expect(blocked).toContainText('These connections use this key.')
  await expect(blocked).toContainText(target)
  await expect(blocked.getByRole('button', { name: 'Delete' })).toBeDisabled()
  await blocked.getByRole('button', { name: 'Cancel' }).click()
  await expect(blocked).toBeHidden()

  await page.getByRole('button', { name: `Delete key: ${KEY_A}` }).click()
  const dialog = page.getByRole('dialog', { name: 'Delete SSH Key' })
  await expect(dialog).not.toContainText('These connections use this key.')
  await dialog.getByRole('button', { name: 'Delete' }).click()
  await expect(dialog).toBeHidden()
  await expect(extraKeyRow(page, KEY_A)).toHaveCount(0)
  await expect(extraKeyRow(page, KEY_B)).toBeVisible()
})
