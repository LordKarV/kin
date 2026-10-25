// Which remote audio to play, and where LiveKit lives. Pure, tested with node --test.

export const AGENT_IDENTITY = 'kin'
export type Route = 'kin' | 'peer' | 'skip'

/**
 * The KIN agent publishes one translated-voice track per listener, `kin-to-<identity>`. Play only mine; the other
 * person's kin-to track is their translation and must never play here. Any other audio from a person is their real
 * voice (played, ducked under KIN). Anything else the agent publishes is ignored.
 */
export function routeTrack(trackName: string, fromIdentity: string, myIdentity: string): Route {
  if (trackName.startsWith('kin-to-')) return trackName === `kin-to-${myIdentity}` ? 'kin' : 'skip'
  if (fromIdentity === AGENT_IDENTITY || fromIdentity === myIdentity) return 'skip'
  return 'peer'
}

/** A wss:// URL from the API is used as is; otherwise go through this page's origin (Vite proxies /rtc to :7880). */
export function lkUrl(apiUrl: string, host: string, pageProtocol = 'https:'): string {
  if (apiUrl.startsWith('wss://')) return apiUrl
  return `${pageProtocol === 'https:' ? 'wss' : 'ws'}://${host}`
}
