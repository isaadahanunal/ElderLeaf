# ElderLeaf web

Mobile-first Next.js app (3 screens: My plots, Plot logbook/compare, Analysis).

```bash
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local   # the FastAPI backend in ../api
npm run dev                                                      # http://localhost:3000
```

All data comes from the API (`src/lib/api.ts` mirrors `api/elderleaf/schemas.py`).
Sign-in is optional. A guest's browser keeps a random device id in localStorage and sends it as `X-Device-Id`; a signed-in user also sends `Authorization: Bearer <token>` (`src/lib/auth.tsx`). Screens: `/login` (sign in / create account) and `/profile`.

## Android app (APK)

The same pages, exported as static files (`BUILD_TARGET=app next build` → `out/`) and packed by Capacitor (`android/`).

```bash
scripts/build-apk.sh https://<your-api>.modal.run   # needs JDK 21 + Android SDK 36 → dist/ElderLeaf.apk
```

- The API address comes from the argument (or `NEXT_PUBLIC_API_URL`) and can be changed in the app: Settings → App.
- Camera: "Take photo" / "Record video" open the phone camera; "Camera with guide" shows the last photo faintly on top.
- Icons and splash come from `public/icon-maskable-512.png` and `public/brand/elderleaf-logo-1024.png`.

