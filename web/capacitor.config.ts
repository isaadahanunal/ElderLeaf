import type { CapacitorConfig } from "@capacitor/cli";

// Android app: the static export in out/ (npm run build:app) is packed into the APK and talks to the API
// at NEXT_PUBLIC_API_URL, or at the server set in the app's Settings.
const config: CapacitorConfig = {
  appId: "com.elderleaf.app",
  appName: "ElderLeaf",
  webDir: "out",
  backgroundColor: "#15251e",
  server: {
    // The app is served from http://localhost (still a secure context, so camera and location work).
    // With an https origin, Chromium silently upgrades http:// images to https:// and the photos from
    // an API on a laptop over Wi-Fi (http://<ip>:8000) would not load. The deployed API is https anyway.
    androidScheme: "http",
    cleartext: true,
  },
  plugins: {
    SystemBars: {
      insetsHandling: "css",
      initialViewportFitValueHint: "cover",
      style: "LIGHT",
    },
  },
};

export default config;
