"""fetch_cluster_selection_function, fetch_cluster_wl_profiles, fit_cluster_wl_mass, plot_completeness."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import pandas as pd
from pydantic import Field, validate_call

from ..common import ArtifactResult, data_cache_dir, data_kind, mpl, ok, resolve_outdir, save_fig
from ..registry import DATASETS

# ---------------------------------------------------------------------------
# Planck PSZ2 completeness: range-fetch the tail of the 403 MB FITS file
# ---------------------------------------------------------------------------
_PLANCK_SELFN_TAIL_BYTES = 130_000  # the completeness HDUs sit in the last ~120 KB

def _planck_completeness(variant: str = "MMF3_cosmology") -> dict:
    """Download the tail of the Planck selection-function FITS and parse the completeness cube."""
    from astropy.io import fits as pyfits

    meta = DATASETS["psz2"]["selection_function"]["files"][variant]
    url = meta["url"]
    total = meta["size_bytes"]
    cache = data_cache_dir() / "planck"
    cache.mkdir(parents=True, exist_ok=True)
    tail_path = cache / f"selfunc_tail_{variant}.bin"

    if not tail_path.is_file() or tail_path.stat().st_size < _PLANCK_SELFN_TAIL_BYTES:
        import urllib.request
        start = total - _PLANCK_SELFN_TAIL_BYTES
        req = urllib.request.Request(url, headers={
            "Range": f"bytes={start}-{total - 1}",
            "User-Agent": "cosmo-mcp-server/0.1",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        tail_path.write_bytes(data)

    raw = tail_path.read_bytes()
    idx = raw.find(b"XTENSION")
    if idx < 0:
        raise RuntimeError(f"No XTENSION found in tail of {url}")

    primary = pyfits.PrimaryHDU().header.tostring().encode()
    hdulist = pyfits.open(io.BytesIO(primary + raw[idx:]), ignore_missing_end=True)

    result: dict = {}
    for hdu in hdulist[1:]:
        name = hdu.name
        arr = np.asarray(hdu.data, dtype=float)
        if name == "SELFUNC":
            result["completeness"] = arr  # shape (n_snr, n_theta, n_y)
        elif name == "YGRID":
            result["y500_grid"] = arr  # arcmin^2
        elif name == "TGRID":
            result["theta500_grid"] = arr  # arcmin
        elif name == "SNR_THRESH":
            result["snr_thresholds"] = arr
    hdulist.close()
    return result


# ---------------------------------------------------------------------------
# ACT DR6: Q(theta500, z) per tile + RMS noise table
# ---------------------------------------------------------------------------
def _act_qfit_rmstab() -> dict:
    """Return QFit and RMSTab from a previously extracted ACT selFn directory, or download."""
    from astropy.io import fits as pyfits

    cache = data_cache_dir() / "act" / "selFn"
    qfit_path = cache / "QFit.fits"
    rms_path = cache / "RMSTab_maxFlags0.fits"

    if not (qfit_path.is_file() and rms_path.is_file()):
        # Stream the 7.4 GB tarball and extract only the small selFn files
        import urllib.request
        url = DATASETS["act_dr6"]["selection_function"]["tarball_url"]
        wanted = {
            "DR6ClusterSearch/selFn/QFit.fits",
            "DR6ClusterSearch/selFn/RMSTab_maxFlags0.fits",
            "DR6ClusterSearch/selFn/config.yml",
            "DR6ClusterSearch/selFn/tileAreas.txt",
        }
        cache.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "cosmo-mcp-server/0.1"})
        resp = urllib.request.urlopen(req, timeout=600)
        with tarfile.open(fileobj=resp, mode="r|gz") as tf:
            for member in tf:
                if member.name in wanted and member.isfile():
                    fh = tf.extractfile(member)
                    if fh is not None:
                        dest = cache / member.name.replace("DR6ClusterSearch/selFn/", "")
                        dest.write_bytes(fh.read())
        resp.close()

    # Parse QFit: one HDU per tile, each has columns (Q, theta500Arcmin, z)
    hdulist = pyfits.open(qfit_path)
    tiles = {}
    for hdu in hdulist[1:]:
        tile = hdu.name
        t = hdu.data
        tiles[tile] = {
            "Q": np.asarray(t["Q"], float).tolist(),
            "theta500Arcmin": np.asarray(t["theta500Arcmin"], float).tolist(),
            "z": np.asarray(t["z"], float).tolist(),
        }
    hdulist.close()

    # Parse RMSTab
    rms = pyfits.open(rms_path)[1].data
    rms_df = pd.DataFrame({
        "tileName": np.char.strip(np.asarray(rms["tileName"], str)),
        "areaDeg2": np.asarray(rms["areaDeg2"], float),
        "y0RMS": np.asarray(rms["y0RMS"], float),
    })
    total_area = float(rms_df["areaDeg2"].sum())

    return {
        "n_tiles": len(tiles),
        "total_area_deg2": total_area,
        "rms_median": float(rms_df["y0RMS"].median()),
        "rms_p5": float(np.percentile(rms_df["y0RMS"], 5)),
        "rms_p95": float(np.percentile(rms_df["y0RMS"], 95)),
        "tiles_sample": dict(list(tiles.items())[:3]),
    }


# ---------------------------------------------------------------------------
# SPT-SZ field completeness: areas + noise correction factors
# ---------------------------------------------------------------------------
def _spt_field_completeness() -> dict:
    """Return SPT-SZ field names, areas, and noise correction factors."""
    field_names = (
        'ra5h30dec-55', 'ra23h30dec-55', 'ra21hdec-60', 'ra3h30dec-60',
        'ra21hdec-50', 'ra4h10dec-50', 'ra0h50dec-50', 'ra2h30dec-50', 'ra1hdec-60',
        'ra5h30dec-45', 'ra6h30dec-55', 'ra3h30dec-42.5', 'ra23hdec-62.5',
        'ra21hdec-42.5', 'ra1hdec-42.5', 'ra22h30dec-55', 'ra23hdec-45',
        'ra6h30dec-45', 'ra6hdec-62.5',
    )
    field_areas = (
        82.8711, 100.241, 147.589, 222.647, 189.955, 155.547, 156.243,
        155.731, 145.888, 102.657, 83.2849, 166.812, 70.4952, 111.217,
        108.625, 83.6339, 204.453, 102.832, 68.6716,
    )
    field_corrections = (
        1.3267815, 1.3875717, 1.2923182, 1.2479916, 1.1095432,
        1.2668965, 1.1357954, 1.1901025, 1.1754438, 1.0798830,
        1.1631297, 1.1999745, 1.1762851, 1.1490106, 1.1916442,
        1.1307591, 1.1864938, 1.1629247, 1.1823912,
    )
    total = sum(field_areas)
    rows = [{"field": n, "area_deg2": a, "gamma_field": g}
            for n, a, g in zip(field_names, field_areas, field_corrections, strict=True)]
    return {
        "n_fields": len(field_names),
        "total_area_deg2": total,
        "fields": rows,
        "xi_cut": 5.0,
        "z_range": [0.25, 2.0],
        "model": "P(xi > xi_cut | zeta, field) = erfc((xi_cut - gamma_f * zeta) / sqrt(2)) / 2",
        "citation": "Bocquet et al. 2019 (arXiv:1812.01679), SPTcluster_data.py",
    }


# ---------------------------------------------------------------------------
# SPT-SZ weak-lensing shear profiles
# ---------------------------------------------------------------------------
def _spt_wl_profiles(output_dir: Path) -> dict:
    """Write the 19 Megacam g_t(r) profiles + source N(z) from the official SPT likelihood release."""
    from . import wl

    data = wl.read_megacam()
    zcl = wl.spt_redshifts(list(data))
    cosmo = wl.FlatLCDM()
    profiles, files = [], []
    for cluster, d in data.items():
        sh, nz = d["shear"], d["nz"]
        df = pd.DataFrame({"r_deg": sh[:, 0], "gt": sh[:, 1], "gt_err": sh[:, 2]})
        if sh.shape[1] > 3:
            df["kbin"] = sh[:, 3]
        if sh.shape[1] > 4:
            df["n_src"] = sh[:, 4].astype(int)
        z = zcl.get(cluster, np.nan)
        if np.isfinite(z):
            df["r_mpc"] = sh[:, 0] * np.pi / 180 * float(cosmo.dA(z))
        csv_path = output_dir / f"spt_wl_{cluster}.csv"
        df.to_csv(csv_path, index=False, float_format="%.6g")
        nz_path = output_dir / f"spt_wl_{cluster}_Nz.csv"
        pd.DataFrame({"z": nz[:, 0], "N": nz[:, 1]}).to_csv(nz_path, index=False, float_format="%.6g")
        files += [csv_path, nz_path]
        beta, beta2 = wl.beta_moments(nz, z, cosmo) if np.isfinite(z) else (np.nan, np.nan)
        snr = float(np.sqrt(np.sum((sh[:, 1] / sh[:, 2]) ** 2)))
        profiles.append({
            "cluster": cluster, "z_cluster": z,
            "profile_csv": csv_path.name, "nz_csv": nz_path.name,
            "n_bins": int(len(sh)),
            "r_min_deg": float(sh[:, 0].min()), "r_max_deg": float(sh[:, 0].max()),
            "r_min_mpc": float(df["r_mpc"].min()) if "r_mpc" in df else np.nan,
            "r_max_mpc": float(df["r_mpc"].max()) if "r_mpc" in df else np.nan,
            "gt_detection_snr": snr,
            "n_source_galaxies": int(nz[:, 1].sum()),
            "beta_mean": beta, "beta2_mean": beta2,
        })
    return {"n_clusters": len(profiles), "profiles": profiles, "files": files}


# =========================================================================
# Public tools
# =========================================================================

@data_kind("summary_statistic")
@validate_call
def fetch_cluster_selection_function(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for selection-function CSV/JSON.")],
    dataset: Annotated[str, Field(description="Dataset key: psz2, act_dr6, or spt_sz.")] = "psz2",
    variant: Annotated[str | None, Field(description=(
        "Planck variant: MMF3_cosmology (default, 65%% sky), union_survey (84%% sky). Ignored for ACT/SPT."
    ))] = None,
) -> ArtifactResult:
    """Fetch the survey selection function / completeness characterisation for a cluster survey.

    Use to get the detection probability as a function of the survey observable
    (Planck: completeness C(Y500, theta500); ACT: Q-filter + RMS noise per tile;
    SPT: field areas + noise correction factors). These are the inputs needed to
    forward-model cluster counts via predict_cluster_counts_lcdm.

    Planck data: range-fetches only the ~120 KB tail of the 403 MB FITS file.
    ACT data: streams the 7.4 GB tarball but extracts only the ~2 MB selFn tables.
    SPT data: hard-coded field parameters from Bocquet+19 (no download needed).
    """
    out = resolve_outdir(output_dir)

    if dataset == "psz2":
        variant = variant or "MMF3_cosmology"
        comp = _planck_completeness(variant)
        # Write completeness cube as a flat CSV
        snr_grid = comp["snr_thresholds"]
        theta_grid = comp["theta500_grid"]
        y_grid = comp["y500_grid"]
        cube = comp["completeness"]  # (n_snr, n_theta, n_y)

        # For the q>=6 cosmology cut (index where snr_grid >= 6)
        snr6_idx = int(np.searchsorted(snr_grid, 6.0))
        comp_q6 = cube[snr6_idx]  # (n_theta, n_y)

        rows = []
        for i, th in enumerate(theta_grid):
            for j, y in enumerate(y_grid):
                rows.append({"theta500_arcmin": float(th), "Y500_arcmin2": float(y),
                             "completeness": float(comp_q6[i, j])})
        csv = out / f"psz2_completeness_q6_{variant}.csv"
        pd.DataFrame(rows).to_csv(csv, index=False, float_format="%.6g")

        meta_json = {
            "dataset": dataset, "variant": variant,
            "snr_cut": float(snr_grid[snr6_idx]),
            "snr_thresholds": snr_grid.tolist(),
            "theta500_grid_arcmin": theta_grid.tolist(),
            "Y500_grid_arcmin2": y_grid.tolist(),
            "completeness_shape": list(cube.shape),
            "note": "completeness[snr_idx, theta_idx, y_idx] in [0, 1]",
        }
        jf = out / f"psz2_selfunc_{variant}.json"
        jf.write_text(json.dumps(meta_json, indent=1))
        return ok(
            f"Planck PSZ2 completeness ({variant}): {cube.shape[1]} theta x {cube.shape[2]} Y bins, "
            f"{cube.shape[0]} SNR thresholds ({snr_grid[0]:.1f}..{snr_grid[-1]:.1f}). "
            f"CSV for q>=6 written.",
            [csv, jf],
            completeness_shape=list(cube.shape),
            snr_thresholds=snr_grid.tolist(),
        )

    elif dataset == "act_dr6":
        info = _act_qfit_rmstab()
        jf = out / "act_dr6_selfunc.json"
        jf.write_text(json.dumps(info, indent=1, default=str))
        return ok(
            f"ACT DR6 selection function: {info['n_tiles']} tiles, total area {info['total_area_deg2']:.0f} deg^2, "
            f"median y0 RMS = {info['rms_median']:.2e}.",
            [jf],
            n_tiles=info["n_tiles"],
            total_area_deg2=info["total_area_deg2"],
        )

    elif dataset == "spt_sz":
        info = _spt_field_completeness()
        csv = out / "spt_sz_fields.csv"
        pd.DataFrame(info["fields"]).to_csv(csv, index=False, float_format="%.6g")
        jf = out / "spt_sz_selfunc.json"
        jf.write_text(json.dumps(info, indent=1))
        return ok(
            f"SPT-SZ completeness: {info['n_fields']} fields, total {info['total_area_deg2']:.0f} deg^2, "
            f"xi_cut={info['xi_cut']}.",
            [csv, jf],
            n_fields=info["n_fields"],
            total_area_deg2=info["total_area_deg2"],
        )
    else:
        raise ValueError(f"No selection function for dataset={dataset!r}. Use psz2, act_dr6, or spt_sz.")


_WL_COLUMNS = {
    "r_deg": "lensing-weighted mean radius of the bin [deg] from the SZ centre",
    "gt": "mean reduced tangential shear <g_t> in the bin, corrected for cluster-member contamination "
          "(Dietrich+19 eq. 18). This is the measured data, not a model.",
    "gt_err": "1-sigma error on gt (shape noise, Dietrich+19 eq. 17)",
    "kbin": "4th column of the release file, labelled 'kbin' but undocumented; NOT used by the official "
            "likelihood - do not rescale gt with it (see kbin_note)",
    "n_src": "5th (unlabelled) column: number of source galaxies in the bin",
    "r_mpc": "r_deg converted to physical Mpc with D_A(z_cluster) for flat LCDM Om=0.3, h=0.7",
}


@data_kind("summary_statistic")
@validate_call
def fetch_cluster_wl_profiles(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for WL shear profile CSVs.")],
    dataset: Annotated[str, Field(description="Dataset key (currently only spt_sz).")] = "spt_sz",
) -> ArtifactResult:
    """Fetch the measured Megacam weak-lensing tangential shear profiles of 19 SPT-SZ clusters (Dietrich+19).

    These are the REAL observed reduced-shear profiles g_t(r) from the official SPT-SZ cluster
    likelihood release (Bocquet+19), not synthetic data. One CSV per cluster (r_deg, gt, gt_err,
    kbin, n_src, r_mpc) plus one source-redshift N(z) CSV per cluster (needed for Sigma_crit /
    <beta>). Use fit_cluster_wl_mass to turn them into M500c/M200c; do not fit to bin means.
    """
    from . import wl

    if dataset != "spt_sz":
        raise ValueError(f"WL profiles not available for {dataset!r}; use spt_sz.")
    out = resolve_outdir(output_dir)
    info = _spt_wl_profiles(out)
    summary_csv = out / "spt_wl_summary.csv"
    pd.DataFrame(info["profiles"]).to_csv(summary_csv, index=False, float_format="%.6g")
    meta = DATASETS["spt_sz"]["wl_data"]
    readme = {
        "what": "Measured Magellan/Megacam weak-lensing reduced tangential shear profiles of 19 SPT-SZ clusters "
                "(Dietrich et al. 2019, MNRAS 483, 2871) as shipped in the official SPT-SZ cluster likelihood "
                "release (Bocquet et al. 2019). Real data: 8 radial bins over 0.75-2.5 Mpc per cluster.",
        "source_url": wl.RELEASE_URL,
        "archive_files": "SPT_SZ_cluster_likelihood-0.0/data/Megacam/<SPT_ID>/<SPT_ID>_shear.txt and _Nz.txt",
        "columns": _WL_COLUMNS,
        "kbin_note": meta["kbin_note"],
        "source_redshifts": "spt_wl_<SPT_ID>_Nz.csv = source redshift histogram N(z) (dz=0.025) after the "
                            "colour cuts; <beta>=<D_ls/D_s> and <beta^2> over this N(z) set Sigma_crit = "
                            "c^2/(4 pi G D_l <beta>) and the reduced-shear correction (as in the release's "
                            "lensing.py). beta_mean / beta2_mean in the summary reproduce Dietrich+19's table "
                            "of source properties (Table 3) to <=0.012.",
        "cluster_redshift": "z_cluster from the SPT-SZ 2500d catalogue (Bocquet+19)",
        "how_to_get_masses": "fit_cluster_wl_mass (NFW + c(M), reduced shear, Sigma_crit from N(z)). The release's "
                             "own likelihood additionally applies the WL bias/scatter calibration of "
                             "WLsimcalib_data.py (Megacam bias 0.938 +- 0.028 from simulations).",
        "citation": meta["citation"],
        "profiles": info["profiles"],
    }
    readme_path = out / "spt_wl_README.json"
    readme_path.write_text(json.dumps(readme, indent=1, default=float))
    return ok(
        f"SPT-SZ Megacam WL: {info['n_clusters']} measured g_t(r) profiles (Dietrich+19, official SPT likelihood "
        f"release) + source N(z) per cluster written; see spt_wl_README.json for columns.",
        [summary_csv, readme_path] + [str(f) for f in info["files"]],
        n_clusters=info["n_clusters"],
        data_origin="real measured shear profiles (Dietrich+19 Megacam), not simulated",
        source_url=wl.RELEASE_URL,
        columns=_WL_COLUMNS, kbin_note=meta["kbin_note"],
        clusters=[{k: p[k] for k in ("cluster", "z_cluster", "profile_csv", "n_bins", "r_min_mpc", "r_max_mpc",
                                     "beta_mean")} for p in info["profiles"]],
        next_step="fit_cluster_wl_mass(output_dir) for NFW M500c/M200c per cluster",
        citation=meta["citation"],
    )


@data_kind("summary_statistic")
@validate_call
def fit_cluster_wl_mass(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for the mass table, JSON and PNG.")],
    clusters: Annotated[list[str] | None, Field(description=(
        "SPT IDs (e.g. 'SPT-CLJ0516-5430'); None = all 19 Megacam clusters."))] = None,
    concentration_model: Annotated[Literal["diemer15", "diemer19", "duffy08"], Field(description=(
        "c(M,z): diemer15 (Diemer & Kravtsov 2015, used by Dietrich+19 and the SPT likelihood 'DK15'), "
        "diemer19, or duffy08 (Duffy+08 200c)."))] = "diemer15",
    r_min_mpc: Annotated[float, Field(ge=0, description=(
        "Inner fit radius [Mpc]. Profiles span 0.75-2.5 Mpc (Dietrich+19 range); the SPT likelihood uses 0.5-1.5."))] = 0.0,
    r_max_mpc: Annotated[float, Field(gt=0, description="Outer fit radius [Mpc].")] = 10.0,
    Om0: Annotated[float, Field(gt=0, lt=1, description="Flat LCDM Omega_m for distances.")] = 0.3,
    h: Annotated[float, Field(gt=0, lt=1.5, description="Hubble parameter h (masses in Msun, not Msun/h).")] = 0.7,
) -> ArtifactResult:
    """NFW weak-lensing mass of SPT-SZ Megacam clusters from their measured g_t(r) profiles.

    Use after (or instead of) fetch_cluster_wl_profiles to get M500c and M200c [1e14 Msun]
    with 68% intervals per cluster. Model (mirrors the release's lensing.py): NFW with c fixed
    by c(M,z), Sigma_crit from each cluster's source N(z) via <beta>, reduced shear
    g = gamma/(1-kappa) (1 + kappa(<beta^2>/<beta>^2 - 1)), Gaussian likelihood, flat prior in
    ln M200c. Reports the ratio to the Dietrich+19 published masses where available. These
    are raw NFW masses: no simulation-calibrated WL bias (~0.94) or LSS scatter is applied.
    """
    from . import wl

    data = wl.read_megacam()
    names = clusters or list(data)
    bad = [n for n in names if n not in data]
    if bad:
        raise ValueError(f"No Megacam profile for {bad}; available: {', '.join(data)}")
    zcl = wl.spt_redshifts(names)
    cosmo = wl.FlatLCDM(Om0=Om0, h=h)
    rows, fits_ = [], []
    for n in names:
        if n not in zcl:
            raise ValueError(f"{n}: no redshift in the SPT-SZ catalogue")
        f = wl.fit_cluster(n, data[n]["shear"], data[n]["nz"], zcl[n], cmodel=concentration_model, cosmo=cosmo,
                           r_min_mpc=r_min_mpc, r_max_mpc=r_max_mpc)
        fits_.append(f)
        row = {k: v for k, v in f.items() if not k.startswith("_")}
        ref = wl.D19_PUBLISHED_M500.get(n)
        row["M500c_D19"], row["M500c_D19_err"] = (ref if ref else (np.nan, np.nan))
        row["ratio_to_D19"] = row["M500c_ml"] / ref[0] if ref else np.nan
        row["pull_vs_D19"] = (row["M500c_ml"] - ref[0]) / ref[1] if ref else np.nan
        tab = wl.D19_SOURCE_TABLE.get(n)
        row["beta_mean_D19"] = tab[0] if tab else np.nan
        rows.append(row)
    df = pd.DataFrame(rows)
    out = resolve_outdir(output_dir)
    stem = f"spt_wl_masses_{concentration_model}" + (f"_r{r_min_mpc:g}-{r_max_mpc:g}" if (r_min_mpc > 0 or r_max_mpc < 10) else "")
    csv = out / f"{stem}.csv"
    df.to_csv(csv, index=False, float_format="%.5g")

    plt = mpl()
    ncol = min(5, len(fits_))
    nrow = int(np.ceil(len(fits_) / ncol))
    fig, axs = plt.subplots(nrow, ncol, figsize=(3.2 * ncol, 2.6 * nrow), squeeze=False)
    for ax, f in zip(axs.flat, fits_, strict=False):
        ax.errorbar(f["_r_mpc"], f["_g"], f["_ge"], fmt="o", ms=3, color="k")
        ax.plot(f["_r_mpc"], f["_model_best"], color="C3")
        ax.axhline(0, color="0.6", lw=0.6)
        ax.set_title(f"{f['cluster'][7:]}  M500={f['M500c_ml']:.1f}", fontsize=8)
        ax.tick_params(labelsize=7)
    for ax in axs.flat[len(fits_):]:
        ax.axis("off")
    fig.supxlabel("R [Mpc]")
    fig.supylabel(r"reduced tangential shear $g_t$")
    fig.tight_layout()
    png = save_fig(fig, out, stem)

    val = df[np.isfinite(df["ratio_to_D19"])]
    validation = None
    if len(val):
        validation = {"n_compared": int(len(val)),
                      "ratio_ml_over_D19": {r.cluster: round(float(r.ratio_to_D19), 3) for r in val.itertuples()},
                      "pull_ml_vs_D19": {r.cluster: round(float(r.pull_vs_D19), 3) for r in val.itertuples()},
                      "median_ratio": float(val["ratio_to_D19"].median()),
                      "n_within_1sigma": int((val["pull_vs_D19"].abs() < 1).sum()),
                      "reference": wl.D19_PUBLISHED_NOTE}
    js = out / f"{stem}.json"
    js.write_text(json.dumps({"model": {"profile": "NFW", "concentration": concentration_model, "Om0": Om0, "h": h,
                                        "r_range_mpc": [r_min_mpc, r_max_mpc],
                                        "estimator": "maximum likelihood + 16/50/84% of the ln M200c posterior"},
                              "validation_vs_D19": validation,
                              "clusters": df.to_dict(orient="records")}, indent=1, default=float))
    msg = f"NFW WL masses for {len(df)} Megacam clusters ({concentration_model})"
    if validation:
        msg += (f"; vs Dietrich+19 (n={validation['n_compared']}): median ratio {validation['median_ratio']:.3f}, "
                f"{validation['n_within_1sigma']}/{validation['n_compared']} within 1 sigma")
    return ok(msg, [csv, js, png],
              masses={r.cluster: {"z": round(r.z, 4), "M500c_ml": round(r.M500c_ml, 3),
                                  "M500c_68": [round(r.M500c_lo, 3), round(r.M500c_hi, 3)],
                                  "M200c_ml": round(r.M200c_ml, 3)} for r in df.itertuples()},
              validation_vs_D19=validation, units="1e14 Msun (h=%.2f), M500c/M200c w.r.t. critical density" % h,
              caveat="Raw NFW masses: no Megacam WL bias (0.938+-0.028, SPT WLsimcalib) or LSS scatter applied; "
                     "intervals are statistical only.",
              citation=DATASETS["spt_sz"]["wl_data"]["citation"])


@data_kind("summary_statistic")
@validate_call
def plot_completeness(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for the PNG.")],
    dataset: Annotated[str, Field(description="Dataset key: psz2, act_dr6, or spt_sz.")] = "psz2",
    variant: Annotated[str | None, Field(description="Planck variant (default MMF3_cosmology).")] = None,
    snr_cut: Annotated[float, Field(gt=0, description="SNR threshold for the completeness contour (Planck only).")] = 6.0,
) -> ArtifactResult:
    """Plot the survey completeness / selection function.

    Planck: heatmap of completeness C(Y500, theta500) at a chosen SNR cut.
    ACT DR6: histogram of tile y0 RMS noise levels.
    SPT-SZ: bar chart of field areas and noise correction factors.
    """
    plt = mpl()
    out = resolve_outdir(output_dir)

    if dataset == "psz2":
        variant = variant or "MMF3_cosmology"
        comp = _planck_completeness(variant)
        snr_grid = comp["snr_thresholds"]
        snr_idx = int(np.argmin(np.abs(snr_grid - snr_cut)))
        cube = comp["completeness"][snr_idx]
        theta = comp["theta500_grid"]
        y = comp["y500_grid"]

        # The Y500 grid is stored in plain arcmin^2 (e.g. 1.1e-4 .. 7.2e-2); plot it unscaled on a log axis.
        fig, ax = plt.subplots(figsize=(8, 5))
        im = ax.pcolormesh(y, theta, cube, cmap="viridis", vmin=0, vmax=1, shading="auto")
        labels = {"xlabel": r"$Y_{500}$ [arcmin$^2$]", "ylabel": r"$\theta_{500}$ [arcmin]",
                  "colorbar": "Completeness (detection probability, 0-1)"}
        ax.set(xscale="log", yscale="log", xlabel=labels["xlabel"], ylabel=labels["ylabel"],
               title=f"Planck PSZ2 completeness ({variant}, q>{snr_grid[snr_idx]:.1f})")
        fig.colorbar(im, ax=ax, label=labels["colorbar"])
        ax.contour(y, theta, cube, levels=[0.2, 0.5, 0.8], colors="w", linewidths=0.8)
        png = save_fig(fig, out, f"psz2_completeness_{variant}")
        return ok(f"Planck completeness plot ({variant}, q>{snr_grid[snr_idx]:.1f}).", [png], axis_labels=labels,
                  y500_range_arcmin2=[float(y.min()), float(y.max())],
                  theta500_range_arcmin=[float(theta.min()), float(theta.max())])

    elif dataset == "act_dr6":
        from astropy.io import fits as pyfits
        cache = data_cache_dir() / "act" / "selFn"
        rms_path = cache / "RMSTab_maxFlags0.fits"
        if not rms_path.is_file():
            _act_qfit_rmstab()
        rms = pyfits.open(rms_path)[1].data
        y0 = np.asarray(rms["y0RMS"], float)
        areas = np.asarray(rms["areaDeg2"], float)

        # y0RMS is the RMS of the filtered central Compton-y (dimensionless, ~1e-5); plotted in units of 1e-5.
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
        ax1.hist(y0 * 1e5, bins=50, weights=areas, edgecolor="k", alpha=0.7)
        labels = {"xlabel": r"$\tilde{y}_0$ RMS / $10^{-5}$ (Compton-y, dimensionless)", "ylabel": "Area [deg$^2$]"}
        ax1.set(xlabel=labels["xlabel"], ylabel=labels["ylabel"], title="ACT DR6 tile noise distribution")
        ax1.axvline(np.median(y0) * 1e5, color="r", ls="--", label=f"median={np.median(y0):.2e}")
        ax1.legend()

        sorted_area = np.sort(areas)[::-1]
        ax2.plot(np.arange(1, len(sorted_area) + 1), np.cumsum(sorted_area))
        ax2.set(xlabel="Number of tiles", ylabel="Cumulative area [deg$^2$]",
                title="ACT DR6 cumulative area")
        png = save_fig(fig, out, "act_dr6_selfunc")
        return ok("ACT DR6 selection function plot.", [png], axis_labels=labels,
                  y0_rms_median=float(np.median(y0)))

    elif dataset == "spt_sz":
        info = _spt_field_completeness()
        fields = info["fields"]
        names = [f["field"] for f in fields]
        areas = [f["area_deg2"] for f in fields]
        gammas = [f["gamma_field"] for f in fields]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
        ax1.bar(range(len(names)), areas, color="steelblue")
        ax1.set(ylabel="Area [deg$^2$]", title="SPT-SZ field areas and noise corrections")
        ax2.bar(range(len(names)), gammas, color="coral")
        ax2.set(ylabel=r"$\gamma_{\rm field}$", xlabel="Field")
        ax2.set_xticks(range(len(names)))
        ax2.set_xticklabels(names, rotation=60, ha="right", fontsize=7)
        ax2.axhline(1, color="k", ls="--", lw=0.8)
        fig.tight_layout()
        png = save_fig(fig, out, "spt_sz_selfunc")
        return ok("SPT-SZ field completeness plot.", [png])

    else:
        raise ValueError(f"No selection function for {dataset!r}.")
