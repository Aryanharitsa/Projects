import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Sparkles, GitCompareArrows } from "lucide-react";

const NavTab = ({ to, icon: Icon, label }) => (
  <NavLink
    to={to}
    end
    className={({ isActive }) =>
      [
        "group inline-flex items-center gap-2 rounded-full px-4 py-1.5",
        "text-sm font-medium transition-all duration-200 border",
        isActive
          ? "bg-gradient-to-r from-indigo-500/20 to-fuchsia-500/20 border-indigo-400/40 text-indigo-100 shadow-[0_0_24px_-6px_rgba(129,140,248,0.6)]"
          : "border-white/10 text-white/70 hover:text-white hover:border-white/30 hover:bg-white/5",
      ].join(" ")
    }
  >
    <Icon className="h-4 w-4" />
    {label}
  </NavLink>
);

export default function NavShell() {
  return (
    <div className="min-h-screen bg-[#0b0c1a] text-white relative">
      {/* ambient gradient backdrop */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10
                   bg-[radial-gradient(circle_at_20%_-10%,rgba(129,140,248,0.25),transparent_55%),radial-gradient(circle_at_85%_20%,rgba(244,114,182,0.18),transparent_55%),radial-gradient(circle_at_50%_110%,rgba(56,189,248,0.18),transparent_55%)]"
      />
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-[#0b0c1a]/70 border-b border-white/10">
        <div className="mx-auto max-w-[1600px] flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 grid place-items-center shadow-lg shadow-indigo-500/30">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight">
                LLM Playground
              </div>
              <div className="text-[11px] text-white/50 -mt-0.5">
                Test · Compare · Ship
              </div>
            </div>
          </div>

          <nav className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 p-1">
            <NavTab to="/" icon={Sparkles} label="Playground" />
            <NavTab to="/compare" icon={GitCompareArrows} label="Compare" />
          </nav>

          <a
            href="https://github.com/Aryanharitsa/Projects/tree/main/LLM_Playground"
            target="_blank"
            rel="noreferrer"
            className="hidden sm:inline-flex text-xs text-white/60 hover:text-white transition-colors"
          >
            View on GitHub ↗
          </a>
        </div>
      </header>

      <main>
        <Outlet />
      </main>
    </div>
  );
}
