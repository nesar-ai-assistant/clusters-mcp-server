---
name: cluster-counts-vs-lcdm
description: Compare observed cluster N(z) above a mass threshold with LCDM predictions (Tinker+08 HMF x Eisenstein-Hu P(k)) for SPT-SZ, ACT DR6, SPT-3G, PSZ2 or eRASS1 (DES Y6 WaZP richness counts per deg^2 as the observed side only) - obs/pred ratio, per-bin pulls, and a Poisson sigma8 profile; with the completeness/mass-calibration caveats
---

# Cluster counts vs LCDM

Goal: a sanity-level "is N(z, >M) consistent with LCDM, and which sigma8 does it
prefer" for one or more surveys. The model has NO selection function, mass scatter
or Eddington bias. It counts halos above the threshold using the catalogue's own
mass scale. Choose thresholds where each sample is close to complete.

1. **Pick the threshold and bins** (M500c, 1e14 Msun):
   - **SPT-SZ**: `m500_min=5`, `z_edges=[0.25,0.4,0.55,0.7,0.85,1.0,1.2,1.5]`.
     Bleem+15: ~100% complete above ~7e14/h at z > 0.25; ~5e14 h70 is the practical edge.
   - **ACT DR6**: `observed_catalog` = a fetch with `snr_min=5`, `m500_min=5`, same bins.
     Area is 16293 deg², taken from the registry.
   - **SPT-3G**: `m500_min=3`, same bins, 1604 deg².
   - **PSZ2**: `m500_min=6`, `z_edges=[0.05,0.15,0.25,0.35,0.5]`.
   - **eRASS1 cosmo**: `m500_min=3`, `z_edges=[0.1,...,0.8]`.
2. **Predict**: `predict_cluster_counts_lcdm(m500_min, z_edges, observed_catalog, sigma8_scan=[0.7,0.75,0.8,0.85])`,
   with fiducial Om0=0.3, h=0.7 and ns=0.965. Expected (verified 2026-11-04):

   | survey | N_pred (s8=0.8) | N_obs | obs/pred | best s8 (Poisson) |
   |---|---|---|---|---|
   | SPT-SZ M>5 | ~138 | 105 | 0.76 | ~0.78 |
   | ACT DR6 SNR>5, M>5 | ~897 | 748 | 0.83 | ~0.79 |
   | SPT-3G M>3 | ~542 | 550 | 1.02 | ~0.80 |
   | PSZ2 M>6 | ~685 | 201 | 0.29 | 0.72 (bias + incompleteness: do not quote) |
   | eRASS1 cosmo M>3 | ~4012 | 1897 | 0.47 | 0.73 (flux-limited: do not quote) |

   - The SPT-SZ preference for sigma8 ≈ 0.78 matches Bocquet+19 (σ8 = 0.77 ± 0.05 at Om = 0.3).
   - The ±0.002-0.006 "err" is Poisson only. The real uncertainty is dominated by the mass
     calibration: a 10% mass shift moves σ8 by ~0.03-0.05.
   - The PSZ2 and eRASS1 deficits are the expected signatures of a hydrostatic mass scale
     and of incompleteness. Use them to illustrate why selection modelling is needed.
3. **Plot**: `plot_counts_vs_prediction([json1, json2, ...])`. This gives dN/dz with Poisson
   errors, pulls, and the Δ(−2lnL) σ8 profiles.
4. **Variations**:
   - Om0=0.315, h=0.674, sigma8=0.811 (Planck 2018) raises N_pred by ~10-20%.
   - `mass_def="200m"` for richness/WL-style masses.
5. **Optical richness counts (DES Y6 WaZP)**: `predict_cluster_counts_lcdm` refuses `des_y6_wazp`.
   The prediction is in M500, and no mass-richness relation is shipped. You can still build the observed side:
   - `fetch_cluster_catalog("des_y6_wazp", richness_min=25, in_cosmo_only=true)` gives 33304 clusters.
   - `compute_cluster_counts([csv], z_edges=[0.1,0.3,0.5,0.7,0.9], richness_min=25)`.
   - The resulting N_per_deg2 is ≈ 0.62, 2.32, 2.78, 2.26. The last bin uses the 3176 deg² depth-limited area,
     from `compute_wazp_footprint_area`.
   - Any LCDM comparison needs an explicit, user-supplied mass-richness relation, labelled as such.
   - A WaZP × SPT crossmatch gives the matched richness-M500 table needed to build one.
6. **Report**: threshold, bins, area, N_obs vs N_pred, obs/pred, the pulls, best σ8 with the
   caveat above, and the files. Never present this as a cosmological constraint.

**Dispatch**: `predict_cluster_counts_lcdm` is heavy. Its kernel is `lcdm.kernels.predict_counts`
(numpy + scipy, JSON in and out). When `set_dispatch` is active, large σ8/Om grids run on
the facility (see `hpc-dispatch-handoff`).
