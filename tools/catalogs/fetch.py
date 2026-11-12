"""fetch_cluster_catalog, describe_catalog_columns, compute_cluster_counts, compute_wazp_footprint_area."""

from __future__ import annotations

from typing import Annotated

import numpy as np
from pydantic import Field, validate_call

from ..common import ArtifactResult, data_kind, ok, param_slug, resolve_outdir
from ..registry import DATASETS
from .io import HARMONISED, apply_cuts, catalog_keys, extra_columns, has_mass, load_catalog, read_native, read_table

DatasetArg = Annotated[str, Field(min_length=1, description=(
    "Catalogue key: psz2, spt_sz, sptpol_100d, spt_ecs, spt3g_5yr, act_dr6, erass1, erass1_cosmo, "
    "des_y6_wazp (optical, richness instead of mass) (see list_clusters_datasets)."))]
OutArg = Annotated[str, Field(min_length=1, description="Directory for output files (created if missing).")]


@data_kind("catalog")
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
    richness_min: Annotated[float | None, Field(ge=0, description=(
        "Optical catalogues only (des_y6_wazp): minimum richness NGALS (Benoist+25 use >=25 for a clean sample)."))] = None,
    richness_max: Annotated[float | None, Field(gt=0, description="Optical catalogues only: maximum richness.")] = None,
    in_cosmo_only: Annotated[bool, Field(description=(
        "des_y6_wazp only: keep IN_COSMO clusters (z below the local ZMAX depth, homogeneous richness) - use for counts."))] = False,
    include_members: Annotated[bool, Field(description=(
        "des_y6_wazp only: also download the members FITS (1.05 GB, 13.1M rows) and write the members of the "
        "selected clusters (ID_CLUSTER, RA, DEC, ZPHOT, PMEM, MAG_*) to a second CSV. Slow on first use."))] = False,
) -> ArtifactResult:
    """Download one cluster catalogue (first use only) and write a harmonised CSV with cuts applied.

    Use this first: every other catalogue tool takes the CSV path it writes.
    Columns: name, ra, dec [deg], z, z_err, M500 [1e14 Msun, M500c], M500_err_lo,
    M500_err_hi, snr (survey-native statistic), survey, dataset. NaN = missing.
    des_y6_wazp (optical) has M500 = NaN everywhere and extra columns richness,
    richness_err (NGALS), z_spec, in_cosmo, cover_frac; cut on richness, not mass.
    """
    meta = DATASETS.get(dataset, {})
    optical = not has_mass(dataset)
    if optical and (m500_min is not None or m500_max is not None or require_mass):
        raise ValueError(f"{dataset} has no mass estimate (M500 is NaN): use richness_min / richness_max "
                         "instead of m500 cuts")
    if include_members and "members" not in meta:
        raise ValueError("include_members is only available for catalogues with a members file (des_y6_wazp)")
    df = load_catalog(dataset)
    n_all = len(df)
    df = apply_cuts(df, z_min, z_max, m500_min, m500_max, snr_min, require_redshift, require_mass,
                    richness_min=richness_min, richness_max=richness_max, in_cosmo=in_cosmo_only)
    out = resolve_outdir(output_dir)
    cuts = {"z_min": z_min, "z_max": z_max, "m500_min": m500_min, "m500_max": m500_max, "snr_min": snr_min,
            "rz": require_redshift, "rm": require_mass, "rich_min": richness_min, "rich_max": richness_max,
            "cosmo": in_cosmo_only}
    active = {k: v for k, v in cuts.items() if v not in (None, False)}
    path = out / (f"clusters_{dataset}.csv" if not active else f"clusters_{dataset}_{param_slug(active)}.csv")
    df.to_csv(path, index=False, float_format="%.6g")
    files = [path]
    z = df["z"].dropna()
    m = df["M500"].dropna()
    extra = {}
    if optical:
        r = df["richness"].dropna()
        extra = {"mass_proxy": "richness (NGALS); no M500 - mass tools skip this catalogue",
                 "richness_median": float(r.median()) if len(r) else None,
                 "richness_range": [float(r.min()), float(r.max())] if len(r) else None,
                 "n_in_cosmo": int(df["in_cosmo"].sum()), "n_with_zspec": int(df["z_spec"].notna().sum()),
                 "footprint": {k: meta["footprint"][k] for k in ("nside", "ordering", "effective_area_deg2",
                                                                 "raw_area_deg2")}}
    if include_members:
        files.append(_write_members(dataset, df, path))
        extra["members_csv"] = files[-1].name
    return ok(
        f"{dataset}: {len(df)} of {n_all} clusters after cuts -> {path.name}",
        files, dataset=dataset, survey=meta["survey"], n_catalog=n_all, n_selected=len(df),
        n_with_z=int(len(z)), n_with_mass=int(len(m)), cuts=active,
        z_range=[float(z.min()), float(z.max())] if len(z) else None,
        z_median=float(z.median()) if len(z) else None,
        m500_median_1e14=float(m.median()) if len(m) else None,
        m500_range_1e14=[float(m.min()), float(m.max())] if len(m) else None,
        area_deg2=meta.get("area_deg2"), columns=HARMONISED + extra_columns(dataset), citation=meta["citation"],
        **extra,
    )


def _write_members(dataset: str, df, cluster_csv):
    """Members of the selected clusters (WaZP ID_CLUSTER == cluster ID; join through NAME -> ID)."""
    import pandas as pd
    from astropy.io import fits

    from ..common import fetch_file
    spec = DATASETS[dataset]["members"]
    path = fetch_file(spec["url"], subdir=spec["subdir"], timeout=7200)
    nat = read_native(dataset)
    name_to_id = dict(zip(np.char.strip(np.asarray(nat["NAME"]).astype(str)), np.asarray(nat["ID"]), strict=True))
    ids = np.array([name_to_id[n] for n in df["name"] if n in name_to_id], dtype=np.int64)
    with fits.open(path, memmap=True) as h:
        d = h[1].data
        sel = np.isin(np.asarray(d["ID_CLUSTER"]), ids)
        cols = ["ID", "ID_CLUSTER", "RA", "DEC", "ZPHOT", "ZSPEC", "PMEM", "FLAG_CG",
                "MAG_G", "MAG_R", "MAG_I", "MAG_Z", "MAG_Y"]
        mem = pd.DataFrame({c.lower(): np.asarray(d[c][sel]).astype(bool if c == "FLAG_CG" else float)
                            if c not in ("ID", "ID_CLUSTER") else np.asarray(d[c][sel]) for c in cols})
    dest = cluster_csv.with_name(cluster_csv.stem + "_members.csv")
    mem.to_csv(dest, index=False, float_format="%.6g")
    return dest


@data_kind("catalog")
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
              extra_columns=meta.get("extra_columns"), mass_proxy=meta.get("mass_proxy", "M500"),
              footprint={k: v for k, v in meta["footprint"].items() if k != "url"} if "footprint" in meta else None,
              citation=meta["citation"])


@data_kind("summary_statistic")
@validate_call
def compute_cluster_counts(
    output_dir: OutArg,
    catalogs: Annotated[list[str], Field(min_length=1, description=(
        "Harmonised CSVs from fetch_cluster_catalog and/or dataset keys (full catalogue)."))],
    z_edges: Annotated[list[float] | None, Field(description="Redshift bin edges (default 0..1.6 step 0.1).")] = None,
    m500_min: Annotated[float | None, Field(ge=0, description="Mass threshold for N(z) in 1e14 Msun (None = all with z).")] = None,
    m_grid: Annotated[list[float] | None, Field(description="M500 thresholds [1e14 Msun] for N(>M) (default log 0.5..30).")] = None,
    normalise_by_area: Annotated[bool, Field(description="Also give counts per deg^2 using each dataset's area.")] = True,
    richness_min: Annotated[float | None, Field(ge=0, description=(
        "Richness threshold for N(z) of optical catalogues (des_y6_wazp NGALS); ignored for SZ/X-ray."))] = None,
    richness_grid: Annotated[list[float] | None, Field(description=(
        "Richness thresholds for N(>richness) of optical catalogues (default log 5..300)."))] = None,
    zmax_area: Annotated[bool, Field(description=(
        "des_y6_wazp: divide each z bin by the footprint area whose ZMAX exceeds z (averaged over the bin; the "
        "depth-limited area where richness is complete), instead of the full 4544.7 deg^2. Pair with in_cosmo "
        "clusters."))] = True,
) -> ArtifactResult:
    """Histogram cluster counts: N(z) per redshift bin and cumulative N(>M500) (or N(>richness)), per catalogue.

    Use to compare survey depths or as the observed side of predict_cluster_counts_lcdm.
    Writes counts_nz.csv and counts_nm.csv (+ a PNG with both panels). Optical catalogues
    without masses (des_y6_wazp) get N(>richness) rows in counts_nrich.csv instead of
    N(>M500); m500_min is not applied to them (use richness_min).
    """
    import pandas as pd

    from ..common import mpl, save_fig
    from ..registry import SURVEY_COLORS
    out = resolve_outdir(output_dir)
    z_edges = np.asarray(z_edges if z_edges else np.round(np.arange(0, 1.61, 0.1), 3), float)
    m_grid = np.asarray(m_grid if m_grid else np.logspace(np.log10(0.5), np.log10(30), 25), float)
    r_grid = np.asarray(richness_grid if richness_grid else np.round(np.logspace(np.log10(5), np.log10(300), 25), 2), float)
    nz_rows, nm_rows, nr_rows, summary = [], [], [], {}
    plt = mpl()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    a3 = None
    for cat in catalogs:
        df = read_table(cat)
        label = str(df["survey"].iloc[0]) if len(df) else str(cat)
        ds = str(df["dataset"].iloc[0]) if "dataset" in df.columns and len(df) else None
        area = DATASETS.get(ds, {}).get("area_deg2") if ds else None
        optical = "richness" in df.columns and not has_mass(ds) if ds else "richness" in df.columns
        zsel = df["z"].to_numpy(float)
        msel = df["M500"].to_numpy(float)
        keep = np.isfinite(zsel)
        if optical:
            rich = df["richness"].to_numpy(float)
            if richness_min is not None:
                keep &= rich >= richness_min
        elif m500_min is not None:
            keep &= msel >= m500_min
        nz, _ = np.histogram(zsel[keep], bins=z_edges)
        area_z = np.full(len(nz), area if area else np.nan, float)
        if optical and zmax_area and ds and "footprint" in DATASETS.get(ds, {}):
            from .footprint import registry_area_above_z
            # mean depth-limited area across each bin (area with ZMAX > z, averaged over z in the bin)
            area_z = np.array([registry_area_above_z(ds, np.linspace(lo, hi, 21)).mean()
                               for lo, hi in zip(z_edges[:-1], z_edges[1:], strict=True)])
        for i, n in enumerate(nz):
            a_i = area_z[i]
            nz_rows.append({"survey": label, "z_lo": z_edges[i], "z_hi": z_edges[i + 1], "N": int(n),
                            "N_poisson_err": float(np.sqrt(max(n, 1))),
                            "area_deg2": float(a_i) if np.isfinite(a_i) else np.nan,
                            "N_per_deg2": n / a_i if (normalise_by_area and np.isfinite(a_i) and a_i > 0) else np.nan})
        col = SURVEY_COLORS.get(label)
        a1.stairs(nz, z_edges, label=label, color=col, lw=1.8)
        if optical:
            rr = df["richness"].to_numpy(float)
            rr = rr[np.isfinite(rr) & np.isfinite(zsel)]
            nr = np.array([(rr >= t).sum() for t in r_grid])
            for t, n in zip(r_grid, nr, strict=True):
                nr_rows.append({"survey": label, "richness_min": t, "N_gt_richness": int(n),
                                "N_gt_richness_per_deg2": n / area if (area and normalise_by_area) else np.nan})
            if a3 is None:
                a3 = a2.twiny()
            a3.step(r_grid, nr, where="post", label=f"{label} (richness, top axis)", color=col, lw=1.8, ls="--")
            summary[label] = {"N_total": int(len(df)), "N_in_z_bins": int(nz.sum()), "area_deg2": area,
                              "mass_proxy": "richness", "richness_min": richness_min,
                              "z_median": float(np.nanmedian(zsel)) if np.isfinite(zsel).any() else None}
            continue
        mm = msel[np.isfinite(msel)]
        nm = np.array([(mm >= t).sum() for t in m_grid])
        for t, n in zip(m_grid, nm, strict=True):
            nm_rows.append({"survey": label, "M500_min_1e14": t, "N_gt_M": int(n),
                            "N_gt_M_per_deg2": n / area if (area and normalise_by_area) else np.nan})
        summary[label] = {"N_total": int(len(df)), "N_in_z_bins": int(nz.sum()), "area_deg2": area,
                          "z_median": float(np.nanmedian(zsel)) if np.isfinite(zsel).any() else None}
        if len(mm):
            a2.step(m_grid, nm, where="post", label=label, color=col, lw=1.8)
    a1.set(xlabel="z", ylabel="N per bin" + (f" (M500 > {m500_min}e14)" if m500_min else ""), title="N(z)")
    a2.set(xscale="log", yscale="log", xlabel=r"$M_{500c}$ [$10^{14} M_\odot$]", ylabel="N(>M)", title="N(>M)")
    if a3 is not None:
        a3.set(xscale="log", xlabel="richness NGALS (optical catalogues)")
        a3.legend(fontsize=8, loc="lower left")
    a1.legend(fontsize=8)
    if nm_rows:
        a2.legend(fontsize=8)
    f1, f2 = out / "counts_nz.csv", out / "counts_nm.csv"
    pd.DataFrame(nz_rows).to_csv(f1, index=False, float_format="%.6g")
    pd.DataFrame(nm_rows, columns=["survey", "M500_min_1e14", "N_gt_M", "N_gt_M_per_deg2"]).to_csv(
        f2, index=False, float_format="%.6g")
    files = [f1, f2]
    if nr_rows:
        f3 = out / "counts_nrich.csv"
        pd.DataFrame(nr_rows).to_csv(f3, index=False, float_format="%.6g")
        files.append(f3)
    png = save_fig(fig, out, "counts_nz_nm")
    return ok(f"Counts for {len(catalogs)} catalogue(s).", [*files, png], summary=summary,
              z_edges=z_edges.tolist(), m500_min=m500_min, richness_min=richness_min)


@data_kind("summary_statistic")
@validate_call
def compute_wazp_footprint_area(
    output_dir: OutArg,
    z_values: Annotated[list[float] | None, Field(description=(
        "Redshifts at which to report the depth-limited area (pixels with ZMAX > z). Default 0.5..1.0 step 0.02."))] = None,
    use_footprint_file: Annotated[bool, Field(description=(
        "True: download (540 MB, first use only) and reduce the HEALPix footprint FITS; False: use the "
        "registry table precomputed from the same file (instant, no download)."))] = False,
    dataset: Annotated[str, Field(description="Optical catalogue with a footprint (des_y6_wazp).")] = "des_y6_wazp",
) -> ArtifactResult:
    """Effective survey area [deg^2] of the DES Y6 WaZP footprint, total and as a function of redshift.

    Use to turn WaZP cluster counts into counts per deg^2: the footprint is a HEALPix
    map (Nside 4096, NESTED) with coverage fraction DETFRAC and depth limit ZMAX per pixel;
    effective area = sum(DETFRAC) x pixel area = 4544.7 deg^2, and at redshift z only the
    pixels with ZMAX > z have complete richness (IN_COSMO). Writes area_vs_z CSV.
    """
    import pandas as pd

    from .footprint import area_above_z, footprint_summary, registry_area_above_z
    meta = DATASETS.get(dataset, {})
    if "footprint" not in meta:
        raise ValueError(f"{dataset!r} has no footprint map; available: des_y6_wazp")
    zs = np.asarray(z_values if z_values else np.round(np.arange(0.5, 1.001, 0.02), 3), float)
    fp = meta["footprint"]
    if use_footprint_file:
        summ = footprint_summary(dataset)
        areas = area_above_z(summ, zs)
        info = {k: summ[k] for k in ("nside", "ordering", "n_pixels", "raw_area_deg2", "effective_area_deg2",
                                     "detfrac_min", "detfrac_max")}
        info = {k: (v.item() if hasattr(v, "item") else v) for k, v in info.items()}
        source = "footprint FITS (reduced and cached as *_zmaxhist.npz)"
    else:
        areas = registry_area_above_z(dataset, zs)
        info = {k: fp[k] for k in ("nside", "ordering", "n_pixels", "raw_area_deg2", "effective_area_deg2")}
        source = "registry table precomputed from the footprint FITS"
    out = resolve_outdir(output_dir)
    path = out / f"{dataset}_area_vs_z.csv"
    pd.DataFrame({"z": zs, "area_zmax_gt_z_deg2": areas,
                  "fraction_of_total": areas / float(info["effective_area_deg2"])}).to_csv(
        path, index=False, float_format="%.6g")
    return ok(f"{dataset}: effective area {float(info['effective_area_deg2']):.1f} deg^2 "
              f"(Nside {info['nside']} {info['ordering']}); area with ZMAX>z written for {len(zs)} redshifts",
              [path], dataset=dataset, source=source, footprint=info,
              area_at_z={f"{z:.2f}": round(float(a), 1) for z, a in zip(zs[::5], areas[::5], strict=True)},
              note="Counts per deg^2 at z: divide N(z) of in_cosmo clusters by area_zmax_gt_z_deg2. "
                   "Benoist+25 quote 4,545 deg^2.",
              citation=meta["citation"])
