import { useEffect, useState, type ReactNode } from 'react'
import { api, LANG, reasonLabel, type Call, type Status, type Trace } from './api'
import { play, playAll } from './audio'

export const STATUS_STYLE: Record<string, { bg: string; text: string; ring: string; dot: string; label: string }> = {
  RED: { bg: 'bg-red-50 dark:bg-red-950/40', text: 'text-red-700 dark:text-red-300', ring: 'ring-red-300 dark:ring-red-800', dot: 'bg-red-600', label: 'Escalated' },
  AMBER: { bg: 'bg-amber-50 dark:bg-amber-950/40', text: 'text-amber-800 dark:text-amber-300', ring: 'ring-amber-300 dark:ring-amber-800', dot: 'bg-amber-500', label: 'Follow up' },
  GREEN: { bg: 'bg-emerald-50 dark:bg-emerald-950/40', text: 'text-emerald-800 dark:text-emerald-300', ring: 'ring-emerald-300 dark:ring-emerald-800', dot: 'bg-emerald-600', label: 'On track' },
  NO_ANSWER: { bg: 'bg-slate-100 dark:bg-slate-800/50', text: 'text-slate-600 dark:text-slate-300', ring: 'ring-slate-300 dark:ring-slate-700', dot: 'bg-slate-400', label: 'No answer' },
}

export function StatusPill({ status, small }: { status: Status | null | undefined; small?: boolean }) {
  if (!status) return <span className="text-xs muted">Not called yet</span>
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.NO_ANSWER
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full ${s.bg} ${s.text} ${small ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'} font-semibold`}>
      <span className={`h-2 w-2 rounded-full ${s.dot}`} aria-hidden />
      {s.label}
    </span>
  )
}

/** tone: semantic. `rule` = a policy rule ID, written like a code in the register's blue ink. */
export function Chip({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'red' | 'amber' | 'green' | 'teal' | 'violet' }) {
  const t = {
    slate: 'bg-black/[.05] text-[var(--ink)] dark:bg-white/[.07]',
    red: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200',
    amber: 'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200',
    green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
    teal: 'bg-brand-50 text-brand-800 dark:bg-brand-900/50 dark:text-brand-100',
    violet: 'border border-current pen bg-transparent font-semibold tabular-nums',
  }[tone]
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium ${t}`}>{children}</span>
}

/**
 * Adherence as a blister pack: one foil pocket per treatment day.
 * A tablet = a confirmed dose (its colour is that day's status); a punched pocket = no dose confirmed.
 */
export function Blister({ statuses, days = 30, today, label = 'Adherence, day by day' }: {
  statuses: (Status | null | undefined)[]; days?: number; today?: number; label?: string
}) {
  const cols = days > 15 ? 15 : days
  return (
    <div className="blister" role="img" aria-label={`${label}: ${statuses.filter((s) => s === 'GREEN' || s === 'RED').length} of ${statuses.length} days with a confirmed dose`}
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, ['--gap' as string]: '4px', ['--pad' as string]: '6px' }}>
      {Array.from({ length: days }, (_, i) => {
        const s = statuses[i]
        const isToday = today === i + 1
        const punched = s === 'NO_ANSWER'
        return (
          <span key={i} title={`Day ${i + 1}: ${s ? STATUS_STYLE[s]?.label : i < statuses.length ? 'not called' : 'upcoming'}`}
            className={`pocket ${punched ? 'empty' : ''} ${isToday ? 'today' : ''}`}>
            {s && s !== 'NO_ANSWER' && <span className={`pill ${s}`} />}
          </span>
        )
      })}
    </div>
  )
}

/** Today's round as one strip of capsules, one per patient; a capsule drops in as each call ends. */
export function RoundBlister({ items }: { items: { id: string; name: string; status?: Status | null; calling?: boolean }[] }) {
  return (
    <div className="blister w-full" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))`, ['--gap' as string]: 'clamp(6px, 1.4vw, 16px)', ['--pad' as string]: 'clamp(10px, 1.6vw, 18px)' }}>
      {items.map((it) => (
        <div key={it.id} className="flex min-w-0 flex-col items-center gap-2">
          <span className={`pocket capsule w-full max-w-[64px] ${it.status === 'NO_ANSWER' ? 'empty' : ''} ${it.calling ? 'calling' : ''}`}
            aria-label={`${it.name}: ${it.status ? STATUS_STYLE[it.status]?.label : it.calling ? 'on a call' : 'waiting'}`}>
            {it.status && it.status !== 'NO_ANSWER' && <span key={it.status} className={`pill dropped ${it.status}`} />}
          </span>
          <span className="w-full truncate text-center text-xs font-semibold sm:text-sm">{it.name}</span>
        </div>
      ))}
    </div>
  )
}

/** Legacy name kept for callers. */
export const Strip = ({ statuses, today }: { statuses: (Status | null)[]; today?: number }) => <Blister statuses={statuses} today={today} />


export function LangTag({ lang }: { lang: string }) {
  return <Chip tone="teal">{LANG[lang] ?? lang}</Chip>
}

export function Wave({ className = '' }: { className?: string }) {
  return <span className={`wave inline-flex h-4 items-center ${className}`}><span /><span /><span /><span /><span /></span>
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-3 sm:p-8" onClick={onClose}>
      <div className="card w-full max-w-3xl p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between gap-4">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-sm muted hover:bg-black/5" aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

const STAGE_EN: Record<string, string> = {
  ask_dose: "Khurak asked: did you take today's dose?", followup_dose: 'Follow-up: yes or no?',
  ask_symptoms: 'Khurak asked: any problems?', confirm_symptom: 'Confirmation question',
  family_check: 'Khurak asked the family: is the patient OK?', probe_dose: 'Probe after a hesitant yes: missed any dose?',
}

/** The explainable-agent view: every turn, the evidence words, and the rule that fired. */
export function TraceView({ trace }: { trace: Trace }) {
  return (
    <div className="space-y-5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill status={trace.status} />
        <LangTag lang={trace.language} />
        <span className="muted">{trace.mode === 'live' ? 'Heard by Prisma v3.0' : 'Mock mode'}{trace.latency_ms?.stt_avg ? `, ${trace.latency_ms.stt_avg} ms per answer` : ''}</span>
      </div>
      <ol className="relative space-y-4 border-l-2 pl-5 line">
        {trace.turns.map((t, i) => (
          <li key={i} className="relative">
            <span className="absolute -left-[31px] top-0 grid h-5 w-5 place-items-center rounded-full bg-[var(--card)] text-xs font-bold pen ring-2 ring-[var(--line)]">{i + 1}</span>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm font-semibold">{STAGE_EN[t.stage] ?? t.stage}</span>
              <span className="flex items-center gap-2 text-xs muted">
                {t.stt_ms ? `${t.stt_ms} ms` : t.source}
                {t.patient_audio && <button className="rounded-md border line px-1.5 py-0.5 hover:bg-black/5" onClick={() => play(t.patient_audio)}>Play answer</button>}
              </span>
            </div>
            <p className="indic mt-1 text-lg leading-snug">“{t.transcript || '(silence)'}”</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <Chip>Dose {t.dose.toLowerCase()}</Chip>
              {t.red_flags.map((r) => <Chip key={r} tone="red">{reasonLabel(r)}</Chip>)}
              {t.negated.map((r) => <Chip key={r} tone="amber">Said not: {reasonLabel(r)}</Chip>)}
              {t.benign.map((r) => <Chip key={r} tone="green">{reasonLabel(r)}</Chip>)}
              {t.watch.map((r) => <Chip key={r} tone="amber">{reasonLabel(r)}</Chip>)}
              <Chip>Confidence {Math.round(t.confidence * 100)}%</Chip>
              {t.step_rule && <Chip tone="violet">Next: {t.step_rule}</Chip>}
            </div>
            {t.evidence.length > 0 && (
              <p className="indic mt-2 text-xs leading-relaxed muted">Matched: {t.evidence.join(', ')}</p>
            )}
            {t.evon ? <p className="mt-1 text-xs pen">Evon second listener: {JSON.stringify(t.evon)}</p> : null}
          </li>
        ))}
      </ol>
      <div className="rounded-xl border-2 p-4" style={{ borderColor: 'var(--pen)' }}>
        <p className="text-sm font-semibold pen">Decision</p>
        <p className="mt-1 text-base font-semibold">{trace.policy_rule}</p>
        <p className="mt-1 text-sm muted">Because: {trace.reasons.map(reasonLabel).join(', ')}</p>
        <p className="mt-2 text-xs muted">Actions taken</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-5 font-mono text-xs">
          {trace.actions.map((a, i) => <li key={i}>{a}</li>)}
        </ul>
      </div>
      <details className="text-xs">
        <summary className="cursor-pointer muted">Raw trace (JSON)</summary>
        <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-black/[.04] p-3 text-[11px] dark:bg-white/[.05]">{JSON.stringify(trace, null, 2)}</pre>
      </details>
    </div>
  )
}

export function TraceButton({ callId, label = 'Why?' }: { callId: string | null | undefined; label?: string }) {
  const [call, setCall] = useState<Call | null>(null)
  const [open, setOpen] = useState(false)
  if (!callId) return null
  return (
    <>
      <button className="rounded-lg border line px-2.5 py-1 text-xs font-medium hover:bg-black/5"
        onClick={async () => { setOpen(true); setCall(await api.call(callId)) }}>{label}</button>
      <Modal open={open} onClose={() => setOpen(false)} title={<>Why Khurak decided this <span className="block font-mono text-xs font-normal muted">{callId}</span></>}>
        {!call ? <p className="muted">Loading…</p> : call.trace ? (
          <>
            <TraceView trace={call.trace} />
            <ReplayCall call={call} />
          </>
        ) : <p className="muted">This call has no trace (seeded history or no answer).</p>}
      </Modal>
    </>
  )
}

export function ReplayCall({ call }: { call: Call }) {
  if (call.trace?.audio_sequence?.length) {
    const seq = call.trace.audio_sequence
    return (
      <button className="mt-4 w-full rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-800"
        onClick={() => playAll(seq)}>Play the call as the patient heard it</button>
    )
  }
  const urls: string[] = [`/audio/rec/${call.id}_a0.wav`]
  ;(call.trace?.turns ?? []).forEach((t, i) => {
    if (t.patient_audio) urls.push(t.patient_audio)
    if (i < (call.trace?.turns.length ?? 0) - 1) urls.push(`/audio/rec/${call.id}_a${i + 1}.wav`)
  })
  urls.push(`/audio/rec/${call.id}_close.wav`)
  return (
    <button className="mt-4 w-full rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-800"
      onClick={() => playAll(urls)}>Play the whole call, both sides</button>
  )
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="card px-4 py-3">
      <p className={`display text-4xl tabular-nums ${tone ?? ''}`}>{value}</p>
      <p className="mt-1 text-sm muted">{label}</p>
    </div>
  )
}
