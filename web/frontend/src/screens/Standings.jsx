import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Standings({ userTid }) {
  const [rows, setRows] = useState([])
  useEffect(() => { api.standings().then(setRows) }, [])
  return (
    <section className="card">
      <h2>리그 순위</h2>
      <table className="dense">
        <thead><tr>
          <th>순위</th><th>팀</th><th>경기</th><th>승</th><th>무</th><th>패</th>
          <th>승률</th><th>게임차</th>
        </tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.tid}
                className={(r.tid === userTid ? 'me ' : '') + (r.rank === 5 ? 'ps-line' : '')}>
              <td>{r.rank}</td>
              <td className="tl">{r.tid === userTid ? '★ ' : ''}{r.name}</td>
              <td>{r.games}</td><td>{r.wins}</td><td>{r.ties}</td><td>{r.losses}</td>
              <td>{r.pct.toFixed(3)}</td><td>{r.gb === 0 ? '-' : r.gb}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">5위까지 포스트시즌 진출 (굵은 선)</p>
    </section>
  )
}
