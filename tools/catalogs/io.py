"""Catalogue readers: download (or use bundled copy), read FITS, harmonise columns.

Harmonised schema (every fetch writes these, in this order):
    name, ra, dec [deg, J2000], z, z_err, M500 [1e14 Msun, M500c],
    M500_err_lo, M500_err_hi [1e14 Msun, 1-sigma], snr, survey, dataset
``snr`` is each survey's native detection statistic: xi (SPT), SNR (ACT,
Planck) or the extent likelihood EXT_LIKE (eROSITA) - NOT directly comparable.
Missing values (no redshift / no mass) are NaN.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

import threading

from ..common import data_cache_dir, fetch_file
from ..registry import DATASETS

_CACHE: dict = {}
_LOCK = threading.RLock()  # re-entrant: harmonising erass1_cosmo reads the erass1 table


def get_cached(key, factory):
    with _LOCK:
        if key not in _CACHE:
            _CACHE[key] = factory()
        return _CACHE[key]


HARMONISED = ["name", "ra", "dec", "z", "z_err", "M500", "M500_err_lo", "M500_err_hi", "snr", "survey", "dataset"]


def _local_fits(dataset: str) -> Path:
    spec = DATASETS[dataset]["file"]
    path = fetch_file(spec["url"], subdir=spec["subdir"], timeout=600)
    member = spec.get("archive_member")
    if member is None:
        return path
    dest = data_cache_dir() / spec["subdir"] / member
    if not (dest.is_file() and dest.stat().st_size > 0):
        with tarfile.open(path, "r:gz") as tf:
            names = [m for m in tf.getmembers() if m.name.endswith(member) and m.isfile()]
            if not names:
                raise RuntimeError(f"{member} not found inside {path}")
            fh = tf.extractfile(names[0])
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(fh.read())
            tmp.replace(dest)
    return dest


def read_native(dataset: str):
    """The raw FITS table (astropy Table) for a dataset, without the multidim columns."""
    from astropy.table import Table

    def load():
        t = Table.read(_local_fits(dataset), hdu=DATASETS[dataset]["file"].get("hdu", 1))
        keep = [c for c in t.colnames if t[c].ndim <= 1]
        return t[keep]
    return get_cached(f"native:{dataset}", load)


def _col(t, name, scale=1.0):
    return np.asarray(t[name], dtype=float) * scale


def _str(t, name):
    v = np.asarray(t[name])
    if v.dtype.kind == "S":
        v = np.char.decode(v, "ascii")
    return np.char.strip(v.astype(str))


def _harmonise(dataset: str) -> pd.DataFrame:
    meta = DATASETS[dataset]
    m = meta["columns"]
    t = read_native(dataset)
    n = len(t)
    ms = m.get("mass_scale", 1.0)
    df = pd.DataFrame({
        "name": _str(t, m["name"]),
        "ra": _col(t, m["ra"]),
        "dec": _col(t, m["dec"]),
        "z": _col(t, m["z"]),
        "z_err": _col(t, m["z_err"]) if m.get("z_err") else np.full(n, np.nan),
        "M500": _col(t, m["M500"], ms) if m.get("M500") else np.full(n, np.nan),
    })
    if m.get("M500_lo_is_bound"):  # eROSITA: lower/upper 1-sigma BOUNDS, not errors
        df["M500_err_lo"] = df["M500"] - _col(t, m["M500_err_lo"], ms)
        df["M500_err_hi"] = _col(t, m["M500_err_hi"], ms) - df["M500"]
    else:
        df["M500_err_lo"] = np.abs(_col(t, m["M500_err_lo"], ms)) if m.get("M500_err_lo") else np.nan
        df["M500_err_hi"] = np.abs(_col(t, m["M500_err_hi"], ms)) if m.get("M500_err_hi") else np.nan
    df["snr"] = _col(t, m["snr"]) if m.get("snr") else np.nan
    df["survey"] = meta["survey"]
    df["dataset"] = dataset
    # sentinels -> NaN: z <= 0 (no redshift), M500 <= 0 (unconfirmed / failed), M500 >= 1e16 Msun (fit failure)
    bad_z = ~(df["z"] > 0)
    df.loc[bad_z, ["z", "z_err"]] = np.nan
    bad_m = ~((df["M500"] > 0) & (df["M500"] < 100))
    df.loc[bad_m, ["M500", "M500_err_lo", "M500_err_hi"]] = np.nan
    if dataset == "erass1_cosmo":  # masses / EXT_LIKE live in the primary catalogue: join on DETUID
        prim = read_native("erass1")
        pidx = {u: i for i, u in enumerate(_str(prim, "DETUID"))}
        idx = np.array([pidx.get(u, -1) for u in _str(t, "DETUID")])
        okj = idx >= 0
        pm = _col(prim, "M500", 0.1)
        for col, vals in (("M500", pm), ("M500_err_lo", pm - _col(prim, "M500_L", 0.1)),
                          ("M500_err_hi", _col(prim, "M500_H", 0.1) - pm), ("snr", _col(prim, "EXT_LIKE"))):
            arr = np.full(n, np.nan)
            arr[okj] = vals[idx[okj]]
            df[col] = arr
        bad_m = ~((df["M500"] > 0) & (df["M500"] < 100))
        df.loc[bad_m, ["M500", "M500_err_lo", "M500_err_hi"]] = np.nan
    return df[HARMONISED]


def load_catalog(dataset: str) -> pd.DataFrame:
    """Full harmonised catalogue (cached in-process). Returns a copy."""
    if dataset not in DATASETS or "columns" not in DATASETS[dataset]:
        raise ValueError(f"Unknown catalogue {dataset!r}. Available: {', '.join(catalog_keys())}")
    return get_cached(f"harm:{dataset}", lambda: _harmonise(dataset)).copy()


def catalog_keys() -> list[str]:
    return [k for k, v in DATASETS.items() if "columns" in v]


def apply_cuts(df: pd.DataFrame, z_min=None, z_max=None, m_min=None, m_max=None, snr_min=None,
               require_z=False, require_mass=False) -> pd.DataFrame:
    sel = np.ones(len(df), bool)
    if z_min is not None:
        sel &= df["z"].to_numpy() >= z_min
    if z_max is not None:
        sel &= df["z"].to_numpy() <= z_max
    if m_min is not None:
        sel &= df["M500"].to_numpy() >= m_min
    if m_max is not None:
        sel &= df["M500"].to_numpy() <= m_max
    if snr_min is not None:
        sel &= df["snr"].to_numpy() >= snr_min
    if require_z:
        sel &= np.isfinite(df["z"].to_numpy())
    if require_mass:
        sel &= np.isfinite(df["M500"].to_numpy())
    return df[sel].reset_index(drop=True)


def read_table(path_or_key: str) -> pd.DataFrame:
    """A harmonised CSV written by fetch_cluster_catalog, or a dataset key (full catalogue)."""
    if path_or_key in DATASETS:
        return load_catalog(path_or_key)
    p = Path(path_or_key).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"{path_or_key!r} is neither a dataset key ({', '.join(catalog_keys())}) "
                                "nor an existing CSV file")
    df = pd.read_csv(p, comment="#")
    missing = {"ra", "dec", "z", "M500"} - set(df.columns)
    if missing:
        raise ValueError(f"{p} lacks harmonised column(s) {sorted(missing)}; pass a fetch_cluster_catalog CSV")
    if "survey" not in df.columns:
        df["survey"] = p.stem
    return df
