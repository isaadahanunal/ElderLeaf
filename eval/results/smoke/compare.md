# Fixed words vs prompt agent: run `smoke`

6 PhenoBench images, confidence threshold 0.5. Same images, same SAM 3.1, same cleanup; only the search words differ. Accuracy uses one-to-one matching at IoU ≥ 0.5.

Conflict rule = what happens when the same plant is found as crop and as weed: `score` keeps the higher-confidence mask, `crop-first` always keeps the crop (the grower told us the crop). Crop/weed precision, recall and F1 are raw SAM masks, so they don't depend on the rule; count, cover and weed share do.

## Accuracy

| system | crop_precision | crop_recall | crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | weed_share_mae_pts |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" · score | 0.617 | 0.673 | 0.643 | 3.833 | 0.833 | 1.853 | 0.200 | 0.323 | 0.247 | 3.905 |
| fixed "plant" · crop-first | 0.617 | 0.673 | 0.643 | 3.833 | 0.833 | 1.853 | 0.200 | 0.323 | 0.247 | 3.905 |
| fixed "crop plant" · score | 0.000 | 0.000 | 0.000 | 9.167 | -9.167 | 9.298 | 0.200 | 0.323 | 0.247 | 81.453 |
| fixed "crop plant" · crop-first | 0.000 | 0.000 | 0.000 | 9.167 | -9.167 | 9.298 | 0.200 | 0.323 | 0.247 | 81.453 |
| fixed "sugar beet plant" · score | 0.800 | 0.436 | 0.565 | 6.000 | -6.000 | 0.916 | 0.200 | 0.323 | 0.247 | 22.548 |
| fixed "sugar beet plant" · crop-first | 0.800 | 0.436 | 0.565 | 4.500 | -4.167 | 0.703 | 0.200 | 0.323 | 0.247 | 6.642 |
| agent (baseten) · score | 0.812 | 0.473 | 0.598 | 8.000 | -8.000 | 2.646 | 0.200 | 0.323 | 0.247 | 56.794 |
| agent (baseten) · crop-first | 0.812 | 0.473 | 0.598 | 4.167 | -3.833 | 0.525 | 0.200 | 0.323 | 0.247 | 8.118 |

## Cost and time per image

| system | SAM calls | SAM $ | LLM tokens in / out | LLM $ | total $ / image | total $ (6 images) | wait |
|---|---|---|---|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 0 / 0 | $0.0000 | $0.0050 | $0.0300 | 6.8s |
| fixed "crop plant" | 2.00 | $0.0050 | 0 / 0 | $0.0000 | $0.0050 | $0.0300 | 6.4s |
| fixed "sugar beet plant" | 2.00 | $0.0050 | 0 / 0 | $0.0000 | $0.0050 | $0.0300 | 6.3s |
| agent (baseten) | 3.83 | $0.0096 | 1905 / 420 | $0.0037 | $0.0133 | $0.0797 | 23.5s |

SAM: $0.0025 per call. Muse Spark: $1.25 / 1M input, $0.15 / 1M cached input, $4.25 / 1M output tokens (reasoning counts as output). Wait = LLM time + SAM rounds (calls in a round run in parallel), measured while the eval ran many images at once, so absolute seconds are pessimistic.

## Leaves (experiment)

6 images. Scored against PhenoBench's sugar beet leaves; weed leaves are not labelled, so a leaf mask on a weed counts as a false alarm (`masks_on_weeds_pct` shows how often). The agent's leaf phrases come from the same Muse Spark call, so leaves only add SAM calls.

| system | leaf_precision | leaf_recall | leaf_f1 | masks_on_weeds_pct | SAM calls | SAM $ / image | SAM $ (6 images) | SAM wait |
|---|---|---|---|---|---|---|---|---|
| fixed "leaf" | 0.942 | 0.589 | 0.725 | 4.233 | 1.00 | $0.0025 | $0.0150 | 4.4s |
| fixed "sugar beet leaf" | 0.125 | 0.003 | 0.006 | 0.000 | 1.00 | $0.0025 | $0.0150 | 3.1s |
| agent (baseten) | 0.714 | 0.182 | 0.290 | 2.597 | 2.50 | $0.0062 | $0.0375 | 8.3s |

## Which of the agent's words worked (kept word, by rank)

- crop: #1: 4, #2: 2
- weed: #1: 4, #fallback: 2
- leaf: #1: 2, #2: 1, #3: 1, #fallback: 2

## By growth stage

| date | system | crop F1 | count MAE | weed F1 | crop cover MAE |
|---|---|---|---|---|---|
| 05-15 | fixed "plant" · score | 0.667 | 1.500 | 0.125 | 0.144 |
| 05-15 | fixed "plant" · crop-first | 0.667 | 1.500 | 0.125 | 0.144 |
| 05-15 | fixed "crop plant" · score | 0.000 | 7.500 | 0.125 | 2.558 |
| 05-15 | fixed "crop plant" · crop-first | 0.000 | 7.500 | 0.125 | 2.558 |
| 05-15 | fixed "sugar beet plant" · score | 0.636 | 5.000 | 0.125 | 0.248 |
| 05-15 | fixed "sugar beet plant" · crop-first | 0.636 | 4.000 | 0.125 | 0.091 |
| 05-15 | agent (baseten) · score | 0.636 | 6.500 | 0.125 | 1.299 |
| 05-15 | agent (baseten) · crop-first | 0.636 | 4.000 | 0.125 | 0.096 |
| 05-26 | fixed "plant" · score | 0.732 | 2.500 | 0.000 | 0.770 |
| 05-26 | fixed "plant" · crop-first | 0.732 | 2.500 | 0.000 | 0.770 |
| 05-26 | fixed "crop plant" · score | 0.000 | 9.000 | 0.000 | 5.871 |
| 05-26 | fixed "crop plant" · crop-first | 0.000 | 9.000 | 0.000 | 5.871 |
| 05-26 | fixed "sugar beet plant" · score | 0.667 | 8.000 | 0.000 | 0.859 |
| 05-26 | fixed "sugar beet plant" · crop-first | 0.667 | 4.500 | 0.000 | 0.162 |
| 05-26 | agent (baseten) · score | 0.774 | 8.500 | 0.000 | 2.234 |
| 05-26 | agent (baseten) · crop-first | 0.774 | 2.500 | 0.000 | 0.328 |
| 06-05 | fixed "plant" · score | 0.553 | 7.500 | 0.545 | 4.645 |
| 06-05 | fixed "plant" · crop-first | 0.553 | 7.500 | 0.545 | 4.645 |
| 06-05 | fixed "crop plant" · score | 0.000 | 11.000 | 0.545 | 19.466 |
| 06-05 | fixed "crop plant" · crop-first | 0.000 | 11.000 | 0.545 | 19.466 |
| 06-05 | fixed "sugar beet plant" · score | 0.444 | 5.000 | 0.545 | 1.640 |
| 06-05 | fixed "sugar beet plant" · crop-first | 0.444 | 5.000 | 0.545 | 1.857 |
| 06-05 | agent (baseten) · score | 0.412 | 9.000 | 0.545 | 4.404 |
| 06-05 | agent (baseten) · crop-first | 0.412 | 6.000 | 0.545 | 1.150 |

## What the agent proposed (first images)

| image | agent's view | crop words → kept | weed words → kept | leaf words → kept |
|---|---|---|---|---|
| 05-15_00184_P0030859.png | Young sugar beet seedlings growing on dry tilled brown soil in bright sunlight | sugar beet seedling / young sugar beet rosette / beet rosette plantlet → **sugar beet seedling** | grass weed blade / narrow leaf grass tuft / clover trifoliate sprout → **weed** | sugar beet leaf / beet seedling leaf / crinkled beet leaf → **leaf** |
| 05-15_00284_P0030695.png | Overhead view of bare tilled brown soil with small green plants along the left edge | sugar beet seedling / sugar beet rosette / young beet plant → **sugar beet seedling** | grass seedling blade / thin grass weed sprout / narrow grass blade → **weed** | sugar beet leaf / crinkled beet leaf / beet rosette leaf → **leaf** |
| 05-26_00056_P0034282.png | Top-down view of bare brown soil with large crinkled green rosettes and tiny seedlings scattered | sugar beet rosette / mature sugar beet plant / crinkled beet rosette → **mature sugar beet plant** | grass seedling / thin grass blade / small grass weed → **grass seedling** | sugar beet leaf / crinkled beet leaf / glossy beet leaflet → **sugar beet leaf** |
| 05-26_00193_P0034121.png | Tilled brown soil with tractor tire tracks and small green seedlings in rows | sugar beet seedling / young sugar beet plant / small beet rosette → **sugar beet seedling** | grass weed seedling / narrow grass blade sprout / tiny grassy weed → **grass weed seedling** | sugar beet leaf / young beet leaf / small rounded beet leaf → **young beet leaf** |
| 06-05_00087_P0037822.png | Top-down view of young sugar beet plants with crinkled leaves growing in dark soil. | sugar beet rosette / mature sugar beet plant / ruffled beet foliage → **mature sugar beet plant** | small grass weed / creeping broadleaf weed / thin grass seedling → **small grass weed** | sugar beet leaf / crinkled beet leaf / ruffled green leaf → **ruffled green leaf** |
| 06-05_00132_P0037822.png | Top-down view of bare brown soil with scattered young green plants. | sugar beet seedling / sugar beet rosette / crinkled beet plant → **sugar beet seedling** | grass weed seedling / narrow grass blade sprout / star-shaped grass weed → **grass weed seedling** | sugar beet leaf / beet rosette leaf / crinkled beet leaf → **sugar beet leaf** |

Files: `compare.csv` (one row per image and system), `compare_leaves.csv`, `compare.json` (the tables above).