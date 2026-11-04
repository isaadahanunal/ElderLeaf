"use client";

import { ReactNode, useEffect, useRef } from "react";
import { BACK_EVENT } from "@/lib/events";
import { IconClose } from "./icons";

/** A panel that slides up from the bottom on phones (a centered dialog on wider screens). */
export function Sheet({ open, onClose, title, subtitle, children }: { open: boolean; onClose: () => void; title: string; subtitle?: string; children: ReactNode }) {
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && close.current();
    const back = (e: Event) => {
      e.preventDefault(); // the Android back button closes the sheet instead of leaving the page
      close.current();
    };
    document.addEventListener("keydown", esc);
    window.addEventListener(BACK_EVENT, back);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", esc);
      window.removeEventListener(BACK_EVENT, back);
      document.body.style.overflow = overflow;
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-label={title}>
      <button aria-label="Close" className="fade absolute inset-0 bg-[#0c1511]/45 backdrop-blur-[2px]" onClick={() => close.current()} />
      <div className="sheet-up relative flex max-h-[92vh] w-full max-w-lg flex-col rounded-t-[28px] bg-card shadow-2xl sm:max-h-[88vh] sm:rounded-[28px]">
        <div className="shrink-0 px-5 pt-3">
          <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-line sm:hidden" />
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-display text-[24px] font-semibold leading-tight">{title}</div>
              {subtitle && <div className="mt-0.5 text-[13px] text-muted">{subtitle}</div>}
            </div>
            <button onClick={() => close.current()} aria-label="Close" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-well text-ink-2">
              <IconClose size={17} />
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-[calc(env(safe-area-inset-bottom)+1.25rem)] pt-4 sm:pb-5">{children}</div>
      </div>
    </div>
  );
}
