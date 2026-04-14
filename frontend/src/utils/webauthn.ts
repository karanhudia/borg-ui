function base64UrlToBuffer(value: string): ArrayBuffer {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const normalized = (value + padding).replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(normalized)
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
}

function bytesToBase64Url(bytes: Uint8Array): string {
  const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join('')
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function credentialToJSON(value: unknown): unknown {
  if (value instanceof ArrayBuffer) {
    return bytesToBase64Url(new Uint8Array(value))
  }

  if (ArrayBuffer.isView(value)) {
    return bytesToBase64Url(new Uint8Array(value.buffer, value.byteOffset, value.byteLength))
  }

  if (Array.isArray(value)) {
    return value.map(credentialToJSON)
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, nested]) => [
        key,
        credentialToJSON(nested),
      ])
    )
  }

  return value
}

function serializeCredential(credential: PublicKeyCredential) {
  const response = credential.response as AuthenticatorResponse & {
    attestationObject?: ArrayBuffer
    clientDataJSON: ArrayBuffer
    transports?: string[]
    getTransports?: () => string[]
    authenticatorData?: ArrayBuffer
    signature?: ArrayBuffer
    userHandle?: ArrayBuffer | null
  }

  const serialized: Record<string, unknown> = {
    id: credential.id,
    type: credential.type,
    rawId: credentialToJSON(credential.rawId),
    response: {
      clientDataJSON: credentialToJSON(response.clientDataJSON),
    },
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment,
  }

  if ('attestationObject' in response && response.attestationObject) {
    ;(serialized.response as Record<string, unknown>).attestationObject = credentialToJSON(
      response.attestationObject
    )
  }

  if ('authenticatorData' in response && response.authenticatorData) {
    ;(serialized.response as Record<string, unknown>).authenticatorData = credentialToJSON(
      response.authenticatorData
    )
  }

  if ('signature' in response && response.signature) {
    ;(serialized.response as Record<string, unknown>).signature = credentialToJSON(
      response.signature
    )
  }

  if ('userHandle' in response) {
    ;(serialized.response as Record<string, unknown>).userHandle = credentialToJSON(
      response.userHandle ?? null
    )
  }

  const transports =
    typeof response.getTransports === 'function'
      ? response.getTransports()
      : Array.isArray(response.transports)
        ? response.transports
        : undefined

  if (transports) {
    ;(serialized.response as Record<string, unknown>).transports = transports
  }

  return serialized
}

export function prepareRegistrationOptions(
  options: Record<string, unknown>
): PublicKeyCredentialCreationOptions {
  const publicKey = options as Record<string, any>

  return {
    ...publicKey,
    challenge: base64UrlToBuffer(publicKey.challenge),
    user: {
      ...publicKey.user,
      id: base64UrlToBuffer(publicKey.user.id),
    },
    excludeCredentials: publicKey.excludeCredentials?.map((credential: Record<string, any>) => ({
      ...credential,
      id: base64UrlToBuffer(credential.id),
    })),
  } as PublicKeyCredentialCreationOptions
}

export function prepareAuthenticationOptions(
  options: Record<string, unknown>
): PublicKeyCredentialRequestOptions {
  const publicKey = options as Record<string, any>

  return {
    ...publicKey,
    challenge: base64UrlToBuffer(publicKey.challenge),
    allowCredentials: publicKey.allowCredentials?.map((credential: Record<string, any>) => ({
      ...credential,
      id: base64UrlToBuffer(credential.id),
    })),
  } as PublicKeyCredentialRequestOptions
}

export async function createPasskeyCredential(options: Record<string, unknown>) {
  const credential = (await navigator.credentials.create({
    publicKey: prepareRegistrationOptions(options),
  })) as PublicKeyCredential | null

  if (!credential) {
    throw new Error('Passkey creation was cancelled')
  }

  return serializeCredential(credential)
}

export async function getPasskeyAssertion(options: Record<string, unknown>) {
  const credential = (await navigator.credentials.get({
    publicKey: prepareAuthenticationOptions(options),
  })) as PublicKeyCredential | null

  if (!credential) {
    throw new Error('Passkey authentication was cancelled')
  }

  return serializeCredential(credential)
}

export async function isConditionalMediationAvailable(): Promise<boolean> {
  if (typeof PublicKeyCredential === 'undefined') return false
  const conditionalCheck = (
    PublicKeyCredential as typeof PublicKeyCredential & {
      isConditionalMediationAvailable?: () => Promise<boolean>
    }
  ).isConditionalMediationAvailable
  if (!conditionalCheck) return false
  return conditionalCheck()
}

export async function getConditionalPasskeyAssertion(
  options: Record<string, unknown>,
  signal?: AbortSignal
) {
  const credential = (await navigator.credentials.get({
    publicKey: prepareAuthenticationOptions(options),
    mediation: 'conditional' as CredentialMediationRequirement,
    signal,
  })) as PublicKeyCredential | null

  if (!credential) {
    throw new Error('Passkey authentication was cancelled')
  }

  return serializeCredential(credential)
}
