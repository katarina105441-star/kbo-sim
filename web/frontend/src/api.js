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
  health: () => req('/api/health'),
  meta: () => req('/api/meta'),
  teamsAll: () => req('/api/teams/all'),
  teamIdentities: () => req('/api/teams/identities'),
  frontOffice: () => req('/api/front-office'),
  engagement: () => req('/api/engagement'),
  ownerEventChoice: (choiceId) => post('/api/engagement/choice', { choice_id: choiceId }),
  career: () => req('/api/career'),
  acceptCareerOffer: (tid) => post('/api/career/accept', { tid }),
  retireCareer: () => post('/api/career/retire'),
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
  developmentState: () => req('/api/development/state'),
  promotePlayer: (pid) => post('/api/development/promote', { pid }),
  demotePlayer: (pid) => post('/api/development/demote', { pid }),
  setDevelopmentFocus: (pid, focus) => put('/api/development/focus', { pid, focus }),
  autoDevelopmentRoster: () => post('/api/development/auto'),
  liveStart: () => post('/api/live/start'),
  liveState: () => req('/api/live/state'),
  liveStep: () => post('/api/live/step'),
  livePitcher: (pid) => post('/api/live/pitcher', { pid }),
  livePinchHitter: (pid) => post('/api/live/pinch-hitter', { pid }),
  livePinchRunner: (base, pid) => post('/api/live/pinch-runner', { base, pid }),
  liveDefense: (outPid, inPid) => post('/api/live/defense', { out_pid: outPid, in_pid: inPid }),
  liveAuto: () => post('/api/live/auto'),
  tradeState: () => req('/api/trade/state'),
  tradePropose: (otherTid, giveAssetIds, receiveAssetIds) => post('/api/trade/propose', {
    other_tid: otherTid, give_asset_ids: giveAssetIds, receive_asset_ids: receiveAssetIds,
  }),
  tradeAcceptCounter: () => post('/api/trade/accept-counter'),
  tradeRejectCounter: () => post('/api/trade/reject-counter'),
  tradeFinish: () => post('/api/trade/finish'),
  faState: () => req('/api/fa/state'),
  faOffer: (aav) => post('/api/fa/offer', { aav }),
  faPass: () => post('/api/fa/pass'),
  faAuto: () => post('/api/fa/auto'),
  faAutoFinish: () => post('/api/fa/auto-finish'),
  compensationState: () => req('/api/fa/compensation/state'),
  compensationProtect: (pids) => post('/api/fa/compensation/protect', { pids }),
  compensationAutoProtect: () => post('/api/fa/compensation/protect-auto'),
  compensationPlayer: (pid) => post('/api/fa/compensation/player', { pid }),
  compensationCash: () => post('/api/fa/compensation/cash'),
  compensationAuto: () => post('/api/fa/compensation/auto'),
  compensationAutoFinish: () => post('/api/fa/compensation/auto-finish'),
  draftState: () => req('/api/draft/state'),
  draftPick: (pid) => post('/api/draft/pick', { pid }),
  draftAutoPick: () => post('/api/draft/auto-pick'),
  player: (pid) => req(`/api/players/${pid}`),
  results: (day) => req(day ? `/api/results?day=${day}` : '/api/results'),
  boxscore: (day, idx) => req(`/api/results/${day}/${idx}`),
  offseason: () => req('/api/offseason/report'),
}
