export const metadata = { title: "TITAN – KYC + AML" };
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh bg-gray-50 text-gray-900">
        <header className="border-b bg-white">
          <nav className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
            <a href="/" className="font-semibold tracking-tight">TITAN</a>
            <div className="flex items-center gap-4 text-sm">
              <a href="/aml" className="hover:underline">AML Engine</a>
              <a href="http://localhost:8000/docs" target="_blank" className="hover:underline">API Docs</a>
            </div>
          </nav>
        </header>
        <main className="mx-auto max-w-6xl p-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 py-6 text-xs text-gray-500">
          © TITAN • Local demo
        </footer>
      </body>
    </html>
  );
}
