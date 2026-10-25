// Typed fetch helpers for the KIN backend (proxied by Vite: /api -> :8000).

const TIMEOUT_MS = 15000
/** Present only when the backend is locked; carried into invite links. */
export const API_KEY = new URLSearchParams(location.search).get('key') || ''

export type Role = 'grandchild' | 'grandparent'
export interface Family { id: number; name: string; heritage_lang: string; language: string }
export interface Language { code: string; name: string; native_name: string; available: boolean }
export interface Relation { path: string; label: string; gloss?: string }
export interface Person { id: string; name: string; render: string; is_learner: boolean; deceased: boolean; generation: number }
export interface Graph { family_id: number; heritage_lang: string; people: Person[] }
export interface JoinResult { call_id: number; room: string; token: string; url: string; role: Role; person: string; name: string; heritage_lang: string }
export interface SetupIn { language: string; your_name: string; their_name: string; you_call_them: string; relation: string }

function detail(body: unknown, status: number): string {
  const d = (body as { detail?: unknown } | null)?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg).filter(Boolean).join('; ')
  return `HTTP ${status}`
}

async function req<T>(path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = API_KEY ? { 'x-kin-key': API_KEY } : {}
  if (body !== undefined) headers['content-type'] = 'application/json'
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
  const data: unknown = await res.json().catch(() => null)
  if (!res.ok) throw new Error(detail(data, res.status))
  return data as T
}

export const errText = (e: unknown) => (e instanceof Error ? (e.name === 'TimeoutError' ? 'KIN did not answer in time' : e.message) : String(e))

export const api = {
  families: () => req<Family[]>('/api/family/all'),
  languages: () => req<Language[]>('/api/languages'),
  relations: () => req<Relation[]>('/api/family/relations'),
  suggest: (term: string, familyId: number) => req<Relation[]>(`/api/family/suggest?${new URLSearchParams({ term, family_id: String(familyId) })}`),
  setup: (b: SetupIn) => req<{ family_id: number; render: string }>('/api/family/setup', b),
  addRelative: (b: { family_id: number; path: string; name: string; you_call_them: string }) =>
    req<{ id: string; name: string; render: string }>('/api/family/relative', b),
  graph: (familyId: number) => req<Graph>(`/api/family/graph?family_id=${familyId}`),
  join: (b: { family_id: number; role: Role; call_id?: number }) => req<JoinResult>('/api/rtc/join', b),
}

/** The person the grandchild calls: oldest living non-learner (the one set up first in practice). */
export const elderOf = (g: Graph): Person | undefined =>
  [...g.people].filter((p) => !p.is_learner && !p.deceased).sort((a, b) => a.generation - b.generation)[0]
