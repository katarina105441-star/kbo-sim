import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const progressLabel = { ahead: '목표 초과', on_track: '목표선', behind: '목표 미달' }

export default function Dashboard({ state, busy, onAdvance, onLive }) {
  const t = state.my_team
  const identity = t.identity
  const seasonOver = state.day >= state.days_total
  const [office, setOffice] = useState(null)

  useEffect(() => {
    api.frontOffice().then(setOffice).catch(() => setOffice(null))
  }, [state.year, state.day, state.my_rank])

  return (
    <div className="two-col">
      <section className="card">
        <h2>{t.name} <span className="badge">{state.my_rank}위</span></h2>
        <div className="bigline">{t.wins}승 {t.ties}무 {t.losses}패
          <span className="muted"> · 승률 {t.pct.toFixed(3)} · {t.games}경기</span></div>
        {identity && <div className="identity-panel">
          <div><b>{identity.label}</b><span>{identity.manager_style}</span></div>
          <div className="identity-tags">
            <span>{identity.strategy_label}</span>
            <span>타격 {identity.offense_label}</span>
            <span>투수 {identity.pitching_label}</span>
            <span>스카우팅 {Math.round(identity.scouting * 100)}</span>
          </div>
          <p>{identity.description}</p>
        </div>}
        {office && <div className={`front-office-panel ${office.risk_level}`}>
          <div className="front-office-head">
            <div>
              <span className="eyebrow">{office.objective.year}년차 구단주 목표</span>
              <b>{office.objective.title}</b>
            </div>
            <span className={`risk-badge ${office.risk_level}`}>{office.risk_label}</span>
          </div>
          <p>{office.objective.summary}</p>
          <div className="objective-row">
            <span>목표 {office.objective.target_rank}위 이내</span>
            <b className={office.progress}>{office.current_rank}위 · {progressLabel[office.progress]}</b>
          </div>
          <div className="confidence-row">
            <span>구단주 신뢰도</span><b>{office.owner_confidence}</b>
          </div>
          <div className="confidence-track">
            <div className="confidence-fill" style={{ width: `${office.owner_confidence}%` }} />
          </div>
          <div className="dismissal-row">
            <span>해임 위험 {office.dismissal_probability}%</span>
            <span>연속 실패 {office.failed_streak}시즌</span>
          </div>
        </div>}
        {state.next_games.length > 0 && (
          <p>다음 경기: {state.next_games.map(g =>
            `${g.away} @ ${g.home}${g.home === state.user_tid ? ' (홈)' : ' (원정)'}`).join(', ')}</p>
        )}
        <h3>시즌 진행</h3>
        <div className="btn-row">
          <button disabled={busy || seasonOver} className="live-start" onClick={onLive}>
            {state.live_active ? '실시간 경기로 복귀 ⚾' : '직접 운영 ⚾'}
          </button>
          <button disabled={busy || state.live_active} onClick={() => onAdvance('day')}>하루 ▶</button>
          <button disabled={busy || state.live_active} onClick={() => onAdvance('series')}>시리즈(3일) ▶▶</button>
          <button disabled={busy || state.live_active} onClick={() => onAdvance('month')}>한 달 ▶▶▶</button>
          <button disabled={busy || state.live_active} className="primary" onClick={() => onAdvance('season_end')}>
            시즌 끝까지 ⏭ {seasonOver ? '(새 시즌 시작)' : ''}
          </button>
        </div>
        {busy && <p className="muted">시뮬레이션 중…</p>}
      </section>
      <section className="card">
        <h3>알림</h3>
        {state.news.length === 0
          ? <p className="muted">아직 소식이 없습니다. 시즌을 진행하세요.</p>
          : <ul className="news">{state.news.map((n, i) => <li key={i}>{n}</li>)}</ul>}
        {office?.latest_evaluation && <div className="latest-evaluation">
          <h3>직전 시즌 프런트 평가</h3>
          <div><b className={`grade grade-${office.latest_evaluation.grade.toLowerCase()}`}>
            {office.latest_evaluation.grade}</b>
            <span>{office.latest_evaluation.year}년차 · {office.latest_evaluation.summary}</span></div>
          <p>신뢰도 {office.latest_evaluation.confidence_before} → {office.latest_evaluation.confidence_after}
            <b> ({office.latest_evaluation.confidence_delta > 0 ? '+' : ''}{office.latest_evaluation.confidence_delta})</b></p>
        </div>}
        {office && office.history.length > 0 && <>
          <h3>감독 성과 기록</h3>
          <div className="career-summary">
            <span>{office.career.seasons}시즌</span>
            <span>목표 달성 {office.career.goals_met}회</span>
            <span>최고 {office.career.best_rank}위</span>
            <span>우승 {office.career.championships}회</span>
          </div>
          <table className="office-history"><thead><tr><th>년차</th><th>목표</th><th>결과</th><th>평가</th><th>신뢰도</th></tr></thead>
            <tbody>{office.history.map(h => (
              <tr key={h.year}><td>{h.year}</td><td>{h.target_rank}위</td>
                <td>{h.actual_rank}위</td><td><b>{h.grade}</b></td>
                <td>{h.confidence_after}</td></tr>))}</tbody>
          </table>
        </>}
        {state.history.length > 0 && <>
          <h3>시즌 연혁</h3>
          <table><thead><tr><th>년차</th><th>우승</th><th>내 순위</th><th>내 성적</th></tr></thead>
            <tbody>{state.history.map(h => (
              <tr key={h.year}><td>{h.year}</td><td>{h.champion}</td>
                <td>{h.my_rank}위</td><td>{h.my_record}</td></tr>))}</tbody>
          </table>
        </>}
      </section>
    </div>
  )
}
