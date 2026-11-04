"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, EXPERIENCE, Experience } from "@/lib/api";
import { markWelcomed, PLOTS_CHANGED } from "@/components/AppShell";
import { IconClose, IconEye, IconEyeOff, IconSprout } from "@/components/icons";
import { Button, ErrorBox, Field, inputClass, Segmented, Spinner } from "@/components/ui";

type Mode = "signin" | "signup";

/** Full-screen sign-in. On the very first launch (?welcome=1) it doubles as the welcome screen. */
export function LoginView() {
  const params = useSearchParams();
  const router = useRouter();
  const welcome = params.get("welcome") === "1";
  const [mode, setMode] = useState<Mode>(params.get("mode") === "signin" ? "signin" : params.get("mode") === "signup" || welcome ? "signup" : "signin");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [experience, setExperience] = useState<Experience>("just_started");
  const next = params.get("next");

  function done() {
    markWelcomed();
    window.dispatchEvent(new Event(PLOTS_CHANGED));
    router.replace(next && next.startsWith("/") ? next : "/");
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const email = String(f.get("email") ?? "");
    const password = String(f.get("password") ?? "");
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") {
        await api.signUp({ email, password, name: String(f.get("name") ?? ""), garden: String(f.get("garden") ?? "") || null, experience });
      } else {
        await api.logIn(email, password);
      }
      done();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-canvas pb-[calc(env(safe-area-inset-bottom)+2rem)] pt-[env(safe-area-inset-top)]">
      <div className="mx-auto max-w-lg px-4 sm:pt-8">
        <section className="forest-panel relative -mx-4 overflow-hidden px-6 pb-8 sm:mx-0 sm:rounded-[32px]">
          <div className="leaf-veins pointer-events-none absolute inset-0" />
          <div aria-hidden="true" className="method-band relative -mx-6 -mb-6 !h-[210px]" />
          {welcome ? (
            <button type="button" onClick={done} className="glass absolute right-4 top-4 rounded-full px-4 py-2 text-sm font-semibold">
              Skip
            </button>
          ) : (
            <button
              type="button"
              onClick={() => (window.history.length > 1 ? router.back() : router.replace("/"))}
              aria-label="Close"
              className="glass absolute right-4 top-4 grid h-10 w-10 place-items-center rounded-full"
            >
              <IconClose size={18} />
            </button>
          )}
          <div className="relative">
            {welcome ? (
              <>
                <div className="flex items-center gap-2.5">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/logo.png" alt="" width={36} height={36} className="h-9 w-9 rounded-[10px] ring-1 ring-white/15" />
                  <span className="font-display text-[19px] font-semibold">ElderLeaf</span>
                </div>
                <h1 className="font-display mt-4 text-[34px] font-semibold leading-[1.08]">An old hand for every new grower</h1>
                <p className="mt-2 text-[15px] leading-relaxed text-[#f6efe2]/80">Count your plants from one photo, follow your plot week by week, and know what is normal.</p>
              </>
            ) : (
              <>
                <h1 className="font-display text-[34px] font-semibold leading-tight">{mode === "signin" ? "Welcome back" : "Join ElderLeaf"}</h1>
                <p className="mt-1.5 text-[15px] text-[#f6efe2]/80">
                  {mode === "signin" ? "Sign in to see your plots on any device." : "Keep your plots safe and open them on any phone or laptop."}
                </p>
              </>
            )}
          </div>
        </section>

        <div className="relative -mt-4 rounded-[26px] bg-card p-5 shadow-[var(--shadow-lift)] sm:mt-5">
          <div className="mb-5 flex justify-center">
            <Segmented
              options={[
                { id: "signup", label: "Create account" },
                { id: "signin", label: "Sign in" },
              ]}
              value={mode}
              onChange={(m) => {
                setMode(m as Mode);
                setError(null);
              }}
            />
          </div>

          <form onSubmit={submit} className="space-y-4">
            {mode === "signup" && (
              <Field label="Your name">
                <input name="name" required maxLength={80} autoComplete="name" placeholder="Ayşe" className={inputClass} />
              </Field>
            )}
            <Field label="E-mail">
              <input name="email" type="email" required autoComplete="email" inputMode="email" autoCapitalize="off" placeholder="you@example.com" className={inputClass} />
            </Field>
            <Field label="Password" hint={mode === "signup" ? "At least 8 characters." : undefined}>
              <span className="relative block">
                <input
                  name="password"
                  type={showPassword ? "text" : "password"}
                  required
                  minLength={mode === "signup" ? 8 : undefined}
                  maxLength={128}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  className={`${inputClass} pr-12`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-1.5 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full text-muted hover:bg-black/5"
                >
                  {showPassword ? <IconEyeOff size={17} /> : <IconEye size={17} />}
                </button>
              </span>
            </Field>

            {mode === "signup" && (
              <>
                <Field label="Garden or community" hint="Optional, e.g. the community garden you grow in.">
                  <input name="garden" maxLength={120} placeholder="METU Bostan" className={inputClass} />
                </Field>
                <div>
                  <span className="mb-1.5 block text-[13px] font-semibold text-ink-2">How long have you been growing?</span>
                  <div className="grid gap-2 sm:grid-cols-3">
                    {EXPERIENCE.map((x) => (
                      <button
                        key={x.id}
                        type="button"
                        onClick={() => setExperience(x.id)}
                        aria-pressed={experience === x.id}
                        className={`rounded-2xl px-3 py-2.5 text-left transition ${experience === x.id ? "bg-brand text-white shadow-sm" : "bg-well text-ink-2 hover:bg-[#ebe7de]"}`}
                      >
                        <span className="block text-sm font-semibold">{x.label}</span>
                        <span className={`block text-xs ${experience === x.id ? "text-white/75" : "text-muted"}`}>{x.hint}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}

            {error && <ErrorBox message={error} />}
            <Button type="submit" size="lg" disabled={busy} className="w-full">
              {busy && <Spinner />} {mode === "signin" ? "Sign in" : "Create account"}
            </Button>
            <p className="text-center text-xs text-muted">Plots you made on this device as a guest move into your account.</p>
          </form>
        </div>

        <div className="mt-5 text-center">
          <Button variant="secondary" size="lg" onClick={done} className="w-full">
            <IconSprout size={17} /> Explore without an account
          </Button>
          <p className="mt-2 text-xs text-muted">The demo garden is open to everyone. You can sign up later in Settings.</p>
        </div>
        {!welcome && (
          <p className="mt-6 text-center text-xs text-muted">
            <Link href="/guide" className="font-semibold text-brand">
              New to growing? Read the guide
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
