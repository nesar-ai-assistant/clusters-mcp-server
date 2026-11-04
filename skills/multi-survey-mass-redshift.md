---
name: multi-survey-mass-redshift
description: Reproduce the classic SZ/X-ray cluster mass-redshift comparison figure (SPT Bleem+15 Fig. 6 style) - SPT-SZ, SPTpol, SPT-3G, ACT DR6, Planck PSZ2 and eRASS1 on one M500-z plane, with completeness-threshold annotations and the mass-convention caveats
---

# Multi-survey M500-z plane

Goal: one figure showing how each survey's selection carves the M500-z plane,
plus the numbers that describe it. Use one `output_dir`.

1. **Fetch** each catalogue with `require_redshift=true, require_mass=true`:
   - `psz2`: 1093
   - `spt_sz`: 516
   - `sptpol_100d`: 79
   - `spt_ecs`: 448
   - `spt3g_5yr`: 7191
   - `act_dr6`: 10040
   - `erass1`: 10441

   For a cleaner SZ comparison, also fetch `act_dr6` with `snr_min=5` (6521).
2. **Read the conventions** with `describe_catalog_columns(<key>, show_native=false)` for
   each catalogue. Masses are NOT on a common calibration:
   - SPT: xi-mass, WL + X-ray calibrated, at fixed Om=0.3, h=0.7, s8=0.8
   - ACT DR6: WL-consistent normalisation, Eddington corrected; `A10_M500cUncorr` is the Planck-like native column
   - PSZ2 MSZ: hydrostatic, no (1−b), expected ~20% low
   - eRASS1: count-rate-mass relation from the eRASS1 cosmology analysis
3. **Plot**: `plot_mass_redshift(catalogs=[...], log_mass=true, z_max=1.8)`.
   Medians from `per_survey`:

   | survey | z_med | M500_med (1e14) |
   |---|---|---|
   | PSZ2 | 0.22 | 4.7 |
   | SPT-SZ | 0.55 | 4.1 |
   | SPT-ECS | ~0.49 | 4.4 |
   | ACT DR6 | 0.58 | 2.8 |
   | SPT-3G | 0.73 | 1.66 |
   | eRASS1 | 0.30 | 1.95 |

   - SZ samples show a nearly z-independent mass floor (SPT-SZ ~3e14, ACT ~2e14, SPT-3G ~1.2e14).
   - Planck's floor rises steeply with z (5' beam).
   - eRASS1 is flux limited: groups below 1e14 at z < 0.1, dropping out by z ~ 0.6.
4. **Sky context**: `plot_cluster_sky_map(... coords="galactic")` shows the eRASS1 half-sky.
5. **Counts by survey**: `compute_cluster_counts(catalogs=[...], m500_min=3)`.
   Use the N(z) and N(>M) per deg² (registry areas: SPT-SZ 2500, SPT-3G 1604, ACT 16293,
   eRASS1 13116, PSZ2 34487 deg²) to compare depth at fixed mass.
   - At M500 > 3e14, SPT-3G has the highest surface density.
   - eRASS1 dominates below 1e14.
6. **Report**: the figure path, the medians table, the mass-floor statements, and the
   explicit caveat that cross-survey mass offsets are 5-25% (quantify with `sz-xray-crossmatch`).
