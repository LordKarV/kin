// Invite links: the grandchild shares one, the grandparent opens it. Pure, tested with node --test.

export interface Invite { call: number; family: number; role: 'grandparent'; key: string }

/** https://<host>/?call=<id>&family=<fid>&role=grandparent (plus the API key when the backend is locked). */
export function inviteLink(host: string, call: number, family: number, key = ''): string {
  const q = new URLSearchParams({ call: String(call), family: String(family), role: 'grandparent' })
  if (key) q.set('key', key)
  return `https://${host}/?${q}`
}

/** The invite in a page's query string, or null when this is not a grandparent link. */
export function parseInvite(search: string): Invite | null {
  const q = new URLSearchParams(search)
  const call = Number(q.get('call'))
  const family = Number(q.get('family'))
  if (q.get('role') !== 'grandparent' || !Number.isInteger(call) || call <= 0 || !Number.isInteger(family) || family <= 0) return null
  return { call, family, role: 'grandparent', key: q.get('key') || '' }
}

/** A language's name in that language ("ta" -> "தமிழ்"), or in English with display = 'en'. */
export function langLabel(code: string, display = code): string {
  try {
    return new Intl.DisplayNames([display], { type: 'language' }).of(code) || code
  } catch {
    return code
  }
}
