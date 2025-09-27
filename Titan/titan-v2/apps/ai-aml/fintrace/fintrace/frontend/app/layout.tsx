// app/layout.tsx
import type { Metadata } from "next"
import "../styles/globals.css"

export const metadata: Metadata = {
  title: "FinTrace",
  description: "AML Intelligence • HackVerse 2025",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  )
}