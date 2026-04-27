import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Credicrew — explainable talent discovery',
  description:
    'Save a job description, get an explainable shortlist, run the hiring pipeline end-to-end.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" data-theme="dark">
      <body className="min-h-screen bg-neutral-950 text-neutral-100 antialiased">
        {children}
      </body>
    </html>
  );
}
