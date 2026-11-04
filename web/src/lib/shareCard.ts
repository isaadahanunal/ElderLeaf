// A 4:5 result card (photo + SAM masks + the numbers + brand) to post on X, Instagram or WhatsApp.
import { AnalysisResult, CLASS_COLORS, fmt, isNativeApp } from "./api";

const W = 1080;
const H = 1350;
const PHOTO_H = 860;
const CREAM = "#f6efe2";
const GOLD = "#c39f64";

function family(cssVar: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim();
  return v ? `${v}, ${fallback}` : fallback;
}

function loadImage(src: string, cors: boolean): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    if (cors) img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Could not load the photo for the card."));
    img.src = src;
  });
}

function hexToRgba(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

export async function makeShareCard({ imageUrl, r, title, subtitle }: { imageUrl: string; r: AnalysisResult; title: string; subtitle: string }): Promise<Blob> {
  const serif = family("--font-serif", "Georgia, serif");
  const sans = family("--font-geist-sans", "system-ui, sans-serif");
  await Promise.all([document.fonts.load(`600 160px ${serif}`), document.fonts.load(`600 40px ${sans}`)]).catch(() => undefined);
  // a separate URL so the browser fetches the photo with CORS headers instead of reusing the cached <img> copy
  const sep = imageUrl.includes("?") ? "&" : "?";
  const [photo, logo] = await Promise.all([loadImage(`${imageUrl}${sep}card=1`, true), loadImage("/logo.png", false)]);

  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#15251e";
  ctx.fillRect(0, 0, W, H);

  // photo, cover-cropped, with the masks on top
  const iw = r.image.width;
  const ih = r.image.height;
  const s = Math.max(W / iw, PHOTO_H / ih);
  const ox = (W - iw * s) / 2;
  const oy = (PHOTO_H - ih * s) / 2;
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, W, PHOTO_H);
  ctx.clip();
  ctx.drawImage(photo, ox, oy, iw * s, ih * s);
  for (const m of r.masks) {
    if (m.class !== "crop" && m.class !== "weed") continue;
    const color = CLASS_COLORS[m.class];
    const path = new Path2D();
    for (const poly of m.polygons) {
      poly.forEach(([x, y], i) => (i === 0 ? path.moveTo(ox + x * s, oy + y * s) : path.lineTo(ox + x * s, oy + y * s)));
      path.closePath();
    }
    ctx.fillStyle = hexToRgba(color, 0.32);
    ctx.fill(path, "evenodd");
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.stroke(path);
  }
  const fade = ctx.createLinearGradient(0, PHOTO_H - 260, 0, PHOTO_H);
  fade.addColorStop(0, "rgba(21,37,30,0)");
  fade.addColorStop(1, "rgba(21,37,30,1)");
  ctx.fillStyle = fade;
  ctx.fillRect(0, PHOTO_H - 260, W, 260);
  ctx.restore();

  // the numbers
  const plants = r.metrics.plant_count.value ?? 0;
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = CREAM;
  ctx.font = `600 190px ${serif}`;
  const big = String(Math.round(plants));
  ctx.fillText(big, 72, PHOTO_H + 120);
  const bigW = ctx.measureText(big).width;
  ctx.fillStyle = GOLD;
  ctx.font = `600 44px ${sans}`;
  ctx.fillText("plants counted", 72 + bigW + 26, PHOTO_H + 62);
  ctx.fillStyle = hexToRgba(CREAM, 0.8);
  ctx.font = `500 36px ${sans}`;
  const cover = r.metrics.canopy_cover_pct.value;
  const weeds = r.metrics.weed_share_pct.value;
  ctx.fillText(`${fmt(cover)}% crop cover · ${fmt(weeds)}% weeds`, 72 + bigW + 26, PHOTO_H + 116);

  ctx.fillStyle = CREAM;
  ctx.font = `600 46px ${serif}`;
  ctx.fillText(title.length > 34 ? `${title.slice(0, 33)}…` : title, 72, PHOTO_H + 230);
  ctx.fillStyle = hexToRgba(CREAM, 0.6);
  ctx.font = `500 32px ${sans}`;
  ctx.fillText(subtitle, 72, PHOTO_H + 282);

  // brand line
  ctx.strokeStyle = hexToRgba(CREAM, 0.14);
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(72, H - 132);
  ctx.lineTo(W - 72, H - 132);
  ctx.stroke();
  ctx.save();
  const lx = 72;
  const ly = H - 100;
  const ls = 64;
  ctx.beginPath();
  ctx.roundRect(lx, ly, ls, ls, 16);
  ctx.clip();
  ctx.drawImage(logo, lx, ly, ls, ls);
  ctx.restore();
  ctx.fillStyle = CREAM;
  ctx.font = `600 44px ${serif}`;
  ctx.fillText("ElderLeaf", lx + ls + 20, ly + 46);
  ctx.fillStyle = hexToRgba(CREAM, 0.55);
  ctx.font = `500 28px ${sans}`;
  ctx.textAlign = "right";
  ctx.fillText("every plant outlined by SAM 3.1", W - 72, ly + 44);
  ctx.textAlign = "left";

  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not draw the card."))), "image/png"));
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

type CapPlugins = {
  Filesystem?: { writeFile: (o: { path: string; data: string; directory: string }) => Promise<{ uri: string }> };
  Share?: { share: (o: { title?: string; text?: string; files?: string[]; dialogTitle?: string }) => Promise<unknown> };
};

/** Opens the phone's share sheet with the card; on a desktop browser without file sharing it downloads the PNG. */
export async function shareCard(blob: Blob, filename: string, text: string): Promise<"shared" | "downloaded" | "cancelled"> {
  try {
    if (isNativeApp()) {
      const plugins = (window as unknown as { Capacitor?: { Plugins?: CapPlugins } }).Capacitor?.Plugins;
      if (plugins?.Filesystem && plugins.Share) {
        const { uri } = await plugins.Filesystem.writeFile({ path: filename, data: await blobToBase64(blob), directory: "CACHE" });
        await plugins.Share.share({ title: "ElderLeaf", text, files: [uri], dialogTitle: "Share your result" });
        return "shared";
      }
    }
    const file = new File([blob], filename, { type: "image/png" });
    if (navigator.canShare?.({ files: [file] })) {
      await navigator.share({ files: [file], title: "ElderLeaf", text });
      return "shared";
    }
  } catch (e) {
    const msg = String((e as Error)?.message ?? e);
    if ((e as Error)?.name === "AbortError" || /cancel/i.test(msg)) return "cancelled";
    throw e;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return "downloaded";
}
