"use client";

import { useEffect, useState } from "react";
import { AnalysisOut, AnalysisResult, fmtDate, PlotDetail } from "@/lib/api";
import { makeShareCard, shareCard } from "@/lib/shareCard";
import { IconClose, IconShare } from "./icons";
import { Button, ErrorBox, Spinner } from "./ui";

/** "Share result": draws a card with the photo, its masks and the numbers, previews it, then opens the share sheet. */
export function ShareResult({ a, r, plot }: { a: AnalysisOut; r: AnalysisResult; plot: PlotDetail | null }) {
  const [busy, setBusy] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [card, setCard] = useState<{ blob: Blob; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const plants = Math.round(r.metrics.plant_count.value ?? 0);
  const crop = (plot?.crop_label ?? "").toLowerCase();
  const subtitle = [plot?.crop_label, r.days_after_planting !== null ? `day ${r.days_after_planting}` : null, fmtDate(a.captured_at)].filter(Boolean).join(" · ");
  const text = `${plants} ${crop ? `${crop} ` : ""}plants counted from one photo with ElderLeaf. Every plant outlined by SAM 3.1.`;

  useEffect(
    () => () => {
      if (card) URL.revokeObjectURL(card.url);
    },
    [card],
  );

  async function open() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const blob = await makeShareCard({ imageUrl: a.image_url, r, title: plot?.name ?? "My plot", subtitle });
      setCard({ blob, url: URL.createObjectURL(blob) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function share() {
    if (!card) return;
    setSharing(true);
    setError(null);
    try {
      const result = await shareCard(card.blob, `elderleaf-${a.id}.png`, text);
      if (result === "downloaded") setNote("Saved to your downloads. Post it anywhere.");
      if (result === "shared") setCard(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSharing(false);
    }
  }

  return (
    <>
      <Button variant="gold" onClick={open} disabled={busy}>
        {busy ? <Spinner /> : <IconShare size={16} />} Share result
      </Button>
      {error && !card && (
        <div className="mt-3">
          <ErrorBox message={error} />
        </div>
      )}
      {card && (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-label="Share your result">
          <button aria-label="Close" className="fade absolute inset-0 bg-[#0c1511]/60 backdrop-blur-[2px]" onClick={() => setCard(null)} />
          <div className="sheet-up relative w-full max-w-md rounded-t-[28px] bg-card px-5 pb-[calc(env(safe-area-inset-bottom)+1.25rem)] pt-4 shadow-2xl sm:rounded-[28px] sm:pb-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="font-display text-[22px] font-semibold">Share your result</div>
              <button onClick={() => setCard(null)} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-full bg-well text-ink-2">
                <IconClose size={17} />
              </button>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={card.url} alt="Your result card" className="mx-auto max-h-[56vh] rounded-2xl shadow-[var(--shadow-lift)]" />
            {error && (
              <div className="mt-3">
                <ErrorBox message={error} />
              </div>
            )}
            {note && <p className="mt-3 text-center text-sm font-semibold text-good">{note}</p>}
            <Button size="lg" onClick={share} disabled={sharing} className="mt-4 w-full">
              {sharing ? <Spinner /> : <IconShare size={17} />} Share
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
