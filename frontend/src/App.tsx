import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { api, type AppStatus } from './api'
import ControlRoom from './pages/ControlRoom'
import PhoneSimulator from './pages/PhoneSimulator'
import WorkerDashboard from './pages/WorkerDashboard'
import PatientTimeline from './pages/PatientTimeline'
import Evaluation from './pages/Evaluation'
import HowItWorks from './pages/HowItWorks'

const NAV = [
  { to: '/', label: 'Control room' },
  { to: '/phone', label: 'Patient phone' },
  { to: '/worker', label: 'Health worker' },
  { to: '/eval', label: 'Evaluation' },
  { to: '/how', label: 'How it decides' },
]

export default function App() {
  const [status, setStatus] = useState<AppStatus | null>(null)
  useEffect(() => {
    const load = () => api.status().then(setStatus).catch(() => setStatus(null))
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b line bg-[var(--card)]/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2.5">
            <img src="/favicon.svg" alt="" className="h-8 w-8" />
            <span className="leading-tight">
              <span className="block text-lg font-bold tracking-tight">Khurak <span className="indic font-semibold text-brand-700 dark:text-brand-500">खुराक</span></span>
              <span className="block text-[11px] muted">Daily TB dose check-in voice agent</span>
            </span>
          </NavLink>
          <nav className="order-3 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === '/'}
                className={({ isActive }) => `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? 'bg-brand-700 text-white' : 'hover:bg-black/5 dark:hover:bg-white/5'}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-1.5 text-[11px] font-medium">
            {status ? (
              <>
                <Badge ok={status.mode === 'live'} label={status.mode === 'live' ? 'Prisma v3.0 · live' : 'MOCK MODE · no API key'} />
                <Badge ok={status.mode === 'live'} label={status.mode === 'live' ? 'Timbre v3.0 · live' : 'placeholder audio'} />
                <Badge ok={status.evon.online} neutral={!status.evon.enabled} label={status.evon.online ? 'Evon v3.3 · online' : status.evon.enabled ? 'Evon · offline' : 'Evon · not connected'} />
              </>
            ) : <Badge ok={false} label="backend offline" />}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Routes>
          <Route path="/" element={<ControlRoom status={status} />} />
          <Route path="/phone" element={<PhoneSimulator status={status} />} />
          <Route path="/phone/:pid" element={<PhoneSimulator status={status} />} />
          <Route path="/worker" element={<WorkerDashboard status={status} />} />
          <Route path="/patient/:pid" element={<PatientTimeline />} />
          <Route path="/eval" element={<Evaluation />} />
          <Route path="/how" element={<HowItWorks />} />
        </Routes>
      </main>
      <footer className="border-t line py-4 text-center text-xs muted">
        All patients, names, phone numbers and voices are <b>synthetic</b>. Prototype only: templates require clinician review; not a medical device.
        <span className="mx-1">·</span> Built on Gnani Prisma v3.0 + Timbre v3.0 for #GreatIndianAIInternshipChallenge
      </footer>
    </div>
  )
}

function Badge({ ok, label, neutral }: { ok: boolean; label: string; neutral?: boolean }) {
  const cls = neutral ? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
    : ok ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300' : 'bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 ${cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${neutral ? 'bg-slate-400' : ok ? 'bg-emerald-500 live-dot' : 'bg-amber-500'}`} />
      {label}
    </span>
  )
}
