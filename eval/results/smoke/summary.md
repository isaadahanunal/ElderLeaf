# SAM 3.1 on PhenoBench: run `smoke`

- Split **val**, 6 images, capture dates 05-15, 05-26, 06-05
- Prompts: `crop plant` → crop, `sugar beet plant` → crop, `weed` → weed, `plant` → plant, `leaf` → leaf, `sugar beet leaf` → leaf
- Match rule: one-to-one, IoU ≥ 0.5. Confidence threshold **0.5**; product cleanup also drops masks < 0.02% of the image.
- 36 SAM requests (~$0.09); median latency 4.89s

## 1. Instance detection per prompt

| prompt | target | GT | pred | precision | recall | F1 | mean IoU (TP) | count MAE/img | count bias/img | FP = other class | best thr (F1) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `crop plant` | crop | 55 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 9.167 | -9.167 | 0 | 0 (F1 0.00) |
| `sugar beet plant` | crop | 55 | 30 | 0.800 | 0.436 | 0.565 | 0.840 | 4.500 | -4.167 | 2 | 0 (F1 0.56) |
| `weed` | weed | 31 | 50 | 0.200 | 0.323 | 0.247 | 0.730 | 5.833 | 3.167 | 29 | 0 (F1 0.25) |
| `plant` | plant | 86 | 60 | 0.800 | 0.558 | 0.658 | 0.790 | 4.333 | -4.333 | 0 | 0 (F1 0.66) |
| `leaf` | leaf | 302 | 189 | 0.942 | 0.589 | 0.725 | 0.823 | 18.833 | -18.833 | 0 | 0 (F1 0.73) |
| `sugar beet leaf` | leaf | 302 | 8 | 0.125 | 0.003 | 0.006 | 0.969 | 49.000 | -49.000 | 0 | 0 (F1 0.01) |

Cells below are **recall / mean IoU of matched (n = GT instances)**.

## 2. By visibility (share of the object inside the image; low = cut off at the photo edge)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` | `sugar beet leaf` |
|---|---|---|---|---|---|---|
| 0.25–0.5 | 0.00 / 0.00 (n=3) | 0.33 / 0.92 (n=3) | – | 1.00 / 0.86 (n=3) | 0.90 / 0.87 (n=10) | 0.00 / 0.00 (n=10) |
| 0.5–0.75 | 0.00 / 0.00 (n=3) | 0.67 / 0.90 (n=3) | – | 0.67 / 0.92 (n=3) | 0.77 / 0.91 (n=13) | 0.08 / 0.97 (n=13) |
| 0.75–0.95 | 0.00 / 0.00 (n=5) | 1.00 / 0.83 (n=5) | 0.00 / 0.00 (n=1) | 1.00 / 0.85 (n=6) | 0.90 / 0.89 (n=10) | 0.00 / 0.00 (n=10) |
| 0.95–1 | 0.00 / 0.00 (n=34) | 0.41 / 0.82 (n=34) | 0.30 / 0.71 (n=27) | 0.51 / 0.76 (n=61) | 0.56 / 0.81 (n=256) | 0.00 / 0.00 (n=256) |
| 0–0.25 | 0.00 / 0.00 (n=10) | 0.20 / 0.92 (n=10) | 0.67 / 0.82 (n=3) | 0.46 / 0.82 (n=13) | 0.46 / 0.84 (n=13) | 0.00 / 0.00 (n=13) |

## 3. By growth stage (capture date)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` | `sugar beet leaf` |
|---|---|---|---|---|---|---|
| 05-15 | 0.00 / 0.00 (n=15) | 0.47 / 0.86 (n=15) | 0.20 / 0.51 (n=5) | 0.50 / 0.78 (n=20) | 0.52 / 0.84 (n=60) | 0.00 / 0.00 (n=60) |
| 05-26 | 0.00 / 0.00 (n=18) | 0.50 / 0.77 (n=18) | 0.00 / 0.00 (n=9) | 0.56 / 0.75 (n=27) | 0.59 / 0.77 (n=95) | 0.00 / 0.00 (n=95) |
| 06-05 | 0.00 / 0.00 (n=22) | 0.36 / 0.91 (n=22) | 0.53 / 0.75 (n=17) | 0.59 / 0.82 (n=39) | 0.62 / 0.85 (n=147) | 0.01 / 0.97 (n=147) |

## 4. By object size (px; product cleanup drops < ~210 px)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` | `sugar beet leaf` |
|---|---|---|---|---|---|---|
| 0–200 | 0.00 / 0.00 (n=5) | 0.00 / 0.00 (n=5) | 0.00 / 0.00 (n=12) | 0.00 / 0.00 (n=17) | 0.12 / 0.64 (n=75) | 0.00 / 0.00 (n=75) |
| 20000–∞ | 0.00 / 0.00 (n=8) | 0.38 / 0.91 (n=8) | – | 0.62 / 0.87 (n=8) | – | – |
| 2000–20000 | 0.00 / 0.00 (n=20) | 0.70 / 0.89 (n=20) | 0.00 / 0.00 (n=1) | 0.86 / 0.88 (n=21) | 0.90 / 0.86 (n=94) | 0.01 / 0.97 (n=94) |
| 200–2000 | 0.00 / 0.00 (n=22) | 0.32 / 0.71 (n=22) | 0.56 / 0.73 (n=18) | 0.62 / 0.71 (n=40) | 0.63 / 0.80 (n=133) | 0.00 / 0.00 (n=133) |

## 5. By crowding (number of other plants touching this one)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` |
|---|---|---|---|---|
| 0 (isolated) | 0.00 / 0.00 (n=43) | 0.51 / 0.83 (n=43) | 0.37 / 0.73 (n=27) | 0.61 / 0.78 (n=70) |
| 1 | 0.00 / 0.00 (n=8) | 0.25 / 0.92 (n=8) | 0.00 / 0.00 (n=2) | 0.30 / 0.90 (n=10) |
| 2+ | 0.00 / 0.00 (n=4) | 0.00 / 0.00 (n=4) | 0.00 / 0.00 (n=2) | 0.33 / 0.81 (n=6) |

## 6. ElderLeaf product metrics (image level)

Count = crop masks after cleanup and crop/weed conflict resolution vs GT crop instances. Canopy = **crop cover** (crop pixels / image, weeds excluded) vs GT crop pixels; errors in percentage points. The `leaf` rows test computing crop cover from leaf masks instead of whole-plant masks. IoU is pixel IoU pooled over all images.

**Pipeline `crop plant + weed`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 6 | 9.167 | -9.167 | 9.298 | 81.453 | 0.410 | 0.000 | 0.027 |
| 05-15 | 2 | 7.500 | -7.500 | 2.558 | 97.523 | 0.866 | 0.000 | 0.017 |
| 05-26 | 2 | 9.000 | -9.000 | 5.871 | 96.809 | 0.855 | 0.000 | 0.017 |
| 06-05 | 2 | 11.000 | -11.000 | 19.466 | 50.028 | 0.204 | 0.000 | 0.045 |

**Pipeline `sugar beet plant + weed`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 6 | 4.500 | -4.167 | 0.703 | 6.642 | 0.874 | 0.847 | 0.173 |
| 05-15 | 2 | 4.000 | -4.000 | 0.091 | 1.965 | 0.860 | 0.875 | 0.302 |
| 05-26 | 2 | 4.500 | -4.500 | 0.162 | 14.595 | 0.859 | 0.853 | 0.134 |
| 06-05 | 2 | 5.000 | -4.000 | 1.857 | 3.364 | 0.880 | 0.842 | 0.184 |

**Pipeline `leaf (all leaves)`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 6 |  |  | 1.074 |  |  | 0.826 |  |
| 05-15 | 2 |  |  | 0.267 |  |  | 0.836 |  |
| 05-26 | 2 |  |  | 0.598 |  |  | 0.844 |  |
| 06-05 | 2 |  |  | 2.356 |  |  | 0.820 |  |

**Pipeline `leaf ∩ crop plant`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 6 |  |  | 9.298 |  |  | 0.000 |  |
| 05-15 | 2 |  |  | 2.558 |  |  | 0.000 |  |
| 05-26 | 2 |  |  | 5.871 |  |  | 0.000 |  |
| 06-05 | 2 |  |  | 19.466 |  |  | 0.000 |  |

**Pipeline `sugar beet leaf (all leaves)`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 6 |  |  | 6.793 |  |  | 0.266 |  |
| 05-15 | 2 |  |  | 2.558 |  |  | 0.000 |  |
| 05-26 | 2 |  |  | 2.186 |  |  | 0.582 |  |
| 06-05 | 2 |  |  | 15.636 |  |  | 0.204 |  |

**Pipeline `sugar beet leaf ∩ crop plant`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 6 |  |  | 9.298 |  |  | 0.000 |  |
| 05-15 | 2 |  |  | 2.558 |  |  | 0.000 |  |
| 05-26 | 2 |  |  | 5.871 |  |  | 0.000 |  |
| 06-05 | 2 |  |  | 19.466 |  |  | 0.000 |  |

**Pipeline `plant (all green vs GT crop+weed)`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 6 | 4.333 | -4.333 | 2.030 |  | 0.737 |  |  |
| 05-15 | 2 | 4.000 | -4.000 | 0.076 |  | 0.862 |  |  |
| 05-26 | 2 | 2.000 | -2.000 | 0.639 |  | 0.861 |  |  |
| 06-05 | 2 | 7.000 | -7.000 | 5.376 |  | 0.682 |  |  |

## Files

- `threshold_sweep.csv`: precision/recall/F1/count error per prompt and threshold
- `gt_matches.csv`: one row per GT instance per prompt (visibility, crowding, size, date, matched, IoU)
- `images.csv`: product metrics per image

Data: PhenoBench (Weyler et al., IEEE TPAMI 2024), CC BY-NC-SA 4.0 per the v1.1.0 release README.