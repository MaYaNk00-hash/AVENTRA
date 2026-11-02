import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "AVENTRA | Enterprise AI Trust & Orchestration Platform",
  description: "Autonomous Agent Workflows, Human-in-the-Loop Governance & Modular ML Intelligence",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#090B10] text-[#E6EDF3] selection:bg-[#1F6FEB]/30 selection:text-[#58A6FF] min-h-screen`}
      >
        {children}
      </body>
    </html>
  );
}
