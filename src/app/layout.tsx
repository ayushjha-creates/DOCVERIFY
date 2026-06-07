import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

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
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
