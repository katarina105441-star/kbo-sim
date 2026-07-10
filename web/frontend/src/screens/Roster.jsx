import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const rate = (v) => <td className={v >= 80 ? 'r-hi' : v >= 65 ? 'r-mid' : ''}>{v}</td>

export default function Roster({ userTid, onPlayer }) {
  const [teams, setTeams] = useState([])
  const [tid, setTid] = useState(userTid)
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('bat')

  useEffect(() => { api.teamsAll().then(setTeams) }, [])
  useEffect(() => { api.roster(tid).then(setData) }, [tid])
  if (!data) return null

  const injForm = (p) => <>
    {p.inj_days > 0 && <span className="inj"> 부상{p.inj_days}일</span>}
    {p.form === 'hot' && <span className="hot"> ▲</span>}
    {p.form === 'cold' && <span className="cold"> ▼</span>}
    {p.stub && <span className="muted"> 신인</span>}
  </>

  return (
    <section className="card">
      <h2>로스터
        <select value={tid} onChange={e => setTid(e.target.value)}>
          {teams.map(t => <option key={t.tid} value={t.tid}>
            {t.tid === userTid ? '★ ' : ''}{t.name}</option>)}
        </select>
        <span className="btn-row inline">
          <button className={tab === 'bat' ? 'tab on' : 'tab'} onClick={() => setTab('bat')}>타자 {data.batters.length}</button>
          <button className={tab === 'pit' ? 'tab on' : 'tab'} onClick={() => setTab('pit')}>투수 {data.pitchers.length}</button>
        </span>
      </h2>
      {tab === 'bat' ? (
        <table className="dense">
          <thead><tr><th>타순</th><th className="tl">이름</th><th>나이</th><th>포지션</th><th>OVR</th>
            <th>컨택</th><th>파워</th><th>선구</th><th>주루</th><th>수비</th><th>송구</th>
            <th>타율</th><th>홈런</th><th>타점</th><th>도루</th><th>OPS</th><th>연봉</th></tr></thead>
          <tbody>
            {data.batters.map(p => (
              <tr key={p.pid} className="click" onClick={() => onPlayer(p.pid)}>
                <td>{p.order ? `${p.order} (${p.slot})` : '-'}</td>
                <td className="tl">{p.name}{injForm(p)}</td>
                <td>{p.age}</td><td>{p.pos}</td><td><b>{Math.round(p.ovr)}</b></td>
                {rate(p.ratings['컨택'])}{rate(p.ratings['파워'])}{rate(p.ratings['선구'])}
                {rate(p.ratings['주루'])}{rate(p.ratings['수비'])}{rate(p.ratings['송구'])}
                <td>{p.line['타율']}</td><td>{p.line['홈런']}</td><td>{p.line['타점']}</td>
                <td>{p.line['도루']}</td><td>{p.line['OPS']}</td>
                <td>{p.salary}억{p.years > 1 ? `×${p.years}년` : ''}</td>
              </tr>))}
          </tbody>
        </table>
      ) : (
        <table className="dense">
          <thead><tr><th>보직</th><th className="tl">이름</th><th>나이</th><th>OVR</th>
            <th>구속</th><th>제구</th><th>구위</th><th>스태미나</th><th>변화구</th>
            <th>승</th><th>패</th><th>세</th><th>이닝</th><th>ERA</th><th>탈삼진</th><th>연봉</th></tr></thead>
          <tbody>
            {data.pitchers.map(p => (
              <tr key={p.pid} className="click" onClick={() => onPlayer(p.pid)}>
                <td>{p.role}</td>
                <td className="tl">{p.name}{injForm(p)}</td>
                <td>{p.age}</td><td><b>{Math.round(p.ovr)}</b></td>
                {rate(p.ratings['구속'])}{rate(p.ratings['제구'])}{rate(p.ratings['구위'])}
                {rate(p.ratings['스태미나'])}{rate(p.ratings['변화구'])}
                <td>{p.line['승']}</td><td>{p.line['패']}</td><td>{p.line['세']}</td>
                <td>{p.line['이닝']}</td><td>{p.line['ERA']}</td><td>{p.line['탈삼진']}</td>
                <td>{p.salary}억{p.years > 1 ? `×${p.years}년` : ''}</td>
              </tr>))}
          </tbody>
        </table>
      )}
      <p className="muted">행을 클릭하면 선수 상세. ▲핫 ▼콜드 = 컨디션. (타순 편집은 MVP-2)</p>
    </section>
  )
}
