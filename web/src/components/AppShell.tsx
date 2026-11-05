"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ReactNode, Suspense, useEffect, useState } from "react";
import { api, AUTH_CHANGED, authToken, isNativeApp, Plot } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";
import { IconBook, IconCamera, IconChevronRight, IconClose, IconGrid, IconHome, IconPlus, IconSettings, IconSprout, IconSun, IconUser } from "./icons";
import { Avatar } from "./ui";

import { NewPlotForm } from "@/app/new/NewPlotView";
import { BACK_EVENT as BACK, OPEN_CAPTURE, OPEN_NEW_PLOT, PLOTS_CHANGED } from "@/lib/events";
import { Sheet } from "./Sheet";

export { PLOTS_CHANGED };

/** Opens the "which plot?" sheet (bottom tab camera button, home hero, guide). */
export function openCaptureSheet() {
  window.dispatchEvent(new CustomEvent(OPEN_CAPTURE));
}

/** Opens the "New plot" sheet from anywhere. */
export function openNewPlotSheet() {
  window.dispatchEvent(new Event(OPEN_NEW_PLOT));
}

// The first time the app opens it greets you with the sign-in screen; after you sign in, sign up or
// choose to explore without an account, it opens straight to your plots.
const WELCOMED = "elderleaf-welcomed";

/** After signing out, the app greets you with the sign-in screen again. */
export function forgetWelcome() {
  try {
    localStorage.removeItem(WELCOMED);
  } catch {}
}

export function markWelcomed() {
  try {
    localStorage.setItem(WELCOMED, "1");
  } catch {}
}

function FirstRunGate() {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let welcomed = true;
    try {
      welcomed = Boolean(localStorage.getItem(WELCOMED) || authToken());
    } catch {}
    if (!welcomed && pathname !== "/login") {
      router.replace("/login?welcome=1");
      return;
    }
    setReady(true);
  }, [pathname, router]);
  if (ready) return null;
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-forest" aria-hidden="true">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="" width={84} height={84} className="breathe h-[84px] w-[84px] rounded-[24px]" />
    </div>
  );
}

function Logo({ dark = false }: { dark?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="" width={40} height={40} className={`h-10 w-10 rounded-[11px] ${dark ? "ring-1 ring-white/15" : "shadow-sm"}`} />
      <span className="leading-tight">
        <span className={`font-display block text-[19px] font-semibold ${dark ? "text-[#f6efe2]" : ""}`}>ElderLeaf</span>
        <span className={`block text-[11px] ${dark ? "text-[#f6efe2]/60" : "text-muted"}`}>An old hand for new growers</span>
      </span>
    </Link>
  );
}


type CapApp = {
  addListener: (event: "backButton", cb: (e: { canGoBack: boolean }) => void) => Promise<{ remove: () => void }>;
  minimizeApp?: () => Promise<void>;
  exitApp: () => Promise<void>;
};

export function AppShell({ children }: { children: ReactNode }) {
  useEffect(() => {
    // offline shell for the installed web app; the Android app ships its files inside the APK
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator && !isNativeApp()) {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    // Android back button: close an open sheet first, then go back, and on the first screen leave the app
    if (!isNativeApp()) return;
    const app = (window as unknown as { Capacitor?: { Plugins?: { App?: CapApp } } }).Capacitor?.Plugins?.App;
    if (!app) return;
    const handle = app.addListener("backButton", ({ canGoBack }) => {
      if (!window.dispatchEvent(new Event(BACK, { cancelable: true }))) return;
      if (canGoBack) window.history.back();
      else if (app.minimizeApp) app.minimizeApp();
      else app.exitApp();
    });
    return () => {
      handle.then((h) => h.remove());
    };
  }, []);

  // the sign-in screen is full screen, without the header, tabs or sidebar
  const bare = usePathname() === "/login";

  return (
    <AuthProvider>
    <FirstRunGate />
    {bare ? (
      <main className="min-h-screen">{children}</main>
    ) : (
    <div className="min-h-screen lg:flex">
      <aside className="forest-panel sticky top-0 hidden h-screen w-[280px] shrink-0 flex-col overflow-hidden lg:flex">
        <div className="leaf-veins pointer-events-none absolute inset-0" />
        <div className="relative flex min-h-0 flex-1 flex-col px-4 py-6">
          <div className="px-2">
            <Logo dark />
          </div>
          <Suspense>
            <SideNav />
          </Suspense>
        </div>
      </aside>

      {/* phone / tablet top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line/70 bg-canvas/85 px-4 pb-2.5 pt-[calc(env(safe-area-inset-top)+0.625rem)] backdrop-blur-xl lg:hidden">
        <Logo />
        <ProfileButton />
      </header>

      <main className="min-w-0 flex-1 px-4 pb-[calc(env(safe-area-inset-bottom)+7rem)] pt-5 sm:px-6 lg:px-10 lg:pb-16 lg:pt-9">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>

      <Suspense>
        <TabBar />
      </Suspense>
      <CaptureSheet />
      <NewPlotSheet />
    </div>
    )}
    </AuthProvider>
  );
}

/** Phone header: the grower's initials (or a person icon for a guest), opens the profile. */
function ProfileButton() {
  const { me, status } = useAuth();
  return (
    <Link href="/settings" aria-label={me ? `Settings: ${me.name}` : "Sign in or create an account"} className="rounded-full active:scale-95">
      {me ? (
        <Avatar name={me.name} size={40} />
      ) : (
        <span className={`grid h-10 w-10 place-items-center rounded-full bg-card text-ink shadow-[var(--shadow-card)] ${status === "loading" ? "opacity-0" : ""}`}>
          <IconUser size={19} />
        </span>
      )}
    </Link>
  );
}

// ------------------------------------------------------------------ phone: bottom tabs

function TabBar() {
  const pathname = usePathname();
  const tab = (href: string, label: string, icon: ReactNode, active: boolean) => (
    <Link href={href} className={`flex flex-1 flex-col items-center gap-1 py-1 text-[11px] font-semibold transition ${active ? "text-brand" : "text-muted"}`}>
      {icon}
      {label}
    </Link>
  );
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 lg:hidden" aria-label="Main">
      <div className="mx-auto max-w-md px-4 pb-[calc(env(safe-area-inset-bottom)+0.75rem)]">
        <div className="relative flex items-center rounded-[26px] border border-white/60 bg-white/85 px-1.5 py-2 shadow-[0_12px_32px_-12px_rgba(21,37,30,0.35)] backdrop-blur-xl">
          {tab("/", "Plots", <IconHome size={22} />, ["/", "/plot", "/analysis", "/analyze", "/new"].includes(pathname))}
          {tab("/guide", "Guide", <IconBook size={22} />, pathname === "/guide")}
          <div className="flex flex-1 justify-center">
            <button
              type="button"
              onClick={() => openCaptureSheet()}
              aria-label="Analyze a plot"
              className="-mt-9 grid h-[62px] w-[62px] place-items-center rounded-full bg-gradient-to-br from-brand to-forest text-[#f6efe2] shadow-[var(--shadow-lift)] ring-4 ring-canvas transition active:scale-95"
            >
              <IconCamera size={26} />
            </button>
          </div>
          {tab("/today", "Today", <IconSun size={22} />, pathname === "/today")}
          {tab("/settings", "Settings", <IconSettings size={22} />, ["/settings", "/profile", "/method"].includes(pathname))}
        </div>
      </div>
    </nav>
  );
}

// ------------------------------------------------------------------ "which plot?" sheet

function CaptureSheet() {
  const [open, setOpen] = useState(false);
  const [plots, setPlots] = useState<Plot[] | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    const show = (e: Event) => {
      setOpen(true);
      api.plots().then(
        (all) => setPlots(all.filter((p) => !p.is_demo)),
        () => setPlots([]),
      );
    };
    window.addEventListener(OPEN_CAPTURE, show);
    return () => window.removeEventListener(OPEN_CAPTURE, show);
  }, []);
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const back = (e: Event) => {
      e.preventDefault(); // the Android back button closes the sheet instead of leaving the page
      setOpen(false);
    };
    window.addEventListener(BACK, back);
    return () => window.removeEventListener(BACK, back);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-label="Analyze a plot">
      <button aria-label="Close" className="fade absolute inset-0 bg-[#0c1511]/45 backdrop-blur-[2px]" onClick={() => setOpen(false)} />
      <div className="sheet-up relative w-full max-w-md rounded-t-[28px] bg-card px-5 pb-[calc(env(safe-area-inset-bottom)+1.25rem)] pt-3 shadow-2xl sm:rounded-[28px] sm:pb-5">
        <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-line sm:hidden" />
        <div className="flex items-center justify-between">
          <div>
            <div className="font-display text-[22px] font-semibold">Which plot?</div>
            <div className="text-[13px] text-muted">Pick the plot you are standing at.</div>
          </div>
          <button onClick={() => setOpen(false)} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-full bg-well text-ink-2">
            <IconClose size={17} />
          </button>
        </div>

        <div className="mt-4 max-h-[50vh] space-y-2 overflow-y-auto">
          {plots === null && <div className="h-16 animate-pulse rounded-2xl bg-well" />}
          {plots?.length === 0 && (
            <div className="rounded-2xl bg-well px-4 py-5 text-center text-sm text-muted">
              <IconSprout size={22} className="mx-auto mb-2 text-brand" />
              No plots yet. Create one first: it takes 20 seconds.
            </div>
          )}
          {plots?.map((p) => (
            <Link key={p.id} href={`/analyze?plot=${p.id}`} className="flex items-center gap-3 rounded-2xl bg-well p-2.5 pr-3.5 transition hover:bg-[#ece9e1] active:scale-[0.99]">
              <span className="h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-line">
                {p.latest && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.latest.image_url} alt="" className="h-full w-full object-cover" />
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-semibold">{p.name}</span>
                <span className="block text-xs text-muted">
                  {p.crop_label}
                  {p.days_after_planting !== null && ` · day ${p.days_after_planting}`}
                </span>
              </span>
              <IconChevronRight size={16} className="text-muted" />
            </Link>
          ))}
        </div>

        <button
          type="button"
          onClick={() => {
            setOpen(false);
            openNewPlotSheet();
          }}
          className="mt-4 flex h-12 w-full items-center justify-center gap-2 rounded-full bg-brand text-[15px] font-semibold text-white active:scale-[0.99]"
        >
          <IconPlus size={17} strokeWidth={2.4} /> New plot
        </button>
      </div>
    </div>
  );
}

function NewPlotSheet() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener(OPEN_NEW_PLOT, show);
    return () => window.removeEventListener(OPEN_NEW_PLOT, show);
  }, []);
  return (
    <Sheet open={open} onClose={() => setOpen(false)} title="New plot" subtitle="A bed, a row or a whole garden">
      {open && <NewPlotForm bare onCancel={() => setOpen(false)} onDone={() => setOpen(false)} />}
    </Sheet>
  );
}

// ------------------------------------------------------------------ desktop sidebar

function SideNav() {
  const pathname = usePathname();
  const params = useSearchParams();
  const [plots, setPlots] = useState<Plot[] | null>(null);
  const activePlot = pathname === "/plot" ? params.get("id") : pathname === "/analyze" ? params.get("plot") : null;

  useEffect(() => {
    const load = () => api.plots().then(setPlots, () => setPlots([]));
    load();
    window.addEventListener(PLOTS_CHANGED, load);
    window.addEventListener(AUTH_CHANGED, load);
    return () => {
      window.removeEventListener(PLOTS_CHANGED, load);
      window.removeEventListener(AUTH_CHANGED, load);
    };
  }, [pathname]);

  const item = (href: string, label: string, icon: ReactNode, active: boolean) => (
    <Link
      href={href}
      className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-semibold transition ${active ? "bg-white/12 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]" : "text-[#f6efe2]/75 hover:bg-white/6 hover:text-white"}`}
    >
      {icon}
      {label}
    </Link>
  );

  const mine = plots?.filter((p) => !p.is_demo) ?? [];
  const demo = plots?.filter((p) => p.is_demo) ?? [];
  return (
    <>
      <button
        type="button"
        onClick={() => openCaptureSheet()}
        className="mt-7 flex h-11 items-center justify-center gap-2 rounded-full bg-gold text-[14px] font-semibold text-forest shadow-lg transition hover:brightness-105 active:scale-[0.99]"
      >
        <IconCamera size={17} /> Analyze a plot
      </button>
      <nav className="mt-5 space-y-1">
        {item("/", "All plots", <IconGrid size={18} />, pathname === "/")}
        {item("/today", "Today", <IconSun size={18} />, pathname === "/today")}
        {item("/guide", "Guide", <IconBook size={18} />, pathname === "/guide")}
        {item("/new", "New plot", <IconPlus size={18} />, pathname === "/new")}
        {item("/settings", "Settings", <IconSettings size={18} />, ["/settings", "/profile", "/method"].includes(pathname))}
      </nav>
      <div className="mt-7 min-h-0 flex-1 space-y-5 overflow-y-auto pr-1">
        <PlotGroup title="My plots" plots={mine} active={activePlot} empty={plots ? "No plots yet" : "Loading…"} />
        {demo.length > 0 && <PlotGroup title="Demo plots" plots={demo} active={activePlot} />}
      </div>
      <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 px-3.5 py-3 text-[12px] leading-snug text-[#f6efe2]/70">
        Masks by <b className="text-[#f6efe2]">SAM 3.1</b>, words by <b className="text-[#f6efe2]">Muse Spark Open</b>, numbers by plain code.
      </div>
      <UserCard active={false} />
    </>
  );
}

function UserCard({ active }: { active: boolean }) {
  const { me, status } = useAuth();
  if (status === "loading") return <div className="mt-3 h-[58px]" />;
  return (
    <Link
      href="/settings"
      className={`mt-3 flex items-center gap-3 rounded-2xl px-2.5 py-2.5 transition ${active ? "bg-white/12" : "hover:bg-white/6"}`}
    >
      {me ? (
        <Avatar name={me.name} size={38} />
      ) : (
        <span className="grid h-[38px] w-[38px] place-items-center rounded-full bg-white/10 text-[#f6efe2]">
          <IconUser size={18} />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-semibold text-[#f6efe2]">{me ? me.name : "Guest"}</span>
        <span className="block truncate text-xs text-[#f6efe2]/55">{me ? (me.garden ?? me.email) : "Sign in to keep your plots"}</span>
      </span>
      <IconChevronRight size={15} className="text-[#f6efe2]/40" />
    </Link>
  );
}

function PlotGroup({ title, plots, active, empty }: { title: string; plots: Plot[]; active: string | null; empty?: string }) {
  return (
    <div>
      <div className="mb-1.5 px-3 text-[11px] font-bold uppercase tracking-wider text-[#f6efe2]/45">{title}</div>
      {plots.length === 0 && empty && <div className="px-3 py-1 text-[13px] text-[#f6efe2]/55">{empty}</div>}
      <ul className="space-y-0.5">
        {plots.map((p) => (
          <li key={p.id}>
            <Link href={`/plot?id=${p.id}`} className={`flex items-center gap-3 rounded-xl px-2 py-2 transition ${active === p.id ? "bg-white/12" : "hover:bg-white/6"}`}>
              <span className="h-9 w-9 shrink-0 overflow-hidden rounded-lg bg-white/10">
                {p.latest && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.latest.image_url} alt="" className="h-full w-full object-cover" />
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px] font-semibold text-[#f6efe2]">{p.name}</span>
                <span className="block truncate text-xs text-[#f6efe2]/55">
                  {p.crop_label}
                  {p.days_after_planting !== null && ` · day ${p.days_after_planting}`}
                </span>
              </span>
              {p.attention.length > 0 && <span className="h-2 w-2 shrink-0 rounded-full bg-gold" title={p.attention.join(", ")} />}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
