import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SynapseOS — your second brain, as an OS",
  description:
    "Notes auto-link via embedding-based synapses. Traverse, query, and grow your personal knowledge graph.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="grain antialiased">
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
