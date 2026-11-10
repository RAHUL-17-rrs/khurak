import { useEffect, useRef, useState } from 'react'
import { bus, staticApi } from './staticApi'

/** Built with VITE_STATIC=1 for Vercel: recorded-round replay + serverless live phone. */
export const STATIC = import.meta.env.VITE_STATIC === '1'

export type Status = 'GREEN' | 'AMBER' | 'RED' | 'NO_ANSWER'

export interface Family { name: string; relation: string; voice: string; phone_masked: string }
export interface Patient {
  id: string; name: string; name_local: string; name_hi: string; age: number; gender: string; city: string
  language: string; voice: string; call_time: string; phone_masked: string; family: Family; regimen: string
  story: string; noise: { kind: string; snr_db: number } | null; treatment_day: number
  today: { status: Status; note: string; call_id: string } | null
  adherence: number; open_alerts: number; strip: Status[]
}
export interface Understanding {
  transcript: string; dose: string; red_flags: string[]; negated: string[]; benign: string[]; watch: string[]
  affirm: boolean; deny: boolean; no_problem: boolean; away: boolean; confidence: number; evidence: string[]
}
export interface TraceTurn {
  stage: string; transcript: string; dose: string; red_flags: string[]; negated: string[]; benign: string[]
  watch: string[]; confidence: number; evidence: string[]; stt_ms: number; source: string; evon: unknown
  step_rule: string | null; patient_audio: string | null
}
export interface Trace {
  call_id: string; patient: string; language: string; kind: string; day: number; turns: TraceTurn[]
  policy_rule: string; status: Status; reasons: string[]; actions: string[]; mode: string
  latency_ms: { stt_avg: number; total: number }; memory?: Record<string, unknown>; audio_sequence?: string[]
}
export interface Call {
  id: string; patient_id: string; day: number; attempt: number; kind: string; state: string; status: Status | null
  rule: string | null; rule_text: string | null; reasons: string[] | null; trace: Trace | null; seeded: number
  started_at: string; turns?: Turn[]; name?: string; language?: string
}
export interface Turn {
  id: number; call_id: string; idx: number; stage: string; answer_audio: string | null; transcript: string
  understanding: Understanding; evon: unknown; stt_ms: number; stt_mock: number; source: string
}
export interface Alert {
  id: number; patient_id: string; call_id: string | null; day: number; level: 'RED' | 'AMBER'; rule: string
  reason: string; quote: string; created_at: string; resolved: number; name: string; language: string
  city: string; age: number
}
export interface StepResult {
  call_id: string; closed: boolean; stage?: string; agent_audio: string; agent_audios?: string[]; agent_text: string; agent_english: string
  tts_mock?: boolean; transcript?: string; understanding?: Understanding; stt_ms?: number; stt_mock?: boolean
  patient_audio?: string | null; status?: Status; rule?: string; rule_text?: string; reasons?: string[]
  trace?: Trace; step_rule?: string | null; evon?: unknown
}
export interface AppStatus {
  mode: 'live' | 'mock'; stt_model: string; tts_model: string; key_present: boolean
  evon: { enabled: boolean; online: boolean; model: string; note?: string }
  day: number; round: { running: boolean; day: number | null; progress: number; total: number }
  worker: { name: string; role: string; centre: string; language: string }
  languages: Record<string, string>; noise_kinds: string[]; max_answer_seconds: number
  api_stats?: { stt_calls: number; tts_calls: number; retries: number }
  hosted?: boolean; recorded_at?: string
}

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail ?? msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}
const post = (url: string, body?: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })

const serverApi = {
  status: () => fetch('/api/status').then(j<AppStatus>),
  patients: () => fetch('/api/patients').then(j<Patient[]>),
  patient: (id: string) => fetch(`/api/patients/${id}`).then(j<Patient & { calls: Call[]; alerts: Alert[]; calendar: { day: number; status: Status; note: string; call_id: string }[]; day: number }>),
  caseNote: (id: string) => post(`/api/patients/${id}/case-note`).then(j<{ note: string; model: string }>),
  runDay: (pace = 1) => post('/api/day/run', { pace }).then(j<{ started: boolean; day: number }>),
  nextDay: () => post('/api/day/next').then(j<{ day: number }>),
  reset: () => post('/api/reset').then(j<{ ok: boolean }>),
  calls: (day?: number) => fetch(`/api/calls${day ? `?day=${day}` : ''}`).then(j<Call[]>),
  call: (id: string) => fetch(`/api/calls/${id}`).then(j<Call & { patient: Patient }>),
  startCall: (patient_id: string, kind = 'patient') => post('/api/calls/start', { patient_id, kind }).then(j<StepResult>),
  answer: (callId: string, opts: { audio?: Blob; text?: string; source: 'live' | 'scripted' | 'typed'; noise?: string; snr?: number }) => {
    const f = new FormData()
    f.append('source', opts.source)
    if (opts.audio) f.append('audio', opts.audio, 'answer.wav')
    if (opts.text !== undefined) f.append('text', opts.text)
    if (opts.noise && opts.noise !== 'clean') { f.append('noise_kind', opts.noise); f.append('snr_db', String(opts.snr ?? 10)) }
    return fetch(`/api/calls/${callId}/answer`, { method: 'POST', body: f }).then(j<StepResult>)
  },
  scriptedPreview: (callId: string) => fetch(`/api/calls/${callId}/scripted`).then(j<{ stage: string; text: string | null }>),
  noAnswer: (callId: string) => post(`/api/calls/${callId}/no-answer`).then(j<{ next: string; unanswered_today: number }>),
  hangup: (callId: string) => post(`/api/calls/${callId}/hangup`),
  alerts: (resolved = 0) => fetch(`/api/alerts?resolved=${resolved}`).then(j<Alert[]>),
  resolve: (id: number, note: string) => post(`/api/alerts/${id}/resolve`, { note }),
  briefing: () => fetch('/api/briefing').then(j<{ text: string; english: string; audio: string; red: number; amber: number; green: number; total: number; seconds: number; mock: boolean }>),
  evalReport: () => fetch('/api/eval').then(j<EvalReport>),
  policy: () => fetch('/api/policy').then(j<{ rules: Record<string, string>; templates: Record<string, Record<string, string>>; english: Record<string, string> }>),
}

export const api: typeof serverApi = STATIC ? (staticApi as unknown as typeof serverApi) : serverApi

export interface Metrics {
  n: number; status_acc: number; rule_acc: number; red_recall: number | null; red_n: number; false_green: number
  false_green_rate: number; red_to_green: number; over_escalation: number; cer?: number | null; stt_ms_avg?: number | null
}
export interface EvalReport {
  generated_at: string; mode: string; models: { stt: string; tts: string }; pipeline: string; n_scenarios: number
  n_calls: number; n_utterances: number; overall_audio: Metrics | null; by_condition: Record<string, Metrics>
  by_language: Record<string, Metrics>
  failures: { cond: string; id: string; lang: string; expected: string; expected_rule: string; got: string; rule: string; heard: string }[]
}

export type KEvent = { type: string; ts: number; [k: string]: unknown }

/** Subscribe to the backend's Server-Sent Events stream. */
export function useEvents(onEvent: (e: KEvent) => void) {
  const cb = useRef(onEvent)
  cb.current = onEvent
  const [connected, setConnected] = useState(false)
  useEffect(() => {
    if (STATIC) {
      setConnected(true)
      return bus.on((e) => cb.current(e))
    }
    let es: EventSource | null = null
    let stop = false
    const open = () => {
      es = new EventSource('/api/events')
      es.onopen = () => setConnected(true)
      es.onerror = () => { setConnected(false); es?.close(); if (!stop) setTimeout(open, 1500) }
      es.onmessage = (m) => {
        const e = JSON.parse(m.data) as KEvent
        if (e.type === 'hello') return
        cb.current(e)
      }
    }
    open()
    return () => { stop = true; es?.close() }
  }, [])
  return connected
}

export const LANG: Record<string, string> = { 'hi-IN': 'Hindi', 'mr-IN': 'Marathi', 'bn-IN': 'Bengali', 'kn-IN': 'Kannada', 'hi-en': 'Hinglish' }

export const REASON: Record<string, string> = {
  yellow_eyes: 'Yellow eyes / skin', blood_cough: 'Blood in cough', persistent_vomit: 'Repeated vomiting',
  breathless: 'Breathlessness', vision: 'Blurred vision', rash: 'Rash / itching', orange_urine: 'Orange urine (expected)',
  mild_nausea: 'Mild nausea', tiredness: 'Tiredness', stopped_treatment: 'Stopped treatment', missed_dose: 'Missed dose',
  unclear_answer: 'Unclear answer', low_confidence: 'Low confidence', dose_taken: 'Dose taken',
  family_reports_away_or_missed: 'Away without medicines (family)', patient_unreachable_family_contacted: 'Unreachable; family contacted',
  home_visit_needed: 'Home visit needed', unspecified_problem: 'Reported a problem', vomiting: 'Vomited once',
  stomach_pain: 'Stomach pain', tingling: 'Tingling', joint_pain: 'Joint pain', no_answer: 'No answer',
  missed_recent_doses: 'Missed doses in last 3 days', hesitant: 'Hesitant answer',
  unwell: 'Feels unwell', asked_about_stopping: 'Asked about stopping',
}
export const reasonLabel = (r: string) => r.split(/[+,]/).filter(Boolean).map((x) => REASON[x.replace('evon:', '')] ?? x.replace(/_/g, ' ')).join(' + ')
