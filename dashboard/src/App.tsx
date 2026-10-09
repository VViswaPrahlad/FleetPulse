import { useState } from "react";
import { NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BrainCircuit,
  ChevronRight,
  Gauge,
  Layers3,
  Menu,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useApi } from "./api";
import {
  Overview,
  Driving,
  DataQuality,
  Intelligence,
} from "./pages/Analytics";
import { PredictionLab } from "./pages/Prediction";

const navigation = [
  { path: "/", label: "Fleet overview", icon: Gauge },
  { path: "/driving", label: "Driving analytics", icon: BarChart3 },
  { path: "/quality", label: "Data quality", icon: ShieldCheck },
  { path: "/ml", label: "ML intelligence", icon: BrainCircuit },
  { path: "/prediction", label: "Prediction lab", icon: SlidersHorizontal },
];
function Layout() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const health = useApi<{ status: string }>("/health");
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {open && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={"sidebar " + (open ? "is-open" : "")}
        aria-label="Main navigation"
      >
        <div className="brand">
          <span className="brand-symbol">
            <Activity size={24} />
          </span>
          <div>
            Fleet<span>Pulse</span>
            <small>AUTOMOTIVE INTELLIGENCE</small>
          </div>
          <button
            className="mobile-only icon-button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
          >
            <X size={20} />
          </button>
        </div>
        <div className="nav-section">WORKSPACE</div>
        <nav>
          {navigation.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              onClick={() => setOpen(false)}
            >
              <Icon size={19} />
              <span>{label}</span>
              <ChevronRight size={14} className="nav-chevron" />
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="source-card">
            <Layers3 size={20} />
            <strong>VED research dataset</strong>
            <p>
              Historical vehicle telemetry.
              <br />
              Local analytics & inference.
            </p>
            <a
              href="https://github.com/gsoh/VED"
              target="_blank"
              rel="noreferrer"
            >
              Dataset provenance
              <ArrowUpRight size={13} />
            </a>
          </div>
          <div className="workspace-status">
            <span className="status-dot" />
            Local portfolio workspace
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-only icon-button"
              aria-label="Open navigation"
              aria-expanded={open}
              onClick={() => setOpen(true)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {navigation.find((n) => n.path === location.pathname)?.label ??
                "Page not found"}
            </strong>
          </div>
          <div
            className={
              "connection " + (health.data?.status === "ok" ? "online" : "")
            }
          >
            <span className="status-dot" />
            {health.loading
              ? "Connecting to API"
              : health.error
                ? "API unavailable"
                : "Local API connected"}
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
        <footer>
          FleetPulse · VED telemetry research
          <span>Historical data. No live vehicle tracking.</span>
        </footer>
      </div>
    </div>
  );
}
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="driving" element={<Driving />} />
        <Route path="quality" element={<DataQuality />} />
        <Route path="ml" element={<Intelligence />} />
        <Route path="prediction" element={<PredictionLab />} />
        <Route
          path="*"
          element={
            <div className="state">
              <h1>Page not found</h1>
              <NavLink to="/">Return to fleet overview</NavLink>
            </div>
          }
        />
      </Route>
    </Routes>
  );
}
