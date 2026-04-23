import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SynapseOS — Your thoughts, connected",
  description:
    "A local-first, AI-native Personal Knowledge OS where every note is a synapse. Write, link, and watch your ideas form a living graph.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-void-900 text-ink-100 antialiased">
        {children}
      </body>
    </html>
  );
}
