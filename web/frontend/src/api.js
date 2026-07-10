async function req(path, opts) {
  const r = await fetch(path, opts)
  if (!r.ok) {
    const body = await r.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${r.status}`)
  }
  return r.json()
}
const post = (path, body) =>
  req(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body || {}) })
const put = (path, body) =>
  req(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body || {}) })

export const api = {
  teamsAll: () => req('/api/teams/all'),
  newGame: (tid, seed) => post('/api/game/new', { tid, seed }),
  state: () => req('/api/game/state'),
  save: () => post('/api/game/save'),
  load: () => post('/api/game/load'),
  advance: (unit) => post('/api/sim/advance', { unit }),
  standings: () => req('/api/standings'),
  roster: (tid) => req(`/api/teams/${tid}/roster`),
  myLineup: () => req('/api/my/lineup'),
  saveLineup: (body) => put('/api/my/lineup', body),
  aiLineup: () => put('/api/my/lineup', { use_ai: true }),
  liveStart: () => post('/api/live/start'),
  liveState: () => req('/api/live/state'),
  liveStep: () => post('/api/live/step'),
  livePitcher: (pid) => post('/api/live/pitcher', { pid }),
  livePinchHitter: (pid) => post('/api/live/pinch-hitter', { pid }),
  livePinchRunner: (base, pid) => post('/api/live/pinch-runner', { base, pid }),
  liveDefense: (outPid, inPid) => post('/api/live/defense', { out_pid: outPid, in_pid: inPid }),
  liveAuto: () => post('/api/live/auto'),
  player: (pid) => req(`/api/players/${pid}`),
  results: (day) => req(day ? `/api/results?day=${day}` : '/api/results'),
  boxscore: (day, idx) => req(`/api/results/${day}/${idx}`),
  offseason: () => req('/api/offseason/report'),
}
