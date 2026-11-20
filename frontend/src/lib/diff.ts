/** Word-level diff (longest common subsequence) for showing what an amendment changes. */

export type DiffPart = { type: 'same' | 'added' | 'removed'; text: string }

const MAX_CELLS = 4_000_000 // ~2000 x 2000 words; beyond that we show "removed all / added all"

const tokens = (s: string) => s.match(/\s+|[^\s]+/g) ?? []

export function diffWords(before: string, after: string): DiffPart[] {
  const a = tokens(before)
  const b = tokens(after)
  if (a.length * b.length > MAX_CELLS) {
    return [
      ...(before ? [{ type: 'removed' as const, text: before }] : []),
      ...(after ? [{ type: 'added' as const, text: after }] : []),
    ]
  }
  // lcs[i][j] = length of LCS of a[i:] and b[j:], stored row by row in one typed array
  const w = b.length + 1
  const lcs = new Uint16Array((a.length + 1) * w)
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i * w + j] = a[i] === b[j] ? lcs[(i + 1) * w + j + 1] + 1 : Math.max(lcs[(i + 1) * w + j], lcs[i * w + j + 1])
    }
  }
  const parts: DiffPart[] = []
  const push = (type: DiffPart['type'], text: string) => {
    const last = parts[parts.length - 1]
    if (last && last.type === type) last.text += text
    else parts.push({ type, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push('same', a[i])
      i++
      j++
    } else if (lcs[(i + 1) * w + j] >= lcs[i * w + j + 1]) {
      push('removed', a[i++])
    } else {
      push('added', b[j++])
    }
  }
  while (i < a.length) push('removed', a[i++])
  while (j < b.length) push('added', b[j++])
  // Whitespace-only changes inside a run read better as unchanged.
  return readable(parts.map((p) => (p.type !== 'same' && !p.text.trim() ? { ...p, type: 'same' } : p)))
}

/**
 * Make changes read as phrases: tiny unchanged fragments ("to", "the of") sitting between two
 * changes are folded into the change, and each change region becomes one removed phrase
 * followed by one added phrase.
 *   "~~on payment made~~ subject ~~at~~ to the ~~rates mentioned~~ provisions"
 *   -> "~~on payment made at the rates mentioned~~ subject to the provisions"
 */
function readable(parts: DiffPart[], maxWords = 2): DiffPart[] {
  const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length
  const out: DiffPart[] = []
  let removed = ''
  let added = ''
  let open = false
  const flush = () => {
    if (removed) out.push({ type: 'removed', text: removed })
    if (added) out.push({ type: 'added', text: added })
    removed = ''
    added = ''
    open = false
  }
  parts.forEach((p, k) => {
    if (p.type === 'removed') {
      removed += p.text
      open = true
    } else if (p.type === 'added') {
      added += p.text
      open = true
    } else {
      const nextIsChange = parts[k + 1] && parts[k + 1].type !== 'same'
      if (open && nextIsChange && words(p.text) <= maxWords) {
        removed += p.text // absorb the short shared fragment into both sides
        added += p.text
      } else {
        flush()
        out.push(p)
      }
    }
  })
  flush()
  return out
}
