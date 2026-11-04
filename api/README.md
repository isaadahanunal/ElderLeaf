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
   A4 → retry if weak → metrics → history → report agent). When `status` is `done`, `result` holds the full
   analysis and `result.report` the combined report; `GET /analyses/{id}/report.md` returns it as Markdown.
4. `GET /plots` (cards), `GET /plots/{id}` (logbook: analyses + notes),
   `GET /plots/{id}/export.csv`, `POST /plots/{id}/notes`, `POST /analyses/{id}/rerun`.
5. `GET /plots/{id}/compare?a={analysis id}&b={analysis id}` (Compare tab): difference table (plants, crop
   cover, weed share, leaf spots, plant size, change per day), the notes in between, and a change
   summary the report agent writes from both photos (validated like the report; template without an LLM).

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

**Mixed beds.** When the grower marks a plot as `mixed` (more than one crop in the same photo) and
names the other crops (`other_crops`, crop ids; `other` if unsure), the agent switches to **scan
mode** (`agent.scan_plants`): it lists one phrase per kind of plant it sees, as many as the photo
needs (at most 8), each marked as a crop (which one) or a weed, and SAM searches all of them
(`run_stats.strategy = "scan"`, `run_stats.scan_items`). A crop none of whose phrases was confident
gets its library word, weeds get "weed", and only if no crop is found at all the plain "plant"
(then the plants can't be told apart: `by_crop["*"]`). A crop whose library word is the generic
"plant" (`other`) never gets a word of its own, so it can't take the named crops' plants. Every crop
mask carries its crop (`masks[].crop`); `metrics.by_crop` gives count and cover per crop, and a named
crop with no plants found gets a "Crop not found" line. Why: on CropAndWeed photos with two crops,
scan mode found the crops (F1 0.78-0.82) where searching the crop names did not (0.04), while for a
single crop the ranked words did better (eval/results/mixed/report.md).

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
- `elderleaf/metrics.py`: plant count, canopy %, weed share %, lesion %, mean plant area (cm² via A4), photo quality.
  Lesion % follows the plan: crop pixels under SAM 'leaf spot' masks or clearly yellow/brown, over crop pixels
  (the leaf-spot search is on by default, `ENABLE_LESION=0` turns it off; it found no spots on 8 healthy PhenoBench photos)
- `elderleaf/pipeline.py`: runs the steps, compares with the previous photo, writes the context lines from templates

- `elderleaf/health.py`: yellowing / browning measured in the crop masks (relative to the photo's own crop color), leaf-spot share
- `elderleaf/agronomy.py` + `crop_agronomy.json`: FAO-56 Kc and stage lengths, growth stage of the day, water need (Kc × ET0)
- `elderleaf/weather.py`: daily ET0 and rain for the plot's location from Open-Meteo (free, no key; `WEATHER=0` turns it off)
- `elderleaf/report_agent.py`: the report agent (below)

No LLM produces a number.

## Report agent (after the masks)

Follows the plan's agent schema. Code runs the tools and records each one in `trace`: `get_plot_history`
(previous photo + the grower's notes since then), `lookup_crop_info` (FAO-56 stage and Kc),
`assess_health` (color and spots inside the crop masks; likelihoods set in code), `get_weather` +
`compute_irrigation` (needs the plot's lat/lon). Code also sets every "Is this normal?" status, the
spacing check (when an A4 sheet gives the scale and the plot has row/plant spacing) and the
"consult an agronomist" flag (photo quality low, spots ≥ 5% of the crop, discoloration of medium
likelihood, or confidence < 0.6).

Muse Spark then gets these facts plus the photo. It may ask SAM 3.1 to **look closer** once (e.g.
"leaf spot", "leaf holes") when it sees a possible problem the code did not measure; the result is
measured in code and added to the facts. Then it writes the report: headline, one line per status,
health summary, change since last photo, water sentence, up to 3 next steps.

A **validator** checks the reply: every number must match a fact (rounding allowed), health signs must
be ones code measured, and no pesticide/chemical names, doses or disease names. Errors go back to the
model once; if it still fails, the code's template texts are used (`report.written_by = "template"`),
so the writer never fails an analysis. `REPORT_AGENT=0` skips the LLM writer.
Typical cost: one or two LLM calls, about $0.007, 10–20 s.
