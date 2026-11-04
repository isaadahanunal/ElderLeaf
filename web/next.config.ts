import type { NextConfig } from "next";

// `npm run build:app` sets BUILD_TARGET=app: a static export in out/, which Capacitor packs into the Android APK.
// Every page is a client page that reads its id from the query string, so nothing needs a server.
const forApp = process.env.BUILD_TARGET === "app";

const nextConfig: NextConfig = {
  // Partial prerendering (cache components) needs a server, so the static app export turns it off.
  // (built straight into out/, so building the APK never disturbs a running `next dev` in .next/)
  ...(forApp
    ? { output: "export" as const, distDir: "out", images: { unoptimized: true } }
    : { cacheComponents: true, partialPrefetching: true }),
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
