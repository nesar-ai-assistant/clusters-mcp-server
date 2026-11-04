---
name: clusters-tour
description: Five-minute all-local tour of the cluster server - fetch catalogues, M500-z overlay, sky map, counts, crossmatch, mass calibration, selection functions, WL profiles, LCDM prediction; one call per tool family with expected numbers
---

# Galaxy-cluster catalogues tour

Goal: touch every tool once, all locally, in under five minutes, using a single
`output_dir` (e.g. `output/tour`). PSZ2 and the SPT catalogues are bundled.
ACT DR6 (26 MB) and eRASS1 (24 MB .tgz) download on first use and are cached.

1. **What is here**: call `list_clusters_datasets`. Expect 8 catalogues: psz2, spt_sz,
   sptpol_100d, spt_ecs, spt3g_5yr, act_dr6, erass1 and erass1_cosmo.
   Then call `describe_catalog_columns("psz2")`. Quote the mass convention: MSZ is hydrostatic.
2. **Fetch** (`require_redshift=true, require_mass=true`) for each catalogue.
   Sanity counts, with "before cuts → after" as `n_catalog → n_selected`:

   | dataset | before cuts | after cuts | median M500 |
   |---|---|---|---|
   | psz2 | 1653 | 1093 | 4.7e14 |
   | spt_sz | 677 | 516 | 4.1e14 |
   | act_dr6 | 10040 | 10040 | 2.8e14 |
   | erass1 | 12247 | 10441 | 1.95e14 |
   | spt3g_5yr (optional) | 8892 | 7191 | 1.66e14 |

   If a total differs, the file changed upstream: stop and report.
3. **M500-z plane**: `plot_mass_redshift(catalogs=[all CSVs])`.
4. **Sky map**: `plot_cluster_sky_map(catalogs=[...], coords="equatorial")`.
5. **Counts**: `compute_cluster_counts(catalogs=[spt_sz CSV, act_dr6 CSV], m500_min=4)`.
   Output includes Poisson errors (N_poisson_err column).
6. **Selection functions**:
   - `fetch_cluster_selection_function(dataset="psz2")`: completeness C(Y500, θ500). Expect 12 SNR thresholds, 32×30 grid.
   - `fetch_cluster_selection_function(dataset="spt_sz")`: 19 fields, total ~2459 deg².
   - `fetch_cluster_selection_function(dataset="act_dr6")`: 293 tiles, total ~12590 deg².
   - `plot_completeness(dataset="psz2")`: heatmap at q≥6.
7. **WL shear profiles**: `fetch_cluster_wl_profiles(dataset="spt_sz")`.
   Expect 19 Megacam tangential shear profiles (g_t vs r).
8. **Crossmatch + mass calibration**:
   - `crossmatch_catalogs(catalog_a=<act_dr6 CSV>, catalog_b=<psz2 CSV>, radius_arcmin=3)` → ~386 matches.
   - `compare_mass_calibration(matched_csv)` → median M_Planck/M_ACT ≈ 0.80 ± 0.02.
9. **LCDM counts**:
   - `predict_cluster_counts_lcdm(m500_min=5, z_edges=[0.25,0.4,0.55,0.7,0.85,1.0,1.2,1.5], observed_catalog="spt_sz")`.
   - Expect ~138 predicted vs 105 observed at σ8=0.8; best σ8 ≈ 0.78.
   - `plot_counts_vs_prediction([<json>])`.
10. **Report**: catalogue counts; M500-z picture; mass ratio; obs/pred; completeness; WL profiles.

For more depth, use `multi-survey-mass-redshift`, `sz-xray-crossmatch` and
`cluster-counts-vs-lcdm`. Heavy prediction scans can be dispatched: see `hpc-dispatch-handoff`.
