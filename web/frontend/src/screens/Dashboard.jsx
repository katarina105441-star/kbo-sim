import React from 'react'

export default function Dashboard({ state, busy, onAdvance }) {
  const t = state.my_team
  const seasonOver = state.day >= state.days_total
  return (
    <div className="two-col">
      <section className="card">
        <h2>{t.name} <span className="badge">{state.my_rank}위</span></h2>
        <div className="bigline">{t.wins}승 {t.ties}무 {t.losses}패
          <span className="muted"> · 승률 {t.pct.toFixed(3)} · {t.games}경기</span></div>
        {state.next_games.length > 0 && (
          <p>다음 경기: {state.next_games.map(g =>
            `${g.away} @ ${g.home}${g.home === state.user_tid ? ' (홈)' : ' (원정)'}`).join(', ')}</p>
        )}
        <h3>시즌 진행</h3>
        <div className="btn-row">
          <button disabled={busy} onClick={() => onAdvance('day')}>하루 ▶</button>
          <button disabled={busy} onClick={() => onAdvance('series')}>시리즈(3일) ▶▶</button>
          <button disabled={busy} onClick={() => onAdvance('month')}>한 달 ▶▶▶</button>
          <button disabled={busy} className="primary" onClick={() => onAdvance('season_end')}>
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
