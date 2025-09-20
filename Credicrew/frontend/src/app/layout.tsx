import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Credicrew',
};

const themeInit = `
try {
  const ls = localStorage.getItem('theme');
  const sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = ls ? ls === 'dark' : sysDark;
  const root = document.documentElement;
  root.classList.toggle('dark', isDark);
  root.setAttribute('data-theme', isDark ? 'dark' : 'light');
} catch {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="min-h-screen bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
        {children}
      </body>
    </html>
  );
}
