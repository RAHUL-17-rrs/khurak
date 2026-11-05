import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, reasonLabel, useEvents, type Alert, type AppStatus, type Patient } from '../api'
import { play } from '../audio'
import { Chip, LangTag, StatusPill, TraceButton, Wave } from '../components'

type Brief = Awaited<ReturnType<typeof api.briefing>>

export default function WorkerDashboard({ status }: { status: AppStatus | null }) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [patients, setPatients] = useState<Patient[]>([])
  const [brief, setBrief] = useState<Brief | null>(null)
  const [briefing, setBriefing] = useState(false)
  const [playingBrief, setPlayingBrief] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    api.alerts(0).then(setAlerts)
    api.patients().then(setPatients)
  }, [])
  useEffect(() => { load() }, [load])
  useEvents((e) => { if (['alert', 'alert_resolved', 'round_finished', 'reset', 'decided'].includes(e.type)) load() })

  const day = status?.day
  const today = alerts.filter((a) => a.day === day)
  const older = alerts.filter((a) => a.day !== day)
  const reds = today.filter((a) => a.level === 'RED')
  const ambers = today.filter((a) => a.level === 'AMBER')
  const greens = patients.filter((p) => p.today?.status === 'GREEN')
  const notCalled = patients.filter((p) => !p.today)

  const playBriefing = async () => {
    setBriefing(true); setErr('')
    try {
      const b = await api.briefing()
      setBrief(b); setBriefing(false); setPlayingBrief(true)
      await play(b.audio)
    } catch (e) { setErr(String(e)) }
    setBriefing(false); setPlayingBrief(false)
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-sm font-medium text-brand-700 dark:text-brand-500">{status?.worker?.role} · {status?.worker?.name}</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Today's work list · day {day}</h1>
          <p className="mt-1 text-sm muted">Sorted by urgency. Every alert carries the patient's exact words and the rule that raised it.</p>
        </div>
        <button onClick={playBriefing} disabled={briefing || playingBrief}
          className="rounded-xl bg-brand-700 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-brand-800 disabled:opacity-70">
          {briefing ? 'Preparing briefing…' : playingBrief ? <span className="inline-flex items-center gap-2"><Wave /> Playing briefing</span> : '▶ Play morning voice briefing (Hindi)'}
        </button>
      </section>
      {err && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}

      {brief && (
        <section className="card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Morning briefing · voice note for the health worker</h2>
            <span className="flex gap-1.5"><Chip tone="red">{brief.red} red</Chip><Chip tone="amber">{brief.amber} amber</Chip><Chip tone="green">{brief.green} green</Chip><Chip>{brief.seconds}s · Timbre v3.0</Chip></span>
          </div>
          <p className="indic mt-2 text-[15px] leading-relaxed">{brief.text}</p>
          <p className="mt-1 text-xs italic muted">{brief.english}</p>
          <audio controls src={brief.audio} className="mt-3 w-full" />
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <AlertColumn title="🔴 See today" subtitle="Danger signs. The patient was told to go to hospital / 108 if worse." items={reds} onDone={load} empty="No red alerts today." />
        <AlertColumn title="🟡 Call or visit" subtitle="Missed / stopped doses, unclear answers, non-urgent symptoms, unreachable patients." items={ambers} onDone={load} empty="No amber alerts today." />
      </div>

      <section className="card p-4">
        <h2 className="font-semibold">🟢 On track today ({greens.length})</h2>
        <div className="mt-2 flex flex-wrap gap-2">
          {greens.map((p) => (
            <Link key={p.id} to={`/patient/${p.id}`} className="rounded-lg border line px-3 py-1.5 text-sm hover:bg-black/5">
              {p.name} <span className="muted">· {reasonLabel(p.today?.note ?? '')}</span>
            </Link>
          ))}
          {greens.length === 0 && <p className="text-sm muted">Run today's calls from the control room.</p>}
        </div>
        {notCalled.length > 0 && <p className="mt-3 text-xs muted">Not yet called today: {notCalled.map((p) => p.name).join(', ')}</p>}
      </section>

      {older.length > 0 && (
        <section className="card p-4">
          <h2 className="font-semibold">Still open from earlier days ({older.length})</h2>
          <ul className="mt-2 divide-y line text-sm">
            {older.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 py-2">
                <span><StatusPill status={a.level} small /> <b className="ml-1">{a.name}</b> · day {a.day} · {reasonLabel(a.reason)}</span>
                <button className="text-xs underline" onClick={async () => { await api.resolve(a.id, 'Followed up'); load() }}>resolve</button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function AlertColumn({ title, subtitle, items, onDone, empty }: { title: string; subtitle: string; items: Alert[]; onDone: () => void; empty: string }) {
  return (
    <section className="space-y-3">
      <div><h2 className="text-lg font-semibold">{title} ({items.length})</h2><p className="text-xs muted">{subtitle}</p></div>
      {items.length === 0 && <p className="card p-4 text-sm muted">{empty}</p>}
      {items.map((a) => <AlertCard key={a.id} a={a} onDone={onDone} />)}
    </section>
  )
}

function AlertCard({ a, onDone }: { a: Alert; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const red = a.level === 'RED'
  const hear = async () => {
    if (!a.call_id) return
    const c = await api.call(a.call_id)
    const turns = c.trace?.turns ?? []
    const t = [...turns].reverse().find((x) => x.patient_audio && (x.red_flags.length || x.watch.length || x.dose !== 'TAKEN')) ?? turns[turns.length - 1]
    await play(t?.patient_audio)
  }
  return (
    <article className={`card p-4 ${red ? 'ring-2 ring-red-300 dark:ring-red-800' : ''}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <Link to={`/patient/${a.patient_id}`} className="font-semibold hover:underline">{a.name}</Link>
          <p className="text-xs muted">{a.age} · {a.city} · {new Date(a.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
        </div>
        <div className="flex items-center gap-1.5"><LangTag lang={a.language} /><Chip tone="violet">{a.rule}</Chip></div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {a.reason.split('+').map((r) => <Chip key={r} tone={red ? 'red' : 'amber'}>{reasonLabel(r)}</Chip>)}
      </div>
      {a.quote && <blockquote className="indic mt-3 border-l-4 border-brand-500 pl-3 text-[15px] leading-snug">“{a.quote}”</blockquote>}
      <div className="mt-3 flex flex-wrap gap-2">
        {a.call_id && <button onClick={hear} className="rounded-lg border line px-2.5 py-1 text-xs font-medium hover:bg-black/5">▶ Hear patient</button>}
        <TraceButton callId={a.call_id} />
        <button disabled={busy} onClick={async () => { setBusy(true); await api.resolve(a.id, red ? 'Visited / referred' : 'Called / visited'); onDone() }}
          className="ml-auto rounded-lg bg-brand-700 px-3 py-1 text-xs font-semibold text-white hover:bg-brand-800 disabled:opacity-60">✓ Mark {red ? 'visited' : 'done'}</button>
      </div>
    </article>
  )
}
