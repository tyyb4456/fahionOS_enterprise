import { formatPrimitive, isFlatObject, labelize } from './utils'

export default function PrettyJSON({ value, depth = 0 }) {
  if (value === null || value === undefined || typeof value !== 'object') {
    return formatPrimitive(value)
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span style={{ fontFamily: "'Knewave', cursive", fontSize: '0.66rem', color: 'rgba(242,237,228,0.25)' }}>No items</span>
    }
    if (value.every(isFlatObject)) {
      const cols = [...new Set(value.flatMap(o => Object.keys(o)))]
      return (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: "'Knewave', cursive", fontSize: '0.63rem' }}>
            <thead>
              <tr style={{ color: 'rgba(242,237,228,0.3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                {cols.map(c => (
                  <th key={c} style={{ padding: '4px 8px', textAlign: 'left', fontWeight: 400, borderBottom: '1px solid rgba(255,255,255,0.07)', whiteSpace: 'nowrap' }}>
                    {labelize(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {value.map((row, i) => (
                <tr key={i} style={{ background: i % 2 ? 'rgba(255,255,255,0.02)' : 'transparent' }}>
                  {cols.map(c => (
                    <td key={c} style={{ padding: '5px 8px', whiteSpace: 'nowrap' }}>{formatPrimitive(row[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {value.map((item, i) => (
          <div key={i} style={{ background: '#191919', border: '1px solid rgba(255,255,255,0.06)', padding: '7px 9px' }}>
            <PrettyJSON value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }

  const entries = Object.entries(value)
  if (entries.length === 0) {
    return <span style={{ fontFamily: "'Knewave', cursive", fontSize: '0.66rem', color: 'rgba(242,237,228,0.25)' }}>Empty</span>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: depth === 0 ? 6 : 4 }}>
      {entries.map(([k, v]) => {
        const isComplex = v && typeof v === 'object'
        return (
          <div key={k} style={{
            display: 'flex', gap: 10,
            flexDirection: isComplex ? 'column' : 'row',
            alignItems: isComplex ? 'stretch' : 'baseline',
            padding: depth === 0 ? '3px 0' : 0,
            borderBottom: depth === 0 ? '1px solid rgba(255,255,255,0.04)' : 'none',
          }}>
            <span style={{
              fontFamily: "'Knewave', cursive", fontSize: '0.62rem',
              letterSpacing: '0.06em', color: 'rgba(242,237,228,0.4)',
              minWidth: isComplex ? 'auto' : 110, flexShrink: 0,
            }}>
              {labelize(k)}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <PrettyJSON value={v} depth={depth + 1} />
            </div>
          </div>
        )
      })}
    </div>
  )
}