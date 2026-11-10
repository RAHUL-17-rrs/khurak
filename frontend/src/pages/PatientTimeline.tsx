import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, reasonLabel, type Status } from '../api'
import { play } from '../audio'
import { Blister, Chip, LangTag, StatusPill, TraceButton } from '../components'

type P = Awaited<ReturnType<typeof api.patient>>

const STAGE_SHORT: Record<string, string> = {
  ask_dose: 'Dose today?', followup_dose: 'Asked again', ask_symptoms: 'Any problems?', confirm_symptom: 'Confirmation',
  probe_dose: 'Missed recently?', family_check: 'Family asked',
}

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
      <Link to="/worker" className="text-sm font-semibold pen hover:underline">Back to the work list</Link>
      <section className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="display text-5xl">{p.name} <span className="indic text-3xl font-medium muted">{p.name_local}</span></h1>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-sm">
              <dt className="muted">Patient</dt><dd>{p.age}, {p.gender === 'F' ? 'female' : 'male'}, {p.city}</dd>
              <dt className="muted">Treatment</dt><dd>Day {p.treatment_day}, regimen {p.regimen}</dd>
              <dt className="muted">Daily call</dt><dd>{p.call_time} on {p.phone_masked}</dd>
              <dt className="muted">Family contact</dt><dd>{p.family.name}, {p.family.relation}</dd>
            </dl>
          </div>
          <div className="flex items-center gap-2"><LangTag lang={p.language} />
            <Link to={`/phone/${p.id}`} className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800">Call {p.name.split(' ')[0]} now</Link></div>
        </div>
        <p className="mt-4 max-w-[75ch] text-sm muted">Synthetic patient. Their story in this demo: {p.story}</p>
      </section>

      <section className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Treatment so far</h2>
          <span className="text-sm muted">Dose confirmed on {taken} of {p.calendar.length} days ({Math.round(100 * taken / Math.max(1, p.calendar.length))}%)</span>
        </div>
        <div className="mt-4 max-w-3xl">
          <Blister statuses={days.map((d) => cal[d]?.status ?? null).slice(0, p.day)} days={days.length} today={p.day} label={`${p.name}'s treatment`} />
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm muted">
          <li className="flex items-center gap-2"><span className="pocket inline-grid h-5 w-5"><span className="pill GREEN" /></span>Dose taken</li>
          <li className="flex items-center gap-2"><span className="pocket inline-grid h-5 w-5"><span className="pill AMBER" /></span>Needs follow-up</li>
          <li className="flex items-center gap-2"><span className="pocket inline-grid h-5 w-5"><span className="pill RED" /></span>Danger sign reported</li>
          <li className="flex items-center gap-2"><span className="pocket empty inline-grid h-5 w-5" />No answer</li>
          <li className="flex items-center gap-2"><span className="pocket inline-grid h-5 w-5 ring-2 ring-[var(--pen)]" />Today</li>
        </ul>
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
        <h2 className="text-lg font-semibold">Calls Khurak made <span className="text-sm font-normal muted">(earlier days are seeded synthetic history)</span></h2>
        {real.map((c) => (
          <article key={c.id} className="card p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <b>Day {c.day}</b><span className="text-sm muted">{c.kind === 'family' ? 'Call to family' : `Attempt ${c.attempt}`}{c.state === 'NO_ANSWER' ? ', not answered' : ''}</span>
                <StatusPill status={c.status} small />{c.rule && <Chip tone="violet">{c.rule}</Chip>}
                {(c.reasons ?? []).map((r) => <Chip key={r}>{reasonLabel(r)}</Chip>)}
              </div>
              <TraceButton callId={c.trace ? c.id : null} />
            </div>
            {(c.turns ?? []).length > 0 && (
              <ul className="mt-2 space-y-1 text-sm">
                {c.turns!.map((t) => (
                  <li key={t.id} className="flex items-start gap-2">
                    <span className="w-32 shrink-0 text-sm muted">{STAGE_SHORT[t.stage] ?? t.stage}</span>
                    <span className="indic flex-1">“{t.transcript || '(silence)'}”</span>
                    {t.answer_audio && <button onClick={() => play(t.answer_audio)} className="text-sm font-semibold pen hover:underline">Play</button>}
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
