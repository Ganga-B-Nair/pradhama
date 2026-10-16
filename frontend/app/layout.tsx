import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "TRACE",
  description: "AI case-assembly assistant for the station counter",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900">{children}</body>
    </html>
  );
}
