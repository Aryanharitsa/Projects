import "./globals.css";
import type { ReactNode } from "react";
import Logo from "../components/Logo";
import StatusPill from "../components/StatusPill";

export const metadata = {
  title: "TITAN — Trusted Identity & Transaction Authentication",
  description:
    "KYC + on-chain attestation + explainable AML risk scoring, in one pipeline.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/aml", label: "AML Console" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/kyc", label: "KYC Pipeline" },
  { href: "/attestations", label: "Attestations" },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://rsms.me/" />
        <link rel="stylesheet" href="https://rsms.me/inter/inter.css" />
      </head>
      <body className="relative">
        <div className="relative z-10 mx-auto flex min-h-dvh max-w-7xl flex-col px-5 py-5 md:px-8">
          <header className="glass-strong flex flex-col items-stretch gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between">
            <a href="/" className="flex items-center gap-3">
              <Logo />
              <span className="hidden text-[11px] uppercase tracking-[0.22em] text-white/40 sm:inline">
                identity · attestation · risk
              </span>
            </a>
            <nav className="flex items-center gap-1">
              {NAV.map((n) => (
                <a
                  key={n.href}
                  href={n.href}
                  className="rounded-lg px-3 py-1.5 text-[13px] text-white/70 hover:bg-white/[0.05] hover:text-white"
                >
                  {n.label}
                </a>
              ))}
              <span className="ml-2 hidden md:inline">
                <StatusPill />
              </span>
            </nav>
          </header>

          <main className="mt-6 flex-1">{children}</main>

          <footer className="mt-10 flex items-center justify-between border-t border-white/5 pt-4 text-[11px] text-white/40">
            <span>© TITAN — local demo · v2</span>
            <span className="font-mono">deterministic · explainable · on-chain</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
