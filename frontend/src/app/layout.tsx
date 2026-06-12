import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DOCVERIFY AI - Document Authenticity Verifier",
  description: "Verify document authenticity with AI-powered forensic analysis. Upload certificates, receipts, invoices and detect tampering.",
  icons: {
    icon: [{ url: "/favicon.ico", type: "image/x-icon" }, { url: "/favicon.png", type: "image/png" }],
    apple: "/logo.jpeg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <head>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
        <script src="https://cdn.tailwindcss.com" />
      </head>
      <body className="min-h-full flex flex-col" style={{ fontFamily: "'Inter', sans-serif", background: "#000", color: "#fff" }}>{children}</body>
    </html>
  );
}
