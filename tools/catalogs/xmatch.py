"""crossmatch_catalogs, compare_mass_calibration."""

from __future__ import annotations

from typing import Annotated

import numpy as np
from pydantic import Field, validate_call

from ..common import ArtifactResult, mpl, ok, resolve_outdir, save_fig
from .io import read_table

TableArg = Annotated[str, Field(min_length=1, description="Harmonised CSV from fetch_cluster_catalog, or a dataset key.")]


def _unit(ra, dec):
    ra, dec = np.radians(ra), np.radians(dec)
    return np.column_stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])


def _mass_ratio_stats(ratio):
    r = np.asarray(ratio, float)
    r = r[np.isfinite(r) & (r > 0)]
    if len(r) < 2:
        return {"n": int(len(r))}
    lr = np.log(r)
    med = np.median(lr)
    # bootstrap error on the median log ratio
    rng = np.random.default_rng(0)
    boots = np.median(rng.choice(lr, size=(500, len(lr)), replace=True), axis=1)
    return {"n": int(len(r)), "median_ratio": float(np.exp(med)), "mean_ratio": float(np.mean(r)),
            "median_ratio_err": float(np.exp(med) * np.std(boots)),
            "scatter_ln": float(1.4826 * np.median(np.abs(lr - med))), "std_ln": float(np.std(lr, ddof=1))}


@validate_call
def crossmatch_catalogs(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for the matched CSV.")],
    catalog_a: TableArg,
    catalog_b: TableArg,
    radius_arcmin: Annotated[float, Field(gt=0, le=60, description="Max angular separation in arcmin.")] = 2.0,
    max_dz: Annotated[float | None, Field(ge=0, description=(
        "Max |z_a - z_b| / (1 + z_a); None = no redshift requirement (entries without z can still match).")
    )] = 0.1,
) -> ArtifactResult:
    """Positionally (+ redshift) cross-match two cluster catalogues; write the matched pairs and mass ratios.

    Use for SZ-vs-X-ray (or SZ-vs-SZ) comparisons. Nearest neighbour in A for each B
    entry within the radius, made one-to-one (each A keeps its closest B). Typical
    radii: 2' for SZ-SZ (ACT/SPT beams ~1'), 3' for Planck (5' beam, larger
    positional error) or SZ-vs-eROSITA. Output CSV has *_a / *_b columns,
    sep_arcmin, dz and mass_ratio = M500_b / M500_a.
    """
    import pandas as pd
    from scipy.spatial import cKDTree
    a, b = read_table(catalog_a), read_table(catalog_b)
    if not len(a) or not len(b):
        raise ValueError("One of the catalogues is empty after cuts")
    la, lb = str(a["survey"].iloc[0]), str(b["survey"].iloc[0])
    tree = cKDTree(_unit(a["ra"].to_numpy(float), a["dec"].to_numpy(float)))
    chord = 2 * np.sin(np.radians(radius_arcmin / 60.0) / 2)
    xb = _unit(b["ra"].to_numpy(float), b["dec"].to_numpy(float))
    k = min(5, len(a))
    dist, idx = tree.query(xb, k=k, distance_upper_bound=chord)
    if k == 1:
        dist, idx = dist[:, None], idx[:, None]
    za, zb = a["z"].to_numpy(float), b["z"].to_numpy(float)
    pairs = []
    for ib in range(len(b)):
        for d, ia in zip(dist[ib], idx[ib], strict=True):
            if not np.isfinite(d):
                break
            if max_dz is not None:
                if not (np.isfinite(za[ia]) and np.isfinite(zb[ib])):
                    continue
                if abs(za[ia] - zb[ib]) / (1 + za[ia]) > max_dz:
                    continue
            pairs.append((ia, ib, 2 * np.degrees(np.arcsin(d / 2)) * 60))
            break
    # one-to-one: each A keeps its closest B
    best: dict[int, tuple] = {}
    for ia, ib, s in pairs:
        if ia not in best or s < best[ia][2]:
            best[ia] = (ia, ib, s)
    sel = sorted(best.values(), key=lambda t: t[0])
    ia = np.array([t[0] for t in sel], int)
    ib = np.array([t[1] for t in sel], int)
    cols = ["name", "ra", "dec", "z", "M500", "M500_err_lo", "M500_err_hi", "snr"]
    m = pd.concat([a.iloc[ia][cols].reset_index(drop=True).add_suffix("_a"),
                   b.iloc[ib][cols].reset_index(drop=True).add_suffix("_b")], axis=1)
    m["sep_arcmin"] = [t[2] for t in sel]
    m["dz"] = m["z_b"] - m["z_a"]
    m["mass_ratio"] = m["M500_b"] / m["M500_a"]
    m["survey_a"], m["survey_b"] = la, lb
    out = resolve_outdir(output_dir)
    slug = lambda s: s.lower().replace(" ", "_")  # noqa: E731
    path = out / f"xmatch_{slug(la)}__{slug(lb)}.csv"
    m.to_csv(path, index=False, float_format="%.6g")
    ms = _mass_ratio_stats(m["mass_ratio"])
    dzs = m["dz"].dropna() / (1 + m["z_a"].dropna().reindex(m["dz"].dropna().index))
    return ok(
        f"{len(m)} matches between {la} ({len(a)}) and {lb} ({len(b)}) within {radius_arcmin}'"
        + (f", |dz|/(1+z)<{max_dz}" if max_dz is not None else "")
        + (f"; median M500 ratio ({lb}/{la}) = {ms['median_ratio']:.3f}" if "median_ratio" in ms else ""),
        [path], n_a=int(len(a)), n_b=int(len(b)), n_matched=int(len(m)),
        match_fraction_a=float(len(m) / len(a)), match_fraction_b=float(len(m) / len(b)),
        radius_arcmin=radius_arcmin, max_dz=max_dz, median_sep_arcmin=float(np.median(m["sep_arcmin"])) if len(m) else None,
        dz_over_1pz_median=float(dzs.median()) if len(dzs) else None,
        dz_over_1pz_nmad=float(1.4826 * np.median(np.abs(dzs - dzs.median()))) if len(dzs) else None,
        mass_ratio=ms, ratio_definition=f"M500[{lb}] / M500[{la}]",
    )


@validate_call
def compare_mass_calibration(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for the PNG / CSV.")],
    matched_csv: Annotated[str, Field(min_length=1, description="CSV written by crossmatch_catalogs.")],
    z_edges: Annotated[list[float] | None, Field(description="Redshift bins for the ratio trend (default 0,0.2,0.4,0.6,0.8,1.2).")] = None,
    fit_slope: Annotated[bool, Field(description="Fit ln M_b = alpha + beta ln(M_a/3e14) by orthogonal-ish (BCES-Y|X and bisector) regression.")] = True,
) -> ArtifactResult:
    """Mass-calibration comparison for matched clusters: M500_b vs M500_a scatter, ratio vs z and vs mass.

    Use after crossmatch_catalogs to quantify relative mass bias between surveys
    (e.g. Planck's hydrostatic 1-b ~0.8 vs WL-calibrated SPT/ACT, or SZ vs eROSITA).
    Reports median ratio with bootstrap error, log-normal scatter, per-z-bin ratios
    and (optionally) a power-law slope.
    """
    import pandas as pd
    df = pd.read_csv(matched_csv)
    need = {"M500_a", "M500_b", "z_a"}
    if not need <= set(df.columns):
        raise ValueError(f"{matched_csv} is not a crossmatch_catalogs output (needs {sorted(need)})")
    la = str(df["survey_a"].iloc[0]) if "survey_a" in df and len(df) else "A"
    lb = str(df["survey_b"].iloc[0]) if "survey_b" in df and len(df) else "B"
    d = df[np.isfinite(df["M500_a"]) & np.isfinite(df["M500_b"]) & (df["M500_a"] > 0) & (df["M500_b"] > 0)].copy()
    if len(d) < 3:
        raise ValueError(f"Only {len(d)} matched clusters with masses in both catalogues - widen the match or cuts")
    d["ratio"] = d["M500_b"] / d["M500_a"]
    overall = _mass_ratio_stats(d["ratio"])
    z_edges = np.asarray(z_edges or [0, 0.2, 0.4, 0.6, 0.8, 1.2], float)
    zbins = []
    for lo, hi in zip(z_edges[:-1], z_edges[1:], strict=True):
        s = d[(d["z_a"] >= lo) & (d["z_a"] < hi)]
        zbins.append({"z_lo": lo, "z_hi": hi, **_mass_ratio_stats(s["ratio"])})
    fit = None
    x, y = np.log(d["M500_a"] / 3.0), np.log(d["M500_b"] / 3.0)
    if fit_slope and len(d) >= 5:
        xm, ym = x.mean(), y.mean()
        sxx, syy, sxy = ((x - xm) ** 2).mean(), ((y - ym) ** 2).mean(), ((x - xm) * (y - ym)).mean()
        b_yx = sxy / sxx
        b_xy = syy / sxy
        b_bis = (b_yx * b_xy - 1 + np.sqrt((1 + b_yx ** 2) * (1 + b_xy ** 2))) / (b_yx + b_xy)
        fit = {"slope_OLS_Y|X": float(b_yx), "slope_bisector": float(b_bis),
               "norm_at_3e14_bisector": float(np.exp(ym - b_bis * xm) * 3.0),
               "pivot_1e14": 3.0, "note": "No measurement-error deconvolution: OLS slope is biased low by Malmquist/scatter."}
    plt = mpl()
    out = resolve_outdir(output_dir)
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.8))
    ax = axs[0]
    ax.errorbar(d["M500_a"], d["M500_b"], xerr=[d.get("M500_err_lo_a", 0 * d["M500_a"]).fillna(0), d.get("M500_err_hi_a", 0 * d["M500_a"]).fillna(0)],
                yerr=[d.get("M500_err_lo_b", 0 * d["M500_b"]).fillna(0), d.get("M500_err_hi_b", 0 * d["M500_b"]).fillna(0)],
                fmt="o", ms=2.5, alpha=0.4, elinewidth=0.5)
    lim = [min(d["M500_a"].min(), d["M500_b"].min()) * 0.8, max(d["M500_a"].max(), d["M500_b"].max()) * 1.2]
    ax.plot(lim, lim, "k--", lw=1, label="1:1")
    ax.plot(lim, np.array(lim) * overall["median_ratio"], "r-", lw=1.2, label=f"median ratio {overall['median_ratio']:.2f}")
    ax.set(xscale="log", yscale="log", xlim=lim, ylim=lim, xlabel=f"M500 {la} [1e14 Msun]", ylabel=f"M500 {lb} [1e14 Msun]")
    ax.legend(fontsize=8)
    axs[1].scatter(d["z_a"], d["ratio"], s=5, alpha=0.4)
    zc = [0.5 * (b["z_lo"] + b["z_hi"]) for b in zbins if "median_ratio" in b]
    zr = [b["median_ratio"] for b in zbins if "median_ratio" in b]
    ze = [b["median_ratio_err"] for b in zbins if "median_ratio" in b]
    axs[1].errorbar(zc, zr, yerr=ze, fmt="s", color="r", ms=6, capsize=3, label="binned median")
    axs[1].axhline(1, color="k", ls="--", lw=1)
    axs[1].set(yscale="log", xlabel="z", ylabel=f"M500 {lb} / {la}")
    axs[1].legend(fontsize=8)
    axs[2].hist(np.log(d["ratio"]), bins=30, alpha=0.7)
    axs[2].axvline(np.log(overall["median_ratio"]), color="r")
    axs[2].set(xlabel=f"ln(M500 {lb} / {la})", ylabel="N", title=f"scatter (NMAD) = {overall['scatter_ln']:.2f}")
    png = save_fig(fig, out, f"mass_calibration_{la}_{lb}".replace(" ", "_").lower())
    csv = out / f"mass_calibration_zbins_{la}_{lb}.csv".replace(" ", "_").lower()
    pd.DataFrame(zbins).to_csv(csv, index=False, float_format="%.6g")
    return ok(f"{len(d)} matched clusters: M500[{lb}]/M500[{la}] median = {overall['median_ratio']:.3f} "
              f"+/- {overall['median_ratio_err']:.3f}, ln-scatter {overall['scatter_ln']:.2f}",
              [png, csv], n=int(len(d)), overall=overall, z_bins=zbins, fit=fit,
              ratio_definition=f"M500[{lb}] / M500[{la}]")
