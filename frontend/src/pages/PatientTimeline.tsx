import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, reasonLabel, type Status } from '../api'
import { play } from '../audio'
import { Chip, LangTag, StatusPill, STATUS_STYLE, TraceButton } from '../components'

type P = Awaited<ReturnType<typeof api.patient>>

export default function PatientTimeline() {
  const { pid = 'P1' } = useParams()
  const [p, setP] = useState<P | null>(null)
  const [note, setNote] = useState<string>('')
  const [noteErr, setNoteErr] = useState('')
  const [noteBusy, setNoteBusy] = useState(false)
  useEffect(() => { setP(null); setNote(''); setNoteErr(''); api.patient(pid).then(setP) }, [pid])
  if (!p) return <p className="muted">Loading…</p>

  const cal: Record<number, { status: Status; note: string; call_id: string }> = {}
  p.calendar.forEach((c) => { cal[c.day] = c })
  const days = Array.from({ length: Math.max(30, p.day) }, (_, i) => i + 1)
  const real = p.calls.filter((c) => !c.seeded)
  const taken = p.calendar.filter((c) => c.status === 'GREEN' || c.status === 'RED').length

  return (
    <div className="space-y-6">
      <Link to="/worker" className="text-sm muted hover:underline">← Work list</Link>
      <section className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{p.name} <span className="indic text-lg font-medium muted">{p.name_local}</span></h1>
            <p className="mt-1 text-sm muted">{p.age} · {p.gender} · {p.city} · {p.phone_masked} · calls at {p.call_time}</p>
            <p className="mt-1 text-sm muted">Regimen {p.regimen} · treatment day {p.treatment_day} · family: {p.family.name} ({p.family.relation})</p>
          </div>
          <div className="flex items-center gap-2"><LangTag lang={p.language} /><Chip>voice: Timbre {p.voice}</Chip>
            <Link to={`/phone/${p.id}`} className="rounded-lg bg-brand-700 px-3 py-1.5 text-sm font-semibold text-white">📞 Call now</Link></div>
        </div>
        <p className="mt-3 text-sm"><b>Synthetic story:</b> {p.story}</p>
      </section>

      <section className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Adherence calendar</h2>
          <span className="text-sm muted">{taken}/{p.calendar.length} days with a confirmed dose ({Math.round(100 * taken / Math.max(1, p.calendar.length))}%)</span>
        </div>
        <div className="mt-3 grid grid-cols-10 gap-1.5 sm:grid-cols-15" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(34px, 1fr))' }}>
          {days.map((d) => {
            const c = cal[d]
            return (
              <div key={d} title={c ? `Day ${d}: ${c.status} · ${reasonLabel(c.note ?? '')}` : `Day ${d}`}
                className={`flex h-9 items-center justify-center rounded-md text-[11px] font-semibold ${c ? `${STATUS_STYLE[c.status]?.dot} text-white` : 'border line muted'} ${d === p.day ? 'ring-2 ring-brand-500 ring-offset-1' : ''}`}>{d}</div>
            )
          })}
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-xs muted">
          {(['GREEN', 'AMBER', 'RED', 'NO_ANSWER'] as Status[]).map((s) => <span key={s} className="flex items-center gap-1"><span className={`h-3 w-3 rounded-sm ${STATUS_STYLE[s].dot}`} />{STATUS_STYLE[s].label}</span>)}
        </div>
      </section>

      <section className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Case note for the health worker <Chip tone="violet">Gnani Evon v3.3</Chip></h2>
          <button disabled={noteBusy} onClick={async () => {
            setNoteBusy(true); setNoteErr('')
            try { setNote((await api.caseNote(p.id)).note) } catch (e) { setNoteErr(String(e).replace('Error: ', '')) }
            setNoteBusy(false)
          }} className="rounded-lg border line px-3 py-1.5 text-sm font-medium hover:bg-black/5">{noteBusy ? 'Writing…' : 'Generate with Evon'}</button>
        </div>
        <p className="mt-1 text-xs muted">Evon summarises the call history. It never decides a status and never speaks to the patient.</p>
        {note && <p className="mt-3 whitespace-pre-line text-sm leading-relaxed">{note}</p>}
        {noteErr && <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">{noteErr}</p>}
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Calls ({real.length} agent calls · days before are seeded synthetic history)</h2>
        {real.map((c) => (
          <article key={c.id} className="card p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <b>Day {c.day}</b><span className="text-xs muted">{c.kind === 'family' ? 'family call' : `attempt ${c.attempt}`} · {c.state}</span>
                <StatusPill status={c.status} small />{c.rule && <Chip tone="violet">{c.rule}</Chip>}
                {(c.reasons ?? []).map((r) => <Chip key={r}>{reasonLabel(r)}</Chip>)}
              </div>
              <TraceButton callId={c.trace ? c.id : null} />
            </div>
            {(c.turns ?? []).length > 0 && (
              <ul className="mt-2 space-y-1 text-sm">
                {c.turns!.map((t) => (
                  <li key={t.id} className="flex items-start gap-2">
                    <span className="w-28 shrink-0 text-xs muted">{t.stage.replace('_', ' ')}</span>
                    <span className="indic flex-1">“{t.transcript || '(silence)'}”</span>
                    {t.answer_audio && <button onClick={() => play(t.answer_audio)} className="text-xs underline">▶</button>}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
        {real.length === 0 && <p className="card p-4 text-sm muted">No agent calls yet for this patient. Run the day from the control room, or call from the phone simulator.</p>}
      </section>
    </div>
  )
}
