import { useEffect, useState } from 'react'
import { api, LANG, type EvalReport, type Metrics } from '../api'
import { Chip, Stat } from '../components'

const COND_LABEL: Record<string, string> = {
  text: 'Ground-truth text (no audio)', clean: 'Clean phone line', street_15db: 'Street traffic · 15 dB SNR',
  crowd_10db: 'Crowd babble · 10 dB SNR', construction_5db: 'Construction · 5 dB SNR', crowd_10db_noboost: 'Crowd 10 dB · keyterm boost OFF',
}
const pct = (x: number | null | undefined) => (x === null || x === undefined ? '–' : `${(x * 100).toFixed(1)}%`)

function Bar({ v, title }: { v: number | null | undefined; title: string }) {
  if (v === null || v === undefined) return <span className="muted">–</span>
  return (
    <span className="flex items-center gap-2" title={`${title}: ${pct(v)}`}>
      <span className="relative h-2 w-24 overflow-hidden rounded bg-black/[.06] dark:bg-white/[.08]">
        <span className="absolute inset-y-0 left-0 rounded bg-brand-600" style={{ width: `${v * 100}%` }} />
      </span>
      <span className="tabular-nums">{pct(v)}</span>
    </span>
  )
}

export default function Evaluation() {
  const [r, setR] = useState<EvalReport | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.evalReport().then(setR).catch((e) => setErr(String(e))) }, [])
  if (err) return <p className="card p-4 text-sm">No evaluation report yet. Run <code>python scripts/evaluate.py</code> in <code>backend/</code>. ({err})</p>
  if (!r) return <p className="muted">Loading…</p>
  const o = r.overall_audio
  const audioConds = Object.entries(r.by_condition).filter(([k]) => !['text', 'crowd_10db_noboost'].includes(k))
  const boost = r.by_condition['crowd_10db'], noboost = r.by_condition['crowd_10db_noboost']

  return (
    <div className="space-y-6">
      <section>
        <p className="text-sm font-medium text-brand-700 dark:text-brand-500">Evaluation · {r.generated_at} · {r.mode}</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Does it work on a noisy phone line?</h1>
        <p className="mt-2 max-w-3xl text-sm muted">{r.pipeline}. Every number below was measured by <code>scripts/evaluate.py</code>, which runs the
          exact production dialogue and policy code. All calls are synthetic: {r.n_scenarios} scripted calls in 5 languages, voiced by different Timbre speakers.</p>
      </section>

      {o && (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Red-flag recall (all noisy audio)" value={pct(o.red_recall)} tone="text-brand-700 dark:text-brand-500" />
          <Stat label="Danger sign marked GREEN" value={o.red_to_green} tone={o.red_to_green ? 'text-red-600' : 'text-emerald-600'} />
          <Stat label="Call status accuracy" value={pct(o.status_acc)} />
          <Stat label="Prisma transcriptions" value={r.n_utterances} />
        </section>
      )}

      <section className="card overflow-x-auto p-4">
        <h2 className="font-semibold">By line condition</h2>
        <table className="mt-3 w-full min-w-[720px] text-sm">
          <thead className="text-left text-xs muted"><tr>
            <th className="py-2 pr-3 font-medium">Condition</th><th className="pr-3 font-medium">Calls</th><th className="pr-3 font-medium">Status accuracy</th>
            <th className="pr-3 font-medium">Red-flag recall</th><th className="pr-3 font-medium">False GREEN</th><th className="pr-3 font-medium">Prisma CER</th><th className="font-medium">STT latency</th>
          </tr></thead>
          <tbody className="divide-y line">
            {Object.entries(r.by_condition).map(([k, m]) => (
              <tr key={k} className={k === 'crowd_10db_noboost' ? 'opacity-70' : ''}>
                <td className="py-2 pr-3">{COND_LABEL[k] ?? k}</td><td className="pr-3 tabular-nums">{m.n}</td>
                <td className="pr-3"><Bar v={m.status_acc} title="Status accuracy" /></td>
                <td className="pr-3"><Bar v={m.red_recall} title="Red-flag recall" /></td>
                <td className={`pr-3 tabular-nums ${m.false_green ? 'font-semibold text-red-600' : ''}`}>{m.false_green}</td>
                <td className="pr-3 tabular-nums">{m.cer === null || m.cer === undefined ? '–' : pct(m.cer)}</td>
                <td className="tabular-nums">{m.stt_ms_avg ? `${m.stt_ms_avg} ms` : '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs muted">False GREEN = a call the ground truth says needs attention, marked safe (the unacceptable error). CER = Prisma character error rate on a script-agnostic phonetic key.</p>
      </section>

      {boost && noboost && (
        <section className="card p-4">
          <h2 className="font-semibold">Prisma v3.0 keyterm boosting (crowd noise, 10 dB)</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {([['Boost ON (TB drug + symptom keyterms)', boost], ['Boost OFF', noboost]] as [string, Metrics][]).map(([label, m]) => (
              <div key={label} className="rounded-xl border line p-3 text-sm">
                <p className="font-medium">{label}</p>
                <p className="mt-1 muted">Status accuracy {pct(m.status_acc)} · red recall {pct(m.red_recall)} · CER {pct(m.cer ?? null)}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="card overflow-x-auto p-4">
        <h2 className="font-semibold">By language (all noisy-audio conditions)</h2>
        <table className="mt-3 w-full min-w-[520px] text-sm">
          <thead className="text-left text-xs muted"><tr><th className="py-2 font-medium">Language</th><th className="font-medium">Calls</th><th className="font-medium">Status accuracy</th><th className="font-medium">Red-flag recall</th><th className="font-medium">False GREEN</th></tr></thead>
          <tbody className="divide-y line">
            {Object.entries(r.by_language).map(([k, m]) => (
              <tr key={k}><td className="py-2">{LANG[k] ?? k}</td><td className="tabular-nums">{m.n}</td><td><Bar v={m.status_acc} title="Status accuracy" /></td>
                <td><Bar v={m.red_recall} title="Red-flag recall" /></td><td className="tabular-nums">{m.false_green}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card p-4">
        <h2 className="font-semibold">Every miss, unedited ({r.failures.length})</h2>
        <p className="mt-1 text-xs muted">Misses are listed so they can be fixed, not hidden. The safety question is the direction of each miss: towards a human (AMBER) is safe, towards GREEN is not.</p>
        {r.failures.length === 0 ? <p className="mt-3 text-sm">No misses.</p> : (
          <ul className="mt-3 space-y-2 text-sm">
            {r.failures.map((f, i) => (
              <li key={i} className="rounded-lg border line p-2.5">
                <div className="flex flex-wrap items-center gap-1.5"><Chip>{COND_LABEL[f.cond] ?? f.cond}</Chip><b>{f.id}</b><span className="muted">{LANG[f.lang]}</span>
                  <Chip tone="green">expected {f.expected} {f.expected_rule}</Chip>
                  <Chip tone={f.got === 'GREEN' && f.expected !== 'GREEN' ? 'red' : 'amber'}>got {f.got} {f.rule}</Chip></div>
                <p className="indic mt-1 text-[13px] muted">{f.heard}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
      {audioConds.length === 0 && <p className="text-sm muted">Only the text-level run is present (no API key at evaluation time).</p>}
    </div>
  )
}
