# SAM 3.1 on PhenoBench: run `full`

- Split **val**, 772 images, capture dates 05-15, 05-26, 06-05
- Prompts: `crop plant` → crop, `sugar beet plant` → crop, `weed` → weed, `plant` → plant, `leaf` → leaf, `sugar beet leaf` → leaf
- Match rule: one-to-one, IoU ≥ 0.5. Confidence threshold **0.5**; product cleanup also drops masks < 0.02% of the image.
- 4632 SAM requests (~$11.58); median latency 9.81s

## 1. Instance detection per prompt

| prompt | target | GT | pred | precision | recall | F1 | mean IoU (TP) | count MAE/img | count bias/img | FP = other class | best thr (F1) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `crop plant` | crop | 6482 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 8.396 | -8.396 | 0 | – (finds nothing) |
| `sugar beet plant` | crop | 6482 | 3772 | 0.833 | 0.485 | 0.613 | 0.842 | 3.878 | -3.510 | 334 | 0.5 (F1 0.61) |
| `weed` | weed | 3926 | 4864 | 0.202 | 0.250 | 0.223 | 0.695 | 4.811 | 1.215 | 2835 | 0.5 (F1 0.22) |
| `plant` | plant | 10408 | 7273 | 0.820 | 0.573 | 0.674 | 0.786 | 4.120 | -4.061 | 0 | 0.5 (F1 0.67) |
| `leaf` | leaf | 35503 | 23937 | 0.897 | 0.605 | 0.722 | 0.842 | 15.407 | -14.982 | 0 | 0.5 (F1 0.72) |
| `sugar beet leaf` | leaf | 35503 | 984 | 0.044 | 0.001 | 0.002 | 0.705 | 44.714 | -44.714 | 0 | 0.5 (F1 0.00) |

Cells below are **recall / mean IoU of matched (n = GT instances)**.

## 2. By visibility (share of the object inside the image; low = cut off at the photo edge)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` | `sugar beet leaf` |
|---|---|---|---|---|---|---|
| 0.25–0.5 | 0.00 / 0.00 (n=496) | 0.66 / 0.85 (n=496) | 0.18 / 0.80 (n=111) | 0.72 / 0.85 (n=607) | 0.65 / 0.85 (n=1297) | 0.01 / 0.82 (n=1297) |
| 0.5–0.75 | 0.00 / 0.00 (n=456) | 0.70 / 0.84 (n=456) | 0.26 / 0.76 (n=108) | 0.73 / 0.83 (n=564) | 0.76 / 0.87 (n=1286) | 0.01 / 0.79 (n=1286) |
| 0.75–0.95 | 0.00 / 0.00 (n=486) | 0.66 / 0.84 (n=486) | 0.28 / 0.69 (n=134) | 0.75 / 0.81 (n=620) | 0.81 / 0.87 (n=1284) | 0.01 / 0.67 (n=1284) |
| 0.95–1 | 0.00 / 0.00 (n=4025) | 0.44 / 0.83 (n=4025) | 0.26 / 0.69 (n=3359) | 0.55 / 0.76 (n=7384) | 0.61 / 0.84 (n=29426) | 0.00 / 0.58 (n=29426) |
| 0–0.25 | 0.00 / 0.00 (n=1019) | 0.39 / 0.87 (n=1019) | 0.04 / 0.75 (n=214) | 0.50 / 0.86 (n=1233) | 0.28 / 0.84 (n=2210) | 0.00 / 0.00 (n=2210) |

## 3. By growth stage (capture date)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` | `sugar beet leaf` |
|---|---|---|---|---|---|---|
| 05-15 | 0.00 / 0.00 (n=3013) | 0.43 / 0.86 (n=3013) | 0.32 / 0.66 (n=1249) | 0.55 / 0.78 (n=4262) | 0.60 / 0.83 (n=12873) | 0.00 / 0.61 (n=12873) |
| 05-26 | 0.00 / 0.00 (n=1571) | 0.49 / 0.78 (n=1571) | 0.19 / 0.65 (n=1097) | 0.54 / 0.75 (n=2668) | 0.62 / 0.82 (n=8696) | 0.00 / 0.77 (n=8696) |
| 06-05 | 0.00 / 0.00 (n=1898) | 0.57 / 0.86 (n=1898) | 0.24 / 0.76 (n=1580) | 0.62 / 0.82 (n=3478) | 0.60 / 0.87 (n=13934) | 0.00 / 0.80 (n=13934) |

## 4. By object size (px; product cleanup drops < ~210 px)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` | `leaf` | `sugar beet leaf` |
|---|---|---|---|---|---|---|
| 0–200 | 0.00 / 0.00 (n=1039) | 0.00 / 0.59 (n=1039) | 0.06 / 0.60 (n=1056) | 0.08 / 0.61 (n=2095) | 0.13 / 0.66 (n=6999) | 0.00 / 0.00 (n=6999) |
| 20000–∞ | 0.00 / 0.00 (n=996) | 0.52 / 0.84 (n=996) | 0.00 / 0.00 (n=5) | 0.60 / 0.84 (n=1001) | 0.97 / 0.90 (n=36) | 0.00 / 0.00 (n=36) |
| 2000–20000 | 0.00 / 0.00 (n=2851) | 0.78 / 0.86 (n=2851) | 0.32 / 0.78 (n=502) | 0.84 / 0.86 (n=3353) | 0.89 / 0.88 (n=11525) | 0.00 / 0.71 (n=11525) |
| 200–2000 | 0.00 / 0.00 (n=1596) | 0.26 / 0.76 (n=1596) | 0.32 / 0.68 (n=2363) | 0.60 / 0.70 (n=3959) | 0.61 / 0.82 (n=16943) | 0.00 / 0.69 (n=16943) |

## 5. By crowding (number of other plants touching this one)

| group | `crop plant` | `sugar beet plant` | `weed` | `plant` |
|---|---|---|---|---|
| 0 (isolated) | 0.00 / 0.00 (n=4643) | 0.52 / 0.85 (n=4643) | 0.30 / 0.69 (n=3019) | 0.64 / 0.79 (n=7662) |
| 1 | 0.00 / 0.00 (n=1140) | 0.42 / 0.81 (n=1140) | 0.07 / 0.70 (n=739) | 0.39 / 0.80 (n=1879) |
| 2+ | 0.00 / 0.00 (n=699) | 0.34 / 0.77 (n=699) | 0.05 / 0.69 (n=168) | 0.39 / 0.78 (n=867) |

## 6. ElderLeaf product metrics (image level)

Count = crop masks after cleanup and crop/weed conflict resolution vs GT crop instances. Canopy = **crop cover** (crop pixels / image, weeds excluded) vs GT crop pixels; errors in percentage points. The `leaf` rows test computing crop cover from leaf masks instead of whole-plant masks. IoU is pixel IoU pooled over all images.

**Pipeline `crop plant + weed`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 772 | 8.396 | -8.396 | 9.553 | 68.035 | 0.304 | 0.000 | 0.055 |
| 05-15 | 399 | 7.551 | -7.551 | 3.041 | 83.856 | 0.721 | 0.000 | 0.031 |
| 05-26 | 170 | 9.241 | -9.241 | 9.791 | 73.972 | 0.479 | 0.000 | 0.040 |
| 06-05 | 203 | 9.350 | -9.350 | 22.155 | 31.967 | 0.117 | 0.000 | 0.106 |

**Pipeline `sugar beet plant + weed`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 772 | 3.878 | -3.513 | 0.768 | 9.712 | 0.878 | 0.864 | 0.130 |
| 05-15 | 399 | 4.053 | -4.033 | 0.227 | 12.683 | 0.837 | 0.844 | 0.222 |
| 05-26 | 170 | 4.300 | -3.712 | 0.692 | 5.961 | 0.860 | 0.850 | 0.152 |
| 06-05 | 203 | 3.182 | -2.325 | 1.895 | 7.013 | 0.896 | 0.875 | 0.087 |

**Pipeline `leaf (all leaves)`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 772 |  |  | 1.285 |  |  | 0.817 |  |
| 05-15 | 399 |  |  | 0.322 |  |  | 0.819 |  |
| 05-26 | 170 |  |  | 1.561 |  |  | 0.788 |  |
| 06-05 | 203 |  |  | 2.947 |  |  | 0.828 |  |

**Pipeline `leaf ∩ crop plant`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 772 |  |  | 9.553 |  |  | 0.000 |  |
| 05-15 | 399 |  |  | 3.041 |  |  | 0.000 |  |
| 05-26 | 170 |  |  | 9.791 |  |  | 0.000 |  |
| 06-05 | 203 |  |  | 22.155 |  |  | 0.000 |  |

**Pipeline `sugar beet leaf (all leaves)`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 772 |  |  | 7.185 |  |  | 0.234 |  |
| 05-15 | 399 |  |  | 1.841 |  |  | 0.368 |  |
| 05-26 | 170 |  |  | 8.032 |  |  | 0.166 |  |
| 06-05 | 203 |  |  | 16.979 |  |  | 0.222 |  |

**Pipeline `sugar beet leaf ∩ crop plant`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 772 |  |  | 9.553 |  |  | 0.000 |  |
| 05-15 | 399 |  |  | 3.041 |  |  | 0.000 |  |
| 05-26 | 170 |  |  | 9.791 |  |  | 0.000 |  |
| 06-05 | 203 |  |  | 22.155 |  |  | 0.000 |  |

**Pipeline `plant (all green vs GT crop+weed)`**

| date | images | count_mae | count_bias | canopy_mae_pts | weed_share_mae_pts | iou_veg | iou_crop | iou_weed |
|---|---|---|---|---|---|---|---|---|
| all | 772 | 4.190 | -4.144 | 0.616 |  | 0.881 |  |  |
| 05-15 | 399 | 3.386 | -3.346 | 0.210 |  | 0.847 |  |  |
| 05-26 | 170 | 4.235 | -4.224 | 0.950 |  | 0.848 |  |  |
| 06-05 | 203 | 5.734 | -5.645 | 1.134 |  | 0.904 |  |  |

## Files

- `threshold_sweep.csv`: precision/recall/F1/count error per prompt and threshold
- `gt_matches.csv`: one row per GT instance per prompt (visibility, crowding, size, date, matched, IoU)
- `images.csv`: product metrics per image

Data: PhenoBench (Weyler et al., IEEE TPAMI 2024), CC BY-NC-SA 4.0 per the v1.1.0 release README.