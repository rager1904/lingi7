import type { Metadata } from "next";
import "./globals.css";

const criticalThemeCss = `
  :root { --color-accent:#1769ff; --color-border-base:rgba(134,164,224,.20); --color-surface-base:#071126; --color-surface-raised:rgba(11,24,53,.84); --color-surface-sunken:rgba(4,13,32,.74); --background-color-surface-base:#030a1a; --background-color-surface-sunken:#050f25; --background-color-surface-overlay:#0c1a38; --border-color-base:rgba(134,164,224,.20); --text-color-primary:#f8fbff; --text-color-secondary:#b6c3df; --text-color-subtle:#8091b4; }
  html, body { background:#030a1a !important; color:#f8fbff !important; }
  .text-primary { color:#f8fbff !important; } .text-secondary { color:#b6c3df !important; } .text-subtle { color:#8091b4 !important; }
  .app-shell { min-height:100vh; background:radial-gradient(950px 480px at 80% -8%,rgba(22,105,255,.27),transparent 62%),radial-gradient(700px 520px at -5% 42%,rgba(11,61,173,.20),transparent 66%),#030a1a !important; }
  .app-bar { background:rgba(2,7,20,.82) !important; border-bottom:1px solid rgba(129,163,228,.16) !important; color:#f8fbff !important; }
  .brand-lockup { color:#f8fbff !important; } .brand-lockup span { color:#5d96ff !important; }
  .studio-intro { background:linear-gradient(100deg,rgba(7,22,52,.92),rgba(8,28,67,.70)) !important; border-color:rgba(121,164,255,.17) !important; }
  .studio-intro h1 { color:#f8fbff !important; } .studio-intro p { color:#71a2ff !important; } .studio-intro span { color:#aab9d7 !important; }
  button { color:#f8fbff; } input, textarea, select { color:#f8fbff !important; }
`;

export const metadata: Metadata = {
  title: "Catalog Enrichment",
  description: "AI-powered product catalog enrichment system",
  icons: {
    icon: [
      { url: '/logo.png', sizes: '32x32', type: 'image/png' },
      { url: '/logo.png', sizes: '16x16', type: 'image/png' },
    ],
    shortcut: '/logo.png',
    apple: '/logo.png',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" style={{ backgroundColor: '#0c0c0c' }}>
      <head>
        <style dangerouslySetInnerHTML={{ __html: criticalThemeCss }} />
        <script 
          type="module" 
          src="https://ajax.googleapis.com/ajax/libs/model-viewer/3.5.0/model-viewer.min.js"
        ></script>
      </head>
      <body className="text-primary min-h-screen" style={{ backgroundColor: 'var(--background-color-surface-base)' }}>
        {children}
      </body>
    </html>
  );
}





