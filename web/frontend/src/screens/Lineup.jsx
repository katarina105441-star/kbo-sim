import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

const FIELD_SLOTS = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DH']

const makeDraft = (data) => ({
  order: [...data.order], slots: { ...data.slots }, rotation: [...data.rotation],
  closer: data.closer, setup: [...data.setup],
})

function validate(draft, byPid) {
  const errors = []
  const unique = (xs) => new Set(xs).size === xs.length
  if (draft.order.length !== 9 || !unique(draft.order)) errors.push('타순은 중복 없는 9명이어야 합니다.')
  const slotPids = FIELD_SLOTS.map(s => draft.slots[s]).filter(Boolean)
  if (slotPids.length !== 9 || !unique(slotPids) ||
      draft.order.some(pid => !slotPids.includes(pid))) errors.push('수비 8슬롯과 DH를 타순 9명에게 한 번씩 배정하세요.')
  if (draft.order.some(pid => byPid[pid]?.inj_days > 0)) errors.push('부상자는 타순에 저장할 수 없습니다.')
  if (draft.rotation.length !== 5 || !unique(draft.rotation)) errors.push('선발 로테이션은 중복 없는 5명이어야 합니다.')
  if (!draft.closer) errors.push('마무리 투수를 지정하세요.')
  const roles = [...draft.rotation, draft.closer, ...draft.setup].filter(Boolean)
  if (!unique(roles)) errors.push('로테이션·마무리·셋업은 서로 겹칠 수 없습니다.')
  if (roles.some(pid => byPid[pid]?.inj_days > 0)) errors.push('부상자는 투수 보직에 저장할 수 없습니다.')
  return errors
}

export default function Lineup() {
  const [data, setData] = useState(null)
  const [draft, setDraft] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = (next) => { setData(next); setDraft(makeDraft(next)); setError('') }
  useEffect(() => { api.myLineup().then(load).catch(e => setError(e.message)) }, [])
  const byPid = useMemo(() => Object.fromEntries(
    [...(data?.batters || []), ...(data?.pitchers || [])].map(p => [p.pid, p])), [data])
  if (!data || !draft) return <section className="card">{error || '라인업 불러오는 중…'}</section>

  const errors = validate(draft, byPid)
  const slotOf = (pid) => FIELD_SLOTS.find(slot => draft.slots[slot] === pid) || ''
  const move = (key, index, delta) => {
    const items = [...draft[key]]
    const to = index + delta
    if (to < 0 || to >= items.length) return
    ;[items[index], items[to]] = [items[to], items[index]]
    setDraft({ ...draft, [key]: items })
  }
  const changeBatter = (index, pid) => {
    const order = [...draft.order]
    const old = order[index]
    const other = order.indexOf(pid)
    const slots = { ...draft.slots }
    if (other >= 0) {
      ;[order[index], order[other]] = [order[other], order[index]]
    } else {
      order[index] = pid
      slots[slotOf(old)] = pid
    }
    setDraft({ ...draft, order, slots })
  }
  const changeSlot = (pid, slot) => {
    const slots = { ...draft.slots }
    const oldSlot = slotOf(pid)
    const otherPid = slots[slot]
    slots[slot] = pid
    slots[oldSlot] = otherPid
    setDraft({ ...draft, slots })
  }
  const changeRotation = (index, pid) => {
    const rotation = [...draft.rotation]
    const other = rotation.indexOf(pid)
    if (other >= 0) [rotation[index], rotation[other]] = [rotation[other], rotation[index]]
    else rotation[index] = pid
    setDraft({ ...draft, rotation })
  }
  const changeCloser = (pid) => setDraft({
    ...draft,
    closer: pid,
    setup: draft.setup.filter(x => x !== pid),
  })
  const toggleSetup = (pid) => setDraft({
    ...draft,
    setup: draft.setup.includes(pid) ? draft.setup.filter(x => x !== pid) : [...draft.setup, pid],
  })
  const submit = async (ai = false) => {
    setBusy(true); setError(''); setMessage('')
    try {
      const next = ai ? await api.aiLineup() : await api.saveLineup(draft)
      load(next)
      setMessage(ai ? 'AI 추천 라인업으로 초기화했습니다.' : '라인업을 저장했습니다.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const healthyPitchers = data.pitchers.filter(p => p.inj_days === 0)
  const bullpenChoices = healthyPitchers.filter(
    p => !draft.rotation.includes(p.pid) && p.pid !== draft.closer)

  return <section className="lineup-page">
    <div className="card lineup-head">
      <div><h2>라인업 관리 · {data.team.name}</h2>
        <p className="muted">타순·수비 슬롯과 투수 보직을 편집합니다. 주포지션 불일치는 저장되지만 경고됩니다.</p></div>
      <div className="btn-row inline">
        <button onClick={() => submit(true)} disabled={busy}>AI 추천</button>
        <button className="primary" onClick={() => submit(false)} disabled={busy || errors.length > 0}>저장</button>
      </div>
    </div>
    {message && <div className="notice ok">{message}</div>}
    {(error || errors.length > 0) && <div className="notice bad">
      {error && <div>{error}</div>}{errors.map(e => <div key={e}>· {e}</div>)}
    </div>}

    <div className="lineup-grid">
      <div className="card">
        <h2>타순 · 수비</h2>
        <table className="dense lineup-table"><thead><tr>
          <th>순</th><th className="tl">선수</th><th>주포지션</th><th>수비</th>
          <th>OVR</th><th>컨택</th><th>파워</th><th>선구</th><th>이동</th>
        </tr></thead><tbody>
          {draft.order.map((pid, i) => { const p = byPid[pid]; const slot = slotOf(pid); const warn = p.pos !== slot
            return <tr key={`${pid}-${i}`} className={warn ? 'warn-row' : ''}>
              <td><b>{i + 1}</b></td><td className="tl"><select value={pid} onChange={e => changeBatter(i, e.target.value)}>
                {data.batters.map(b => <option key={b.pid} value={b.pid} disabled={b.inj_days > 0}>
                  {b.name}{b.inj_days ? ` (부상 ${b.inj_days}일)` : ''}</option>)}
              </select></td><td>{p.pos}</td><td><select value={slot} onChange={e => changeSlot(pid, e.target.value)}>
                {FIELD_SLOTS.map(s => <option key={s}>{s}</option>)}</select>{warn && <span className="slot-warn"> ⚠</span>}</td>
              <td><b>{Math.round(p.ovr)}</b></td><td>{p.ratings['컨택']}</td><td>{p.ratings['파워']}</td><td>{p.ratings['선구']}</td>
              <td><button className="mini" onClick={() => move('order', i, -1)} disabled={i === 0}>↑</button>
                <button className="mini" onClick={() => move('order', i, 1)} disabled={i === 8}>↓</button></td>
            </tr>})}
        </tbody></table>
      </div>

      <div>
        <div className="card"><h2>선발 로테이션</h2>
          {draft.rotation.map((pid, i) => { const p = byPid[pid]; const choices = healthyPitchers.filter(
            q => q.pid === pid || (q.pid !== draft.closer && !draft.setup.includes(q.pid)))
            return <div className="role-row" key={`${pid}-${i}`}>
            <b>{i + 1}선발</b><select value={pid} onChange={e => changeRotation(i, e.target.value)}>
              {choices.map(q => <option key={q.pid} value={q.pid}>{q.name} ({q.pos}, OVR {Math.round(q.ovr)})</option>)}
            </select><span>{p.ratings['스태미나']} STA</span>
            <button className="mini" onClick={() => move('rotation', i, -1)} disabled={i === 0}>↑</button>
            <button className="mini" onClick={() => move('rotation', i, 1)} disabled={i === 4}>↓</button>
          </div>})}
        </div>
        <div className="card"><h2>불펜 보직</h2>
          <label className="closer-row"><b>마무리</b><select value={draft.closer || ''}
            onChange={e => changeCloser(e.target.value)}>
            <option value="">선택</option>{healthyPitchers.filter(p => !draft.rotation.includes(p.pid)).map(
              p => <option key={p.pid} value={p.pid}>{p.name} ({p.pos}, OVR {Math.round(p.ovr)})</option>)}
          </select></label>
          <h3>셋업 투수 <span className="muted">(0명 이상, 마무리·선발과 중복 불가)</span></h3>
          <div className="setup-list">{bullpenChoices.map(p => <label key={p.pid}>
            <input type="checkbox" checked={draft.setup.includes(p.pid)} onChange={() => toggleSetup(p.pid)} />
            <span>{p.name}</span><small>{p.pos} · OVR {Math.round(p.ovr)} · 구위 {p.ratings['구위']}</small>
          </label>)}</div>
        </div>
      </div>
    </div>
    {data.warnings.length > 0 && <div className="card"><h3>저장된 포지션 경고</h3>
      {data.warnings.map(w => <p key={`${w.pid}-${w.slot}`} className="warn-text">⚠ {w.message}</p>)}</div>}
  </section>
}
