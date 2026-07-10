import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function TeamSelect({ onStart, onLoad }) {
  const [teams, setTeams] = useState([])
  const [tid, setTid] = useState(null)
  const [seed, setSeed] = useState('')

  useEffect(() => {
    Promise.all([api.teamsAll(), api.teamIdentities()]).then(([rows, identities]) => {
      setTeams(rows.map(team => ({ ...team, identity: identities[team.tid] })))
    })
  }, [])

  return (
    <div className="team-select">
      <h1>⚾ KBO 매니저 — 단장 모드</h1>
      <p className="muted">운영할 구단을 선택하세요. 나머지 9개 구단은 서로 다른 운영 철학으로 움직입니다.</p>
      <div className="team-grid">
        {teams.map(t => (
          <button key={t.tid} className={tid === t.tid ? 'team-card on' : 'team-card'}
                  onClick={() => setTid(t.tid)}>
            <div className="team-tid">{t.tid}</div>
            <div className="team-name">{t.name}</div>
            <div className="muted">{t.city} · {t.stadium}</div>
            {t.identity && <div className="identity-mini">
              <b>{t.identity.label}</b>
              <span>{t.identity.manager_style}</span>
              <span>{t.identity.strategy_label} · 타격 {t.identity.offense_label} · 투수 {t.identity.pitching_label}</span>
            </div>}
          </button>
        ))}
      </div>
      {tid && teams.find(t => t.tid === tid)?.identity && <div className="identity-preview">
        <b>{teams.find(t => t.tid === tid).identity.label}</b>
        <span>{teams.find(t => t.tid === tid).identity.description}</span>
      </div>}
      <div className="start-row">
        <label>시드(선택): <input value={seed} onChange={e => setSeed(e.target.value)}
                                placeholder="비우면 랜덤" /></label>
        <button className="primary" disabled={!tid}
                onClick={() => onStart(tid, seed === '' ? null : Number(seed))}>
          {tid ? `${tid}로 시작` : '팀을 선택하세요'}
        </button>
        <button className="ghost" onClick={() => onLoad().catch(e => alert(e.message))}>
          저장된 게임 불러오기
        </button>
      </div>
    </div>
  )
}
