"""fetch_cluster_catalog, describe_catalog_columns, compute_cluster_counts."""

from __future__ import annotations

from typing import Annotated

import numpy as np
from pydantic import Field, validate_call

from ..common import ArtifactResult, ok, param_slug, resolve_outdir
from ..registry import DATASETS
from .io import HARMONISED, apply_cuts, catalog_keys, load_catalog, read_native, read_table

DatasetArg = Annotated[str, Field(min_length=1, description=(
    "Catalogue key: psz2, spt_sz, sptpol_100d, spt_ecs, spt3g_5yr, act_dr6, erass1, erass1_cosmo "
    "(see list_clusters_datasets)."))]
OutArg = Annotated[str, Field(min_length=1, description="Directory for output files (created if missing).")]


@validate_call
def fetch_cluster_catalog(
    output_dir: OutArg,
    dataset: DatasetArg,
    z_min: Annotated[float | None, Field(ge=0, description="Minimum redshift (drops entries without z).")] = None,
    z_max: Annotated[float | None, Field(gt=0, description="Maximum redshift.")] = None,
    m500_min: Annotated[float | None, Field(ge=0, description="Minimum M500c in 1e14 Msun.")] = None,
    m500_max: Annotated[float | None, Field(gt=0, description="Maximum M500c in 1e14 Msun.")] = None,
    snr_min: Annotated[float | None, Field(description="Minimum native detection statistic (xi / SNR / EXT_LIKE).")] = None,
    require_redshift: Annotated[bool, Field(description="Keep only entries with a redshift.")] = False,
    require_mass: Annotated[bool, Field(description="Keep only entries with an M500 estimate.")] = False,
) -> ArtifactResult:
    """Download one cluster catalogue (first use only) and write a harmonised CSV with cuts applied.

    Use this first: every other catalogue tool takes the CSV path it writes.
    Columns: name, ra, dec [deg], z, z_err, M500 [1e14 Msun, M500c], M500_err_lo,
    M500_err_hi, snr (survey-native statistic), survey, dataset. NaN = missing.
    """
    df = load_catalog(dataset)
    n_all = len(df)
    df = apply_cuts(df, z_min, z_max, m500_min, m500_max, snr_min, require_redshift, require_mass)
    out = resolve_outdir(output_dir)
    cuts = {"z_min": z_min, "z_max": z_max, "m500_min": m500_min, "m500_max": m500_max, "snr_min": snr_min,
            "rz": require_redshift, "rm": require_mass}
    active = {k: v for k, v in cuts.items() if v not in (None, False)}
    path = out / (f"clusters_{dataset}.csv" if not active else f"clusters_{dataset}_{param_slug(active)}.csv")
    df.to_csv(path, index=False, float_format="%.6g")
    z = df["z"].dropna()
    m = df["M500"].dropna()
    meta = DATASETS[dataset]
    return ok(
        f"{dataset}: {len(df)} of {n_all} clusters after cuts -> {path.name}",
        [path], dataset=dataset, survey=meta["survey"], n_catalog=n_all, n_selected=len(df),
        n_with_z=int(len(z)), n_with_mass=int(len(m)), cuts=active,
        z_range=[float(z.min()), float(z.max())] if len(z) else None,
        z_median=float(z.median()) if len(z) else None,
        m500_median_1e14=float(m.median()) if len(m) else None,
        m500_range_1e14=[float(m.min()), float(m.max())] if len(m) else None,
        area_deg2=meta.get("area_deg2"), columns=HARMONISED, citation=meta["citation"],
    )


@validate_call
def describe_catalog_columns(
    dataset: DatasetArg,
    show_native: Annotated[bool, Field(description="Also list every native FITS column with unit and an example.")] = True,
) -> ArtifactResult:
    """Explain a catalogue's columns: harmonised mapping, units, mass convention, and native FITS columns.

    Use before comparing masses across surveys - each survey's M500 comes from
    a different scaling relation, and ``snr`` means different things.
    """
    if dataset not in catalog_keys():
        raise ValueError(f"Unknown catalogue {dataset!r}. Available: {', '.join(catalog_keys())}")
    meta = DATASETS[dataset]
    native = None
    if show_native:
        t = read_native(dataset)
        native = []
        for c in t.colnames:
            v = t[c][0]
            if isinstance(v, bytes):
                v = v.decode(errors="ignore")
            native.append({"column": c, "unit": str(t[c].unit) if t[c].unit is not None else "",
                           "dtype": str(t[c].dtype), "example": str(v)[:40]})
    return ok(f"{dataset}: harmonised mapping + {len(native or [])} native columns.",
              dataset=dataset, survey=meta["survey"], harmonised_columns=HARMONISED,
              mapping={k: v for k, v in meta["columns"].items()}, conventions=meta["conventions"],
              n_rows_expected=meta["n_rows"], area_deg2=meta.get("area_deg2"), native_columns=native,
              citation=meta["citation"])


@validate_call
def compute_cluster_counts(
    output_dir: OutArg,
    catalogs: Annotated[list[str], Field(min_length=1, description=(
        "Harmonised CSVs from fetch_cluster_catalog and/or dataset keys (full catalogue)."))],
    z_edges: Annotated[list[float] | None, Field(description="Redshift bin edges (default 0..1.6 step 0.1).")] = None,
    m500_min: Annotated[float | None, Field(ge=0, description="Mass threshold for N(z) in 1e14 Msun (None = all with z).")] = None,
    m_grid: Annotated[list[float] | None, Field(description="M500 thresholds [1e14 Msun] for N(>M) (default log 0.5..30).")] = None,
    normalise_by_area: Annotated[bool, Field(description="Also give counts per deg^2 using each dataset's area.")] = True,
) -> ArtifactResult:
    """Histogram cluster counts: N(z) per redshift bin and cumulative N(>M500), per catalogue.

    Use to compare survey depths or as the observed side of predict_cluster_counts_lcdm.
    Writes counts_nz.csv and counts_nm.csv (+ a PNG with both panels).
    """
    import pandas as pd

    from ..common import mpl, save_fig
    from ..registry import SURVEY_COLORS
    out = resolve_outdir(output_dir)
    z_edges = np.asarray(z_edges if z_edges else np.round(np.arange(0, 1.61, 0.1), 3), float)
    m_grid = np.asarray(m_grid if m_grid else np.logspace(np.log10(0.5), np.log10(30), 25), float)
    nz_rows, nm_rows, summary = [], [], {}
    plt = mpl()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    for cat in catalogs:
        df = read_table(cat)
        label = str(df["survey"].iloc[0]) if len(df) else str(cat)
        ds = str(df["dataset"].iloc[0]) if "dataset" in df.columns and len(df) else None
        area = DATASETS.get(ds, {}).get("area_deg2") if ds else None
        zsel = df["z"].to_numpy(float)
        msel = df["M500"].to_numpy(float)
        keep = np.isfinite(zsel)
        if m500_min is not None:
            keep &= msel >= m500_min
        nz, _ = np.histogram(zsel[keep], bins=z_edges)
        mm = msel[np.isfinite(msel)]
        nm = np.array([(mm >= t).sum() for t in m_grid])
        for i, n in enumerate(nz):
            nz_rows.append({"survey": label, "z_lo": z_edges[i], "z_hi": z_edges[i + 1], "N": int(n),
                            "N_per_deg2": n / area if (area and normalise_by_area) else np.nan})
        for t, n in zip(m_grid, nm, strict=True):
            nm_rows.append({"survey": label, "M500_min_1e14": t, "N_gt_M": int(n),
                            "N_gt_M_per_deg2": n / area if (area and normalise_by_area) else np.nan})
        summary[label] = {"N_total": int(len(df)), "N_in_z_bins": int(nz.sum()), "area_deg2": area,
                          "z_median": float(np.nanmedian(zsel)) if np.isfinite(zsel).any() else None}
        col = SURVEY_COLORS.get(label)
        a1.stairs(nz, z_edges, label=label, color=col, lw=1.8)
        if len(mm):
            a2.step(m_grid, nm, where="post", label=label, color=col, lw=1.8)
    a1.set(xlabel="z", ylabel="N per bin" + (f" (M500 > {m500_min}e14)" if m500_min else ""), title="N(z)")
    a2.set(xscale="log", yscale="log", xlabel=r"$M_{500c}$ [$10^{14} M_\odot$]", ylabel="N(>M)", title="N(>M)")
    a1.legend(fontsize=8)
    a2.legend(fontsize=8)
    f1, f2 = out / "counts_nz.csv", out / "counts_nm.csv"
    pd.DataFrame(nz_rows).to_csv(f1, index=False, float_format="%.6g")
    pd.DataFrame(nm_rows).to_csv(f2, index=False, float_format="%.6g")
    png = save_fig(fig, out, "counts_nz_nm")
    return ok(f"Counts for {len(catalogs)} catalogue(s).", [f1, f2, png], summary=summary,
              z_edges=z_edges.tolist(), m500_min=m500_min)
