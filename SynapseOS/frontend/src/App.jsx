import { NavLink, Outlet } from "react-router-dom";
import { Brain, Sparkles, Github } from "lucide-react";
import clsx from "clsx";

const Tab = ({ to, icon: Icon, label }) => (
  <NavLink
    to={to}
    end
    className={({ isActive }) =>
      clsx(
        "inline-flex items-center gap-2 rounded-full px-4 py-1.5",
        "text-sm font-medium transition-all duration-200 border",
        isActive
          ? "bg-gradient-to-r from-indigo-500/25 to-fuchsia-500/25 border-indigo-400/40 text-indigo-100 shadow-[0_0_24px_-6px_rgba(129,140,248,0.6)]"
          : "border-white/10 text-white/70 hover:text-white hover:border-white/30 hover:bg-white/5"
      )
    }
  >
    <Icon className="h-4 w-4" />
    {label}
  </NavLink>
);

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-[#05060f]/60 border-b border-white/10">
        <div className="mx-auto max-w-[1600px] flex items-center justify-between px-6 py-3">
          <NavLink to="/" className="flex items-center gap-3 group">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 grid place-items-center shadow-lg shadow-indigo-500/30 group-hover:shadow-fuchsia-500/40 transition-shadow">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight">
                SynapseOS
              </div>
              <div className="text-[11px] text-white/50 -mt-0.5 tracking-wide">
                your thoughts, wired
              </div>
            </div>
          </NavLink>

          <nav className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 p-1">
            <Tab to="/" icon={Sparkles} label="Home" />
            <Tab to="/brain" icon={Brain} label="Brain" />
          </nav>

          <a
            href="https://github.com/Aryanharitsa/Projects/tree/main/SynapseOS"
            target="_blank"
            rel="noreferrer"
            className="hidden sm:inline-flex items-center gap-1 text-xs text-white/60 hover:text-white transition-colors"
          >
            <Github className="h-3.5 w-3.5" />
            Source
          </a>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-white/5 py-6 text-center text-[11px] text-white/30">
        Built as a living graph · © {new Date().getFullYear()} SynapseOS
      </footer>
    </div>
  );
}
