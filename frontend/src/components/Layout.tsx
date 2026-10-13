import { useState, type FormEvent } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  BadgeCheck,
  BarChart3,
  BookOpen,
  Database,
  Dna,
  FlaskConical,
  Gauge,
  Info,
  Menu,
  Microscope,
  ScatterChart,
  Search,
  ShieldAlert,
  Upload,
  X,
} from "lucide-react";

const NAV = [
  { to: "/", label: "Dashboard", icon: Gauge, end: true },
  { to: "/biomarkers", label: "Biomarker Explorer", icon: FlaskConical },
  { to: "/cancers", label: "Cancer Explorer", icon: Microscope },
  { to: "/entities", label: "Genes, Proteins & Pathways", icon: Dna },
  { to: "/publications", label: "Research Evidence", icon: BookOpen },
  { to: "/gaps", label: "Evidence Gaps", icon: ShieldAlert },
  { to: "/prevalence", label: "Evidence vs Prevalence", icon: ScatterChart },
  { to: "/validation", label: "Score Validation", icon: BadgeCheck },
  { to: "/analytics", label: "SQL Analytics", icon: BarChart3 },
  { to: "/methodology", label: "Scoring Method", icon: Activity },
  { to: "/import", label: "Data Import", icon: Upload },
  { to: "/about", label: "About & Sources", icon: Info },
];

export function Layout() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) navigate(`/biomarkers?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 transform bg-navy-900 text-slate-200 transition-transform lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex h-16 items-center gap-2 border-b border-white/10 px-5">
          <Database className="h-6 w-6 text-teal-300" aria-hidden />
          <div>
            <div className="font-semibold tracking-tight text-white">CancerBioMap</div>
            <div className="text-[11px] text-slate-400">Biomarker evidence database</div>
          </div>
          <button className="ml-auto lg:hidden" onClick={() => setOpen(false)} aria-label="Close navigation"><X className="h-5 w-5" /></button>
        </div>
        <nav className="space-y-0.5 p-3" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${isActive ? "bg-white/10 font-medium text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}>
              <Icon className="h-4 w-4" aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        <p className="absolute bottom-4 left-5 right-5 text-[11px] leading-snug text-slate-500">
          For research and education only. Not for clinical decision-making.
        </p>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/95 px-4 backdrop-blur sm:px-6">
          <button className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation"><Menu className="h-5 w-5 text-navy-800" /></button>
          <form onSubmit={submit} className="relative w-full max-w-xl" role="search">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <label htmlFor="global-search" className="sr-only">Search biomarkers</label>
            <input id="global-search" value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search biomarkers by gene symbol, name or code (e.g. KRAS, CBM-003)"
              className="w-full rounded-lg border border-slate-300 bg-slate-50 py-2 pl-9 pr-3 text-sm focus:bg-white" />
          </form>
        </header>
        <main id="main" className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
