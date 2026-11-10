import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, reasonLabel, STATIC, useEvents, type AppStatus, type KEvent, type Patient, type Status } from '../api'
import { play } from '../audio'
import { Chip, LangTag, RoundBlister, StatusPill, STATUS_STYLE, Strip, TraceButton, Wave } from '../components'

type Phase = 'idle' | 'dialing' | 'no_answer' | 'family' | 'speaking' | 'listening' | 'thinking' | 'done' | 'error'
interface Live {
  phase: Phase; callId?: string; agent?: string; agentEn?: string; heard?: string; sttMs?: number
  status?: Status; rule?: string; ruleText?: string; reasons?: string[]; note?: string; kind?: string
}
interface LogLine { ts: number; text: string; tone: 'red' | 'amber' | 'green' | 'slate' | 'violet'; pid?: string }

const PHASE_LABEL: Record<Phase, string> = {
  idle: 'Waiting', dialing: 'Dialing', no_answer: 'No answer', family: 'Calling the family',
  speaking: 'Khurak is speaking', listening: 'Listening', thinking: 'Understanding the answer', done: 'Call finished', error: 'Call failed',
}

export default function ControlRoom({ status }: { status: AppStatus | null }) {
  const [patients, setPatients] = useState<Patient[]>([])
  const [live, setLive] = useState<Record<string, Live>>({})
  const [log, setLog] = useState<LogLine[]>([])
  const [running, setRunning] = useState(false)
  const [day, setDay] = useState<number | null>(null)
  const [pace, setPace] = useState(1)
  const [listenTo, setListenTo] = useState<string | null>(null)
  const [roundActive, setRoundActive] = useState(false)
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
        setRunning(true); setRoundActive(true); setLive({}); addLog(`Round started for day ${e.day}, ${e.total} patients`, 'violet'); break
      case 'call_dialing':
        upd(pid, { phase: e.kind === 'family' ? 'family' : 'dialing', callId: e.call_id as string, kind: e.kind as string, heard: undefined, agent: undefined, status: undefined })
        addLog(e.kind === 'family' ? `${name}: calling family contact (${e.who})` : `${name}: dialing (attempt ${e.attempt})`, 'slate', pid); break
      case 'no_answer':
        upd(pid, { phase: 'no_answer', note: `attempt ${e.attempt}` }); addLog(`${name}: no answer (attempt ${e.attempt})`, 'amber', pid); break
      case 'retry_scheduled':
        addLog(`${name}: rule X1, retry in 2 hours (compressed for the demo)`, 'slate', pid); break
      case 'family_call':
        addLog(`${name}: rule X2, two unanswered calls, so calling ${e.relation ?? 'family'} ${e.family ?? ''}`, 'amber', pid); break
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
        addLog(`${name}: ${(e.reasons as string[]).map(reasonLabel).join(', ')}. ${STATUS_STYLE[st]?.label ?? st} (${e.rule})`, st === 'RED' ? 'red' : st === 'AMBER' ? 'amber' : 'green', pid)
        break
      }
      case 'alert':
        addLog(`${e.level === 'RED' ? 'Urgent alert' : 'Alert'} sent to the health worker: ${name}, ${reasonLabel(e.reason as string)}`, e.level === 'RED' ? 'red' : 'amber', pid); break
      case 'call_error':
        upd(pid, { phase: 'error', note: e.error as string }); addLog(`${name}: error ${e.error}`, 'red', pid); break
      case 'round_finished':
        setRunning(false); setRoundActive(false); addLog(`Round finished for day ${e.day}`, 'violet'); load(); break
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

  const firstName = (n: string) => n.split(' ')[0]
  const roundItems = patients.map((p) => {
    const l = live[p.id]
    return { id: p.id, name: firstName(p.name), status: l?.status ?? (l || roundActive ? undefined : p.today?.status),
      calling: Boolean(l && !['done', 'idle', 'error', 'no_answer'].includes(l.phase)) }
  })
  const tally = [counts.RED && `${counts.RED} escalated`, counts.AMBER && `${counts.AMBER} to follow up`, counts.GREEN && `${counts.GREEN} on track`].filter(Boolean).join(', ')
  const BORDER: Record<string, string> = { RED: 'border-l-red-600', AMBER: 'border-l-amber-500', GREEN: 'border-l-emerald-600', NO_ANSWER: 'border-l-slate-400' }

  return (
    <div className="space-y-8">
      <section className="space-y-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <h1 className="display text-5xl sm:text-7xl">Day {day ?? '…'}. {patients.length || 'Eight'} patients to call.</h1>
            <p className="mt-3 text-lg muted">
              Khurak phones each patient in their own language, listens on an 8 kHz line with Gnani Prisma, and a fixed
              rulebook decides what happens next. Every danger sign reaches {status?.worker?.name?.split(' ')[0] ?? 'the health worker'} the same day.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={run} disabled={running}
              className="rounded-xl bg-brand-700 px-6 py-3 text-base font-semibold text-white hover:bg-brand-800 disabled:opacity-70">
              {running ? <span className="inline-flex items-center gap-2"><Wave /> Calling patients</span> : "Run today's calls"}
            </button>
            <label className="sr-only" htmlFor="pace">Speed</label>
            <select id="pace" value={pace} onChange={(e) => setPace(Number(e.target.value))} className="card px-3 py-3 text-sm">
              <option value={1}>Real time</option>
              <option value={0.4}>Faster</option>
              <option value={0}>Fastest</option>
            </select>
            <button onClick={async () => { await api.reset(); setLive({}); setLog([]); load() }} disabled={running}
              className="rounded-xl px-3 py-3 text-sm font-semibold muted hover:text-[var(--ink)] disabled:opacity-50">Reset</button>
            {!STATIC && <button onClick={async () => { await api.nextDay(); load() }} disabled={running}
              className="rounded-xl px-3 py-3 text-sm font-semibold muted hover:text-[var(--ink)] disabled:opacity-50">Next day</button>}
          </div>
        </div>

        <RoundBlister items={roundItems} />
        <p className="text-base">
          {tally ? <><span className="font-semibold">{tally}.</span> <span className="muted">{done} of {patients.length} calls finished.</span></>
            : <span className="muted">No calls yet today. Each tablet drops into its pocket when that call ends.</span>}
        </p>

        {err && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}
        {STATIC && (
          <p className="max-w-3xl text-sm muted">
            This hosted demo replays a round recorded live against Gnani Prisma v3.0 and Timbre v3.0
            {status?.recorded_at ? ` on ${status.recorded_at}` : ''}: the real audio, transcripts and decisions, at their real pace.
            The <Link to="/phone" className="font-semibold pen underline underline-offset-2">patient phone</Link> is fully live.
          </p>
        )}
        {status?.mode === 'mock' && !STATIC && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            No Gnani API key found, so audio is a placeholder and transcripts are the scripted text. Add GNANI_API_KEY to <code>.env</code> for live speech.
          </p>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <section className="grid gap-4 sm:grid-cols-2" aria-label="Patients">
          {patients.map((p) => {
            const l = live[p.id]
            const st = l?.status ?? (l || roundActive ? undefined : p.today?.status)
            const active = l && !['done', 'idle', 'error'].includes(l.phase)
            return (
              <article key={p.id} className={`card border-l-[5px] p-4 ${st ? BORDER[st] : 'border-l-[var(--line)]'} ${active ? 'outline outline-2 outline-[var(--pen)]' : ''}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <Link to={`/patient/${p.id}`} className="text-lg font-semibold leading-tight hover:underline">{p.name}</Link>
                    <p className="text-sm muted">{p.age}, {p.city}. Day {p.treatment_day} of treatment.</p>
                  </div>
                  <LangTag lang={p.language} />
                </div>
                <div className="mt-3 min-h-[96px] rounded-lg bg-black/[.03] p-3 text-sm dark:bg-white/[.04]">
                  {!l ? (
                    p.today && !roundActive ? <p className="muted">Today: {reasonLabel(p.today.note || '')}</p>
                      : <p className="muted">{p.story}{p.noise ? ` Answers with ${p.noise.kind.replace('_', ' ')} noise at ${p.noise.snr_db} dB.` : ''}</p>
                  ) : (
                    <>
                      <p className="flex items-center gap-2 font-semibold">
                        {active && <Wave className="pen" />}{PHASE_LABEL[l.phase]}{l.note && l.phase !== 'done' ? `: ${l.note}` : ''}
                      </p>
                      {l.agent && <p className="indic mt-1 line-clamp-2"><span className="muted">Khurak:</span> {l.agent}</p>}
                      {l.agentEn && <p className="line-clamp-1 text-xs italic muted">{l.agentEn}</p>}
                      {l.heard !== undefined && <p className="indic mt-1"><span className="muted">{l.kind === 'family' ? 'Family' : 'Patient'}:</span> “{l.heard || '…'}”</p>}
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
                    <button onClick={() => setListenTo(listenTo === p.id ? null : p.id)} aria-pressed={listenTo === p.id}
                      className={`rounded-lg border line px-2.5 py-1 text-sm font-medium ${listenTo === p.id ? 'bg-brand-700 text-white' : 'hover:bg-black/5'}`}
                      title="Hear this patient's call during the round">{listenTo === p.id ? 'Listening' : 'Listen in'}</button>
                    <TraceButton callId={l?.callId ?? p.today?.call_id} />
                  </div>
                </div>
                <div className="mt-3"><Strip statuses={[...p.strip.slice(0, p.treatment_day - 1), ...(st ? [st] : [])]} today={p.treatment_day} /></div>
              </article>
            )
          })}
        </section>

        <aside className="card flex max-h-[780px] flex-col p-4 xl:sticky xl:top-24 xl:self-start">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">What Khurak decided</h2>
            <span className="flex items-center gap-1.5 text-sm muted">
              <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-500 live-dot' : 'bg-slate-400'}`} aria-hidden />{connected ? 'Live' : 'Reconnecting'}
            </span>
          </div>
          {log.length === 0 && <p className="text-sm muted">Each decision appears here as it happens, with the rule that made it.</p>}
          <ol className="space-y-1.5 overflow-y-auto pr-1 text-sm" aria-live="polite">
            {log.map((l, i) => (
              <li key={i} className={`indic rounded-md px-2 py-1.5 ${{ red: 'bg-red-50 text-red-900 dark:bg-red-950/40 dark:text-red-200', amber: 'bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200', green: 'bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200', violet: 'bg-brand-50 text-brand-900 dark:bg-brand-900/30 dark:text-brand-100', slate: '' }[l.tone]}`}>
                <time className="mr-2 text-xs tabular-nums muted">{new Date(l.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>{l.text}
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  )
}
