import "./globals.css";
import type { Metadata } from "next";
import { Sidebar } from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "ClipForge",
  description: "Turn long videos into short-form content — fully local.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-ink-950 text-ink-100 antialiased">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 overflow-x-hidden">
            <div className="mx-auto max-w-6xl px-6 py-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
