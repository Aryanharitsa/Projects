// src/app/layout.tsx
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Credicrew",
  description: "Talent intelligence, simplified.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased bg-white text-neutral-900">{children}</body>
    </html>
  );
}
