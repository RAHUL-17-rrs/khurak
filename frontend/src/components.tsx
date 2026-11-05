import { useEffect, useState, type ReactNode } from 'react'
import { api, LANG, reasonLabel, type Call, type Status, type Trace } from './api'
import { play, playAll } from './audio'

export const STATUS_STYLE: Record<string, { bg: string; text: string; ring: string; dot: string; label: string }> = {
  RED: { bg: 'bg-red-50 dark:bg-red-950/40', text: 'text-red-700 dark:text-red-300', ring: 'ring-red-300 dark:ring-red-800', dot: 'bg-red-500', label: 'Red · escalate' },
  AMBER: { bg: 'bg-amber-50 dark:bg-amber-950/40', text: 'text-amber-800 dark:text-amber-300', ring: 'ring-amber-300 dark:ring-amber-800', dot: 'bg-amber-500', label: 'Amber · follow up' },
  GREEN: { bg: 'bg-emerald-50 dark:bg-emerald-950/40', text: 'text-emerald-700 dark:text-emerald-300', ring: 'ring-emerald-300 dark:ring-emerald-800', dot: 'bg-emerald-500', label: 'Green · on track' },
  NO_ANSWER: { bg: 'bg-slate-100 dark:bg-slate-800/50', text: 'text-slate-600 dark:text-slate-300', ring: 'ring-slate-300 dark:ring-slate-700', dot: 'bg-slate-400', label: 'No answer' },
}

export function StatusPill({ status, small }: { status: Status | null | undefined; small?: boolean }) {
  if (!status) return <span className="text-xs muted">not called yet</span>
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.NO_ANSWER
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full ${s.bg} ${s.text} ${small ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'} font-semibold`}>
      <span className={`h-2 w-2 rounded-full ${s.dot}`} />
      {small ? status.replace('_', ' ') : s.label}
    </span>
  )
}

export function Chip({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'red' | 'amber' | 'green' | 'teal' | 'violet' }) {
  const t = {
    slate: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    red: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200',
    amber: 'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200',
    green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
    teal: 'bg-brand-100 text-brand-800 dark:bg-brand-900/50 dark:text-brand-100',
    violet: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200',
  }[tone]
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ${t}`}>{children}</span>
}

export function Strip({ statuses, days = 30 }: { statuses: (Status | null)[]; days?: number }) {
  const cells = statuses.slice(-days)
  return (
    <div className="flex gap-[3px]" aria-label="adherence calendar">
      {cells.map((s, i) => (
        <span key={i} title={`Day ${statuses.length - cells.length + i + 1}: ${s ?? '-'}`}
          className={`h-4 w-2 rounded-sm ${s ? STATUS_STYLE[s]?.dot ?? 'bg-slate-300' : 'bg-slate-200 dark:bg-slate-700'}`} />
      ))}
    </div>
  )
}

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
  ask_dose: 'Asked: took today\'s dose?', followup_dose: 'Follow-up: yes or no?', ask_symptoms: 'Asked: any problems?',
  confirm_symptom: 'Confirmation question', family_check: 'Asked family: is the patient OK?',
}

/** The explainable-agent view: every turn, the evidence words, and the rule that fired. */
export function TraceView({ trace }: { trace: Trace }) {
  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill status={trace.status} />
        <Chip tone="violet">{trace.policy_rule}</Chip>
        <LangTag lang={trace.language} />
        <Chip>{trace.mode === 'live' ? 'Prisma v3.0 live' : 'mock mode'}</Chip>
        {trace.latency_ms?.stt_avg ? <Chip>STT avg {trace.latency_ms.stt_avg} ms</Chip> : null}
      </div>
      <ol className="space-y-3">
        {trace.turns.map((t, i) => (
          <li key={i} className="rounded-xl border line p-3">
            <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide muted">{STAGE_EN[t.stage] ?? t.stage}</span>
              <span className="flex items-center gap-2 text-xs muted">
                {t.stt_ms ? `${t.stt_ms} ms` : t.source}
                {t.patient_audio && <button className="rounded border line px-1.5 py-0.5 hover:bg-black/5" onClick={() => play(t.patient_audio)}>▶ audio</button>}
              </span>
            </div>
            <p className="indic text-base">“{t.transcript || '(silence)'}”</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <Chip>dose: {t.dose}</Chip>
              {t.red_flags.map((r) => <Chip key={r} tone="red">🔴 {reasonLabel(r)}</Chip>)}
              {t.negated.map((r) => <Chip key={r} tone="amber">negated: {reasonLabel(r)}</Chip>)}
              {t.benign.map((r) => <Chip key={r} tone="green">{reasonLabel(r)}</Chip>)}
              {t.watch.map((r) => <Chip key={r} tone="amber">{reasonLabel(r)}</Chip>)}
              <Chip>conf {Math.round(t.confidence * 100)}%</Chip>
              {t.step_rule && <Chip tone="violet">→ {t.step_rule}</Chip>}
            </div>
            {t.evidence.length > 0 && (
              <p className="mt-2 font-mono text-[11px] leading-relaxed muted indic">evidence: {t.evidence.join(' · ')}</p>
            )}
            {t.evon ? <p className="mt-1 text-[11px] text-violet-700 dark:text-violet-300">Evon second listener: {JSON.stringify(t.evon)}</p> : null}
          </li>
        ))}
      </ol>
      <div className="rounded-xl bg-black/[.03] p-3 dark:bg-white/[.04]">
        <p className="text-xs font-semibold uppercase tracking-wide muted">Decision</p>
        <p className="mt-1 font-medium">{trace.policy_rule}</p>
        <p className="mt-1 text-xs muted">Reasons: {trace.reasons.map(reasonLabel).join(', ')}</p>
        <ul className="mt-2 space-y-0.5 font-mono text-[11px]">
          {trace.actions.map((a, i) => <li key={i}>→ {a}</li>)}
        </ul>
      </div>
      <details className="text-xs">
        <summary className="cursor-pointer muted">Raw trace JSON</summary>
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
      <Modal open={open} onClose={() => setOpen(false)} title={<>Decision trace · <span className="font-mono text-sm">{callId}</span></>}>
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
  const urls: string[] = [`/audio/rec/${call.id}_a0.wav`]
  ;(call.trace?.turns ?? []).forEach((t, i) => {
    if (t.patient_audio) urls.push(t.patient_audio)
    if (i < (call.trace?.turns.length ?? 0) - 1) urls.push(`/audio/rec/${call.id}_a${i + 1}.wav`)
  })
  urls.push(`/audio/rec/${call.id}_close.wav`)
  return (
    <button className="mt-4 w-full rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-800"
      onClick={() => playAll(urls)}>▶ Replay the whole call (agent + patient audio, 8 kHz phone line)</button>
  )
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="card px-4 py-3">
      <p className="text-xs font-medium muted">{label}</p>
      <p className={`mt-0.5 text-2xl font-bold tabular-nums ${tone ?? ''}`}>{value}</p>
    </div>
  )
}
