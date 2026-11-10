import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, LANG, reasonLabel, type AppStatus, type Patient, type StepResult, type Understanding } from '../api'
import { play, playAll, stopAudio, WavRecorder } from '../audio'
import { Chip, LangTag, StatusPill, TraceButton, Wave } from '../components'

type Phase = 'idle' | 'ringing' | 'connecting' | 'agent' | 'your_turn' | 'recording' | 'processing' | 'patient_audio' | 'closed' | 'missed'
interface TurnView { agent?: string; agentEn?: string; heard?: string; u?: Understanding; sttMs?: number; source?: string; stepRule?: string | null; mock?: boolean }

const NOISES = [
  { id: 'clean', label: 'Quiet room' }, { id: 'street', label: '🚗 Street traffic' },
  { id: 'construction', label: '🏗️ Construction' }, { id: 'pressure_cooker', label: '🍳 Pressure cooker' },
  { id: 'crowd', label: '👥 Crowd' },
]
const STAGE_HINT: Record<string, string> = {
  ask_dose: 'Did you take today\'s dose?', followup_dose: 'Yes or no?', ask_symptoms: 'Any problems?',
  confirm_symptom: 'Confirm: yes or no?', family_check: 'Is the patient OK?', probe_dose: 'Missed any dose in 3 days?',
}

export default function PhoneSimulator({ status }: { status: AppStatus | null }) {
  const { pid } = useParams()
  const nav = useNavigate()
  const [patients, setPatients] = useState<Patient[]>([])
  const [phase, setPhase] = useState<Phase>('idle')
  const [kind, setKind] = useState<'patient' | 'family'>('patient')
  const [callId, setCallId] = useState<string | null>(null)
  const [stage, setStage] = useState<string>('')
  const [turns, setTurns] = useState<TurnView[]>([])
  const [final, setFinal] = useState<StepResult | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [noise, setNoise] = useState('clean')
  const [snr, setSnr] = useState(10)
  const [typed, setTyped] = useState('')
  const [err, setErr] = useState('')
  const [secs, setSecs] = useState(0)
  const [missedInfo, setMissedInfo] = useState<string>('')
  const rec = useRef<WavRecorder | null>(null)
  const timer = useRef<number | null>(null)
  const [level, setLevel] = useState(0)

  useEffect(() => { api.patients().then(setPatients) }, [])
  const patient = patients.find((p) => p.id === (pid ?? 'P1')) ?? patients[0]

  useEffect(() => () => { stopAudio(); if (callId && phase !== 'closed') api.hangup(callId) }, []) // eslint-disable-line

  const reset = () => {
    stopAudio(); setPhase('idle'); setCallId(null); setTurns([]); setFinal(null); setPreview(null); setErr(''); setMissedInfo('')
  }

  const ring = (k: 'patient' | 'family' = 'patient') => {
    reset(); setKind(k); setPhase('ringing')
  }

  const pickUp = async () => {
    if (!patient) return
    setPhase('connecting')
    try {
      const r = await api.startCall(patient.id, kind)
      setCallId(r.call_id)
      await speak(r)
    } catch (e) { setErr(String(e)); setPhase('idle') }
  }

  const decline = async () => {
    if (!patient) return
    try {
      const r = await api.startCall(patient.id, 'patient')
      const n = await api.noAnswer(r.call_id)
      setMissedInfo(n.next === 'call_family'
        ? `Rule X2: ${n.unanswered_today} unanswered calls today, so Khurak now calls the family contact, ${patient.family.name} (${patient.family.relation}).`
        : 'Rule X1: no answer, so Khurak will try again in 2 hours (at most twice).')
      setPhase('missed')
    } catch (e) { setErr(String(e)); setPhase('idle') }
  }

  async function speak(r: StepResult) {
    setTurns((t) => [...t, { agent: r.agent_text, agentEn: r.agent_english }])
    setStage(r.stage ?? '')
    setPhase('agent')
    await playAll(r.agent_audios?.length ? r.agent_audios : [r.agent_audio], 150)
    if (r.closed) { setFinal(r); setPhase('closed'); return }
    setPhase('your_turn')
    if (r.call_id) api.scriptedPreview(r.call_id).then((p) => setPreview(p.text)).catch(() => setPreview(null))
  }

  async function handle(r: StepResult, source: string) {
    setTurns((t) => {
      const c = [...t]
      c[c.length - 1] = { ...c[c.length - 1], heard: r.transcript, u: r.understanding, sttMs: r.stt_ms, source, stepRule: r.step_rule, mock: r.stt_mock }
      return c
    })
    await speak(r)
  }

  const answerScripted = async () => {
    if (!callId) return
    setPhase('processing'); setErr('')
    try {
      const r = await api.answer(callId, { source: 'scripted' })
      setPhase('patient_audio')
      await play(r.patient_audio)
      await handle(r, 'scripted synthetic voice')
    } catch (e) { setErr(String(e)); setPhase('your_turn') }
  }

  const startRec = async () => {
    setErr('')
    try {
      rec.current = new WavRecorder()
      await rec.current.start()
      setPhase('recording'); setSecs(0)
      const t0 = Date.now()
      timer.current = window.setInterval(() => {
        const s = (Date.now() - t0) / 1000
        setSecs(s); setLevel(rec.current?.level ?? 0)
        if (s >= (status?.max_answer_seconds ?? 15)) stopRec()
      }, 100)
    } catch { setErr('Microphone permission denied. You can still use a scripted or typed answer.') }
  }

  const stopRec = async () => {
    if (timer.current) { clearInterval(timer.current); timer.current = null }
    if (!rec.current || !callId) return
    const cap = await rec.current.stop()
    rec.current = null
    setLevel(0)
    // Don't spend a Prisma call on an empty recording, and don't report it as the patient's silence.
    if (cap.seconds < 0.4) {
      setErr('That recording was too short. Hold the button long enough to finish your sentence.')
      setPhase('your_turn'); return
    }
    if (cap.peak < 0.012) {
      setErr(`No sound reached the browser from “${cap.device}”, so there was nothing to send. ` +
        'Check that the right microphone is selected and unmuted, and watch the meter move while you speak.')
      setPhase('your_turn'); return
    }
    setPhase('processing')
    try {
      const r = await api.answer(callId, { audio: cap.blob, source: 'live', noise, snr })
      await handle(r, noise === 'clean' ? 'your voice (live mic)' : `your voice + ${noise} @ ${snr} dB`)
    } catch (e) { setErr(String(e)); setPhase('your_turn') }
  }

  const answerTyped = async () => {
    if (!callId || !typed.trim()) return
    setPhase('processing')
    try {
      const r = await api.answer(callId, { text: typed, source: 'typed' })
      setTyped('')
      await handle(r, 'typed (bypasses speech)')
    } catch (e) { setErr(String(e)); setPhase('your_turn') }
  }

  const who = kind === 'family' ? `${patient?.family.name} (${patient?.family.relation})` : patient?.name
  const inCall = ['agent', 'your_turn', 'recording', 'processing', 'patient_audio', 'connecting'].includes(phase)

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,380px)_1fr]">
      {/* patient picker */}
      <aside className="space-y-2">
        <h2 className="text-sm font-semibold muted">Synthetic patients</h2>
        {patients.map((p) => (
          <button key={p.id} onClick={() => { if (!inCall) { nav(`/phone/${p.id}`); reset() } }}
            className={`card block w-full px-3 py-2 text-left text-sm ${p.id === patient?.id ? 'ring-2 ring-brand-500' : 'hover:bg-black/[.02]'} ${inCall ? 'cursor-not-allowed opacity-70' : ''}`}>
            <span className="flex items-center justify-between gap-2"><b>{p.name}</b><LangTag lang={p.language} /></span>
            <span className="mt-0.5 line-clamp-2 block text-xs muted">{p.story}</span>
          </button>
        ))}
      </aside>

      {/* phone */}
      <section className="mx-auto w-full max-w-[380px]">
        <div className="relative rounded-[2.6rem] border-[10px] border-slate-900 bg-slate-950 p-4 text-white shadow-2xl dark:border-slate-700" style={{ minHeight: 640 }}>
          <div className="mx-auto mb-4 h-5 w-28 rounded-full bg-slate-900" />
          <p className="text-center text-xs text-slate-400">{patient?.phone_masked}, in {LANG[patient?.language ?? ''] ?? ''}{kind === 'family' ? ', family contact' : ''}</p>

          {phase === 'idle' && (
            <div className="mt-24 text-center">
              <p className="text-sm text-slate-400">{patient ? `${patient.name}'s phone` : 'Loading…'}</p>
              <button onClick={() => ring('patient')} className="mt-6 rounded-full bg-brand-600 px-6 py-3 font-semibold hover:bg-brand-500">Khurak calls {patient?.name.split(' ')[0]}</button>
              <button onClick={() => ring('family')} className="mt-3 block w-full text-sm text-slate-400 underline">Or call their {patient?.family.relation} instead</button>
            </div>
          )}

          {phase === 'ringing' && (
            <div className="mt-20 text-center">
              <div className="ringing mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-brand-600"><svg viewBox="0 0 24 24" className="h-9 w-9" fill="currentColor" aria-hidden><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z"/></svg></div>
              <p className="mt-5 text-xl font-semibold">Khurak</p>
              <p className="text-sm text-slate-400">Health centre, calling {who}</p>
              <div className="mt-16 flex justify-around">
                {kind === 'patient' && <button onClick={decline} className="flex h-16 w-16 items-center justify-center rounded-full bg-red-600 text-2xl" title="Don't answer">✕</button>}
                <button onClick={pickUp} className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500 text-2xl" title="Answer">✆</button>
              </div>
              <p className="mt-3 text-xs text-slate-500">Green answers. Red lets it ring out.</p>
            </div>
          )}

          {phase === 'missed' && (
            <div className="mt-20 text-center">
              <p className="text-4xl">📵</p>
              <p className="mt-3 font-semibold">Missed call from Khurak</p>
              <p className="mt-3 text-sm text-slate-300">{missedInfo}</p>
              <button onClick={() => ring('patient')} className="mt-6 block w-full rounded-full bg-slate-800 py-2 text-sm">Retry now</button>
              <button onClick={() => ring('family')} className="mt-2 block w-full rounded-full bg-brand-600 py-2 text-sm font-semibold">Call family contact</button>
            </div>
          )}

          {(inCall || phase === 'closed') && (
            <div className="flex flex-col" style={{ minHeight: 540 }}>
              <div className="text-center">
                <p className="font-semibold">Khurak, from the health centre</p>
                <p className="text-xs text-slate-400">{phase === 'closed' ? 'Call ended' : `On call with ${who}`}</p>
              </div>
              <div className="mt-3 flex-1 space-y-2 overflow-y-auto pr-1" style={{ maxHeight: 330 }}>
                {turns.map((t, i) => (
                  <div key={i} className="space-y-2">
                    {t.agent && (
                      <div className="max-w-[90%] rounded-2xl rounded-tl-sm bg-brand-700 px-3 py-2">
                        <p className="indic text-[14px] leading-snug">{t.agent}</p>
                        <p className="mt-1 text-[11px] italic text-brand-100/80">{t.agentEn}</p>
                      </div>
                    )}
                    {t.heard !== undefined && (
                      <div className="ml-auto max-w-[90%] rounded-2xl rounded-tr-sm bg-slate-800 px-3 py-2">
                        <p className="indic text-[14px]">{t.heard || '(silence)'}</p>
                        <p className="mt-1 text-[11px] text-slate-400">{t.mock ? 'Mock transcript' : `Heard by Prisma v3.0${t.sttMs ? ` in ${t.sttMs} ms` : ''}`}, {t.source}</p>
                      </div>
                    )}
                  </div>
                ))}
                {phase === 'patient_audio' && <p className="text-right text-xs text-slate-400"><Wave /> Patient answering (synthetic Timbre voice on an 8 kHz line)</p>}
                {phase === 'processing' && <p className="text-right text-xs text-slate-400"><Wave /> Prisma is transcribing, then the rules decide</p>}
                {phase === 'agent' && <p className="text-xs text-brand-100"><Wave /> Khurak is speaking</p>}
              </div>

              {phase === 'closed' && final && (
                <div className="mt-3 rounded-2xl bg-white p-3 text-slate-900">
                  <div className="flex items-center justify-between"><StatusPill status={final.status} /><Chip tone="violet">{final.rule}</Chip></div>
                  <p className="mt-2 text-sm font-medium">{final.rule_text}</p>
                  <p className="mt-1 text-xs text-slate-600">{(final.reasons ?? []).map(reasonLabel).join(', ')}</p>
                  <div className="mt-2 flex gap-2"><TraceButton callId={final.call_id} label="Why this decision?" />
                    <button onClick={reset} className="rounded-lg border px-2.5 py-1 text-xs">New call</button></div>
                </div>
              )}

              {['your_turn', 'recording'].includes(phase) && (
                <div className="mt-3 space-y-2">
                  <p className="text-center text-sm text-slate-300">Your turn to answer: {STAGE_HINT[stage] ?? stage}</p>
                  {phase === 'recording' ? (
                    <button onClick={stopRec} className="w-full rounded-2xl bg-red-600 py-3 font-semibold">
                      Stop and send ({secs.toFixed(1)}s / {status?.max_answer_seconds ?? 15}s)
                      <span className="mx-auto mt-2 flex h-2 w-11/12 overflow-hidden rounded bg-black/40" aria-hidden>
                        <span className="h-full rounded bg-white transition-[width] duration-100" style={{ width: `${Math.min(100, level * 100)}%` }} />
                      </span>
                      <span className="mt-1 block text-xs font-normal">
                        {level > 0.04 ? 'Microphone is picking you up' : secs > 1.2 ? 'No sound yet. Is the right mic selected?' : 'Speak now'}
                      </span>
                    </button>
                  ) : (
                    <>
                      <button onClick={answerScripted} className="w-full rounded-2xl bg-brand-600 px-3 py-2.5 text-left text-sm font-semibold hover:bg-brand-500">
                        Play scripted answer
                        {preview && <span className="indic mt-0.5 block text-xs font-normal text-brand-50/90">“{preview}”</span>}
                      </button>
                      <button onClick={startRec} className="w-full rounded-2xl bg-slate-800 py-2.5 text-sm font-semibold hover:bg-slate-700">Answer with your own voice</button>
                      <form onSubmit={(e) => { e.preventDefault(); answerTyped() }} className="flex gap-1.5">
                        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Or type an answer, e.g. हाँ ले ली"
                          className="indic min-w-0 flex-1 rounded-xl bg-slate-800 px-3 py-2 text-sm outline-none placeholder:text-slate-500" />
                        <button className="rounded-xl bg-slate-700 px-3 text-sm font-semibold">Send</button>
                      </form>
                    </>
                  )}
                  {phase !== 'recording' && callId && (
                    <button onClick={() => { api.hangup(callId); reset() }} className="mx-auto block text-[11px] text-red-300 underline">hang up</button>
                  )}
                </div>
              )}
            </div>
          )}
          {err && <p className="mt-3 rounded-lg bg-red-500/20 px-2 py-1 text-xs text-red-200">{err}</p>}
        </div>
      </section>

      {/* understanding panel */}
      <section className="space-y-4">
        <div className="card p-4">
          <h2 className="font-semibold">Line conditions for your live answer</h2>
          <p className="mt-1 text-xs muted">Your mic audio is mixed with synthetic background noise at the chosen SNR, then sent through a simulated phone line (300–3400 Hz, 8 kHz, G.711 μ-law) before Prisma hears it.</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {NOISES.map((n) => (
              <button key={n.id} onClick={() => setNoise(n.id)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium ${noise === n.id ? 'bg-brand-700 text-white' : 'border line hover:bg-black/5'}`}>{n.label}</button>
            ))}
          </div>
          {noise !== 'clean' && (
            <label className="mt-3 flex items-center gap-3 text-sm">SNR {snr} dB
              <input type="range" min={0} max={20} value={snr} onChange={(e) => setSnr(Number(e.target.value))} className="flex-1 accent-teal-700" />
              <span className="text-xs muted">{snr <= 5 ? 'very noisy' : snr <= 10 ? 'noisy' : 'mild'}</span>
            </label>
          )}
          {patient?.noise && <p className="mt-2 text-xs muted">Scripted answers for {patient.name} already include {patient.noise.kind.replace('_', ' ')} at {patient.noise.snr_db} dB.</p>}
        </div>

        <div className="card p-4">
          <h2 className="font-semibold">What the agent understood</h2>
          {turns.filter((t) => t.u).length === 0 && <p className="mt-2 text-sm muted">Each answer shows up here: what Prisma heard, what Khurak understood, and the rule that picked the next step.</p>}
          <ol className="mt-2 space-y-3">
            {turns.filter((t) => t.u).map((t, i) => (
              <li key={i} className="rounded-xl border line p-3 text-sm">
                <p className="indic">“{t.heard || '(silence)'}”</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  <Chip>dose: {t.u!.dose}</Chip>
                  {t.u!.red_flags.map((r) => <Chip key={r} tone="red">{reasonLabel(r)}</Chip>)}
                  {t.u!.negated.map((r) => <Chip key={r} tone="amber">said NOT: {reasonLabel(r)}</Chip>)}
                  {t.u!.benign.map((r) => <Chip key={r} tone="green">{reasonLabel(r)}</Chip>)}
                  {t.u!.watch.map((r) => <Chip key={r} tone="amber">{reasonLabel(r)}</Chip>)}
                  <Chip>confidence {Math.round(t.u!.confidence * 100)}%</Chip>
                  {t.stepRule && <Chip tone="violet">next: {t.stepRule}</Chip>}
                </div>
                {t.u!.evidence.length > 0 && <p className="indic mt-2 font-mono text-[11px] muted">{t.u!.evidence.join(', ')}</p>}
              </li>
            ))}
          </ol>
        </div>
        <div className="card p-4 text-sm">
          <h2 className="font-semibold">Try it</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] muted">
            <li>Say <span className="indic">“हाँ ले ली, लेकिन आँखें पीली हो गई हैं”</span> and the call escalates at once.</li>
            <li>Say <span className="indic">“आँखें पीली नहीं हैं”</span> and Khurak asks one confirmation question instead of guessing.</li>
            <li>Say <span className="indic">“पेशाब लाल आ रहा है”</span> and you hear the approved reassurance: orange urine is a normal rifampicin effect.</li>
            <li>Talk about the weather and you get one follow-up question, then a follow-up flag. Unsure is never marked safe.</li>
            <li>Say <span className="indic">“हम्म… शायद ले ली थी”</span>, or wait 3 seconds before answering, and the hesitant yes gets probed.</li>
          </ul>
        </div>
      </section>
    </div>
  )
}
