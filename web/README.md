# ElderLeaf web

Mobile-first Next.js app (3 screens: My plots, Plot logbook/compare, Analysis).

```bash
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local   # the FastAPI backend in ../api
npm run dev                                                      # http://localhost:3000
```

All data comes from the API (`src/lib/api.ts` mirrors `api/elderleaf/schemas.py`).
There is no login: the browser keeps a random device id in localStorage and sends it as `X-Device-Id`.
