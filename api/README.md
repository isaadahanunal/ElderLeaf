# ElderLeaf API (FastAPI)

```bash
cp ../.env.example ../.env        # add MODEL_API_KEY
uv sync
uv run uvicorn elderleaf.app:app --reload     # http://localhost:8000/docs
uv run pytest -q                              # offline tests (fake SAM, no key needed)
```

Locally it uses SQLite (`.data/elderleaf.db`) and stores photos in `.data/files` (served at `/files`).
In production, set `DATABASE_URL` (Supabase Postgres) and `STORAGE_BACKEND=supabase`.

## Flow

1. `POST /plots` creates a plot (send an `X-Device-Id` header; there's no login).
2. `POST /plots/{id}/analyses` uploads a photo (multipart `file`, optional `captured_at`) and
   returns `202` with status `pending` straight away.
3. Poll `GET /analyses/{id}` every second. `trace` fills in step by step (quality → SAM crop / weed /
   A4 → retry if weak → metrics → history). When `status` is `done`, `result` holds the full analysis.
4. `GET /plots` (cards), `GET /plots/{id}` (logbook: analyses + notes),
   `GET /plots/{id}/export.csv`, `POST /plots/{id}/notes`, `POST /analyses/{id}/rerun`.

## How SAM's search words are chosen

With `PROMPT_STRATEGY=agent` (default) and an LLM key, Muse Spark looks at the photo and proposes
3 ranked phrases for the crop and 3 for the weeds (`elderleaf/agent.py`). The pipeline tries them
in order and stops at the first confident answer, then falls back to the fixed word
(`elderleaf/prompting.py`). Crop and weed tries of the same round run in parallel. Without a key,
or if the agent fails, it uses the fixed words. `result.run_stats` records the proposals, every
attempt, the chosen word and its rank, SAM calls, LLM tokens, $ and time. Provider: Muse Spark Open
on Baseten when `BASETEN_API_KEY` is set, else Muse Spark 1.3 on Meta Model API.

When a weed phrase also matches a crop plant, the crop wins (`priority=["crop", "weed"]`), because
the grower told us the crop.

## Seeing the masks

- `GET /analyses/{id}/overlay.png`: the photo with the final masks (crop green, weed magenta, A4 blue)
  and their ids. Its URL is `overlay_url` in the analysis response.
- `GET /analyses/{id}/sam.png?prompt=...`: everything one SAM call returned, including masks
  dropped by the threshold (gray). Each `run_sam` step in `trace` carries this link as `image_url`.
  It reads the cache only, so it never triggers a new paid call.
- Try prompts on any photo from the command line (one picture per prompt + a side-by-side sheet):

  ```bash
  uv run python -m elderleaf.try_sam ../photo.jpg "lettuce plant" "weed" "white paper sheet"
  ```

The `result` shape (`AnalysisResult` in `elderleaf/schemas.py`) is the contract with the frontend.
Mask outlines come as polygons in image pixels, ready for a canvas. Generate TypeScript types with:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o ../web/src/api.d.ts
```

## Where the numbers come from

- `elderleaf/sam.py`: SAM 3.1 client (one concept per request, cached by image hash + prompt)
- `elderleaf/masks.py`: confidence/size cleanup; crop-vs-weed conflicts go to the higher score
- `elderleaf/metrics.py`: plant count, canopy %, weed share %, lesion %, mean plant area (cm² via A4), photo quality
- `elderleaf/pipeline.py`: runs the steps, compares with the previous photo, writes the context lines from templates

No LLM produces a number. The Muse Spark agent (next) re-prompts SAM and rephrases context only.
