# SAM 3.1 on PhenoBench: run `calib`

- Split **train**, 60 images, capture dates 05-15, 05-26, 06-05
- Prompts: `crop plant` → crop, `sugar beet plant` → crop, `weed` → weed, `plant` → plant, `leaf` → leaf
- Match rule: one-to-one, IoU ≥ 0.5. Confidence threshold **0.5**; product cleanup also drops masks < 0.02% of the image.
- 300 SAM requests (~$0.75); median latency 8.65s

## 1. Instance detection per prompt

| prompt | target | GT | pred | precision | recall | F1 | mean IoU (TP) | count MAE/img | count bias/img | FP = other class | best thr (F1) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `crop plant` | crop | 555 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 9.250 | -9.250 | 0 | – (finds nothing) |
| `sugar beet plant` | crop | 555 | 354 | 0.799 | 0.510 | 0.623 | 0.821 | 3.517 | -3.350 | 33 | 0.5 (F1 0.62) |
| `weed` | weed | 363 | 371 | 0.164 | 0.168 | 0.166 | 0.676 | 4.433 | 0.133 | 234 | 0.5 (F1 0.17) |
| `plant` | plant | 918 | 596 | 0.814 | 0.528 | 0.641 | 0.779 | 5.367 | -5.367 | 0 | 0.5 (F1 0.64) |
| `leaf` | leaf | 3345 | 2117 | 0.889 | 0.563 | 0.689 | 0.839 | 21.167 | -20.467 | 0 | 0.5 (F1 0.69) |

Cells below are **recall / mean IoU of matched (n = GT instances)**.

## 2. By visibility (share of the object inside the image; low = cut off at the photo edge)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` |
|---|---|---|---|---|---|
| 0.25–0.5 | 0.00 / 0.00 (n=46) | 0.59 / 0.84 (n=46) | 0.17 / 0.60 (n=6) | 0.81 / 0.83 (n=52) | 0.65 / 0.87 (n=117) |
| 0.5–0.75 | 0.00 / 0.00 (n=42) | 0.62 / 0.85 (n=42) | 0.29 / 0.61 (n=7) | 0.67 / 0.83 (n=49) | 0.69 / 0.85 (n=143) |
| 0.75–0.95 | 0.00 / 0.00 (n=40) | 0.70 / 0.84 (n=40) | 0.10 / 0.75 (n=10) | 0.66 / 0.83 (n=50) | 0.74 / 0.88 (n=127) |
| 0.95–1 | 0.00 / 0.00 (n=324) | 0.50 / 0.80 (n=324) | 0.18 / 0.68 (n=323) | 0.49 / 0.75 (n=647) | 0.57 / 0.83 (n=2720) |
| 0–0.25 | 0.00 / 0.00 (n=103) | 0.39 / 0.85 (n=103) | 0.00 / 0.00 (n=17) | 0.52 / 0.83 (n=120) | 0.22 / 0.85 (n=238) |

## 3. By growth stage (capture date)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` |
|---|---|---|---|---|---|
| 05-15 | 0.00 / 0.00 (n=155) | 0.48 / 0.86 (n=155) | 0.25 / 0.67 (n=106) | 0.47 / 0.78 (n=261) | 0.60 / 0.84 (n=721) |
| 05-26 | 0.00 / 0.00 (n=206) | 0.50 / 0.77 (n=206) | 0.13 / 0.64 (n=135) | 0.54 / 0.75 (n=341) | 0.54 / 0.81 (n=1147) |
| 06-05 | 0.00 / 0.00 (n=194) | 0.55 / 0.84 (n=194) | 0.15 / 0.73 (n=122) | 0.57 / 0.81 (n=316) | 0.57 / 0.86 (n=1477) |

## 4. By object size (px; product cleanup drops < ~210 px)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` |
|---|---|---|---|---|---|
| 0–200 | 0.00 / 0.00 (n=63) | 0.00 / 0.00 (n=63) | 0.03 / 0.55 (n=130) | 0.05 / 0.62 (n=193) | 0.09 / 0.66 (n=613) |
| 20000–∞ | 0.00 / 0.00 (n=101) | 0.60 / 0.82 (n=101) | – | 0.62 / 0.83 (n=101) | 1.00 / 0.94 (n=3) |
| 2000–20000 | 0.00 / 0.00 (n=257) | 0.71 / 0.84 (n=257) | 0.33 / 0.71 (n=42) | 0.83 / 0.83 (n=299) | 0.89 / 0.87 (n=1147) |
| 200–2000 | 0.00 / 0.00 (n=134) | 0.30 / 0.75 (n=134) | 0.23 / 0.68 (n=191) | 0.51 / 0.69 (n=325) | 0.51 / 0.81 (n=1582) |

## 5. By crowding (number of other plants touching this one)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` |
|---|---|---|---|---|
| 0 (isolated) | 0.00 / 0.00 (n=367) | 0.57 / 0.83 (n=367) | 0.20 / 0.68 (n=279) | 0.58 / 0.78 (n=646) |
| 1 | 0.00 / 0.00 (n=120) | 0.40 / 0.80 (n=120) | 0.04 / 0.60 (n=68) | 0.41 / 0.77 (n=188) |
| 2+ | 0.00 / 0.00 (n=68) | 0.37 / 0.78 (n=68) | 0.06 / 0.53 (n=16) | 0.37 / 0.79 (n=84) |

## 6. ElderLeaf product metrics (image level)

Count = crop masks after cleanup and crop/weed conflict resolution vs GT crop instances. Canopy = **crop cover** (crop pixels / image, weeds excluded) vs GT crop pixels; errors in percentage points. The `leaf` rows test computing crop cover from leaf masks instead of whole-plant masks. IoU is pixel IoU pooled over all images.

**Pipeline `crop plant + weed`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 60 | 9.250 | -9.250 | 12.489 | 60.513 | 0.257 | 0.000 | 0.049 |
| 05-15 | 20 | 7.750 | -7.750 | 3.685 | 76.528 | 0.692 | 0.000 | 0.042 |
| 05-26 | 20 | 10.300 | -10.300 | 8.308 | 80.595 | 0.512 | 0.000 | 0.035 |
| 06-05 | 20 | 9.700 | -9.700 | 25.473 | 24.417 | 0.096 | 0.000 | 0.078 |

**Pipeline `sugar beet plant + weed`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 60 | 3.517 | -3.350 | 0.862 | 5.960 | 0.883 | 0.874 | 0.096 |
| 05-15 | 20 | 3.650 | -3.350 | 0.386 | 7.847 | 0.833 | 0.831 | 0.193 |
| 05-26 | 20 | 3.750 | -3.750 | 0.818 | 6.104 | 0.847 | 0.831 | 0.127 |
| 06-05 | 20 | 3.150 | -2.950 | 1.381 | 3.929 | 0.904 | 0.896 | 0.038 |

**Pipeline `leaf (all leaves)`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 60 |  |  | 1.687 |  |  | 0.813 |  |
| 05-15 | 20 |  |  | 0.302 |  |  | 0.816 |  |
| 05-26 | 20 |  |  | 1.345 |  |  | 0.759 |  |
| 06-05 | 20 |  |  | 3.415 |  |  | 0.831 |  |

**Pipeline `leaf ∩ crop plant`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 60 |  |  | 12.489 |  |  | 0.000 |  |
| 05-15 | 20 |  |  | 3.685 |  |  | 0.000 |  |
| 05-26 | 20 |  |  | 8.308 |  |  | 0.000 |  |
| 06-05 | 20 |  |  | 25.473 |  |  | 0.000 |  |

**Pipeline `plant (all green vs GT crop+weed)`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 60 | 5.467 | -5.467 | 0.691 |  | 0.889 |  |  |
| 05-15 | 20 | 5.250 | -5.250 | 0.324 |  | 0.841 |  |  |
| 05-26 | 20 | 5.250 | -5.250 | 0.803 |  | 0.855 |  |  |
| 06-05 | 20 | 5.900 | -5.900 | 0.947 |  | 0.909 |  |  |

## Files

- `threshold_sweep.csv`: precision/recall/F1/count error per prompt and threshold
- `gt_matches.csv`: one row per GT instance per prompt (visibility, crowding, size, date, matched, IoU)
- `images.csv`: product metrics per image

Data: PhenoBench (Weyler et al., IEEE TPAMI 2024), CC BY-NC-SA 4.0 per the v1.1.0 release README.