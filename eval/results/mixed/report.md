# Mixed scenes: fixed words vs prompt agent (ranked) vs agent scan mode

Confidence threshold 0.5. LLMs: spark-open-1026, wonder-1.0. Scores use the app's final masks (tiny masks dropped, duplicates merged, crop wins over weed), matched one-to-one at IoU ≥ 0.5, so PhenoBench numbers differ a little from compare.md (raw masks). `right_crop_f1` also requires the right crop name (– when the system cannot tell crops apart). CropAndWeed plants of unsorted or rare species are ignored. CropAndWeed images may not be published (licence); these numbers may.

## PhenoBench (sugar beet, weeds as one class)

4 photos.

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 4 | 0.714 | 0.556 | 0.625 | 0.625 | 2.000 | -1.500 | 0.186 | 0.333 | 0.143 | 0.200 | – | – |
| fixed crop name | 4 | 1.000 | 0.185 | 0.312 | 0.312 | 5.500 | -5.500 | 0.077 | 0.053 | 0.143 | 0.077 | – | – |
| agent (ranked) · spark-open-1026 | 4 | 0.600 | 0.333 | 0.429 | 0.429 | 3.500 | -3.000 | 0.170 | 0.048 | 0.143 | 0.071 | – | – |
| agent (scan) · spark-open-1026 | 4 | 1.000 | 0.185 | 0.312 | 0.312 | 5.500 | -5.500 | 0.084 | 0.045 | 0.143 | 0.069 | – | – |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 13.7s |
| fixed crop name | 2.00 | $0.0050 | 12.0s |
| agent (ranked) · spark-open-1026 | 4.50 | $0.0154 | 36.2s |
| agent (scan) · spark-open-1026 | 2.00 | $0.0086 | 21.1s |

2 photos that every system ran on (incl. agent (ranked) · wonder-1.0, agent (scan) · wonder-1.0).

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 2 | 0.571 | 0.571 | 0.571 | 0.571 | 1.000 | 0.000 | 0.276 | 0.000 | 0.000 | 0.000 | – | – |
| fixed crop name | 2 | 1.000 | 0.143 | 0.250 | 0.250 | 6.000 | -6.000 | 0.069 | 0.000 | 0.000 | 0.000 | – | – |
| agent (ranked) · spark-open-1026 | 2 | 0.500 | 0.429 | 0.462 | 0.462 | 2.000 | -1.000 | 0.244 | 0.000 | 0.000 | 0.000 | – | – |
| agent (scan) · spark-open-1026 | 2 | 1.000 | 0.143 | 0.250 | 0.250 | 6.000 | -6.000 | 0.072 | 0.000 | 0.000 | 0.000 | – | – |
| agent (ranked) · wonder-1.0 | 2 | 1.000 | 0.286 | 0.444 | 0.444 | 5.000 | -5.000 | 0.026 | 0.000 | 0.000 | 0.000 | – | – |
| agent (scan) · wonder-1.0 | 2 | 1.000 | 0.143 | 0.250 | 0.250 | 6.000 | -6.000 | 0.072 | 0.000 | 0.000 | 0.000 | – | – |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 14.1s |
| fixed crop name | 2.00 | $0.0050 | 12.1s |
| agent (ranked) · spark-open-1026 | 5.50 | $0.0180 | 42.9s |
| agent (scan) · spark-open-1026 | 2.00 | $0.0092 | 20.3s |
| agent (ranked) · wonder-1.0 | 2.50 | $0.0239 | 21.2s |
| agent (scan) · wonder-1.0 | 2.50 | $0.0276 | 17.6s |

Scan mode, spark-open-1026: 2.0 phrases per photo (1.0 crop); named every crop of the photo in 4/4 photos; answers: ok: 4

Scan mode, wonder-1.0: 2.5 phrases per photo (1.0 crop); named every crop of the photo in 2/2 photos; answers: ok: 2

| photo | crops | scan phrases · spark-open-1026 | scan phrases · wonder-1.0 |
|---|---|---|---|
| 05-15_00052_P0030859.png | sugar beet | sugar beet seedling (sugar beet); small grass seedling (weed) | sugar beet seedling (sugar beet); grass seedling (weed); thin dry weed stem (weed) |
| 05-15_00282_P0030792.png | sugar beet | sugar beet seedling (sugar beet); grass seedling (weed) | sugar beet seedling (sugar beet); grass seedling (weed) |

## A: CropAndWeed, one crop per photo (8 crops, mostly 3+ weed species)

1 photos.

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 1 | 0.286 | 1.000 | 0.444 | 0.444 | 5.000 | 5.000 | 0.186 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| fixed crop name | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 2.000 | -2.000 | 0.471 | 0.333 | 0.400 | 0.364 | 0.000 | 0.500 |
| agent (ranked) · spark-open-1026 | 1 | 1.000 | 0.500 | 0.667 | 0.667 | 1.000 | -1.000 | 0.005 | 0.400 | 0.400 | 0.400 | 0.000 | 0.500 |
| agent (scan) · spark-open-1026 | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 2.000 | -2.000 | 0.471 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| agent (ranked) · wonder-1.0 | 1 | 0.400 | 1.000 | 0.571 | 0.571 | 3.000 | 3.000 | 0.132 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| agent (scan) · wonder-1.0 | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 2.000 | -2.000 | 0.471 | 0.333 | 0.200 | 0.250 | 0.000 | 0.250 |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 14.6s |
| fixed crop name | 2.00 | $0.0050 | 14.6s |
| agent (ranked) · spark-open-1026 | 6.00 | $0.0198 | 37.4s |
| agent (scan) · spark-open-1026 | 1.00 | $0.0055 | 12.8s |
| agent (ranked) · wonder-1.0 | 3.00 | $0.0240 | 14.2s |
| agent (scan) · wonder-1.0 | 2.00 | $0.0225 | 12.9s |

Crop F1 / weed F1 by crop:

| crop | fixed "plant" | fixed crop name | agent (ranked) · spark-open-1026 | agent (scan) · spark-open-1026 | agent (ranked) · wonder-1.0 | agent (scan) · wonder-1.0 |
|---|---|---|---|---|---|---|
| maize | 0.44 / 0.00 | 0.00 / 0.36 | 0.67 / 0.40 | 0.00 / 0.00 | 0.57 / 0.00 | 0.00 / 0.25 |

Scan mode, spark-open-1026: 1.0 phrases per photo (1.0 crop); named every crop of the photo in 1/1 photos; answers: ok: 1

Scan mode, wonder-1.0: 2.0 phrases per photo (1.0 crop); named every crop of the photo in 1/1 photos; answers: ok: 1

| photo | crops | scan phrases · spark-open-1026 | scan phrases · wonder-1.0 |
|---|---|---|---|
| vwg-0709-0009 | maize | maize seedling (maize) | maize seedling (maize); tiny broadleaf weed seedling (weed) |

## B-real: CropAndWeed photos with two crops

1 photos.

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 1 | 0.107 | 0.333 | 0.162 | – | 21.000 | 21.000 | 7.307 | 0.375 | 0.061 | 0.105 | 0.000 | 0.077 |
| fixed crop name | 1 | 0.125 | 0.111 | 0.118 | 0.118 | 0.000 | 0.000 | 6.295 | 0.407 | 0.224 | 0.289 | 0.100 | 0.256 |
| agent (scan) · spark-open-1026 | 1 | 0.111 | 0.111 | 0.111 | 0.111 | 1.000 | 1.000 | 6.576 | 0.400 | 0.163 | 0.232 | 0.100 | 0.179 |
| agent (scan) · wonder-1.0 | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 9.000 | -9.000 | 0.349 | 0.667 | 0.204 | 0.312 | 0.000 | 0.256 |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 14.2s |
| fixed crop name | 3.00 | $0.0075 | 18.2s |
| agent (scan) · spark-open-1026 | 3.00 | $0.0123 | 25.1s |
| agent (scan) · wonder-1.0 | 3.00 | $0.0360 | 29.2s |

Scan mode, spark-open-1026: 3.0 phrases per photo (1.0 crop); named every crop of the photo in 0/1 photos; answers: ok: 1

Scan mode, wonder-1.0: 3.0 phrases per photo (0.0 crop); named every crop of the photo in 0/1 photos; answers: ok: 1

| photo | crops | scan phrases · spark-open-1026 | scan phrases · wonder-1.0 |
|---|---|---|---|
| ave-0007-0000 | sugar beet+sunflower | sugar beet seedling (sugar beet); grass seedling (weed); tiny broadleaf weed seedling (weed) | serrated thistle rosette (weed); thin grass seedling (weed); small oval-leaf rosette (weed) |

## B-collage: two photos of different crops side by side

1 photos.

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 1 | 0.308 | 1.000 | 0.471 | – | 9.000 | 9.000 | 0.988 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| fixed crop name | 1 | 0.571 | 1.000 | 0.727 | 0.364 | 3.000 | 3.000 | 0.746 | 0.333 | 0.250 | 0.286 | 0.000 | 0.333 |
| agent (scan) · spark-open-1026 | 1 | 0.444 | 1.000 | 0.615 | 0.308 | 5.000 | 5.000 | 0.893 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| agent (scan) · wonder-1.0 | 1 | 0.333 | 1.000 | 0.500 | 0.250 | 8.000 | 8.000 | 0.975 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 16.1s |
| fixed crop name | 3.00 | $0.0075 | 16.1s |
| agent (scan) · spark-open-1026 | 2.00 | $0.0086 | 17.4s |
| agent (scan) · wonder-1.0 | 4.00 | $0.0371 | 19.5s |

Scan mode, spark-open-1026: 2.0 phrases per photo (1.0 crop); named every crop of the photo in 0/1 photos; answers: ok: 1

Scan mode, wonder-1.0: 4.0 phrases per photo (2.0 crop); named every crop of the photo in 1/1 photos; answers: ok: 1

| photo | crops | scan phrases · spark-open-1026 | scan phrases · wonder-1.0 |
|---|---|---|---|
| ave-0084-0020+vwg-0683-0011 | sugar beet+soybean | sugar beet seedling (sugar beet); small broadleaf weed seedling (weed) | sugar beet seedling (sugar beet); soybean seedling (soybean); small broadleaf weed rosette (weed); thin grass blade sprout (weed) |

Files: `rows.csv` (one row per photo and system), `summary.json`, `records_*.jsonl` (every call, per LLM).