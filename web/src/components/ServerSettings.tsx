"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, apiUrl, DEFAULT_API_URL, setServerUrl } from "@/lib/api";
import { IconServer } from "./icons";
import { Button, Card, inputClass, Spinner } from "./ui";

/** Which ElderLeaf API this device talks to. Lets the Android app point at the deployed API or a laptop on the same Wi-Fi. */
export function ServerSettings({ onSaved }: { onSaved?: () => void }) {
  const [value, setValue] = useState("");
  const [state, setState] = useState<"idle" | "checking" | "ok" | "bad">("idle");
  const [custom, setCustom] = useState(false);

  useEffect(() => {
    setValue(apiUrl());
    setCustom(apiUrl() !== DEFAULT_API_URL);
  }, []);

  async function test(next: string | null) {
    setServerUrl(next);
    setValue(apiUrl());
    setCustom(apiUrl() !== DEFAULT_API_URL);
    setState("checking");
    try {
      await api.health();
      setState("ok");
      onSaved?.();
    } catch {
      setState("bad");
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    test(value);
  }

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2.5">
        <span className="grid h-[30px] w-[30px] place-items-center rounded-full bg-brand-soft text-brand">
          <IconServer size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-ink-2">Server</div>
          <div className="text-xs text-muted">The ElderLeaf API this device talks to</div>
        </div>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          inputMode="url"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          placeholder="https://elderleaf-api.modal.run"
          aria-label="Server address"
          className={`${inputClass} font-mono text-[13px]`}
        />
        <Button type="submit" disabled={state === "checking" || !value.trim()}>
          {state === "checking" && <Spinner />} Save and test
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[13px]">
        <span className={state === "ok" ? "font-semibold text-good" : state === "bad" ? "font-semibold text-bad" : "text-muted"}>
          {state === "ok" && "Connected."}
          {state === "bad" && "No answer from this address."}
          {(state === "idle" || state === "checking") && "Use the https:// address of the deployed API, or http://<laptop-ip>:8000 on the same Wi-Fi."}
        </span>
        {custom && (
          <button type="button" onClick={() => test(null)} className="font-semibold text-brand underline underline-offset-2">
            Back to default
          </button>
        )}
      </div>
    </Card>
  );
}
