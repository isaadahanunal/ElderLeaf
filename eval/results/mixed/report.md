# Mixed scenes: fixed words vs prompt agent (ranked) vs agent scan mode

Confidence threshold 0.5. LLMs: spark-open-1026, wonder-1.0. Scores use the app's final masks (tiny masks dropped, duplicates merged, crop wins over weed), matched one-to-one at IoU ≥ 0.5, so PhenoBench numbers differ a little from compare.md (raw masks). `right_crop_f1` also requires the right crop name (– when the system cannot tell crops apart). CropAndWeed plants of unsorted or rare species are ignored. CropAndWeed images may not be published (licence); these numbers may.

## PhenoBench (sugar beet, weeds as one class)

772 photos.

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 772 | 0.595 | 0.662 | 0.627 | 0.627 | 2.657 | 0.942 | 1.109 | 0.088 | 0.003 | 0.005 | – | – |
| fixed crop name | 772 | 0.833 | 0.485 | 0.613 | 0.613 | 3.878 | -3.513 | 0.768 | 0.301 | 0.191 | 0.234 | – | – |
| agent (ranked) · spark-open-1026 | 772 | 0.780 | 0.484 | 0.598 | 0.598 | 3.797 | -3.183 | 1.059 | 0.310 | 0.215 | 0.254 | – | – |
| agent (scan) · spark-open-1026 | 772 | 0.775 | 0.424 | 0.548 | 0.548 | 4.457 | -3.804 | 4.266 | 0.310 | 0.206 | 0.248 | – | – |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 11.9s |
| fixed crop name | 2.00 | $0.0050 | 11.9s |
| agent (ranked) · spark-open-1026 | 3.70 | $0.0130 | 51.5s |
| agent (scan) · spark-open-1026 | 2.20 | $0.0096 | 24.6s |

100 photos that every system ran on (incl. agent (ranked) · wonder-1.0, agent (scan) · wonder-1.0).

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 100 | 0.584 | 0.652 | 0.616 | 0.616 | 2.690 | 1.010 | 1.164 | 0.050 | 0.002 | 0.004 | – | – |
| fixed crop name | 100 | 0.808 | 0.441 | 0.570 | 0.570 | 4.400 | -3.980 | 0.787 | 0.277 | 0.209 | 0.238 | – | – |
| agent (ranked) · spark-open-1026 | 100 | 0.752 | 0.461 | 0.572 | 0.572 | 4.070 | -3.390 | 1.125 | 0.316 | 0.222 | 0.260 | – | – |
| agent (scan) · spark-open-1026 | 100 | 0.766 | 0.385 | 0.512 | 0.512 | 5.020 | -4.360 | 4.250 | 0.311 | 0.233 | 0.266 | – | – |
| agent (ranked) · wonder-1.0 | 100 | 0.772 | 0.457 | 0.574 | 0.574 | 4.060 | -3.580 | 0.764 | 0.316 | 0.244 | 0.275 | – | – |
| agent (scan) · wonder-1.0 | 100 | 0.759 | 0.366 | 0.494 | 0.494 | 4.930 | -4.530 | 2.962 | 0.299 | 0.258 | 0.277 | – | – |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 12.3s |
| fixed crop name | 2.00 | $0.0050 | 12.2s |
| agent (ranked) · spark-open-1026 | 3.77 | $0.0132 | 49.4s |
| agent (scan) · spark-open-1026 | 2.19 | $0.0095 | 26.1s |
| agent (ranked) · wonder-1.0 | 2.90 | $0.0257 | 39.6s |
| agent (scan) · wonder-1.0 | 2.60 | $0.0271 | 32.5s |

Scan mode, spark-open-1026: 2.2 phrases per photo (1.3 crop); named every crop of the photo in 772/772 photos; answers: ok: 772

Scan mode, wonder-1.0: 2.6 phrases per photo (1.3 crop); named every crop of the photo in 98/100 photos; answers: ok: 100

| photo | crops | scan phrases · spark-open-1026 | scan phrases · wonder-1.0 |
|---|---|---|---|
| 05-15_00052_P0030859.png | sugar beet | sugar beet seedling (sugar beet); small grass seedling (weed) | sugar beet seedling (sugar beet); grass seedling (weed); thin dry weed stem (weed) |
| 05-15_00056_P0030859.png | sugar beet | sugar beet seedling (sugar beet) | sugar beet rosette (sugar beet); small broadleaf weed seedling (weed) |
| 05-15_00071_P0030859.png | sugar beet | sugar beet seedling (sugar beet); tiny broadleaf weed seedling (weed) | sugar beet plant (sugar beet); grass seedling (weed) |
| 05-15_00075_P0030859.png | sugar beet | sugar beet seedling (sugar beet); grass seedling (weed) | sugar beet seedling (sugar beet); grass seedling (weed) |
| 05-15_00080_P0030859.png | sugar beet | sugar beet seedling (sugar beet); grass seedling (weed) | sugar beet seedling (sugar beet); sugar beet leaf (sugar beet) |
| 05-15_00093_P0030943.png | sugar beet | sugar beet seedling (sugar beet) | sugar beet seedling (sugar beet) |

## A: CropAndWeed, one crop per photo (8 crops, mostly 3+ weed species)

160 photos.

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 160 | 0.280 | 0.778 | 0.412 | 0.412 | 10.137 | 9.887 | 1.585 | 0.208 | 0.007 | 0.013 | 0.006 | 0.007 |
| fixed crop name | 160 | 0.630 | 0.244 | 0.352 | 0.352 | 4.213 | -3.112 | 2.002 | 0.448 | 0.365 | 0.402 | 0.222 | 0.445 |
| agent (ranked) · spark-open-1026 | 160 | 0.354 | 0.737 | 0.479 | 0.479 | 6.987 | 5.987 | 1.481 | 0.378 | 0.081 | 0.134 | 0.037 | 0.106 |
| agent (scan) · spark-open-1026 | 160 | 0.334 | 0.620 | 0.434 | 0.434 | 7.144 | 4.806 | 1.598 | 0.457 | 0.086 | 0.144 | 0.045 | 0.108 |
| agent (ranked) · wonder-1.0 | 160 | 0.346 | 0.728 | 0.469 | 0.469 | 7.300 | 6.225 | 1.431 | 0.447 | 0.083 | 0.139 | 0.037 | 0.108 |
| agent (scan) · wonder-1.0 | 160 | 0.345 | 0.624 | 0.444 | 0.444 | 6.831 | 4.519 | 1.851 | 0.429 | 0.115 | 0.182 | 0.061 | 0.146 |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 25.0s |
| fixed crop name | 2.00 | $0.0050 | 25.8s |
| agent (ranked) · spark-open-1026 | 3.61 | $0.0124 | 64.4s |
| agent (scan) · spark-open-1026 | 1.98 | $0.0081 | 35.2s |
| agent (ranked) · wonder-1.0 | 3.16 | $0.0252 | 56.9s |
| agent (scan) · wonder-1.0 | 2.67 | $0.0263 | 39.0s |

Crop F1 / weed F1 by crop:

| crop | fixed "plant" | fixed crop name | agent (ranked) · spark-open-1026 | agent (scan) · spark-open-1026 | agent (ranked) · wonder-1.0 | agent (scan) · wonder-1.0 |
|---|---|---|---|---|---|---|
| maize | 0.39 / 0.04 | 0.07 / 0.37 | 0.51 / 0.07 | 0.07 / 0.28 | 0.43 / 0.05 | 0.07 / 0.33 |
| sugar beet | 0.44 / 0.01 | 0.59 / 0.42 | 0.59 / 0.40 | 0.51 / 0.35 | 0.57 / 0.34 | 0.52 / 0.33 |
| sunflower | 0.42 / 0.02 | 0.00 / 0.48 | 0.49 / 0.09 | 0.48 / 0.07 | 0.49 / 0.13 | 0.47 / 0.10 |
| soybean | 0.45 / 0.02 | 0.00 / 0.36 | 0.46 / 0.00 | 0.46 / 0.00 | 0.47 / 0.05 | 0.46 / 0.01 |
| pumpkin | 0.29 / 0.00 | 0.00 / 0.41 | 0.38 / 0.21 | 0.27 / 0.22 | 0.42 / 0.23 | 0.33 / 0.29 |
| bean | 0.38 / 0.00 | 0.46 / 0.47 | 0.43 / 0.08 | 0.38 / 0.02 | 0.41 / 0.08 | 0.41 / 0.09 |
| pea | 0.48 / 0.01 | 0.60 / 0.46 | 0.49 / 0.03 | 0.49 / 0.01 | 0.49 / 0.02 | 0.49 / 0.01 |
| potato | 0.34 / 0.01 | 0.12 / 0.24 | 0.46 / 0.13 | 0.40 / 0.10 | 0.45 / 0.21 | 0.42 / 0.22 |

Scan mode, spark-open-1026: 2.0 phrases per photo (1.0 crop); named every crop of the photo in 158/160 photos; answers: ok: 160

Scan mode, wonder-1.0: 2.7 phrases per photo (1.1 crop); named every crop of the photo in 157/160 photos; answers: ok: 160

| photo | crops | scan phrases · spark-open-1026 | scan phrases · wonder-1.0 |
|---|---|---|---|
| ave-0045-0001 | bean | small bean seedling (bean); spiky rosette weed (weed) | bean seedling (bean); long serrated leaf rosette (weed); grass seedling (weed) |
| ave-0045-0013 | bean | bean seedling (bean); spiky rosette weed (weed) | bean seedling (bean); serrated leaf weed rosette (weed) |
| ave-0048-0004 | bean | bean seedling rosette (bean); spiky serrated rosette (weed) | bean seedling (bean); spiky thistle rosette (weed) |
| ave-0048-0022 | bean | bean seedling (bean); spiny thistle rosette (weed) | bean seedling (bean); spiky thistle rosette (weed); small serrated weed seedling (weed); grass blade weed (weed) |
| ave-0051-0010 | sunflower | sunflower seedling (sunflower); broadleaf weed rosette (weed); grass weed seedling (weed) | sunflower seedling (sunflower); serrated broadleaf weed rosette (weed); thin grass blade tuft (weed) |
| ave-0053-0006 | sunflower | sunflower seedling (sunflower); grass seedling (weed) | sunflower seedling (sunflower); grass seedling (weed); tiny broadleaf weed seedling (weed) |

## B-real: CropAndWeed photos with two crops

38 photos.

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 38 | 0.750 | 0.859 | 0.801 | – | 3.053 | 1.895 | 0.474 | 0.186 | 0.018 | 0.033 | 0.013 | 0.048 |
| fixed crop name | 38 | 0.588 | 0.023 | 0.044 | 0.040 | 10.921 | -10.921 | 2.101 | 0.100 | 0.108 | 0.104 | 0.060 | 0.403 |
| agent (scan) · spark-open-1026 | 38 | 0.881 | 0.702 | 0.781 | 0.460 | 3.079 | -2.132 | 0.802 | 0.117 | 0.020 | 0.035 | 0.005 | 0.113 |
| agent (scan) · wonder-1.0 | 38 | 0.919 | 0.732 | 0.815 | 0.481 | 2.816 | -2.132 | 0.399 | 0.221 | 0.043 | 0.072 | 0.005 | 0.274 |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 36.5s |
| fixed crop name | 3.00 | $0.0075 | 38.6s |
| agent (scan) · spark-open-1026 | 2.37 | $0.0096 | 46.3s |
| agent (scan) · wonder-1.0 | 2.68 | $0.0355 | 57.0s |

Scan mode, spark-open-1026: 2.4 phrases per photo (1.7 crop); named every crop of the photo in 27/38 photos; answers: ok: 38

Scan mode, wonder-1.0: 2.7 phrases per photo (1.7 crop); named every crop of the photo in 27/38 photos; answers: ok: 38

| photo | crops | scan phrases · spark-open-1026 | scan phrases · wonder-1.0 |
|---|---|---|---|
| ave-0007-0000 | sugar beet+sunflower | sugar beet seedling (sugar beet); grass seedling (weed); tiny broadleaf weed seedling (weed) | serrated thistle rosette (weed); thin grass seedling (weed); small oval-leaf rosette (weed) |
| ave-0110-0008 | maize+sunflower | maize seedling (maize); sunflower seedling (sunflower); tiny broadleaf weed seedling (weed) | maize seedling (maize); young maize sprout (maize); sunflower seedling (sunflower); star leaf weed (weed); thin grass weed (weed) |
| ave-0110-0010 | maize+sunflower | maize seedling (maize); sunflower seedling (sunflower) | maize seedling (maize); sunflower seedling (sunflower); round leaf weed rosette (weed) |
| ave-0110-0013 | maize+sunflower | maize seedling (maize); sunflower seedling (sunflower) | sunflower seedling (sunflower); maize seedling (maize) |
| ave-0110-0015 | maize+sunflower | maize seedling (maize); sunflower seedling (sunflower) | maize seedling (maize); sunflower seedling (sunflower) |
| ave-0110-0016 | maize+sunflower | maize seedling (maize); sunflower seedling (sunflower) | maize seedling (maize); tiny maize sprout (maize); sunflower seedling (sunflower); pointed leaf weed seedling (weed) |

## B-collage: two photos of different crops side by side

40 photos.

| system | photos | crop_precision | crop_recall | crop_f1 | right_crop_f1 | count_mae | count_bias | cover_mae_pts | weed_precision | weed_recall | weed_f1 | grass_recall | broadleaf_recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed "plant" | 40 | 0.334 | 0.873 | 0.484 | – | 10.675 | 10.675 | 1.606 | 0.300 | 0.005 | 0.010 | 0.010 | 0.002 |
| fixed crop name | 40 | 0.699 | 0.475 | 0.566 | 0.298 | 3.325 | -1.825 | 1.523 | 0.483 | 0.367 | 0.417 | 0.299 | 0.399 |
| agent (scan) · spark-open-1026 | 40 | 0.394 | 0.865 | 0.542 | 0.308 | 8.050 | 7.800 | 1.382 | 0.480 | 0.040 | 0.074 | 0.031 | 0.044 |
| agent (scan) · wonder-1.0 | 40 | 0.417 | 0.820 | 0.552 | 0.326 | 7.200 | 6.300 | 1.319 | 0.527 | 0.114 | 0.188 | 0.113 | 0.115 |

| system | SAM calls | $ / photo | wait |
|---|---|---|---|
| fixed "plant" | 2.00 | $0.0050 | 46.9s |
| fixed crop name | 3.00 | $0.0075 | 48.5s |
| agent (scan) · spark-open-1026 | 2.83 | $0.0106 | 58.3s |
| agent (scan) · wonder-1.0 | 3.70 | $0.0334 | 68.1s |

Scan mode, spark-open-1026: 2.8 phrases per photo (1.9 crop); named every crop of the photo in 35/40 photos; answers: ok: 40

Scan mode, wonder-1.0: 3.7 phrases per photo (2.0 crop); named every crop of the photo in 36/40 photos; answers: ok: 40

| photo | crops | scan phrases · spark-open-1026 | scan phrases · wonder-1.0 |
|---|---|---|---|
| ave-0048-0022+ave-0405-0007 | bean+potato | potato seedling (potato); bean seedling (bean); spiky thistle rosette (weed) | bean seedling (bean); potato plant (potato); spiky weed rosette (weed); tiny weed seedling (weed) |
| ave-0051-0010+ave-0405-0005 | sunflower+potato | sunflower seedling (sunflower); potato seedling (potato); spiky broadleaf weed rosette (weed); grass weed seedling (weed) | sunflower seedling (sunflower); potato seedling (potato); serrated broadleaf weed rosette (weed); thin grass seedling (weed) |
| ave-0072-0018+ave-0228-0010 | maize+sunflower | sunflower seedling (sunflower); spiny thistle rosette (weed); small broadleaf weed seedling (weed) | maize seedling (maize); sunflower seedling (sunflower); serrated weed rosette (weed); tiny broadleaf weed seedling (weed) |
| ave-0084-0020+vwg-0683-0011 | sugar beet+soybean | sugar beet seedling (sugar beet); small broadleaf weed seedling (weed) | sugar beet seedling (sugar beet); soybean seedling (soybean); small broadleaf weed rosette (weed); thin grass blade sprout (weed) |
| ave-0132-0014+ave-0202-0016 | maize+sugar beet | maize seedling (maize); sugar beet seedling (sugar beet) | maize seedling (maize); sugar beet seedling (sugar beet); tiny broadleaf weed seedling (weed) |
| ave-0134-0020+ave-0181-0001 | maize+bean | maize seedling (maize); bean seedling (bean); broadleaf weed seedling (weed); grass weed seedling (weed) | maize seedling (maize); round leaf bean seedling (bean); pale broadleaf weed seedling (weed); thin grass weed seedling (weed) |

Files: `rows.csv` (one row per photo and system), `summary.json`, `records_*.jsonl` (every call, per LLM).