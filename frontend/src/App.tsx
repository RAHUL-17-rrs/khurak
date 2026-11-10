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
      <header className="sticky top-0 z-40 border-b line bg-[var(--bg)]/92 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-end gap-x-8 gap-y-1 px-4 pt-3">
          <NavLink to="/" className="flex items-center gap-2.5 pb-2.5" aria-label="Khurak home">
            <img src="/favicon.svg" alt="" className="h-9 w-9" />
            <span className="wordmark text-[28px] leading-none">Khurak <span className="indic pen">खुराक</span></span>
          </NavLink>
          <nav className="order-3 -mb-px flex w-full gap-5 overflow-x-auto sm:order-none sm:w-auto" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === '/'}
                className={({ isActive }) => `whitespace-nowrap border-b-[3px] pb-2.5 pt-1 text-[15px] font-semibold ${isActive ? 'border-[var(--pen)] pen' : 'border-transparent muted hover:text-[var(--ink)]'}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <p className="ml-auto pb-3 text-sm muted" title={status ? `Evon: ${status.evon.online ? 'online' : 'not connected'}` : ''}>
            {status ? (
              <span className="inline-flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${status.mode === 'live' ? 'bg-emerald-500 live-dot' : 'bg-amber-500'}`} aria-hidden />
                {status.mode === 'live' ? 'Live on Gnani Prisma v3.0 and Timbre v3.0' : 'Mock mode: add a Gnani API key for live speech'}
              </span>
            ) : 'Server offline'}
          </p>
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
      <footer className="border-t line">
        <div className="mx-auto flex max-w-7xl flex-col gap-1 px-4 py-5 text-sm muted sm:flex-row sm:justify-between">
          <p>Every patient, name, number and voice here is synthetic. A prototype: templates need clinician review before real use.</p>
          <p>Built on Gnani Prisma v3.0 and Timbre v3.0 for #GreatIndianAIInternshipChallenge</p>
        </div>
      </footer>
    </div>
  )
}
