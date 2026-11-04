"""predict_cluster_counts_lcdm (heavy, dispatchable), plot_counts_vs_prediction."""

from __future__ import annotations

import json
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, validate_call

from ..common import ArtifactResult, data_kind, mpl, ok, param_slug, resolve_outdir, save_fig
from ..registry import DATASETS
from . import kernels

KERNEL_FN = "lcdm.kernels.predict_counts"
KERNEL_DEPS = ["numpy", "scipy"]


def _observed(catalog: str, z_edges, m_min):
    from ..catalogs.io import read_table
    df = read_table(catalog)
    z, m = df["z"].to_numpy(float), df["M500"].to_numpy(float)
    sel = np.isfinite(z) & np.isfinite(m) & (m >= m_min)
    n, _ = np.histogram(z[sel], bins=z_edges)
    ds = str(df["dataset"].iloc[0]) if "dataset" in df.columns and len(df) else None
    return n.astype(int).tolist(), str(df["survey"].iloc[0]) if len(df) else catalog, ds


@data_kind("summary_statistic")
@validate_call
def predict_cluster_counts_lcdm(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for the prediction CSV/JSON.")],
    m500_min: Annotated[float, Field(gt=0, description="M500c threshold in 1e14 Msun (catalogue h70 units).")] = 5.0,
    z_edges: Annotated[list[float] | None, Field(description="Redshift bin edges (default 0.1..1.3 step 0.1).")] = None,
    area_deg2: Annotated[float | None, Field(gt=0, le=41253, description=(
        "Survey area [deg^2]; default = the observed catalogue's registry area.")) ] = None,
    observed_catalog: Annotated[str | None, Field(description=(
        "Harmonised CSV or dataset key: its N(z, M500 >= m500_min) is compared with the prediction."))] = None,
    Om0: Annotated[float, Field(gt=0.05, lt=0.9, description="Matter density today.")] = 0.3,
    Ob0: Annotated[float, Field(gt=0, lt=0.2, description="Baryon density today.")] = 0.049,
    h: Annotated[float, Field(gt=0.4, lt=1.0, description="H0/100.")] = 0.7,
    ns: Annotated[float, Field(gt=0.8, lt=1.2, description="Scalar spectral index.")] = 0.965,
    sigma8: Annotated[float, Field(gt=0.4, lt=1.3, description="sigma8 today.")] = 0.8,
    sigma8_scan: Annotated[list[float] | None, Field(description=(
        "Optional sigma8 grid for a Poisson -2lnL profile vs the observed counts (each point ~1-3 s locally)."))] = None,
    mass_def: Annotated[Literal["500c", "200c", "200m"], Field(description="Mass definition of the threshold.")] = "500c",
) -> ArtifactResult:
    """Predict LCDM cluster counts dN/dz above a mass threshold (Tinker+08 HMF x Eisenstein-Hu P(k)) and compare with a catalogue.

    Use to ask "is this survey's N(z) above M consistent with LCDM / which sigma8?".
    No selection function, mass scatter or Eddington bias is modelled: pick a
    threshold where the catalogue is ~complete (SPT-SZ ~5e14 at z>0.25, ACT DR6
    SNR>5 ~5e14, PSZ2 ~6e14 at z~0.2) and treat ratios at the 10-20% level as the
    systematics floor (the mass-calibration uncertainty dominates). Heavy:
    runs as an HPC kernel when dispatch is active.
    """
    z_edges = list(z_edges or np.round(np.arange(0.1, 1.31, 0.1), 3).tolist())
    obs, label, ds = (None, None, None)
    if observed_catalog:
        obs, label, ds = _observed(observed_catalog, np.asarray(z_edges), m500_min)
    if area_deg2 is None:
        area_deg2 = DATASETS.get(ds, {}).get("area_deg2") if ds else None
        if area_deg2 is None:
            raise ValueError("area_deg2 is required (no observed_catalog with a registry area given)")
    if sigma8_scan and obs is None:
        raise ValueError("sigma8_scan needs observed_catalog")
    args = {"z_edges": z_edges, "m_min_1e14": m500_min, "area_deg2": float(area_deg2),
            "cosmology": {"Om0": Om0, "Ob0": Ob0, "h": h, "ns": ns, "sigma8": sigma8}, "mass_def": mass_def,
            "observed_counts": obs, "sigma8_grid": sigma8_scan}
    from mcp_server.dispatch import remote_site, run_kernel  # lazy: server-only
    site = remote_site()
    files = []
    if site:
        res = run_kernel(KERNEL_FN, args, pip_deps=KERNEL_DEPS, duration=900)
        payload = res["result"]
        files = list(res.get("artifact_files") or [])
        where = str(res.get("host", site))
    else:
        payload = kernels.predict_counts(**args)
        where = "local"
    import pandas as pd
    out = resolve_outdir(output_dir)
    stem = f"lcdm_counts_{param_slug({**args['cosmology'], 'm': m500_min, 'a': area_deg2, 'obs': label, 'md': mass_def})}"
    tab = {"z_lo": payload["z_lo"], "z_hi": payload["z_hi"], "z_mid": payload["z_mid"],
           "N_pred": payload["N_pred"], "dNdz_pred": payload["dNdz_pred"]}
    if obs is not None:
        tab["N_obs"] = payload["N_obs"]
        tab["pull"] = payload["pull"]
    csv = out / f"{stem}.csv"
    pd.DataFrame(tab).to_csv(csv, index=False, float_format="%.6g")
    payload["observed_survey"] = label
    payload["ran_on"] = where
    js = out / f"{stem}.json"
    js.write_text(json.dumps(payload, indent=1))
    msg = f"LCDM (sigma8={sigma8}, Om={Om0}) predicts {payload['N_pred_total']:.0f} clusters with M500>={m500_min}e14 in {area_deg2:.0f} deg^2"
    if obs is not None:
        msg += f"; {label} has {payload['N_obs_total']:.0f} (obs/pred = {payload['ratio_obs_pred_total']:.2f})"
    if "sigma8_best" in payload:
        msg += f"; best sigma8 = {payload['sigma8_best']:.3f}" + (f" +/- {payload['sigma8_err_1sig']:.3f}" if "sigma8_err_1sig" in payload else "")
    keep = {k: payload[k] for k in ("N_pred_total", "N_obs_total", "ratio_obs_pred_total", "poisson_m2lnL",
                                     "sigma8_best", "sigma8_err_1sig", "model") if k in payload}
    return ok(msg, [csv, js, *files], ran_on=where, area_deg2=area_deg2, m500_min=m500_min, observed_survey=label,
              cosmology=args["cosmology"], **keep,
              caveat="No selection function / scatter / Eddington bias; catalogue masses depend on each survey's scaling relation.")


predict_cluster_counts_lcdm.weight = "heavy"


@data_kind("summary_statistic")
@validate_call
def plot_counts_vs_prediction(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for the PNG.")],
    prediction_json: Annotated[list[str], Field(min_length=1, description=(
        "One or more JSON files written by predict_cluster_counts_lcdm (e.g. different sigma8 or surveys)."))],
    per_unit_z: Annotated[bool, Field(description="Plot dN/dz instead of N per bin.")] = True,
    stem: Annotated[str, Field(description="Output file stem.")] = "counts_vs_lcdm",
) -> ArtifactResult:
    """Plot observed cluster N(z) (Poisson errors) against LCDM predictions, with a residual panel and the sigma8 profile if scanned.

    Use after predict_cluster_counts_lcdm.
    """
    plt = mpl()
    out = resolve_outdir(output_dir)
    preds = [json.loads(open(p).read()) for p in prediction_json]
    has_scan = any("sigma8_m2lnL" in p for p in preds)
    ncol = 2 if has_scan else 1
    fig, axs = plt.subplots(2, ncol, figsize=(7 * ncol, 6.5), gridspec_kw={"height_ratios": [3, 1]}, squeeze=False)
    ax, axr = axs[0, 0], axs[1, 0]
    summary = []
    for i, p in enumerate(preds):
        zl, zh = np.asarray(p["z_lo"]), np.asarray(p["z_hi"])
        dz = (zh - zl) if per_unit_z else np.ones_like(zl)
        edges = np.append(zl, zh[-1])
        npred = np.asarray(p["N_pred"])
        c = f"C{i}"
        lab = f"LCDM s8={p['cosmology']['sigma8']}, Om={p['cosmology']['Om0']}, M>{p['m_min_1e14'][0]:g}e14"
        ax.stairs(npred / dz, edges, color=c, lw=1.8, label=lab)
        if "N_obs" in p:
            nobs = np.asarray(p["N_obs"], float)
            zm = 0.5 * (zl + zh)
            ax.errorbar(zm, nobs / dz, yerr=np.sqrt(np.maximum(nobs, 1)) / dz, fmt="o", color=c, ms=4,
                        label=f"{p.get('observed_survey')} ({int(nobs.sum())})")
            axr.errorbar(zm, (nobs - npred) / np.sqrt(np.maximum(npred, 1e-9)), fmt="o", color=c, ms=4)
        summary.append({"file": prediction_json[i], "N_pred_total": p["N_pred_total"], "N_obs_total": p.get("N_obs_total"),
                        "sigma8": p["cosmology"]["sigma8"], "sigma8_best": p.get("sigma8_best")})
        if has_scan and "sigma8_m2lnL" in p:
            g, l2 = np.asarray(p["sigma8_grid"]), np.asarray(p["sigma8_m2lnL"])
            axs[0, 1].plot(g, l2 - l2.min(), "o-", color=c, label=p.get("observed_survey"))
    ax.set(yscale="log", ylabel="dN/dz" if per_unit_z else "N per bin", title=f"Cluster counts vs LCDM ({preds[0]['area_deg2']:.0f} deg^2)")
    ax.legend(fontsize=8)
    axr.axhline(0, color="k", lw=0.8)
    axr.set(xlabel="z", ylabel="(obs-pred)/sqrt(pred)")
    if has_scan:
        axs[0, 1].axhline(1, color="gray", ls="--")
        axs[0, 1].set(xlabel="sigma8", ylabel="Delta(-2 ln L) Poisson", title="sigma8 profile (Om fixed)")
        axs[0, 1].legend(fontsize=8)
        axs[1, 1].axis("off")
    png = save_fig(fig, out, stem)
    return ok(f"Counts-vs-LCDM plot for {len(preds)} prediction(s).", [png], summary=summary)
