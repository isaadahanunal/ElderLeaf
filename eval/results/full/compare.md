# Fixed words vs prompt agent: run `full`

772 PhenoBench images, confidence threshold 0.5. Same images, same SAM 3.1, same cleanup; only the search words differ. Accuracy uses one-to-one matching at IoU ≥ 0.5.

Conflict rule = what happens when the same plant is found as crop and as weed: `score` keeps the higher-confidence mask, `crop-first` always keeps the crop (the grower told us the crop). Crop/weed precision, recall and F1 are raw SAM masks, so they don't depend on the rule; count, cover and weed share do.

## Accuracy

| system | crop_precision | crop_recall | crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | weed_share_mae_pts |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" · score | 0.593 | 0.666 | 0.628 | 2.763 | 0.483 | 1.093 | 0.202 | 0.250 | 0.223 | 7.929 |
| fixed "plant" · crop-first | 0.593 | 0.666 | 0.628 | 2.657 | 0.942 | 1.109 | 0.202 | 0.250 | 0.223 | 7.929 |
| fixed "crop plant" · score | 0.000 | 0.000 | 0.000 | 8.396 | -8.396 | 9.553 | 0.202 | 0.250 | 0.223 | 68.035 |
| fixed "crop plant" · crop-first | 0.000 | 0.000 | 0.000 | 8.396 | -8.396 | 9.553 | 0.202 | 0.250 | 0.223 | 68.035 |
| fixed "sugar beet plant" · score | 0.833 | 0.485 | 0.613 | 4.617 | -4.508 | 0.785 | 0.202 | 0.250 | 0.223 | 15.390 |
| fixed "sugar beet plant" · crop-first | 0.833 | 0.485 | 0.613 | 3.878 | -3.513 | 0.768 | 0.202 | 0.250 | 0.223 | 9.712 |
| agent (baseten) · score | 0.779 | 0.485 | 0.598 | 6.251 | -6.101 | 3.107 | 0.213 | 0.332 | 0.260 | 44.345 |
| agent (baseten) · crop-first | 0.779 | 0.485 | 0.598 | 3.797 | -3.183 | 1.059 | 0.213 | 0.332 | 0.260 | 8.997 |

## Cost and time per image

| system | SAM calls | SAM $ | LLM tokens in / out | LLM $ | total $ / image | total $ (772 images) | wait |
|---|---|---|---|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 0 / 0 | $0.0000 | $0.0050 | $3.8600 | 11.9s |
| fixed "crop plant" | 2.00 | $0.0050 | 0 / 0 | $0.0000 | $0.0050 | $3.8600 | 11.6s |
| fixed "sugar beet plant" | 2.00 | $0.0050 | 0 / 0 | $0.0000 | $0.0050 | $3.8600 | 11.9s |
| agent (baseten) | 3.70 | $0.0093 | 1916 / 454 | $0.0038 | $0.0130 | $10.0593 | 51.5s |

SAM: $0.0025 per call. Muse Spark: $1.25 / 1M input, $0.15 / 1M cached input, $4.25 / 1M output tokens (reasoning counts as output). Wait = LLM time + SAM rounds (calls in a round run in parallel), measured while the eval ran many images at once, so absolute seconds are pessimistic.

## Leaves (experiment)

772 images. Scored against PhenoBench's sugar beet leaves; weed leaves are not labelled, so a leaf mask on a weed counts as a false alarm (`masks_on_weeds_pct` shows how often). The agent's leaf phrases come from the same Muse Spark call, so leaves only add SAM calls.

| system | leaf_precision | leaf_recall | leaf_f1 | masks_on_weeds_pct | SAM calls | SAM $ / image | SAM $ (772 images) | SAM wait |
|---|---|---|---|---|---|---|---|---|
| fixed "leaf" | 0.897 | 0.605 | 0.722 | 5.544 | 1.00 | $0.0025 | $1.9300 | 10.2s |
| fixed "sugar beet leaf" | 0.044 | 0.001 | 0.002 | 1.626 | 1.00 | $0.0025 | $1.9300 | 10.3s |
| agent (baseten) | 0.821 | 0.274 | 0.411 | 4.858 | 2.58 | $0.0065 | $4.9800 | 32.0s |

## Which of the agent's words worked (kept word, by rank)

- crop: #1: 467, #2: 246, #3: 25, #fallback: 34
- weed: #1: 437, #2: 105, #3: 91, #fallback: 139
- leaf: #1: 256, #2: 106, #3: 143, #fallback: 267

## By growth stage

| date | system | crop F1 | count MAE | weed F1 | crop cover MAE |
|---|---|---|---|---|---|
| 05-15 | fixed "plant" · score | 0.645 | 2.153 | 0.203 | 0.312 |
| 05-15 | fixed "plant" · crop-first | 0.645 | 1.850 | 0.203 | 0.336 |
| 05-15 | fixed "crop plant" · score | 0.000 | 7.551 | 0.203 | 3.041 |
| 05-15 | fixed "crop plant" · crop-first | 0.000 | 7.551 | 0.203 | 3.041 |
| 05-15 | fixed "sugar beet plant" · score | 0.589 | 4.496 | 0.203 | 0.271 |
| 05-15 | fixed "sugar beet plant" · crop-first | 0.589 | 4.053 | 0.203 | 0.227 |
| 05-15 | agent (baseten) · score | 0.614 | 5.787 | 0.177 | 1.732 |
| 05-15 | agent (baseten) · crop-first | 0.614 | 3.356 | 0.177 | 0.231 |
| 05-26 | fixed "plant" · score | 0.657 | 3.135 | 0.162 | 1.278 |
| 05-26 | fixed "plant" · crop-first | 0.657 | 3.335 | 0.162 | 1.289 |
| 05-26 | fixed "crop plant" · score | 0.000 | 9.241 | 0.162 | 9.791 |
| 05-26 | fixed "crop plant" · crop-first | 0.000 | 9.241 | 0.162 | 9.791 |
| 05-26 | fixed "sugar beet plant" · score | 0.608 | 6.582 | 0.162 | 0.838 |
| 05-26 | fixed "sugar beet plant" · crop-first | 0.608 | 4.300 | 0.162 | 0.692 |
| 05-26 | agent (baseten) · score | 0.603 | 7.324 | 0.165 | 3.329 |
| 05-26 | agent (baseten) · crop-first | 0.603 | 4.306 | 0.165 | 1.107 |
| 06-05 | fixed "plant" · score | 0.578 | 3.650 | 0.326 | 2.473 |
| 06-05 | fixed "plant" · crop-first | 0.578 | 3.675 | 0.326 | 2.476 |
| 06-05 | fixed "crop plant" · score | 0.000 | 9.350 | 0.326 | 22.155 |
| 06-05 | fixed "crop plant" · crop-first | 0.000 | 9.350 | 0.326 | 22.155 |
| 06-05 | fixed "sugar beet plant" · score | 0.648 | 3.207 | 0.326 | 1.753 |
| 06-05 | fixed "sugar beet plant" · crop-first | 0.648 | 3.182 | 0.326 | 1.895 |
| 06-05 | agent (baseten) · score | 0.569 | 6.266 | 0.448 | 5.623 |
| 06-05 | agent (baseten) · crop-first | 0.569 | 4.236 | 0.448 | 2.647 |

## What the agent proposed (first images)

| image | agent's view | crop words → kept | weed words → kept | leaf words → kept |
|---|---|---|---|---|
| 05-15_00052_P0030859.png | Top-down view of dry tilled soil with a couple small sugar beet plants | sugar beet seedling / young sugar beet rosette / small beet plant → **sugar beet seedling** | thin grass blade / grass weed sprout / clover weed leaf → **clover weed leaf** | sugar beet leaf / crinkled beet leaf / broad green leaf → **broad green leaf** |
| 05-15_00053_P0030859.png | Top-down view of bare brown soil with small green rosettes growing in a row | sugar beet seedling / young sugar beet rosette / small beet plant → **sugar beet seedling** | thin grass blade / grass weed sprout / narrow grass seedling → **narrow grass seedling** | sugar beet leaf / crinkled beet leaf / young beet rosette leaf → **young beet rosette leaf** |
| 05-15_00053_P0030943.png | top-down view of dry brown tilled soil with a small green plant at the edge | sugar beet seedling / young sugar beet plant / small sugar beet rosette → **sugar beet seedling** | grass blade / thin grass seedling / tiny grass sprout → **thin grass seedling** | sugar beet leaf / young beet leaf / small beet leaflet → **young beet leaf** |
| 05-15_00054_P0030859.png | Top-down view of bare brown soil with scattered small green sugar beet seedlings | sugar beet seedling / sugar beet rosette / young beet plant → **sugar beet seedling** | grass blade seedling / thin grass sprout / small grassy weed → **grass blade seedling** | sugar beet leaf / beet rosette leaf / young beet leaflet → **leaf** |
| 05-15_00054_P0030943.png | Bare brown soil viewed from above with a small green plant at the top edge | sugar beet seedling / young sugar beet rosette / sugar beet sprout → **sugar beet seedling** | grass seedling blade / thin grass sprout / narrow grass weed → **weed** | sugar beet leaf / beet seedling leaf / young beet leaflet → **leaf** |
| 05-15_00055_P0030859.png | Top-down view of young sugar beet plants growing in rows on bare brown soil | sugar beet seedling / sugar beet rosette / young beet plant → **sugar beet seedling** | thin grass blade / tiny grass seedling / clover weed sprout → **tiny grass seedling** | sugar beet leaf / beet plant leaf / crinkled beet leaf → **leaf** |
| 05-15_00055_P0030943.png | Top-down view of dry brown tilled soil with sparse small green seedlings and a larger leafy plant in the corner | sugar beet seedling / young sugar beet rosette / small beet plant → **sugar beet seedling** | thin grass seedling / tiny grass sprout / narrow grass blade → **thin grass seedling** | sugar beet leaf / beet rosette leaf / young beet leaf → **young beet leaf** |
| 05-15_00056_P0030859.png | Young sugar beet seedlings growing in a row on dry tilled brown soil. | sugar beet seedling / young sugar beet rosette / small sugar beet plant → **sugar beet seedling** | grass seedling / thin grass weed / narrow blade grass → **grass seedling** | sugar beet leaf / crinkled beet leaf / broad beet leaflet → **leaf** |
| 05-15_00057_P0030859.png | Bare brown tilled soil with a small green sugar beet plant growing on the right side | sugar beet seedling / young sugar beet rosette / small beet plant → **sugar beet seedling** | grass seedling / thin grass blade / clover weed sprout → **grass seedling** | sugar beet leaf / crinkled beet leaf / young rosette leaf → **young rosette leaf** |
| 05-15_00058_P0030859.png | Bare tilled brown soil with a single small green rosette casting a shadow | sugar beet seedling / young sugar beet rosette / small beet plant → **sugar beet seedling** | grass seedling / narrow grass blade / thin bladed grass sprout → **grass seedling** | sugar beet leaf / crinkled beet leaf / young beet rosette leaf → **young beet rosette leaf** |
| 05-15_00059_P0030859.png | Top-down view of bare tilled brown soil with sparse tiny green seedlings | sugar beet seedling / young sugar beet sprout / small sugar beet rosette → **plant** | grass blade seedling / thin grassy weed sprout / small clover weed leaflet → **weed** | sugar beet cotyledon leaf / small beet seedling leaf / young beet rosette leaf → **small beet seedling leaf** |
| 05-15_00060_P0030859.png | Top-down view of bare tilled soil with a young sugar beet plant and small sprouts | sugar beet seedling / young sugar beet plant / small beet rosette → **sugar beet seedling** | grass seedling / thin grass blade / clover weed sprout → **grass seedling** | sugar beet leaf / beet rosette leaf / crinkled beet leaflet → **leaf** |

Files: `compare.csv` (one row per image and system), `compare_leaves.csv`, `compare.json` (the tables above).