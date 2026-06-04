export function getDefaultRepositoryEncryption(borgVersion: 1 | 2 = 1) {
  return borgVersion === 2 ? 'repokey-aes-ocb' : 'repokey'
}
