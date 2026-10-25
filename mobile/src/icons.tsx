// Inline icons (no icon font, no emoji). currentColor everywhere.
const P = { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' } as const

export const MicIcon = ({ off = false }: { off?: boolean }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...P}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    {off && <path d="M4 4l16 16" />}
  </svg>
)
export const PhoneIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...P}>
    <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />
  </svg>
)
export const HangUpIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...P}>
    <path d="M3 15.5c5-5 13-5 18 0l-2.5 2.5-3.5-2v-2.5a10 10 0 0 0-6 0V16l-3.5 2z" />
  </svg>
)
export const SpeakerIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...P}>
    <path d="M4 9h4l5-4v14l-5-4H4zM16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" />
  </svg>
)
export const CloseIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...P}><path d="M6 6l12 12M18 6L6 18" /></svg>
)
export const CheckIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="currentColor" /><path d="M7 12.5l3.2 3L17 9" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
)
