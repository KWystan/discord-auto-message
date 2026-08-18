// Interval presets (minutes): 60, 90, 120, ... 360.
export const INTERVAL_OPTIONS = Array.from({ length: 11 }, (_, i) => 60 + i * 30)

export function fmtIntervalMin(m) {
  const h = Math.floor(m / 60)
  const r = m % 60
  if (h === 0) return `${m} minutes`
  const hPart = h === 1 ? '1 hour' : `${h} hours`
  if (r === 0) return hPart
  return `${hPart} and ${r} minute${r === 1 ? '' : 's'}`
}

const EMOJI_RE = /^\p{Extended_Pictographic}\ufe0f?(?:\u200d\p{Extended_Pictographic}\ufe0f?)*/u

// Pull the leading emoji out of a live Discord channel name (e.g. the
// "🚧" in "🚧・buy-sell-signs") so rows can show it as their glyph while the
// short hardcoded name stays the display name.
export function channelIcon(liveName) {
  if (!liveName) return ''
  const m = String(liveName).match(EMOJI_RE)
  return m ? m[0] : ''
}

