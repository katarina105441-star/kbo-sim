import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function PlayerModal({ pid, onClose }) {
  const [p, setP] = useState(null)
  useEffect(() => { api.player(pid).then(setP) }, [pid])
  if (!p) return null
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <button className="close" onClick={onClose}>✕</button>
        <h2>{p.name} <span className="muted">{p.age}세 · {p.pos} · {p.hand} · {p.team}</span></h2>
        <p>OVR <b>{Math.round(p.ovr)}</b>{p.age < 30 && <> · 잠재 <b>{Math.round(p.pot)}</b></>}
          {' '}· 계약 {p.salary}억 × {p.years}년
          {p.signing_bonus > 0 && ` (계약금 ${p.signing_bonus}억)`}
          {' '}· FA 서비스 {p.service_years}년{p.fa_grade && ` · 직전 FA ${p.fa_grade}등급`}</p>
        <div className="rate-bars">
          {Object.entries(p.ratings).map(([k, v]) => (
            <div key={k} className="rate-bar">
              <span className="rlabel">{k}</span>
              <div className="bar"><div className={'fill' + (v >= 80 ? ' hi' : '')}
                                        style={{ width: `${Math.min(100, v)}%` }} /></div>
              <span className="rval">{v}</span>
            </div>))}
        </div>
        <h3>시즌 기록</h3>
        <table className="dense"><thead><tr>
          {Object.keys(p.season_full).map(k => <th key={k}>{k}</th>)}</tr></thead>
          <tbody><tr>{Object.values(p.season_full).map((v, i) => <td key={i}>{v}</td>)}</tr></tbody>
        </table>
        {p.basis && <p className="muted">능력치 근거: {p.basis}{p.est ? ' (추정)' : ''}</p>}
      </div>
    </div>
  )
}
