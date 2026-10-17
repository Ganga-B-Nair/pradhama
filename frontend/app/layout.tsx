import "./globals.css";
import type { ReactNode } from "react";
import { SessionProvider } from "@/lib/session";

export const metadata = {
  title: "TRACE",
  description: "AI case-assembly assistant for the station counter",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>{children}</SessionProvider>
        <footer>TRACE · AI case-assembly assistant · the officer files the FIR, not TRACE.</footer>
      </body>
    </html>
  );
}
