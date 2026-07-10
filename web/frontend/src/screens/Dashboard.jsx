import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const progressLabel = { ahead: '목표 초과', on_track: '목표선', behind: '목표 미달' }
const signed = n => `${n > 0 ? '+' : ''}${n}`

function effectText(effects) {
  const parts = []
  if (effects.budget) parts.push(`예산 ${signed(effects.budget)}억`)
  if (effects.confidence) parts.push(`신뢰도 ${signed(effects.confidence)}`)
  if (effects.points) parts.push(`포인트 +${effects.points}`)
  return parts.join(' · ') || '즉시 수치 변화 없음'
}

export default function Dashboard({ state, busy, onAdvance, onLive, onRefresh }) {
  const t = state.my_team
  const identity = t.identity
  const seasonOver = state.day >= state.days_total
  const [office, setOffice] = useState(null)
  const [engagement, setEngagement] = useState(null)
  const [choosing, setChoosing] = useState(false)
  const [choiceError, setChoiceError] = useState('')

  const reloadPanels = () => Promise.all([api.frontOffice(), api.engagement()])
    .then(([nextOffice, nextEngagement]) => {
      setOffice(nextOffice)
      setEngagement(nextEngagement)
    })
    .catch(() => {})

  useEffect(() => { reloadPanels() }, [state.year, state.day, state.my_rank])

  const chooseOwnerResponse = async choiceId => {
    setChoosing(true)
    setChoiceError('')
    try {
      const response = await api.ownerEventChoice(choiceId)
      setEngagement(response.state)
      setOffice(await api.frontOffice())
      await onRefresh?.()
    } catch (error) {
      setChoiceError(error.message)
    } finally {
      setChoosing(false)
    }
  }

  const pendingEvent = engagement?.pending_event
  const progressBlocked = Boolean(pendingEvent)
  const unlocked = engagement?.achievements?.filter(a => a.unlocked) || []
  const latestReward = engagement?.latest_season_reward

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
        {pendingEvent && <div className="owner-event-panel">
          <span className="event-kicker">구단주 긴급 안건 · {pendingEvent.milestone}일차</span>
          <h3>{pendingEvent.title}</h3>
          <p>{pendingEvent.description}</p>
          <div className="event-choices">
            {pendingEvent.choices.map(choice => <button key={choice.id}
              disabled={choosing || busy} onClick={() => chooseOwnerResponse(choice.id)}>
              <b>{choice.label}</b>
              <span>{choice.description}</span>
              <small>{effectText(choice.effects)}</small>
            </button>)}
          </div>
          {choiceError && <p className="event-error">{choiceError}</p>}
          <p className="event-block-note">응답 전에는 시즌을 진행할 수 없습니다.</p>
        </div>}
        {state.next_games.length > 0 && (
          <p>다음 경기: {state.next_games.map(g =>
            `${g.away} @ ${g.home}${g.home === state.user_tid ? ' (홈)' : ' (원정)'}`).join(', ')}</p>
        )}
        <h3>시즌 진행</h3>
        <div className="btn-row">
          <button disabled={busy || seasonOver || progressBlocked} className="live-start" onClick={onLive}>
            {state.live_active ? '실시간 경기로 복귀 ⚾' : '직접 운영 ⚾'}
          </button>
          <button disabled={busy || state.live_active || progressBlocked} onClick={() => onAdvance('day')}>하루 ▶</button>
          <button disabled={busy || state.live_active || progressBlocked} onClick={() => onAdvance('series')}>시리즈(3일) ▶▶</button>
          <button disabled={busy || state.live_active || progressBlocked} onClick={() => onAdvance('month')}>한 달 ▶▶▶</button>
          <button disabled={busy || state.live_active || progressBlocked} className="primary" onClick={() => onAdvance('season_end')}>
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
        {latestReward?.reward_budget > 0 && <div className="season-reward">
          <b>직전 시즌 목표 보상</b>
          <span>예산 +{latestReward.reward_budget}억 · 프런트 포인트 +{latestReward.reward_points}</span>
        </div>}
        {engagement && <div className="achievement-panel">
          <div className="achievement-head">
            <h3>감독 업적</h3>
            <span>{engagement.achievement_count}/{engagement.achievement_total} · 포인트 {engagement.front_office_points}</span>
          </div>
          {unlocked.length === 0
            ? <p className="muted">시즌 목표와 구단주 안건을 수행하면 업적이 해금됩니다.</p>
            : <div className="achievement-grid">{unlocked.map(a => <div key={a.id}>
                <b>{a.title}</b><span>{a.description}</span><small>보상 예산 +{a.reward}억</small>
              </div>)}</div>}
        </div>}
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
