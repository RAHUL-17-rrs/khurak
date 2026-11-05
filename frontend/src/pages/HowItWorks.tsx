import { useEffect, useState } from 'react'
import { api, LANG } from '../api'
import { Chip } from '../components'

type Policy = Awaited<ReturnType<typeof api.policy>>

const PIPE = [
  { t: 'Timbre v3.0', d: 'Speaks fixed, reviewable templates in the patient\'s language. 8 kHz phone audio, cached.' },
  { t: '8 kHz phone line', d: 'Patient audio is band-limited 300–3400 Hz, μ-law encoded: what a real call carries.' },
  { t: 'Prisma v3.0', d: 'Transcribes with TB keyterm boosting, a call topic and previous-turn context.' },
  { t: 'Classifier', d: 'Lexicon + fuzzy + script-agnostic phonetic matching, negation & question aware. No LLM.' },
  { t: 'Policy table', d: 'Deterministic rules, first match wins. Every decision has a rule ID and evidence words.' },
  { t: 'Tools', d: 'Escalate, flag, reassure, retry, call family, log, brief the health worker.' },
]

const INVARIANTS = [
  ['Any danger sign → RED, immediately', 'Nothing downstream can downgrade it. The patient is told to go to hospital / 108 if worse.'],
  ['Never GREEN when unsure', 'Unclear or low-confidence answers always go to a human as AMBER.'],
  ['Negation is confirmed, not guessed', '“आँखें पीली नहीं हैं” triggers one yes/no confirmation question.'],
  ['Questions are not statements', '“दवा बंद कर दूँ क्या?” (should I stop?) is not read as “I stopped”.'],
  ['The patient only hears templates', 'No generated text ever reaches a patient. Templates need clinician review before real use.'],
  ['Evon can only add concern', 'The optional LLM second listener may raise AMBER for human review; it can never lower a status.'],
]

export default function HowItWorks() {
  const [p, setP] = useState<Policy | null>(null)
  const [lang, setLang] = useState('hi-IN')
  useEffect(() => { api.policy().then(setP) }, [])

  return (
    <div className="space-y-8">
      <section>
        <p className="text-sm font-medium text-brand-700 dark:text-brand-500">How Khurak decides</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Rules decide. Humans approve. Nothing is invented.</h1>
        <p className="mt-2 max-w-3xl text-sm muted">
          99DOTS, India's missed-call adherence system, records a missed call and nothing else. A missed call cannot say
          “my urine turned orange and I'm scared” or “my eyes are yellow”. Voice can. Khurak listens, but every action comes from an auditable rule table.
        </p>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {PIPE.map((s, i) => (
          <div key={s.t} className="card p-4">
            <p className="text-xs font-semibold text-brand-700 dark:text-brand-500">Step {i + 1}</p>
            <p className="mt-0.5 font-semibold">{s.t}</p>
            <p className="mt-1 text-sm muted">{s.d}</p>
          </div>
        ))}
      </section>

      <section className="card p-5">
        <h2 className="font-semibold">Safety invariants (unit-tested)</h2>
        <ul className="mt-3 grid gap-3 md:grid-cols-2">
          {INVARIANTS.map(([a, b]) => <li key={a} className="rounded-xl border line p-3"><p className="font-medium">{a}</p><p className="mt-1 text-sm muted indic">{b}</p></li>)}
        </ul>
      </section>

      {p && (
        <>
          <section className="card overflow-x-auto p-5">
            <h2 className="font-semibold">Policy table: evaluated top to bottom, first match wins</h2>
            <table className="mt-3 w-full min-w-[560px] text-sm">
              <tbody className="divide-y line">
                {Object.entries(p.rules).map(([k, v]) => (
                  <tr key={k}><td className="w-16 py-2 align-top"><Chip tone={k.startsWith('X') ? 'slate' : k.startsWith('F') ? 'teal' : 'violet'}>{k}</Chip></td><td className="py-2">{v}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs muted">R = within a call · F = family call · X = across calls and days (retries, family escalation, 3-day home visit).</p>
          </section>

          <section className="card p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">Everything Khurak can say</h2>
              <div className="flex gap-1">
                {Object.keys(p.templates).map((l) => (
                  <button key={l} onClick={() => setLang(l)} className={`rounded-lg px-2.5 py-1 text-xs font-medium ${lang === l ? 'bg-brand-700 text-white' : 'border line'}`}>{LANG[l] ?? l}</button>
                ))}
              </div>
            </div>
            <table className="mt-3 w-full text-sm">
              <tbody className="divide-y line">
                {Object.entries(p.templates[lang]).map(([k, v]) => (
                  <tr key={k}><td className="w-44 py-2 pr-3 align-top font-mono text-xs muted">{k}</td>
                    <td className="py-2"><p className="indic">{v}</p><p className="text-xs italic muted">{p.english[k]}</p></td></tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  )
}
