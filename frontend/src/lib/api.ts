export type GroundedSpan = { source: string; rendered: string; node_id: string }
export type Card = { kind: string; source: string; literal: string; meaning: string; why_it_matters: string }
export type LinkerSpan = { start: number; end: number; source: string; node_id: string | null; type: string; confidence: number; rendered: string; candidates: string[]; method: string }
export type Transcript = {
  type: 'transcript'; utterance_id: number; call_id: number; speaker: string; listener: string; role: string
  src_text: string; translation: string; target_lang: string; grounded_spans: GroundedSpan[]; pragmatics_cards: Card[]
  passthrough: string[]; linker_spans: LinkerSpan[]; latencies: Record<string, number>; confidence: number; error: string | null
}
export type Person = { id: string; name: string; lang_name: string; render: string; aliases: string[]; notes: string; deceased: boolean; gender: string; birth_year: number | null; is_learner: boolean }
export type Edge = { src: string; dst: string; relation: string; lang_term: string }
export type Thing = { id: string; kind: string; name: string; lang_name: string; aliases: string[]; note: string }

export function kinKey(): string { try { return localStorage.getItem('kin.key') || '' } catch { return '' } }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const key = kinKey()
  const r = await fetch(path, { ...init, headers: { 'content-type': 'application/json', ...(key ? { 'X-KIN-Key': key } : {}), ...(init?.headers || {}) } })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json() as Promise<T>
}

export function wsUrl(path: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const key = kinKey()
  return `${proto}://${location.host}${path}${key ? (path.includes('?') ? '&' : '?') + 'key=' + encodeURIComponent(key) : ''}`
}
