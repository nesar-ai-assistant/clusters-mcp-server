---
name: sz-xray-crossmatch
description: Cross-match SZ catalogues (ACT DR6, SPT-SZ, SPT-3G, Planck PSZ2) with each other and with eROSITA eRASS1, and quantify relative mass calibration (median M500 ratio, log scatter, z trend, slope) - recovers the Planck hydrostatic bias 1-b~0.8
---

# SZ-vs-SZ and SZ-vs-X-ray mass calibration

Goal: relative mass bias and scatter between surveys for matched clusters.
Ratios are always M500[b]/M500[a]; keep the order fixed when reporting.

1. **Fetch** with `require_mass=true`. For eRASS1, also set `require_redshift=true`.
2. **Choose a match radius**:
   - 2' for ACT/SPT/eRASS1 pairs (arcmin-scale beams and PSFs)
   - 3' for anything involving Planck (5' beam)

   Keep `max_dz=0.1`, which means |Δz|/(1+z) < 0.1. Photo-z catalogues need this
   loose a cut. Set `max_dz=null` for a positional-only match.
3. **SZ vs SZ** (`crossmatch_catalogs` then `compare_mass_calibration`):
   - a = SPT-SZ, b = ACT DR6 (snr_min=5): ~405 matches, ratio ≈ 0.98
   - a = SPT-SZ, b = SPT-3G: ~279 matches, ratio ≈ 1.00 (same calibration chain)
   - a = SPT-SZ, b = PSZ2 (3'): ~81 matches, ratio ≈ 0.83
   - a = ACT DR6, b = PSZ2 (3'): ~386 matches, ratio 0.80 ± 0.02, ln-scatter 0.34

   The Planck numbers are the hydrostatic mass bias. Planck 2015 XXIV used 1−b = 0.8
   as the baseline. WL calibrations give 0.6-0.8.
4. **SZ vs eROSITA** (a = SZ, b = eRASS1 with mass + z):
   - SPT-SZ: ~330 matches, ratio 0.95 ± 0.01, ln-scatter 0.26
   - SPT-3G: ~655 matches, ratio 0.91 ± 0.01
   - ACT DR6 (a = eRASS1, b = ACT): ~1955 matches, M_ACT/M_eRASS1 ≈ 1.01
   - PSZ2: ~432 matches, M_eRASS1/M_Planck ≈ 1.33 (≈ 1/0.75, the same hydrostatic offset)

   Read `z_bins`: SPT/eRASS1 trends down to ~0.89 at z > 0.6. That is where eRASS1 is
   flux limited and Eddington biased upward.
5. **Slope**: `fit.slope_bisector` (pivot 3e14). A slope below 1 means the two mass proxies
   have a different mass dependence. The OLS slope is biased low by scatter and selection,
   so quote the bisector and say it has no error deconvolution.
6. **Report**: for each pair, give n_matched, match fractions, the median ratio ± bootstrap
   error, ln-scatter, the z trend, and the PNG/CSV paths. Interpret relative to the
   calibration source:
   - SPT and ACT DR6 are WL calibrated, so they agree to ~2-3%
   - eRASS1 is WL calibrated with a different method, so expect ~5-10% offsets
   - Planck is hydrostatic, so expect ~20% low

   Do not call a 5% offset a "tension". Calibration systematics are 5-10% per survey.
