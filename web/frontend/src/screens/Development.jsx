import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

const FOCUS_LABEL = {
  balanced: '균형', contact: '컨택·선구', power: '파워', defense: '수비·주루',
  velocity: '구속', control: '제구', stuff: '구위·변화구', stamina: '스태미나',
}

function focusChoices(player) {
  return player.pos === 'SP' || player.pos === 'RP' || player.pos === 'CL'
    ? ['balanced', 'velocity', 'control', 'stuff', 'stamina']
    : ['balanced', 'contact', 'power', 'defense']
}

function PlayerRow({ player, level, busy, onMove, onFocus, onPlayer }) {
  return <tr className="development-row">
    <td className="tl click" onClick={() => onPlayer(player.pid)}>
      <b>{player.name}</b>
      {player.inj_days > 0 && <span className="inj"> 부상 {player.inj_days}일</span>}
      {player.stub && <span className="muted"> 유망주</span>}
    </td>
    <td>{player.age}</td><td>{player.pos}</td>
    <td><b>{Math.round(player.ovr)}</b></td><td>{Math.round(player.pot)}</td>
    <td>{player.salary}억</td>
    {level === 'minors' ? <>
      <td>{player.minor_days}일</td>
      <td>{player.minor_seasons}</td>
      <td>{player.dev_last_gain > 0 ? `+${player.dev_last_gain.toFixed(2)}` : '-'}</td>
      <td>
        <select value={player.focus} disabled={busy}
                onChange={e => onFocus(player.pid, e.target.value)}>
          {focusChoices(player).map(value => <option key={value} value={value}>
            {FOCUS_LABEL[value]}</option>)}
        </select>
      </td>
      <td><button disabled={busy} onClick={() => onMove('promote', player.pid)}>1군 콜업</button></td>
    </> : <>
      <td>{player.line?.G ?? '-'}</td>
      <td>{player.form === 'hot' ? '▲ 핫' : player.form === 'cold' ? '▼ 콜드' : '-'}</td>
      <td colSpan="2">{player.years > 1 ? `${player.years}년 계약` : '단년 계약'}</td>
      <td><button disabled={busy} onClick={() => onMove('demote', player.pid)}>2군 이동</button></td>
    </>}
  </tr>
}

export default function Development({ onPlayer }) {
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('minors')
  const [group, setGroup] = useState('all')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = () => api.developmentState().then(setData).catch(e => setError(e.message))
  useEffect(() => { load() }, [])

  const run = async (action) => {
    setBusy(true); setMessage(''); setError('')
    try {
      const response = await action()
      setData(response.development)
      const result = response.result
      if (result.action === 'promote') setMessage(`${result.player.name}을(를) 1군으로 콜업했습니다.`)
      else if (result.action === 'demote') setMessage(`${result.player.name}을(를) 2군으로 이동했습니다.`)
      else if (result.action === 'focus') setMessage(`${result.player.name}의 육성 방향을 변경했습니다.`)
      else setMessage(`AI 편성 완료 · 콜업 ${result.promoted.length}명 / 2군 이동 ${result.demoted.length}명`)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const move = (action, pid) => {
    const text = action === 'promote' ? '1군으로 콜업할까요?' : '2군으로 이동할까요?'
    if (!window.confirm(text)) return
    run(() => action === 'promote' ? api.promotePlayer(pid) : api.demotePlayer(pid))
  }

  const players = useMemo(() => {
    if (!data) return []
    const source = tab === 'minors' ? data.minors : data.active
    if (group === 'bat') return source.filter(p => !['SP', 'RP', 'CL'].includes(p.pos))
    if (group === 'pit') return source.filter(p => ['SP', 'RP', 'CL'].includes(p.pos))
    return source
  }, [data, tab, group])

  if (!data) return <section className="card">2군·육성 정보를 불러오는 중…</section>

  return <section className="card development-page">
    <div className="development-header">
      <div>
        <h2>2군·육성 관리</h2>
        <p className="muted">1군 {data.active_count}/{data.active_max}명 · 2군 {data.minor_count}명</p>
      </div>
      <button disabled={busy} onClick={() => {
        if (window.confirm('OVR 기준 14야수·11투수로 1군을 자동 편성할까요?')) run(api.autoDevelopmentRoster)
      }}>AI 1군 편성</button>
    </div>

    {message && <div className="notice ok">{message}</div>}
    {error && <div className="notice bad">{error}</div>}

    <div className="development-toolbar">
      <div className="btn-row">
        <button className={tab === 'minors' ? 'tab on' : 'tab'} onClick={() => setTab('minors')}>
          2군 {data.minor_count}</button>
        <button className={tab === 'active' ? 'tab on' : 'tab'} onClick={() => setTab('active')}>
          1군 {data.active_count}</button>
      </div>
      <div className="btn-row">
        <button className={group === 'all' ? 'tab on' : 'tab'} onClick={() => setGroup('all')}>전체</button>
        <button className={group === 'bat' ? 'tab on' : 'tab'} onClick={() => setGroup('bat')}>야수</button>
        <button className={group === 'pit' ? 'tab on' : 'tab'} onClick={() => setGroup('pit')}>투수</button>
      </div>
    </div>

    <div className="development-table-wrap">
      <table className="dense development-table">
        <thead><tr>
          <th className="tl">이름</th><th>나이</th><th>포지션</th><th>OVR</th><th>POT</th><th>연봉</th>
          {tab === 'minors' ? <>
            <th>2군일</th><th>누적</th><th>최근성장</th><th>육성방향</th><th>이동</th>
          </> : <>
            <th>경기</th><th>컨디션</th><th colSpan="2">계약</th><th>이동</th>
          </>}
        </tr></thead>
        <tbody>{players.map(player => <PlayerRow key={player.pid} player={player}
          level={tab} busy={busy} onMove={move}
          onFocus={(pid, focus) => run(() => api.setDevelopmentFocus(pid, focus))}
          onPlayer={onPlayer} />)}</tbody>
      </table>
    </div>

    <div className="development-guide">
      <b>육성 규칙</b>
      <span>2군 등록 30일부터 성장 보너스가 발생하며 144일에 최대치가 됩니다.</span>
      <span>23세 이하가 가장 효율적이고, 27세 이상은 효과가 크게 감소합니다.</span>
      <span>경기 가능한 건강한 야수 9명·투수 6명이 부족하면 최고 2군 선수가 자동 콜업됩니다.</span>
    </div>
  </section>
}
