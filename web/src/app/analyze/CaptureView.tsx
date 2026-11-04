"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { DragEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDate, PlotDetail, today } from "@/lib/api";
import { IconCamera, IconUpload, IconVideo } from "@/components/icons";
import { BackLink, Button, Card, Chip, ErrorBox, inputClass, Notice, PageHead, Segmented, Spinner } from "@/components/ui";

type Mode = "photo" | "video";

export function CaptureView() {
  const params = useSearchParams();
  const plotId = params.get("plot") ?? "";
  const router = useRouter();
  const [plot, setPlot] = useState<PlotDetail | null>(null);
  const [mode, setMode] = useState<Mode>(params.get("mode") === "video" ? "video" : "photo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [date, setDate] = useState(today());
  const [preview, setPreview] = useState<{ blob: Blob; url: string; name: string } | null>(null);
  const [camera, setCamera] = useState(false);

  useEffect(() => {
    if (plotId) api.plot(plotId).then(setPlot, (e) => setError(e.message));
  }, [plotId]);

  const lastPhoto = plot?.analyses.filter((a) => a.mode === "photo" && a.status === "done").at(-1);

  const choose = useCallback((blob: Blob, name: string) => {
    setCamera(false);
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old.url);
      return { blob, url: URL.createObjectURL(blob), name };
    });
  }, []);

  async function send() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const a = await api.upload(plotId, preview.blob, mode, date, preview.name);
      router.push(`/analysis?id=${a.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <BackLink href={`/plot?id=${plotId}`} label={plot?.name ?? "Plot"} />
      <PageHead
        title="New analysis"
        chips={
          plot && (
            <>
              <Chip tone="brand">{plot.crop_label}</Chip>
              {plot.days_after_planting !== null && <Chip>Day {plot.days_after_planting}</Chip>}
            </>
          )
        }
      />
      <div className="mb-6">
        <Segmented
          options={[
            {
              id: "photo",
              label: (
                <>
                  <IconCamera size={15} /> Photo
                </>
              ),
            },
            {
              id: "video",
              label: (
                <>
                  <IconVideo size={15} /> Row video
                </>
              ),
            },
          ]}
          value={mode}
          onChange={(m) => {
            setMode(m as Mode);
            setPreview(null);
            setCamera(false);
          }}
        />
      </div>

      {plot?.is_demo && (
        <div className="mb-4">
          <Notice>Demo plots are read-only. Create your own plot to analyse a photo.</Notice>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          {preview ? (
            <Card className="fade-in p-3">
              <div className="overflow-hidden rounded-xl bg-black">
                {mode === "photo" ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={preview.url} alt="Selected photo" className="max-h-[65vh] w-full object-contain" />
                ) : (
                  <video src={preview.url} className="max-h-[65vh] w-full" controls playsInline muted />
                )}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 p-1">
                <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} className={`${inputClass} w-44`} aria-label="Taken on" />
                <div className="flex-1" />
                <Button variant="secondary" onClick={() => setPreview(null)} disabled={busy}>
                  Retake
                </Button>
                <Button onClick={send} disabled={busy || plot?.is_demo} size="lg">
                  {busy && <Spinner />} {mode === "photo" ? "Analyze photo" : "Count the row"}
                </Button>
              </div>
            </Card>
          ) : camera ? (
            <LiveCamera ghostUrl={lastPhoto?.image_url} onShot={choose} onClose={() => setCamera(false)} />
          ) : (
            <DropZone mode={mode} onPick={choose} onCamera={mode === "photo" ? () => setCamera(true) : undefined} />
          )}
          {error && (
            <div className="mt-4">
              <ErrorBox message={error} />
            </div>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <div className="mb-4 text-[15px] font-bold">{mode === "photo" ? "Tips for a good photo" : "How to film a row"}</div>
            <div className="space-y-3">
              {(mode === "photo"
                ? [
                    ["Same spot", "Shoot from a fixed stake or stone every time."],
                    ["From above", "Phone flat, about 1–1.5 m over the plants."],
                    ["A4 sheet", "Put one in the frame to get sizes in cm²."],
                    ["Soft light", "Avoid harsh sun and your own shadow."],
                  ]
                : [
                    ["Slow walk", "About 15 seconds along one row."],
                    ["Phone low", "5–12 plants in view at a time."],
                    ["One way", "Don’t turn back or zig-zag."],
                    ["Whole row", "Start before the first plant, stop after the last."],
                  ]
              ).map(([t, d], i) => (
                <div key={t} className="flex gap-3">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-soft text-[13px] font-bold text-brand">{i + 1}</span>
                  <div>
                    <div className="text-sm font-semibold">{t}</div>
                    <div className="text-[13px] text-muted">{d}</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
          {mode === "photo" && lastPhoto && (
            <Card className="p-3">
              <div className="relative overflow-hidden rounded-xl">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={lastPhoto.image_url} alt="Last photo of this plot" className="w-full" />
                <span className="absolute left-2 top-2 rounded-full bg-white/90 px-2.5 py-1 text-xs font-bold">Last photo · {fmtDate(lastPhoto.captured_at)}</span>
              </div>
              <p className="px-1 pb-1 pt-2.5 text-[13px] text-muted">Frame the new photo the same way. “Camera with guide” shows this one faintly on top.</p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function DropZone({ mode, onPick, onCamera }: { mode: Mode; onPick: (b: Blob, name: string) => void; onCamera?: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const accept = mode === "photo" ? "image/*" : "video/*";

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.type.startsWith(mode === "photo" ? "image/" : "video/")) onPick(f, f.name);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`flex min-h-[380px] flex-col items-center justify-center rounded-3xl border-2 border-dashed px-6 py-12 text-center transition ${
        over ? "border-brand bg-brand-soft" : "border-[#d5d7dd] bg-card"
      }`}
    >
      <span className="grid h-20 w-20 place-items-center rounded-full bg-gradient-to-br from-brand to-forest text-[#f9ecdb] shadow-lg ring-4 ring-gold/25">
        {mode === "photo" ? <IconCamera size={34} /> : <IconVideo size={34} />}
      </span>
      <p className="mt-5 text-xl font-bold">{mode === "photo" ? "Snap your plot" : "Film one row"}</p>
      <p className="mt-1 text-sm text-muted">{mode === "photo" ? "Take a photo or drop one here (JPG, PNG, HEIC)" : "Record a video or drop one here (MP4, MOV)"}</p>
      <input
        ref={fileRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onPick(f, f.name);
          e.target.value = "";
        }}
      />
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <Button size="lg" onClick={() => fileRef.current?.click()}>
          <IconUpload size={17} /> {mode === "photo" ? "Choose photo" : "Choose video"}
        </Button>
        {onCamera && (
          <Button size="lg" variant="secondary" onClick={onCamera}>
            <IconCamera size={17} /> Camera with guide
          </Button>
        )}
      </div>
    </div>
  );
}

function LiveCamera({ ghostUrl, onShot, onClose }: { ghostUrl?: string; onShot: (b: Blob, name: string) => void; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [camError, setCamError] = useState<string | null>(null);
  const [ghost, setGhost] = useState(true);

  useEffect(() => {
    let active: MediaStream | null = null;
    let cancelled = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCamError("The camera is not available in this browser. Use “Choose photo” instead.");
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((t) => t.stop());
        active = s;
        setStream(s);
      })
      .catch(() => setCamError("Camera permission was not given. Use “Choose photo” instead."));
    return () => {
      cancelled = true;
      active?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    if (videoRef.current && stream) videoRef.current.srcObject = stream;
  }, [stream]);

  function shoot() {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    c.toBlob((b) => b && onShot(b, "plot.jpg"), "image/jpeg", 0.92);
  }

  if (camError)
    return (
      <div className="space-y-3">
        <ErrorBox message={camError} />
        <Button variant="secondary" onClick={onClose}>
          Back
        </Button>
      </div>
    );

  return (
    <div className="relative overflow-hidden rounded-3xl bg-black">
      {stream ? (
        <video ref={videoRef} autoPlay playsInline muted className="w-full" />
      ) : (
        <div className="grid aspect-[4/3] place-items-center text-sm text-white/70">
          <span className="flex items-center gap-2">
            <Spinner /> Opening the camera
          </span>
        </div>
      )}
      {stream && ghostUrl && ghost && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={ghostUrl} alt="" className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-35" />
      )}
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-5 pb-5 pt-12">
        <button onClick={onClose} className="rounded-full bg-white/20 px-4 py-2 text-sm font-semibold text-white backdrop-blur">
          Cancel
        </button>
        <button onClick={shoot} disabled={!stream} aria-label="Take photo" className="grid h-[72px] w-[72px] place-items-center rounded-full border-4 border-white bg-white/25 active:scale-95">
          <span className="h-14 w-14 rounded-full bg-white" />
        </button>
        {ghostUrl ? (
          <button onClick={() => setGhost(!ghost)} className="rounded-full bg-white/20 px-4 py-2 text-sm font-semibold text-white backdrop-blur">
            {ghost ? "Hide guide" : "Show guide"}
          </button>
        ) : (
          <span className="w-[86px]" />
        )}
      </div>
    </div>
  );
}
