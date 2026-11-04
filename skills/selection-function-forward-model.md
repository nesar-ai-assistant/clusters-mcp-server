---
name: selection-function-forward-model
description: Recipe to extract selection functions and use them alongside LCDM counts - Planck PSZ2 completeness to show how the mass limit varies with z and theta, ACT tile noise, SPT field corrections, plus WL shear profiles
---

# Selection function + forward model recipe

Goal: extract the selection function data for each survey, understand completeness,
and use it to interpret the LCDM count predictions.

## Steps

1. **Planck PSZ2 completeness**:
   ```
   fetch_cluster_selection_function(output_dir, dataset="psz2")
   plot_completeness(output_dir, dataset="psz2", snr_cut=6)
   ```
   - Expect a (12, 32, 30) completeness cube: 12 SNR thresholds (4.5–10), 32 θ500 bins (0.9–35 arcmin), 30 Y500 bins.
   - At q≥6, completeness is >80% for Y500 > 4e-4 arcmin² and θ500 > 2 arcmin.
   - The 65% sky cosmology mask (MMF3_cosmology) matches the 439/507 COSMO=True clusters.

2. **ACT DR6 tile noise**:
   ```
   fetch_cluster_selection_function(output_dir, dataset="act_dr6")
   plot_completeness(output_dir, dataset="act_dr6")
   ```
   - 293 tiles, total area ~12590 deg², median y0 RMS = 1.07e-5.
   - The Q(θ500, z) filter mismatch tables encode how the matched-filter response varies across the sky.

3. **SPT-SZ field completeness**:
   ```
   fetch_cluster_selection_function(output_dir, dataset="spt_sz")
   plot_completeness(output_dir, dataset="spt_sz")
   ```
   - 19 fields, total ~2459 deg², field correction factors γ_f range from 1.08 to 1.39.
   - Detection probability: P(ξ > ξ_cut | ζ) = erfc((ξ_cut − γ_f × ζ) / √2) / 2.

4. **WL mass calibration data**:
   ```
   fetch_cluster_wl_profiles(output_dir, dataset="spt_sz")
   ```
   - 19 Megacam tangential shear profiles g_t(r) with errors.
   - These are the mass calibration inputs for the Bocquet+19 analysis.

5. **Compare with LCDM prediction**:
   ```
   predict_cluster_counts_lcdm(output_dir, m500_min=6, observed_catalog="psz2",
       z_edges=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0],
       sigma8_scan=[0.7, 0.72, 0.74, 0.76, 0.78, 0.8, 0.82, 0.84])
   ```
   - At M500 > 6e14 and z > 0, PSZ2 has ~200 clusters.
   - LCDM at σ8=0.8 predicts more; the deficit reflects the Planck hydrostatic mass bias.
   - The completeness data above shows that PSZ2 is >90% complete at this threshold for z < 0.5.

## Verified numbers (2026-11-04)

- Planck completeness: 32 θ × 30 Y bins, SNR range 4.5–10.0. At q≥6, 80% completeness at Y500 ≈ 4e-4 arcmin².
- ACT: 293 tiles, 12590 deg² total, median RMS 1.07e-5.
- SPT: 19 fields, 2459 deg², γ_f = 1.08–1.39.
- SPT WL: 19 Megacam clusters with 6–20 radial bins each.
