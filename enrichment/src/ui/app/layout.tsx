import type { Metadata } from "next";
import "./globals.css";

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






