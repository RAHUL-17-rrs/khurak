import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, reasonLabel, useEvents, type AppStatus, type KEvent, type Patient, type Status } from '../api'
import { play } from '../audio'
import { Chip, LangTag, StatusPill, Stat, STATUS_STYLE, Strip, TraceButton, Wave } from '../components'

type Phase = 'idle' | 'dialing' | 'no_answer' | 'family' | 'speaking' | 'listening' | 'thinking' | 'done' | 'error'
interface Live {
  phase: Phase; callId?: string; agent?: string; agentEn?: string; heard?: string; sttMs?: number
  status?: Status; rule?: string; ruleText?: string; reasons?: string[]; note?: string; kind?: string
}
interface LogLine { ts: number; text: string; tone: 'red' | 'amber' | 'green' | 'slate' | 'violet'; pid?: string }

const PHASE_LABEL: Record<Phase, string> = {
  idle: 'Waiting', dialing: '📞 Dialing…', no_answer: '📵 No answer', family: '👪 Calling family…',
  speaking: '🔊 Khurak speaking', listening: '🎙️ Listening', thinking: '🧠 Prisma + policy…', done: 'Done', error: '⚠ Error',
}

export default function ControlRoom({ status }: { status: AppStatus | null }) {
  const [patients, setPatients] = useState<Patient[]>([])
  const [live, setLive] = useState<Record<string, Live>>({})
  const [log, setLog] = useState<LogLine[]>([])
  const [running, setRunning] = useState(false)
  const [day, setDay] = useState<number | null>(null)
  const [pace, setPace] = useState(1)
  const [listenTo, setListenTo] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const queue = useRef<string[]>([])
  const playing = useRef(false)
  const listenRef = useRef<string | null>(null)
  listenRef.current = listenTo

  const load = useCallback(() => api.patients().then(setPatients).catch((e) => setErr(String(e))), [])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (status) { setDay(status.day); setRunning(status.round.running) } }, [status])

  const enqueue = (url?: unknown) => {
    if (typeof url !== 'string') return
    queue.current.push(url)
    if (playing.current) return
    playing.current = true
    ;(async () => {
      while (queue.current.length) await play(queue.current.shift())
      playing.current = false
    })()
  }

  const upd = (pid: string, patch: Partial<Live>) => setLive((l) => ({ ...l, [pid]: { ...(l[pid] ?? { phase: 'idle' }), ...patch } }))
  const addLog = (text: string, tone: LogLine['tone'] = 'slate', pid?: string) =>
    setLog((l) => [{ ts: Date.now(), text, tone, pid }, ...l].slice(0, 80))

  const connected = useEvents((e: KEvent) => {
    const pid = e.patient_id as string
    const name = (e.name as string) ?? patients.find((p) => p.id === pid)?.name ?? pid
    const mine = listenRef.current && pid === listenRef.current
    switch (e.type) {
      case 'round_started':
        setRunning(true); setLive({}); addLog(`Round started · day ${e.day} · ${e.total} patients`, 'violet'); break
      case 'call_dialing':
        upd(pid, { phase: e.kind === 'family' ? 'family' : 'dialing', callId: e.call_id as string, kind: e.kind as string, heard: undefined, agent: undefined, status: undefined })
        addLog(e.kind === 'family' ? `${name}: calling family contact (${e.who})` : `${name}: dialing (attempt ${e.attempt})`, 'slate', pid); break
      case 'no_answer':
        upd(pid, { phase: 'no_answer', note: `No answer · attempt ${e.attempt}` }); addLog(`${name}: no answer (attempt ${e.attempt})`, 'amber', pid); break
      case 'retry_scheduled':
        addLog(`${name}: X1 → retry in 2 h (compressed for demo)`, 'slate', pid); break
      case 'family_call':
        addLog(`${name}: X2 → 2 unanswered attempts → calling ${e.relation ?? 'family'} ${e.family ?? ''}`, 'amber', pid); break
      case 'agent_speaking':
        upd(pid, { phase: 'speaking', agent: e.text as string, agentEn: e.english as string })
        if (mine) enqueue(e.audio)
        setTimeout(() => setLive((l) => l[pid]?.phase === 'speaking' ? { ...l, [pid]: { ...l[pid], phase: 'listening' } } : l), 1800)
        break
      case 'listening_done':
        upd(pid, { phase: 'thinking' }); break
      case 'transcribed':
        upd(pid, { phase: 'thinking', heard: e.text as string, sttMs: e.stt_ms as number })
        if (mine) enqueue(e.audio)
        addLog(`${name}: Prisma heard “${e.text}” (${e.stt_ms} ms)`, 'slate', pid); break
      case 'decided': {
        const st = e.status as Status
        upd(pid, { phase: 'done', status: st, rule: e.rule as string, ruleText: e.rule_text as string, reasons: e.reasons as string[] })
        if (mine) enqueue(e.audio)
        addLog(`${name} → ${e.rule}: ${(e.reasons as string[]).map(reasonLabel).join(', ')} → ${st}`, st === 'RED' ? 'red' : st === 'AMBER' ? 'amber' : 'green', pid)
        break
      }
      case 'alert':
        addLog(`${e.level === 'RED' ? '🚨' : '⚠️'} Alert to health worker: ${name} · ${reasonLabel(e.reason as string)}`, e.level === 'RED' ? 'red' : 'amber', pid); break
      case 'call_error':
        upd(pid, { phase: 'error', note: e.error as string }); addLog(`${name}: error ${e.error}`, 'red', pid); break
      case 'round_finished':
        setRunning(false); addLog(`Round finished · day ${e.day}`, 'violet'); load(); break
      case 'reset': case 'day_changed':
        setLive({}); setDay(e.day as number); load(); break
    }
  })

  const counts = { RED: 0, AMBER: 0, GREEN: 0 } as Record<string, number>
  patients.forEach((p) => {
    const s = live[p.id]?.status ?? p.today?.status
    if (s && s in counts) counts[s]++
  })
  const done = patients.filter((p) => live[p.id]?.phase === 'done' || (!running && p.today)).length

  const run = async () => {
    setErr('')
    try { await api.runDay(pace); setRunning(true) } catch (e) { setErr(String(e)) }
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-medium text-brand-700 dark:text-brand-500">Control room · {status?.worker?.centre ?? 'Demo TB Unit'}</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Day {day ?? '…'} of treatment round</h1>
          <p className="mt-1 max-w-2xl text-sm muted">
            Khurak calls every patient in their own language, understands the answer on an 8 kHz phone line with Prisma v3.0,
            and a deterministic policy decides: reassure, ask again, call family, or alert the health worker.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={pace} onChange={(e) => setPace(Number(e.target.value))} className="card px-2 py-2 text-sm" aria-label="pace">
            <option value={1}>Demo pace</option>
            <option value={0.4}>Fast</option>
            <option value={0}>Max speed</option>
          </select>
          <button onClick={run} disabled={running}
            className="rounded-xl bg-brand-700 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-800 disabled:opacity-60">
            {running ? <span className="inline-flex items-center gap-2"><Wave /> Calling patients…</span> : '▶ Run today\'s calls'}
          </button>
          <button onClick={async () => { await api.reset(); setLive({}); setLog([]); load() }} disabled={running}
            className="rounded-xl border line px-3 py-2.5 text-sm font-medium hover:bg-black/5 disabled:opacity-50">Reset demo</button>
          <button onClick={async () => { await api.nextDay(); load() }} disabled={running}
            className="rounded-xl border line px-3 py-2.5 text-sm font-medium hover:bg-black/5 disabled:opacity-50">Next day →</button>
        </div>
      </section>

      {err && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}
      {status?.mode === 'mock' && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Mock mode: no GNANI_API_KEY found. Audio is a placeholder and transcripts are the scripted text. Add your key to <code>.env</code> for real Prisma + Timbre.
        </p>
      )}

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="🔴 Escalated today" value={counts.RED} tone="text-red-600" />
        <Stat label="🟡 Follow up" value={counts.AMBER} tone="text-amber-600" />
        <Stat label="🟢 On track" value={counts.GREEN} tone="text-emerald-600" />
        <Stat label="Calls complete" value={`${done}/${patients.length}`} />
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <section className="grid gap-3 sm:grid-cols-2">
          {patients.map((p) => {
            const l = live[p.id]
            const st = l?.status ?? (l ? undefined : p.today?.status)
            const s = st ? STATUS_STYLE[st] : null
            const active = l && !['done', 'idle', 'error'].includes(l.phase)
            return (
              <article key={p.id} className={`card p-4 transition ${s ? `ring-2 ${s.ring}` : ''} ${active ? 'ring-2 ring-brand-500/60' : ''}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <Link to={`/patient/${p.id}`} className="font-semibold hover:underline">{p.name}</Link>
                    <p className="text-xs muted">{p.age} · {p.city} · day {p.treatment_day} · {p.phone_masked}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <LangTag lang={p.language} />
                    {p.noise && <Chip tone="slate">🔊 {p.noise.kind.replace('_', ' ')} {p.noise.snr_db} dB</Chip>}
                  </div>
                </div>
                <div className="mt-3 min-h-[92px] rounded-lg bg-black/[.025] p-2.5 text-sm dark:bg-white/[.03]">
                  {!l ? (
                    p.today ? <p className="text-xs muted">Today: {reasonLabel(p.today.note || '')}</p>
                      : <p className="text-xs muted">{p.story}</p>
                  ) : (
                    <>
                      <p className="flex items-center gap-2 text-xs font-semibold">
                        {active && <Wave className="text-brand-600" />}{PHASE_LABEL[l.phase]}{l.note && l.phase !== 'done' ? ` · ${l.note}` : ''}
                      </p>
                      {l.agent && <p className="indic mt-1 line-clamp-2 text-[13px]"><span className="muted">Khurak:</span> {l.agent}</p>}
                      {l.agentEn && <p className="line-clamp-1 text-[11px] muted italic">{l.agentEn}</p>}
                      {l.heard !== undefined && <p className="indic mt-1 text-[13px]"><span className="muted">{l.kind === 'family' ? 'Family' : 'Patient'}:</span> “{l.heard || '…'}”</p>}
                    </>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusPill status={st} small />
                    {l?.rule && <Chip tone="violet">{l.rule}</Chip>}
                    {(l?.reasons ?? []).slice(0, 2).map((r) => <Chip key={r} tone={st === 'RED' ? 'red' : st === 'AMBER' ? 'amber' : 'green'}>{reasonLabel(r)}</Chip>)}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button onClick={() => setListenTo(listenTo === p.id ? null : p.id)}
                      className={`rounded-lg border line px-2.5 py-1 text-xs font-medium ${listenTo === p.id ? 'bg-brand-700 text-white' : 'hover:bg-black/5'}`}
                      title="Hear this patient's call live during the round">{listenTo === p.id ? '🎧 Listening' : '🎧 Listen in'}</button>
                    <TraceButton callId={l?.callId ?? p.today?.call_id} />
                  </div>
                </div>
                <div className="mt-3"><Strip statuses={[...p.strip.slice(0, p.treatment_day - 1), ...(st ? [st] : [])]} /></div>
              </article>
            )
          })}
        </section>

        <aside className="card flex max-h-[760px] flex-col p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">Agent decision log</h2>
            <span className="flex items-center gap-1.5 text-xs muted">
              <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-500 live-dot' : 'bg-slate-400'}`} />{connected ? 'live' : 'reconnecting'}
            </span>
          </div>
          {log.length === 0 && <p className="text-sm muted">Press “Run today's calls”. Every decision appears here with the rule that fired.</p>}
          <ol className="space-y-1.5 overflow-y-auto pr-1 text-[13px]">
            {log.map((l, i) => (
              <li key={i} className={`indic rounded-md px-2 py-1 ${{ red: 'bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200', amber: 'bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200', green: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200', violet: 'bg-violet-50 text-violet-800 dark:bg-violet-950/40 dark:text-violet-200', slate: '' }[l.tone]}`}>
                <span className="mr-1.5 font-mono text-[10px] muted">{new Date(l.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>{l.text}
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  )
}
