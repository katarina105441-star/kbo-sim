import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

export default function TeamSelect({ onStart, onLoad }) {
  const [teams, setTeams] = useState([])
  const [tid, setTid] = useState(null)
  const [seed, setSeed] = useState('')
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [showSeed, setShowSeed] = useState(false)

  const selectedTeam = useMemo(() => teams.find(team => team.tid === tid), [teams, tid])

  const loadInitial = async () => {
    setLoading(true)
    setError('')
    try {
      const [rows, identities, nextMeta] = await Promise.all([
        api.teamsAll(), api.teamIdentities(), api.meta(),
      ])
      setTeams(rows.map(team => ({ ...team, identity: identities[team.tid] })))
      setMeta(nextMeta)
    } catch (e) {
      setError(`게임 서버와 연결하지 못했습니다: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadInitial() }, [])

  const startGame = async () => {
    if (!tid) return
    const parsedSeed = seed.trim() === '' ? null : Number(seed)
    if (parsedSeed !== null && (!Number.isInteger(parsedSeed) || parsedSeed < 0)) {
      setError('시드는 0 이상의 정수로 입력하거나 비워두세요.')
      return
    }
    setWorking('start')
    setError('')
    try {
      await onStart(tid, parsedSeed)
    } catch (e) {
      setError(`새 커리어를 시작하지 못했습니다: ${e.message}`)
    } finally {
      setWorking('')
    }
  }

  const loadGame = async () => {
    setWorking('load')
    setError('')
    try {
      await onLoad()
    } catch (e) {
      setError(`저장된 게임을 불러오지 못했습니다: ${e.message}`)
    } finally {
      setWorking('')
    }
  }

  if (loading) return (
    <div className="launch-state">
      <div className="launch-spinner" />
      <h2>KBO 매니저를 준비하고 있습니다.</h2>
      <p>구단 정보와 게임 상태를 확인하는 중입니다.</p>
    </div>
  )

  if (error && teams.length === 0) return (
    <div className="launch-state error">
      <span>연결 오류</span>
      <h2>첫 화면을 불러오지 못했습니다.</h2>
      <p>{error}</p>
      <button className="primary" onClick={loadInitial}>다시 연결</button>
      <small>실행 창이 켜져 있는지 확인한 뒤 다시 시도하세요.</small>
    </div>
  )

  return (
    <div className="team-select">
      <header className="launch-hero">
        <div>
          <span className="release-chip">v{meta?.version || '—'} · {meta?.release_name || 'KBO 매니저'}</span>
          <h1>⚾ 한 구단을 맡아 감독 커리어를 완성하세요.</h1>
          <p>경기 운영부터 트레이드·FA·드래프트, 해임과 재취업, 은퇴와 명예의 전당까지 이어지는 장기 야구 시뮬레이션입니다.</p>
        </div>
        <div className="launch-flow">
          <span><b>1</b> 구단 선택</span>
          <span><b>2</b> 시즌 운영</span>
          <span><b>3</b> 오프시즌 개입</span>
          <span><b>4</b> 감독 커리어</span>
        </div>
      </header>

      <div className="select-heading">
        <div><h2>운영할 구단 선택</h2><p>나머지 9개 구단은 고유한 운영 철학으로 움직입니다.</p></div>
        <span>{teams.length}개 구단</span>
      </div>
      <div className="team-grid">
        {teams.map(team => (
          <button key={team.tid} className={tid === team.tid ? 'team-card on' : 'team-card'}
                  onClick={() => setTid(team.tid)}>
            <div className="team-card-head"><span className="team-tid">{team.tid}</span>
              {team.identity && <small>{team.identity.strategy_label}</small>}</div>
            <div className="team-name">{team.name}</div>
            <div className="muted">{team.city} · {team.stadium}</div>
            {team.identity && <div className="identity-mini">
              <b>{team.identity.label}</b>
              <span>{team.identity.manager_style}</span>
              <span>타격 {team.identity.offense_label} · 투수 {team.identity.pitching_label}</span>
            </div>}
          </button>
        ))}
      </div>

      {selectedTeam && <div className="identity-preview">
        <div><span>선택 구단</span><b>{selectedTeam.name}</b></div>
        <p>{selectedTeam.identity?.description}</p>
      </div>}

      <div className="start-panel">
        <div className="start-main">
          <button className="primary launch-primary" disabled={!tid || Boolean(working)} onClick={startGame}>
            {working === 'start' ? '커리어 생성 중…' : (tid ? `${selectedTeam.name} 새 커리어 시작` : '구단을 먼저 선택하세요')}
          </button>
          <button className="load-button" disabled={Boolean(working) || meta?.save_exists === false}
                  onClick={loadGame}>
            {working === 'load' ? '불러오는 중…' : '저장된 커리어 이어하기'}
          </button>
        </div>
        <button className="seed-toggle" onClick={() => setShowSeed(!showSeed)}>
          {showSeed ? '시드 설정 닫기' : '고급 설정: 시드 고정'}
        </button>
        {showSeed && <label className="seed-field">
          <span>시드</span>
          <input inputMode="numeric" value={seed} onChange={e => setSeed(e.target.value)}
                 placeholder="비우면 매번 다른 세계" />
          <small>같은 숫자를 사용하면 같은 초기 조건으로 시작합니다.</small>
        </label>}
        {meta?.save_exists === false && <p className="save-hint">아직 저장된 커리어가 없습니다.</p>}
        {error && <p className="launch-error">{error}</p>}
      </div>
      <footer className="launch-footer">Python {meta?.python} · {meta?.platform} · 저장 위치 `saves/save.pkl`</footer>
    </div>
  )
}
