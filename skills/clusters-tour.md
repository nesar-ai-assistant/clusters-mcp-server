---
name: clusters-tour
description: Five-minute all-local tour of the cluster server - fetch Planck PSZ2 + SPT-SZ (bundled) and ACT DR6 / eRASS1 (download), M500-z overlay, sky map, N(z) counts, one crossmatch + mass calibration, one LCDM count prediction; one call per tool family with expected numbers
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
3. **M500-z plane**: `plot_mass_redshift(catalogs=[all CSVs])`. Medians:
   - eRASS1 at z ≈ 0.30 (low mass, low z: flux limited)
   - PSZ2 at z ≈ 0.22 (most massive)
   - SPT-SZ / ACT at z ≈ 0.55-0.58 (flat in mass to high z)
   - SPT-3G at z ≈ 0.73 (deepest)
4. **Sky map**: `plot_cluster_sky_map(catalogs=[...], coords="equatorial")`. Footprints:
   - SPT: southern 20h-7h, Dec < -40°
   - ACT: wide band −60° < Dec < +20°
   - eRASS1: western Galactic half
   - Planck: all-sky outside the Galactic plane
5. **Counts**: `compute_cluster_counts(catalogs=[spt_sz CSV, act_dr6 CSV], m500_min=4)`.
6. **Crossmatch + mass calibration**:
   - Run `crossmatch_catalogs(catalog_a=<act_dr6 CSV>, catalog_b=<psz2 CSV>, radius_arcmin=3)`.
     Expect ~386 matches.
   - Then run `compare_mass_calibration(matched_csv)`. Expect a median M_Planck/M_ACT of
     0.80 ± 0.02 with ln-scatter ~0.34. This is the Planck hydrostatic bias, 1−b ≈ 0.8.
7. **LCDM counts**:
   - Call `predict_cluster_counts_lcdm(m500_min=5, z_edges=[0.25,0.4,0.55,0.7,0.85,1.0,1.2,1.5], observed_catalog="spt_sz")`.
   - Expect ~138 predicted vs 105 observed (obs/pred ≈ 0.76) at sigma8 = 0.8.
   - Then call `plot_counts_vs_prediction([<json>])`.
   - Each prediction takes under a second locally.
8. **Report**: catalogue counts; the M500-z picture (SZ vs X-ray selection); the
   Planck/ACT mass ratio; obs/pred for SPT-SZ; the list of files.

For more depth, use `multi-survey-mass-redshift`, `sz-xray-crossmatch` and
`cluster-counts-vs-lcdm`. Heavy prediction scans can be dispatched: see `hpc-dispatch-handoff`.
