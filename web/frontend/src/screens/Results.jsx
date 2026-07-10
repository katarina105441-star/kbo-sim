import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

function Boxscore({ box }) {
  const inn = box.line.away.length
  return (
    <div className="boxscore">
      <table className="dense">
        <thead><tr><th className="tl">팀</th>
          {Array.from({ length: inn }, (_, i) => <th key={i}>{i + 1}</th>)}
          <th>R</th></tr></thead>
        <tbody>
          {['away', 'home'].map(s => (
            <tr key={s}><td className="tl">{box[s].name}</td>
              {box.line[s].map((v, i) => <td key={i}>{v === null ? 'X' : v}</td>)}
              <td><b>{box[s].runs}</b></td></tr>))}
        </tbody>
      </table>
      <p className="muted">
        {box.tie ? `${box.innings}회 무승부` :
          `승 ${box.decisions['승'] || '-'} · 패 ${box.decisions['패'] || '-'}` +
          (box.decisions['세'] ? ` · 세 ${box.decisions['세']}` : '')}
      </p>
      {['away', 'home'].map(s => (
        <div key={s}>
          <h4>{box[s].name} 타자</h4>
          <table className="dense"><thead><tr>
            <th>타순</th><th className="tl">이름</th><th>포지션</th><th>타수</th><th>안타</th>
            <th>홈런</th><th>타점</th><th>득점</th><th>볼넷</th><th>삼진</th><th>도루</th>
          </tr></thead><tbody>
            {box.batting[s].map(b => (
              <tr key={b['순']}><td>{b['순']}</td><td className="tl">{b['이름']}</td>
                <td>{b['포지션']}</td><td>{b['타수']}</td><td>{b['안타']}</td><td>{b['홈런']}</td>
                <td>{b['타점']}</td><td>{b['득점']}</td><td>{b['볼넷']}</td><td>{b['삼진']}</td>
                <td>{b['도루']}</td></tr>))}
          </tbody></table>
          <h4>{box[s].name} 투수</h4>
          <table className="dense"><thead><tr>
            <th className="tl">이름</th><th>이닝</th><th>투구</th><th>피안타</th><th>실점</th>
            <th>자책</th><th>볼넷</th><th>삼진</th>
          </tr></thead><tbody>
            {box.pitching[s].map((p, i) => (
              <tr key={i}><td className="tl">{p['이름']}</td><td>{p['이닝']}</td>
                <td>{p['투구']}</td><td>{p['피안타']}</td><td>{p['실점']}</td>
                <td>{p['자책']}</td><td>{p['볼넷']}</td><td>{p['삼진']}</td></tr>))}
          </tbody></table>
        </div>
      ))}
    </div>
  )
}

export default function Results({ userTid, onWatch }) {
  const [data, setData] = useState(null)
  const [box, setBox] = useState(null)

  const loadDay = (d, keepBox) =>
    api.results(d).then(r => { setData(r); if (!keepBox) setBox(null) })
  useEffect(() => { loadDay() }, [])
  const openBox = (i) => api.boxscore(data.day, i)
    .then(b => { setBox(b); loadDay(data.day, true) })   // 결과 보기 = 공개 → 목록 갱신

  if (!data) return null
  if (data.games.length === 0)
    return <section className="card"><h2>일정·결과</h2>
      <p className="muted">아직 경기가 없습니다. 대시보드에서 시즌을 진행하세요.</p></section>

  return (
    <section className="card">
      <h2>일정·결과
        <span className="day-nav">
          <button disabled={data.day <= 1} onClick={() => loadDay(data.day - 1)}>◀</button>
          {' '}{data.day}일차 / {data.last_day}{' '}
          <button disabled={data.day >= data.last_day} onClick={() => loadDay(data.day + 1)}>▶</button>
        </span>
      </h2>
      <div className="game-list">
        {data.games.map((g, i) => (
          <div key={i}
               className={'game-row' + ((g.away === userTid || g.home === userTid) ? ' me' : '')}>
            {g.hidden ? (
              <span className="game-score hidden-score">
                {g.away} <b>?</b> : <b>?</b> {g.home}
                <span className="muted"> 결과 미공개</span>
              </span>
            ) : (
              <span className="game-score" onClick={() => openBox(i)}>
                {g.away} <b>{g.score[0]}</b> : <b>{g.score[1]}</b> {g.home}{g.tie ? ' 무' : ''}
              </span>
            )}
            <span className="spacer" />
            {g.watchable &&
              <button className="watch-btn" onClick={() => onWatch(data.day, i)}>
                ▶ 관전</button>}
            <button className="ghost2" onClick={() => openBox(i)}>
              {g.hidden ? '결과 보기' : '결과'}</button>
          </div>
        ))}
      </div>
      {box && <Boxscore box={box} />}
    </section>
  )
}
