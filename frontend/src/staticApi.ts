/**
 * Hosted (Vercel) mode. Same API surface as the FastAPI backend, but:
 *  - dashboards read a snapshot exported right after a round recorded LIVE against Gnani;
 *  - "Run today's calls" replays that recorded round, event by event, at its real timing;
 *  - the Patient phone is genuinely live: /api/live/* is a stateless serverless function that
 *    sends each answer to Gnani Prisma v3.0 and runs the same classifier + policy code.
 */
import type { Alert, AppStatus, Call, EvalReport, KEvent, Patient, StepResult, Trace } from './api'

type Listener = (e: KEvent) => void
const listeners = new Set<Listener>()
export const bus = {
  on(fn: Listener) { listeners.add(fn); return () => { listeners.delete(fn) } },
  emit(e: KEvent) { listeners.forEach((fn) => fn(e)) },
}

const cache = new Map<string, Promise<unknown>>()
function demo<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(`/demo/${path}`).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`)
      return r.json()
    }))
  }
  return cache.get(path) as Promise<T>
}

// ---------------------------------------------------------------- local state (per browser)
const RESOLVED_KEY = 'khurak.resolved'
function resolvedSet(): Set<number> {
  try { return new Set(JSON.parse(localStorage.getItem(RESOLVED_KEY) ?? '[]')) } catch { return new Set() }
}
function saveResolved(s: Set<number>) {
  try { localStorage.setItem(RESOLVED_KEY, JSON.stringify([...s])) } catch { /* private mode */ }
}
const liveCalls = new Map<string, { state: string; pid: string; kind: string; stage: string; trace?: Trace; prompts: { audio: string }[] }>()
const missed: Record<string, number> = {}
let liveStatus: Promise<{ live: boolean; stt_model: string; per_ip_per_hour: number }> | null = null
const getLive = () => (liveStatus ??= fetch('/api/live/status').then((r) => (r.ok ? r.json() : { live: false })).catch(() => ({ live: false })))

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail ?? msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}

// ---------------------------------------------------------------- replay of the recorded round
let replayTimers: number[] = []
let replaying = false
async function replay(speed: number) {
  const round = await demo<{ day: number; events: (KEvent & { t: number })[] }>('round.json')
  replayTimers.forEach(clearTimeout)
  replayTimers = []
  replaying = true
  for (const e of round.events) {
    const id = window.setTimeout(() => {
      bus.emit({ ...e, ts: Date.now() / 1000 })
      if (e.type === 'round_finished') replaying = false
    }, (e.t * 1000) / speed)
    replayTimers.push(id)
  }
  return round.day
}

function toStep(callId: string, r: Record<string, unknown>): StepResult {
  const prompts = (r.prompts as { audio: string; text: string; english: string }[]) ?? []
  return {
    ...(r as object),
    call_id: callId,
    closed: Boolean(r.closed),
    agent_audio: prompts[0]?.audio ?? '',
    agent_audios: prompts.map((p) => p.audio),
    agent_text: prompts.map((p) => p.text).join(' '),
    agent_english: prompts.map((p) => p.english).join(' '),
  } as StepResult
}

export const staticApi = {
  status: async (): Promise<AppStatus> => {
    const [s, live] = await Promise.all([demo<AppStatus>('status.json'), getLive()])
    return { ...s, mode: live.live ? 'live' : 'mock', hosted: true, round: { ...s.round, running: replaying } } as AppStatus
  },
  patients: () => demo<Patient[]>('patients.json'),
  patient: (id: string) => demo<never>(`patients/${id}.json`),
  caseNote: async (): Promise<{ note: string; model: string }> => {
    throw new Error('Evon case notes need a hosted Evon server (EVON_BASE_URL); not connected on the public demo.')
  },
  runDay: async (pace = 1) => {
    const speed = pace >= 1 ? 1 : pace >= 0.4 ? 2.5 : 8
    const day = await replay(speed)
    return { started: true, day }
  },
  nextDay: async () => ({ day: (await demo<AppStatus>('status.json')).day }),
  reset: async () => {
    replayTimers.forEach(clearTimeout); replaying = false
    saveResolved(new Set())
    bus.emit({ type: 'reset', ts: Date.now() / 1000, day: (await demo<AppStatus>('status.json')).day })
    return { ok: true }
  },
  calls: () => demo<Call[]>('calls.json'),
  call: async (id: string) => {
    const l = liveCalls.get(id)
    if (l) return { id, patient_id: l.pid, trace: l.trace ?? null, status: l.trace?.status ?? null } as unknown as Call & { patient: Patient }
    return demo<Call & { patient: Patient }>(`calls/${id}.json`)
  },
  startCall: async (patient_id: string, kind = 'patient'): Promise<StepResult> => {
    const r = await j<Record<string, unknown>>(await fetch('/api/live/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ patient_id, kind }),
    }))
    const callId = `live_${patient_id}_${Date.now().toString(36)}`
    liveCalls.set(callId, { state: r.state as string, pid: patient_id, kind, stage: r.stage as string, prompts: r.prompts as { audio: string }[] })
    return toStep(callId, r)
  },
  answer: async (callId: string, opts: { audio?: Blob; text?: string; source: 'live' | 'scripted' | 'typed'; noise?: string; snr?: number }): Promise<StepResult> => {
    const c = liveCalls.get(callId)
    if (!c) throw new Error('call not active')
    const f = new FormData()
    f.append('state', c.state)
    let patientAudio: string | null = null
    if (opts.source === 'scripted') {
      const script = await demo<Record<string, Record<string, { text: string; audio: string }>>>('script.json')
      const line = script[c.pid]?.[c.stage]
      const live = await getLive()
      if (!line) { f.append('source', 'typed'); f.append('text', '') }
      else if (!live.live) { f.append('source', 'typed'); f.append('text', line.text); patientAudio = line.audio }
      else {
        const blob = await (await fetch(line.audio)).blob()
        f.append('source', 'scripted'); f.append('audio', blob, 'answer.wav'); f.append('clip_url', line.audio)
        patientAudio = line.audio
      }
    } else if (opts.audio) {
      f.append('source', 'live'); f.append('audio', opts.audio, 'answer.wav')
      if (opts.noise && opts.noise !== 'clean') { f.append('noise_kind', opts.noise); f.append('snr_db', String(opts.snr ?? 10)) }
    } else {
      f.append('source', 'typed'); f.append('text', opts.text ?? '')
    }
    const r = await j<Record<string, unknown>>(await fetch('/api/live/answer', { method: 'POST', body: f }))
    c.state = r.state as string
    c.stage = (r.stage as string) ?? 'closed'
    if (r.trace) c.trace = { ...(r.trace as Trace), call_id: callId }
    const step = toStep(callId, r)
    if (patientAudio) step.patient_audio = patientAudio
    return step
  },
  scriptedPreview: async (callId: string) => {
    const c = liveCalls.get(callId)
    const script = await demo<Record<string, Record<string, { text: string }>>>('script.json')
    return { stage: c?.stage ?? '', text: c ? script[c.pid]?.[c.stage]?.text ?? null : null }
  },
  noAnswer: async (callId: string) => {
    const pid = liveCalls.get(callId)?.pid ?? callId
    missed[pid] = (missed[pid] ?? 0) + 1
    return { next: missed[pid] >= 2 ? 'call_family' : 'retry_in_2h', unanswered_today: missed[pid] }
  },
  hangup: async (callId: string) => { liveCalls.delete(callId); return new Response() },
  alerts: async (resolved = 0) => {
    const done = resolvedSet()
    const all = await demo<Alert[]>('alerts.json')
    return all.filter((a) => (resolved ? done.has(a.id) : !done.has(a.id)))
  },
  resolve: async (id: number) => {
    const s = resolvedSet(); s.add(id); saveResolved(s)
    bus.emit({ type: 'alert_resolved', ts: Date.now() / 1000, alert_id: id })
    return new Response()
  },
  briefing: () => demo<never>('briefing.json'),
  evalReport: () => demo<EvalReport>('eval.json'),
  policy: () => demo<never>('policy.json'),
}
