import type { Tokens } from './tokens'

export function gaugeColor(pct: number, T: Tokens) {
  return pct > 80 ? T.red : pct > 60 ? T.amber : T.blue
}

export function toGB(b: number) {
  return (b / 1024 / 1024 / 1024).toFixed(1)
}

export function toCompactGB(b: number) {
  const gb = b / 1024 / 1024 / 1024
  return gb >= 10 ? gb.toFixed(0) : gb.toFixed(1)
}
