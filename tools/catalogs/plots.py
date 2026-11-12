"""plot_mass_redshift, plot_cluster_sky_map."""

from __future__ import annotations

from typing import Annotated, Literal

import numpy as np
from pydantic import Field, validate_call

from ..common import ArtifactResult, data_kind, mpl, ok, resolve_outdir, save_fig
from ..registry import SURVEY_COLORS
from .io import read_table

CatList = Annotated[list[str], Field(min_length=1, description=(
    "Harmonised CSVs from fetch_cluster_catalog and/or dataset keys (full catalogue)."))]


@data_kind("catalog")
@validate_call
def plot_mass_redshift(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for the PNG.")],
    catalogs: CatList,
    log_mass: Annotated[bool, Field(description="Log M500 axis.")] = True,
    z_max: Annotated[float | None, Field(gt=0, description="Upper x limit.")] = None,
    marker_size: Annotated[float, Field(gt=0, description="Scatter marker size.")] = 6.0,
    stem: Annotated[str, Field(description="Output file stem.")] = "mass_redshift",
) -> ArtifactResult:
    """Overlay several cluster catalogues in the M500-z plane (the standard selection-function picture).

    Use to show how SZ (flat-in-M at high z) and X-ray (flux-limited, low z, low mass)
    selections differ. Only entries with both z and M500 are drawn.
    """
    plt = mpl()
    out = resolve_outdir(output_dir)
    fig, ax = plt.subplots(figsize=(8, 5.5))
    stats = {}
    dfs = [read_table(c) for c in catalogs]
    skipped = [str(d["survey"].iloc[0]) for d in dfs if len(d) and "richness" in d.columns and d["M500"].isna().all()]
    dfs = [d for d in dfs if not (len(d) and "richness" in d.columns and d["M500"].isna().all())]
    if not dfs:
        raise ValueError(f"No catalogue with M500 to plot ({', '.join(skipped)} carry richness, not mass)")
    order = np.argsort([-len(d) for d in dfs])  # big catalogues underneath
    for i in order:
        df = dfs[i]
        ok_ = np.isfinite(df["z"]) & np.isfinite(df["M500"])
        d = df[ok_]
        label = str(df["survey"].iloc[0]) if len(df) else catalogs[i]
        ax.scatter(d["z"], d["M500"], s=marker_size, alpha=0.5 if len(d) > 2000 else 0.75,
                   color=SURVEY_COLORS.get(label), label=f"{label} ({len(d)})", lw=0)
        stats[label] = {"n_plotted": int(len(d)),
                        "z_median": float(d["z"].median()) if len(d) else None,
                        "m500_median_1e14": float(d["M500"].median()) if len(d) else None,
                        "m500_p10_p90": [float(d["M500"].quantile(0.1)), float(d["M500"].quantile(0.9))] if len(d) else None}
    ax.set(xlabel="redshift", ylabel=r"$M_{500c}$ [$10^{14}\,M_\odot$]", title="Cluster mass-redshift plane")
    if log_mass:
        ax.set_yscale("log")
    if z_max:
        ax.set_xlim(0, z_max)
    ax.legend(markerscale=3, fontsize=8)
    ax.grid(alpha=0.3)
    png = save_fig(fig, out, stem)
    return ok(f"M500-z plot of {len(dfs)} catalogue(s)." + (f" Skipped (no mass): {', '.join(skipped)}." if skipped else ""),
              [png], per_survey=stats, skipped_no_mass=skipped,
              note="Masses come from survey-specific scaling relations; see describe_catalog_columns. "
                   "Optical catalogues (DES Y6 WaZP) have richness, not M500, and are skipped.")


@data_kind("catalog")
@validate_call
def plot_cluster_sky_map(
    output_dir: Annotated[str, Field(min_length=1, description="Directory for the PNG.")],
    catalogs: CatList,
    coords: Annotated[Literal["equatorial", "galactic"], Field(description="Coordinate frame of the map.")] = "equatorial",
    color_by: Annotated[Literal["survey", "z", "M500", "richness"], Field(description=(
        "Colour points by survey, redshift, mass, or richness (optical catalogues only).")) ] = "survey",
    marker_size: Annotated[float, Field(gt=0, description="Marker size.")] = 3.0,
    stem: Annotated[str, Field(description="Output file stem.")] = "sky_map",
) -> ArtifactResult:
    """Mollweide sky map of one or more cluster catalogues (RA increasing to the left, astronomical convention).

    Use to show footprints and overlaps (e.g. SPT south, ACT equatorial strip,
    eRASS1 western Galactic half, Planck all-sky) before a crossmatch.
    """
    plt = mpl()
    out = resolve_outdir(output_dir)
    fig = plt.figure(figsize=(11, 6))
    ax = fig.add_subplot(111, projection="mollweide")
    counts = {}
    sc = None
    for cat in catalogs:
        df = read_table(cat)
        label = str(df["survey"].iloc[0]) if len(df) else cat
        lon, lat = df["ra"].to_numpy(float), df["dec"].to_numpy(float)
        if coords == "galactic":
            from astropy import units as u
            from astropy.coordinates import SkyCoord
            g = SkyCoord(lon * u.deg, lat * u.deg, frame="icrs").galactic
            lon, lat = g.l.deg, g.b.deg
        x = -np.radians(np.where(lon > 180, lon - 360, lon))  # east to the left
        y = np.radians(lat)
        if color_by == "survey":
            ax.scatter(x, y, s=marker_size, color=SURVEY_COLORS.get(label), label=f"{label} ({len(df)})", lw=0, alpha=0.7)
        else:
            if color_by not in df.columns:
                raise ValueError(f"{label} has no {color_by!r} column")
            vals = df[color_by].to_numpy(float)
            sc = ax.scatter(x, y, s=marker_size, c=np.log10(vals) if color_by in ("M500", "richness") else vals,
                            cmap="viridis", lw=0, alpha=0.8, label=label)
        counts[label] = int(len(df))
    ticks = np.arange(-150, 181, 30)
    ax.set_xticks(np.radians(ticks))
    ax.set_xticklabels([f"{(-t) % 360}°" for t in ticks], fontsize=7)
    ax.grid(alpha=0.3)
    if color_by == "survey":
        ax.legend(loc="lower right", markerscale=4, fontsize=7, bbox_to_anchor=(1.12, -0.05))
    elif sc is not None:
        fig.colorbar(sc, ax=ax, orientation="horizontal", shrink=0.6, pad=0.06,
                     label={"M500": "log10 M500 [1e14 Msun]", "richness": "log10 richness NGALS"}.get(color_by, "z"))
    ax.set_title(f"Cluster catalogues ({coords})", pad=14)
    png = save_fig(fig, out, f"{stem}_{coords}")
    return ok(f"Sky map ({coords}) of {sum(counts.values())} clusters.", [png], counts=counts, coords=coords)
