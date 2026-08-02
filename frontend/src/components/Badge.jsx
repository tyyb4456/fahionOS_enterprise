const badgeMap = {
  critical: { bg: 'rgba(239,68,68,0.12)',    border: 'rgba(239,68,68,0.35)',    text: '#f87171' },
  warning:  { bg: 'rgba(250,204,21,0.12)',   border: 'rgba(250,204,21,0.35)',   text: '#facc15' },
  info:     { bg: 'rgba(212,212,216,0.12)',   border: 'rgba(212,212,216,0.35)',   text: '#d4d4d8' },
  healthy:  { bg: 'rgba(74,222,128,0.12)',   border: 'rgba(74,222,128,0.35)',   text: '#4ade80' },
  pending:  { bg: 'rgba(212,212,216,0.12)',   border: 'rgba(212,212,216,0.35)',   text: '#d4d4d8' },
  posted:   { bg: 'rgba(74,222,128,0.12)',   border: 'rgba(74,222,128,0.35)',   text: '#4ade80' },
  skipped:  { bg: 'rgba(148,163,184,0.12)',  border: 'rgba(148,163,184,0.35)',  text: '#94a3b8' },
}

export default function Badge({ level }) {
  const s = badgeMap[level] || badgeMap.info
  return (
    <span style={{
      fontSize: '0.6rem', fontWeight: 600,
      letterSpacing: '0.1em', textTransform: 'uppercase',
      padding: '2px 8px',
      background: s.bg, border: `1px solid ${s.border}`, color: s.text,
      fontFamily: "'Knewave', cursive",
    }}>
      {level}
    </span>
  )
}
