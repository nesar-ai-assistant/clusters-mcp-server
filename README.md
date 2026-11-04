# clusters-mcp-server

**Galaxy Cluster Catalogs MCP Server.** An MCP server for public SZ and X-ray galaxy-cluster catalogues:

- Planck PSZ2
- SPT-SZ 2500d (Bocquet+19), SPTpol 100d, SPT-ECS and SPT-3G Main 5yr
- ACT DR6
- eROSITA eRASS1, primary and cosmology samples

Each catalogue downloads on demand and is harmonised to one schema.

## Data products

| dataset | Catalogs | Summary statistics | Published results |
|---|---|---|---|
| psz2 | SZ cluster catalog (1653) | Completeness C(Y500, θ500) for MMF3/union masks | — |
| spt_sz | SZ cluster catalog (677) | Field areas + noise corrections (19 fields); Megacam/HST WL shear profiles (32 clusters) | σ8(Ωm/0.3)^0.2 = 0.766±0.025 (Bocquet+19) |
| sptpol_100d | SZ cluster catalog (89) | — | — |
| spt_ecs | SZ cluster catalog (470) | — | — |
| spt3g_5yr | SZ cluster catalog (8892) | — | — |
| act_dr6 | SZ cluster catalog (10040) | Q(θ500, z) per tile; tile RMS noise levels (293 tiles) | — |
| erass1 | X-ray cluster catalog (12247) | — | — |
| erass1_cosmo | Cosmology subsample (5259) | — | S8 = 0.86±0.01 (Ghirardini+24) |

- All URLs were verified by download on 2026-11-04.
- Build analyses on catalogs and summary statistics; published results are for comparison only.
- The cache lives in `~/.cache/cosmo-mcp/clusters-mcp-server/`; override it with `$COSMO_MCP_DATA`.

**Selection functions:**
- **Planck PSZ2:** survey completeness C(Y500, θ500) at various SNR cuts, range-fetched from the 403 MB IRSA FITS (~120 KB tail).
- **ACT DR6:** Q-filter mismatch per tile (QFit.fits, 293 tiles) + tile noise levels (RMSTab), streamed from the 7.4 GB nemo tarball (~2 MB extracted).
- **SPT-SZ:** field-by-field areas and noise correction factors (Bocquet+19), hard-coded (no download).
- **eRASS1:** selection function not publicly released (Clerc+24 describes the method but data files are not downloadable).

**Weak-lensing shear profiles:**
- **SPT-SZ:** 19 Megacam tangential shear profiles + 13 HST shear datasets from the SPT-SZ cluster likelihood (Bocquet+19).

| | |
|---|---|
| ![M500-z](docs/figures/mass_redshift.png) | ![sky](docs/figures/sky_map_equatorial.png) |
| ![Planck completeness](docs/figures/psz2_completeness_MMF3_cosmology.png) | ![SPT fields](docs/figures/spt_sz_selfunc.png) |

## Harmonised schema

Every catalogue is written with these columns:
- name, ra, dec [deg]
- z, z_err
- **M500** [1e14 Msun, M500c], M500_err_lo, M500_err_hi
- snr: the survey-native statistic
- survey, dataset

**Masses come from each survey's own scaling relation.** Run `describe_catalog_columns` to see which.

## Tools

| tool | kind | what |
|---|---|---|
| `list_clusters_datasets`, `describe_clusters_dataset`, `list_clusters_skills`, `load_clusters_skill` | meta | discovery |
| `fetch_cluster_catalog` | catalog | download + harmonise + z/mass/SNR cuts → CSV |
| `describe_catalog_columns` | catalog | mapping, units, mass conventions, native FITS columns |
| `plot_mass_redshift` | catalog | multi-survey M500–z overlay |
| `plot_cluster_sky_map` | catalog | Mollweide map (equatorial/galactic), coloured by survey/z/M500 |
| `crossmatch_catalogs` | catalog | KD-tree angular + Δz/(1+z) one-to-one match → matched CSV |
| `compute_cluster_counts` | summary_statistic | N(z) and N(>M) with Poisson errors, raw and per deg² |
| `compare_mass_calibration` | summary_statistic | M500_b vs M500_a: median ratio ± bootstrap, ln scatter |
| `fetch_cluster_selection_function` | summary_statistic | survey completeness (Planck/ACT/SPT) |
| `fetch_cluster_wl_profiles` | summary_statistic | WL tangential shear profiles (SPT-SZ Megacam) |
| `plot_completeness` | summary_statistic | completeness heatmap (Planck) / noise histogram (ACT) / field bar (SPT) |
| `predict_cluster_counts_lcdm` (**heavy**) | summary_statistic | Tinker+08 × EH98 dN/dz above M for a sky area |
| `plot_counts_vs_prediction` | summary_statistic | observed N(z) vs LCDM with pulls and σ8 profile |
| `set_dispatch`, `get_dispatch`, `auth_status`, `export_dispatch_pack` | — | HPC dispatch (generic) |

## Skills

- `clusters-tour`
- `multi-survey-mass-redshift`
- `sz-xray-crossmatch`
- `cluster-counts-vs-lcdm`
- `hpc-dispatch-handoff`

## Key numbers (verified)

- **Planck PSZ2 completeness:** 12 SNR thresholds (4.5–10), 32 θ500 bins (0.9–35′), 30 Y500 bins (1.1e-4–0.072 arcmin²). At q≥6 the survey is >80% complete above Y500 ≈ 4e-4 arcmin² for θ500 > 2′.
- **ACT DR6 selection function:** 293 tiles, total 12590 deg², median y0 RMS = 1.07e-5.
- **SPT-SZ WL:** 19 Megacam + 13 HST clusters with shear profiles (r ~ 0.01–0.5 deg).
- **ACT DR6 × PSZ2** (3′): 386 matches. M_Planck/M_ACT = 0.80 ± 0.02, ln-scatter 0.34.
- **SPT-SZ, M500 > 5e14, z > 0.25:** LCDM (σ8=0.8) predicts 138 vs 105 observed → best σ8 ≈ 0.78.

## Install / run

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
MPLBACKEND=Agg .venv/bin/python -m pytest -q        # includes network tests
.venv/bin/python tests/smoke_server.py
./run_server.sh                                     # stdio; or: .venv/bin/python -m mcp_server --transport http --port 8014
```

## Caveats

- `predict_cluster_counts_lcdm` has no selection function, mass–observable scatter or Eddington bias. It is a sanity check, not a cosmology constraint.
- Cross-survey masses use different calibrations, with 5–25% offsets.
- eRASS1 selection function is not publicly released.
