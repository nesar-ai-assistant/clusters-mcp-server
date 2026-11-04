"""fetch_cluster_selection_function, fetch_cluster_wl_profiles, plot_completeness."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
from pydantic import Field, validate_call

from ..common import ArtifactResult, data_cache_dir, data_kind, fetch_file, mpl, ok, resolve_outdir, save_fig
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
    """Extract Megacam tangential shear profiles from the SPT likelihood tarball."""
    meta = DATASETS["spt_sz"]["wl_data"]
    tgz = fetch_file(meta["url"], subdir=meta["subdir"], timeout=600)
    prefix = meta["archive_member_prefix"]

    profiles = []
    files = []
    with tarfile.open(tgz, "r:gz") as tf:
        for m in tf.getmembers():
            if m.name.startswith(prefix + "Megacam/") and m.name.endswith("_shear.txt") and m.isfile():
                fh = tf.extractfile(m)
                if fh is None:
                    continue
                cluster = m.name.split("/")[-2]
                data = np.loadtxt(io.BytesIO(fh.read()), comments="#")
                # columns: r_deg, gt, Delta_gt, kbin, N_gal(optional)
                csv_path = output_dir / f"spt_wl_{cluster}.csv"
                df = pd.DataFrame({
                    "r_deg": data[:, 0],
                    "gt": data[:, 1],
                    "gt_err": data[:, 2],
                })
                if data.shape[1] > 3:
                    df["kbin"] = data[:, 3]
                df.to_csv(csv_path, index=False, float_format="%.6g")
                files.append(csv_path)
                profiles.append({
                    "cluster": cluster,
                    "n_radial_bins": len(data),
                    "r_min_deg": float(data[:, 0].min()),
                    "r_max_deg": float(data[:, 0].max()),
                    "gt_mean": float(data[:, 1].mean()),
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


@data_kind("summary_statistic")
@validate_call
def fetch_cluster_wl_profiles(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for WL shear profile CSVs.")],
    dataset: Annotated[str, Field(description="Dataset key (currently only spt_sz).")] = "spt_sz",
) -> ArtifactResult:
    """Fetch published weak-lensing tangential shear profiles for clusters with WL follow-up.

    Currently available: SPT-SZ Megacam shear profiles (20 clusters, Dietrich+19).
    Each profile gives g_t(r) with errors as a CSV file per cluster.
    These are real summary-statistic data products that can be used for mass calibration.
    """
    if dataset != "spt_sz":
        raise ValueError(f"WL profiles not available for {dataset!r}; use spt_sz.")
    out = resolve_outdir(output_dir)
    info = _spt_wl_profiles(out)
    summary_csv = out / "spt_wl_summary.csv"
    pd.DataFrame(info["profiles"]).to_csv(summary_csv, index=False, float_format="%.6g")
    return ok(
        f"SPT-SZ WL shear profiles: {info['n_clusters']} Megacam clusters written.",
        [summary_csv] + [str(f) for f in info["files"]],
        n_clusters=info["n_clusters"],
        clusters=[p["cluster"] for p in info["profiles"]],
    )


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

        fig, ax = plt.subplots(figsize=(8, 5))
        im = ax.pcolormesh(y * 1e4, theta, cube, cmap="viridis", vmin=0, vmax=1, shading="auto")
        ax.set(xscale="log", xlabel=r"$Y_{500}$ [$10^{-4}$ arcmin$^2$]",
               ylabel=r"$\theta_{500}$ [arcmin]",
               title=f"Planck PSZ2 completeness ({variant}, q>{snr_grid[snr_idx]:.1f})")
        fig.colorbar(im, ax=ax, label="Completeness")
        ax.contour(y * 1e4, theta, cube, levels=[0.2, 0.5, 0.8], colors="w", linewidths=0.8)
        png = save_fig(fig, out, f"psz2_completeness_{variant}")
        return ok(f"Planck completeness plot ({variant}, q>{snr_grid[snr_idx]:.1f}).", [png])

    elif dataset == "act_dr6":
        from astropy.io import fits as pyfits
        cache = data_cache_dir() / "act" / "selFn"
        rms_path = cache / "RMSTab_maxFlags0.fits"
        if not rms_path.is_file():
            _act_qfit_rmstab()
        rms = pyfits.open(rms_path)[1].data
        y0 = np.asarray(rms["y0RMS"], float)
        areas = np.asarray(rms["areaDeg2"], float)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
        ax1.hist(y0 * 1e6, bins=50, weights=areas, edgecolor="k", alpha=0.7)
        ax1.set(xlabel=r"$y_0$ RMS [$\mu$K-arcmin$^2$]", ylabel="Area [deg$^2$]",
                title="ACT DR6 tile noise distribution")
        ax1.axvline(np.median(y0) * 1e6, color="r", ls="--", label=f"median={np.median(y0)*1e6:.1f}")
        ax1.legend()

        sorted_area = np.sort(areas)[::-1]
        ax2.plot(np.arange(1, len(sorted_area) + 1), np.cumsum(sorted_area))
        ax2.set(xlabel="Number of tiles", ylabel="Cumulative area [deg$^2$]",
                title="ACT DR6 cumulative area")
        png = save_fig(fig, out, "act_dr6_selfunc")
        return ok("ACT DR6 selection function plot.", [png])

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
