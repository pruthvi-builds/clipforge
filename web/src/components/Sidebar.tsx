"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const NAV = [
  { href: "/", label: "Projects", icon: "▤" },
  { href: "/create", label: "Create", icon: "＋" },
  { href: "/settings", label: "Settings", icon: "⚙" },
  { href: "/setup", label: "Setup check", icon: "◈" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [version, setVersion] = useState<string>("");
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = () =>
      api
        .health()
        .then((h) => {
          if (cancelled) return;
          setVersion(h.version);
          setOnline(true);
        })
        .catch(() => {
          if (!cancelled) setOnline(false);
        });
    check();
    // A single check-on-mount could permanently show "API offline" if it
    // happened to race a brief restart; keep rechecking so it self-heals.
    const id = setInterval(check, 8000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] bg-ink-900 px-4 py-6">
      <div className="mb-8 flex items-center gap-2 px-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand-500 text-sm font-bold text-white">
          CF
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight">ClipForge</div>
          <div className="text-[11px] text-ink-100/40">local · free</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV.map((n) => {
          const active =
            n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-white/[0.06] text-white"
                  : "text-ink-100/60 hover:bg-white/[0.03] hover:text-ink-100"
              }`}
            >
              <span className="w-4 text-center opacity-70">{n.icon}</span>
              {n.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto px-2 text-[11px] text-ink-100/35">
        <div className="flex items-center gap-1.5">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              online === null
                ? "bg-ink-600"
                : online
                  ? "bg-accent"
                  : "bg-red-500"
            }`}
          />
          {online === null
            ? "connecting…"
            : online
              ? `API v${version}`
              : "API offline"}
        </div>
        {online === false && (
          <div className="mt-1 leading-snug">
            Start it with <code className="text-ink-100/60">npm run api</code>
          </div>
        )}
      </div>
    </aside>
  );
}
