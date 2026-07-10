import React, { useMemo, useState } from 'react'
import { api } from '../api.js'

const PHASE = { win: '윈나우', rebuild: '리빌딩', mid: '중립' }

function AssetRow({ asset, selected, onToggle, disabled }) {
  return <label className={`trade-asset ${selected ? 'selected' : ''}`}>
    <input type="checkbox" checked={selected} disabled={disabled}
           onChange={() => onToggle(asset.id)} />
    {asset.type === 'player' ? <>
      <span className="trade-asset-main"><b>{asset.name}</b><small>{asset.age}세 · {asset.pos}</small></span>
      <span>OVR {Math.round(asset.ovr)}</span>
      <span>{asset.salary.toFixed(1)}억</span>
      <span className="trade-value">가치 {asset.estimated_value.toFixed(1)}</span>
    </> : <>
      <span className="trade-asset-main"><b>{asset.name}</b><small>원소속 {asset.original_tid}</small></span>
      <span className="trade-value">가치 {asset.estimated_value.toFixed(1)}</span>
    </>}
  </label>
}

function Package({ title, assets }) {
  const total = assets.reduce((sum, asset) => sum + asset.estimated_value, 0)
  return <div className="trade-package">
    <h4>{title} <span>추정가치 {total.toFixed(1)}</span></h4>
    {assets.map(asset => <div key={asset.id} className="trade-package-line">
      <b>{asset.name}</b>
      <span>{asset.type === 'player' ? `${asset.age}세 · ${asset.pos} · OVR ${Math.round(asset.ovr)}` : `원소속 ${asset.original_tid}`}</span>
    </div>)}
  </div>
}

export default function TradeBoard({ market, onMarketChange, onComplete }) {
  const [targetTid, setTargetTid] = useState(market.teams[0]?.tid || '')
  const [giveIds, setGiveIds] = useState([])
  const [receiveIds, setReceiveIds] = useState([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const target = market.teams.find(team => team.tid === targetTid) || market.teams[0]
  const userAssets = useMemo(() => [...market.user.players, ...market.user.picks], [market])
  const targetAssets = useMemo(() => target ? [...target.players, ...target.picks] : [], [target])
  const selectedGive = userAssets.filter(asset => giveIds.includes(asset.id))
  const selectedReceive = targetAssets.filter(asset => receiveIds.includes(asset.id))
  const giveValue = selectedGive.reduce((sum, asset) => sum + asset.estimated_value, 0)
  const receiveValue = selectedReceive.reduce((sum, asset) => sum + asset.estimated_value, 0)

  const toggle = (setter, current, id) => {
    setter(current.includes(id) ? current.filter(value => value !== id) : [...current, id].slice(0, 4))
  }

  const run = async (action) => {
    setBusy(true); setNotice(''); setError('')
    try {
      const response = await action()
      if (response.result?.message) setNotice(response.result.message)
      if (response.trade) onMarketChange(response.trade)
      if (response.trade_complete) onComplete(response)
      if (response.result?.status === 'accepted' || response.result?.status === 'counter_accepted') {
        setGiveIds([]); setReceiveIds([])
      }
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const propose = () => {
    if (!target || giveIds.length === 0 || receiveIds.length === 0) return
    const text = `${market.user.name}이(가) ${selectedGive.map(a => a.name).join(', ')}을 내주고 ` +
      `${target.name}의 ${selectedReceive.map(a => a.name).join(', ')}을 받는 제안을 보낼까요?`
    if (!window.confirm(text)) return
    run(() => api.tradePropose(target.tid, giveIds, receiveIds))
  }

  const changeTarget = (tid) => {
    setTargetTid(tid); setReceiveIds([]); setNotice(''); setError('')
  }

  return <section className="trade-board">
    <div className="trade-header">
      <div>
        <h2>{market.year}년 트레이드 시장</h2>
        <p className="muted">우리 팀 전략: {PHASE[market.user_phase]} · 남은 사용자 거래 {market.trades_remaining}회</p>
      </div>
      <button disabled={busy} onClick={() => {
        if (window.confirm('트레이드 시장을 종료하고 FA 시장으로 이동할까요?')) run(api.tradeFinish)
      }}>트레이드 시장 종료</button>
    </div>

    {notice && <div className="notice ok">{notice}</div>}
    {error && <div className="notice bad">{error}</div>}

    {market.pending_counter && <div className="trade-counter">
      <h3>{market.pending_counter.other_name} 역제안</h3>
      <div className="trade-counter-grid">
        <Package title="우리가 내주는 자산" assets={market.pending_counter.user_gives} />
        <Package title="우리가 받는 자산" assets={market.pending_counter.user_receives} />
      </div>
      <div className="trade-actions">
        <button className="primary" disabled={busy} onClick={() => run(api.tradeAcceptCounter)}>역제안 수락</button>
        <button disabled={busy} onClick={() => run(api.tradeRejectCounter)}>역제안 거절</button>
      </div>
    </div>}

    <div className="trade-targets">
      {market.teams.map(team => <button key={team.tid}
        className={target?.tid === team.tid ? 'on' : ''}
        onClick={() => changeTarget(team.tid)}>
        <b>{team.tid}</b><span>{team.name}</span><small>{team.rank}위 · {PHASE[team.phase]}</small>
      </button>)}
    </div>

    {target && <>
      <div className="trade-columns">
        <div className="trade-column">
          <h3>우리 팀이 내줄 자산 <span>{giveIds.length}/4</span></h3>
          <div className="trade-scroll">
            {userAssets.map(asset => <AssetRow key={asset.id} asset={asset}
              selected={giveIds.includes(asset.id)} disabled={busy || market.trades_remaining <= 0}
              onToggle={id => toggle(setGiveIds, giveIds, id)} />)}
          </div>
        </div>
        <div className="trade-column">
          <h3>{target.name}에서 받을 자산 <span>{receiveIds.length}/4</span></h3>
          <div className="trade-scroll">
            {targetAssets.map(asset => <AssetRow key={asset.id} asset={asset}
              selected={receiveIds.includes(asset.id)} disabled={busy || market.trades_remaining <= 0}
              onToggle={id => toggle(setReceiveIds, receiveIds, id)} />)}
          </div>
        </div>
      </div>

      <div className="trade-summary">
        <div><span>우리가 내주는 추정가치</span><b>{giveValue.toFixed(1)}</b></div>
        <div className="trade-arrow">↔</div>
        <div><span>우리가 받는 추정가치</span><b>{receiveValue.toFixed(1)}</b></div>
        <button className="primary" disabled={busy || market.trades_remaining <= 0 || !giveIds.length || !receiveIds.length}
                onClick={propose}>트레이드 제안</button>
      </div>
      <p className="muted trade-hint">표시 가치는 중립적인 추정치입니다. 상대 구단은 경쟁 상황·미래 선호·포지션 구성에 따라 다르게 평가합니다.</p>
    </>}

    {(market.user_trades.length > 0 || market.ai_trades.length > 0) && <div className="trade-history">
      <h3>이번 시장 성사 내역</h3>
      {market.user_trades.map((deal, i) => <div key={`u-${i}`}>
        <b>우리 팀 ↔ {deal.other_name}</b>
        <span>{deal.user_gives.map(a => a.name).join(', ')} ↔ {deal.user_receives.map(a => a.name).join(', ')}</span>
      </div>)}
      {market.ai_trades.map((deal, i) => <div key={`a-${i}`}>
        <b>{deal.win_tid} ↔ {deal.reb_tid}</b>
        <span>{deal.veteran} ↔ {deal.prospects.join(', ')}{deal.picks.length ? ` + ${deal.picks.join(', ')}R 지명권` : ''}</span>
      </div>)}
    </div>}
  </section>
}
