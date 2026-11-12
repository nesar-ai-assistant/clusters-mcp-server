"""DES Y6 WaZP footprint: effective area and area(z) from the HEALPix coverage map.

The footprint FITS (540 MB) is a partial HEALPix map, Nside 4096, NESTED ordering
(explicit pixel indexing): columns PIXEL, DETFRAC (detection coverage fraction of the
pixel, 0.11-1) and ZMAX (highest redshift at which the WaZP richness is complete given
the local z-band depth, Benoist+25 Sect. 2.2). Effective area = sum(DETFRAC) * pixel area.
For counts at redshift z, the relevant area is sum(DETFRAC) over pixels with ZMAX > z
(this is what the catalogue's IN_COSMO flag selects on).

The reduction (a DETFRAC-weighted ZMAX histogram) is computed once and cached as a small
.npz next to the FITS, so later calls never re-read the 540 MB file.
"""

from __future__ import annotations

import numpy as np

from ..common import data_cache_dir, fetch_file
from ..registry import DATASETS

ZMAX_EDGES = np.round(np.arange(0.0, 1.5001, 0.005), 3)


def _pixel_area_deg2(nside: int) -> float:
    return 4 * np.pi * (180 / np.pi) ** 2 / (12 * nside**2)


def reduce_footprint(path) -> dict:
    """Read the footprint FITS and return header info + DETFRAC-weighted ZMAX histogram (deg^2)."""
    from astropy.io import fits
    with fits.open(path, memmap=True) as h:
        hdr = h[1].header
        nside = int(hdr["NSIDE"])
        ordering = str(hdr.get("ORDERING", "")).strip()
        d = h[1].data
        frac = np.asarray(d["DETFRAC"], dtype=float)
        zmax = np.asarray(d["ZMAX"], dtype=float)
    pa = _pixel_area_deg2(nside)
    hist, _ = np.histogram(np.clip(zmax, ZMAX_EDGES[0], ZMAX_EDGES[-1] - 1e-9), bins=ZMAX_EDGES, weights=frac * pa)
    return {"nside": nside, "ordering": ordering, "n_pixels": int(frac.size),
            "pixel_area_deg2": pa, "raw_area_deg2": float(frac.size * pa),
            "effective_area_deg2": float(frac.sum() * pa),
            "detfrac_min": float(frac.min()), "detfrac_max": float(frac.max()),
            "zmax_edges": ZMAX_EDGES, "area_hist_deg2": hist}


def footprint_summary(dataset: str = "des_y6_wazp") -> dict:
    """Cached footprint reduction (downloads the footprint FITS on first use)."""
    spec = DATASETS[dataset]["footprint"]
    cache = data_cache_dir() / spec["subdir"] / (spec["url"].rsplit("/", 1)[-1].replace(".fits", "_zmaxhist.npz"))
    if cache.is_file():
        z = np.load(cache)
        out = {k: z[k] for k in ("zmax_edges", "area_hist_deg2")}
        out.update({k: z[k].item() for k in z.files if k not in out})
        return out
    path = fetch_file(spec["url"], subdir=spec["subdir"], timeout=3600)
    red = reduce_footprint(path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, **{k: np.asarray(v) for k, v in red.items()})
    return red


def area_above_z(summary: dict, z) -> np.ndarray:
    """Effective area [deg^2] of pixels whose ZMAX exceeds z (richness complete at z)."""
    edges, hist = np.asarray(summary["zmax_edges"]), np.asarray(summary["area_hist_deg2"])
    cum = np.concatenate([np.cumsum(hist[::-1])[::-1], [0.0]])  # area with ZMAX >= edge
    return np.interp(np.atleast_1d(np.asarray(z, float)), edges, cum)


def registry_area_above_z(dataset: str, z) -> np.ndarray:
    """Same as area_above_z but from the registry's precomputed table (no download)."""
    tab = DATASETS[dataset]["footprint"]["area_zmax_gt_deg2"]
    zs = np.array(sorted(tab), float)
    a = np.array([tab[k] for k in sorted(tab)], float)
    zz = np.atleast_1d(np.asarray(z, float))
    return np.where(zz <= zs[0], DATASETS[dataset]["area_deg2"], np.interp(zz, zs, a))
