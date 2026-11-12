"""SPT-SZ Megacam weak-lensing data (Dietrich+19) and NFW mass fits.

Data: the official SPT-SZ cluster likelihood release (Bocquet et al. 2019),
https://pole.uchicago.edu/public/data/sptsz-clusters/SPT_SZ_cluster_likelihood-0.0.tar.gz
(MIT licence). For each of the 19 Megacam clusters it ships
``data/Megacam/<SPT_ID>/<SPT_ID>_shear.txt`` and ``<SPT_ID>_Nz.txt``:

* shear.txt: 8 radial bins over 0.75-2.5 Mpc (Dietrich+19 Sect. 5.1; r in degrees),
  columns ``r/deg  gt  Delta gt  kbin`` plus an unnamed 5th column. gt is the weighted
  mean reduced tangential shear, already corrected for cluster-member contamination
  (Dietrich+19 eq. 18); Delta gt is its 1-sigma error. The release does not document
  ``kbin``, and the official likelihood (lensing.py) reads only columns 0-2. See
  KBIN_NOTE for what the numbers look like.
* Nz.txt: the source-galaxy redshift histogram (``z  N(z)``, dz = 0.025, 0-5) after the
  colour/magnitude cuts, which the likelihood uses to compute <beta> and <beta^2>.

The fit mirrors lensing.py: Sigma_crit = c^2/(4 pi G D_l <beta>), NFW Delta Sigma and
Sigma (Wright & Brainerd 2000), reduced shear
g = gamma/(1-kappa) * (1 + kappa (<beta^2>/<beta>^2 - 1)) (Seitz & Schneider 1997),
and a Gaussian likelihood per bin. Dietrich+19 fit the full 0.75-2.5 Mpc range with c fixed
by the Diemer & Kravtsov 2015 c(M); the likelihood code instead uses only 0.5-1.5 Mpc
(h=0.7 reference cosmology) inside its joint mass-calibration model.
"""

from __future__ import annotations

import io
import re
import tarfile

import numpy as np
from numpy.lib import scimath as sm

from ..common import fetch_file
from ..registry import DATASETS

SIGMA_CRIT_PREFAC = 1.6624541593797974e18  # c^2 / (4 pi G) [Msun / Mpc], as in the SPT lensing.py

RELEASE_URL = "https://pole.uchicago.edu/public/data/sptsz-clusters/SPT_SZ_cluster_likelihood-0.0.tar.gz"

KBIN_NOTE = DATASETS["spt_sz"]["wl_data"]["kbin_note"]

# Dietrich+19 (MNRAS 483, 2871) Table 3: <beta>, <beta^2> and n_gal [arcmin^-2] per Megacam cluster
D19_SOURCE_TABLE = {
    "SPT-CLJ0234-5831": (0.48, 0.25, 12.1), "SPT-CLJ0240-5946": (0.50, 0.27, 12.3),
    "SPT-CLJ0254-5857": (0.46, 0.23, 11.1), "SPT-CLJ0307-6225": (0.40, 0.18, 7.9),
    "SPT-CLJ0317-5935": (0.46, 0.23, 9.2), "SPT-CLJ0346-5439": (0.40, 0.18, 13.1),
    "SPT-CLJ0348-4515": (0.56, 0.32, 12.1), "SPT-CLJ0426-5455": (0.35, 0.14, 8.9),
    "SPT-CLJ0509-5342": (0.46, 0.23, 11.7), "SPT-CLJ0516-5430": (0.60, 0.37, 9.3),
    "SPT-CLJ0551-5709": (0.48, 0.24, 8.4), "SPT-CLJ2022-6323": (0.51, 0.28, 7.4),
    "SPT-CLJ2030-5638": (0.50, 0.27, 9.0), "SPT-CLJ2032-5627": (0.60, 0.37, 8.4),
    "SPT-CLJ2135-5726": (0.47, 0.24, 9.7), "SPT-CLJ2138-6008": (0.54, 0.31, 4.0),
    "SPT-CLJ2145-5644": (0.44, 0.21, 9.9), "SPT-CLJ2332-5358": (0.51, 0.27, 11.5),
    "SPT-CLJ2355-5055": (0.57, 0.34, 10.1),
}

# Dietrich+19 Fig. 9 (comparison with High+12): NFW M500 at R500,WL [1e14 Msun] of the 5 clusters the
# paper labels individually. Digitised from the vector PDF figure in the arXiv source (1711.05344,
# figures/high_comparison.pdf; axis ticks 1e14/1e15 -> log mapping, symmetric 1-sigma error bars).
# The paper does not tabulate the other 14 individual masses.
D19_PUBLISHED_M500 = {
    "SPT-CLJ0516-5430": (7.70, 2.19), "SPT-CLJ2022-6323": (3.78, 2.30), "SPT-CLJ2030-5638": (2.73, 1.63),
    "SPT-CLJ2032-5627": (9.08, 3.14), "SPT-CLJ2135-5726": (7.65, 2.66),
}
D19_PUBLISHED_NOTE = ("Dietrich+19 Fig. 9 (High+12 comparison), digitised from the vector figure in the arXiv "
                      "source; fit with c(M) of Diemer & Kravtsov 2015 over 0.75-2.5 Mpc, Om=0.3, h=0.7.")


# ----------------------------------------------------------------------------- data access
def release_path():
    meta = DATASETS["spt_sz"]["wl_data"]
    return fetch_file(meta["url"], subdir=meta["subdir"], timeout=600)


def read_megacam() -> dict:
    """{cluster: {"shear": (n,5) array, "nz": (m,2) array}} from the release tarball (cached in-process)."""
    from ..common import get_cached

    def load():
        prefix = DATASETS["spt_sz"]["wl_data"]["archive_member_prefix"] + "Megacam/"
        out: dict = {}
        with tarfile.open(release_path(), "r:gz") as tf:
            for m in tf.getmembers():
                if not (m.isfile() and m.name.startswith(prefix)):
                    continue
                kind = "shear" if m.name.endswith("_shear.txt") else "nz" if m.name.endswith("_Nz.txt") else None
                if kind is None:
                    continue
                cluster = m.name.split("/")[-2]
                fh = tf.extractfile(m)
                out.setdefault(cluster, {})[kind] = np.loadtxt(io.BytesIO(fh.read()), comments="#", ndmin=2)
        return {k: v for k, v in sorted(out.items()) if "shear" in v and "nz" in v}
    return get_cached("megacam_release", load)


def spt_redshifts(names) -> dict:
    """Cluster redshifts from the SPT-SZ 2500d catalogue (Bocquet+19)."""
    from ..catalogs.io import load_catalog
    df = load_catalog("spt_sz")
    zmap = dict(zip(df["name"], df["z"], strict=True))
    return {n: float(zmap[n]) for n in names if n in zmap and np.isfinite(zmap[n])}


# ----------------------------------------------------------------------------- physics
class FlatLCDM:
    """Minimal flat LCDM distances (astropy) with h-ful masses in Msun (no h scaling)."""

    def __init__(self, Om0: float = 0.3, h: float = 0.7):
        from astropy.cosmology import FlatLambdaCDM
        self.Om0, self.h = Om0, h
        self.c = FlatLambdaCDM(H0=100 * h, Om0=Om0)

    def dA(self, z):
        return np.asarray(self.c.angular_diameter_distance(z).value, float)  # Mpc

    def dA12(self, z1, z2):
        try:
            d = self.c.angular_diameter_distance(z1, z2)  # astropy >= 7.1
        except TypeError:
            d = self.c.angular_diameter_distance_z1z2(z1, z2)
        return np.asarray(d.value, float)

    def rho_c(self, z):
        return float(self.c.critical_density(z).to("Msun/Mpc3").value)


def beta_moments(nz: np.ndarray, z_l: float, cosmo: FlatLCDM) -> tuple[float, float]:
    """<beta>, <beta^2> with beta = D_ls/D_s (0 for z_s <= z_l), weighted by N(z) (as lensing.py get_beta)."""
    zs, w = nz[:, 0], nz[:, 1]
    beta = np.zeros_like(zs)
    bg = zs > z_l
    beta[bg] = cosmo.dA12(z_l, zs[bg]) / cosmo.dA(zs[bg])
    return float(np.sum(w * beta) / w.sum()), float(np.sum(w * beta**2) / w.sum())


def concentration_200c(m200c, z, model: str, cosmo: FlatLCDM):
    """c200c(M200c [Msun], z). duffy08: Duffy+08 full-sample 200c fit; diemer15/diemer19 via colossus."""
    m200c = np.asarray(m200c, float)
    if model == "duffy08":
        return 5.71 * (m200c * cosmo.h / 2e12) ** -0.084 * (1 + z) ** -0.47
    try:
        from colossus.cosmology import cosmology as ccosmo
        from colossus.halo import concentration
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(f"c(M) model {model!r} needs colossus (pip install colossus); "
                           "or use concentration_model='duffy08'") from exc
    ccosmo.setCosmology("clusters_wl", {"flat": True, "H0": 100 * cosmo.h, "Om0": cosmo.Om0, "Ob0": 0.049,
                                        "sigma8": 0.81, "ns": 0.965}, persistence="")
    return np.asarray(concentration.concentration(m200c * cosmo.h, "200c", z, model=model), float)


def _arcsec(x):
    return 0.5 * np.pi + 1j * np.log(sm.sqrt(1 - 1.0 / x**2) + 1j / x)


def nfw_sigma_dsigma(x, rs, rho_c, delta_c):
    """NFW Sigma and Delta Sigma [Msun/Mpc^2] at x = R/r_s (lensing.py get_Sigma / get_Delta_Sigma)."""
    fac = 2 * rs * rho_c * delta_c
    root = sm.sqrt(x**2 - 1)
    dsig = fac * (1 / (1 - x**2) + (((3 * x**2) - 2) * _arcsec(x) / (x**2 * root**3)).real + 2 * np.log(x / 2) / x**2)
    sig = fac * (1 / (x**2 - 1) - (_arcsec(x) / root**3).real)
    return np.real(sig), np.real(dsig)


def m_delta_from_200c(m200c, c200c, delta: float = 500.0):
    """Convert NFW M200c (c200c) to M_delta,c."""
    from scipy.optimize import brentq
    mu = lambda c: np.log(1 + c) - c / (1 + c)  # noqa: E731
    out = np.empty_like(np.asarray(m200c, float))
    for i, (m, c) in enumerate(zip(np.atleast_1d(m200c), np.atleast_1d(c200c), strict=True)):
        cd = brentq(lambda cc, c=c: mu(c) / mu(cc) - (200.0 / delta) * (c / cc) ** 3, 1e-3, 100.0)
        out[i] = m * mu(cd) / mu(c)
    return out


def reduced_shear_model(r_mpc, m200c, z_l, beta, beta2, cmodel, cosmo: FlatLCDM):
    """Model g_t [len(r), len(M)] for an NFW halo grid."""
    m200c = np.atleast_1d(np.asarray(m200c, float))
    rho_c = cosmo.rho_c(z_l)
    c = concentration_200c(m200c, z_l, cmodel, cosmo)
    r200 = (3 * m200c / (4 * np.pi * 200 * rho_c)) ** (1 / 3)
    rs = r200 / c
    delta_c = 200 / 3 * c**3 / (np.log(1 + c) - c / (1 + c))
    x = np.asarray(r_mpc, float)[:, None] / rs[None, :]
    sig, dsig = nfw_sigma_dsigma(x, rs[None, :], rho_c, delta_c[None, :])
    s_crit = SIGMA_CRIT_PREFAC / float(cosmo.dA(z_l)) / beta
    gamma, kappa = dsig / s_crit, sig / s_crit
    return gamma / (1 - kappa) * (1 + kappa * (beta2 / beta**2 - 1)), c


def fit_cluster(cluster: str, shear: np.ndarray, nz: np.ndarray, z_l: float, *, cmodel: str = "diemer15",
                cosmo: FlatLCDM | None = None, r_min_mpc: float = 0.0, r_max_mpc: float = np.inf,
                mgrid=None) -> dict:
    """Grid NFW fit of one cluster's g_t(r): likelihood on log-spaced M200c, flat prior in ln M."""
    cosmo = cosmo or FlatLCDM()
    beta, beta2 = beta_moments(nz, z_l, cosmo)
    r_mpc = shear[:, 0] * np.pi / 180 * float(cosmo.dA(z_l))
    keep = (r_mpc > r_min_mpc) & (r_mpc < r_max_mpc)
    if keep.sum() < 2:
        raise ValueError(f"{cluster}: fewer than 2 radial bins inside [{r_min_mpc}, {r_max_mpc}] Mpc")
    r, g, ge = r_mpc[keep], shear[keep, 1], shear[keep, 2]
    m = np.asarray(mgrid if mgrid is not None else np.logspace(13.0, 15.9, 581), float)
    model, c = reduced_shear_model(r, m, z_l, beta, beta2, cmodel, cosmo)
    chi2 = np.sum(((model - g[:, None]) / ge[:, None]) ** 2, axis=0)
    like = np.exp(-0.5 * (chi2 - chi2.min()))
    cdf = np.cumsum(like)
    cdf /= cdf[-1]
    m500 = m_delta_from_200c(m, c, 500.0)
    q = lambda arr, p: float(np.interp(p, cdf, arr))  # noqa: E731
    ibest = int(np.argmin(chi2))
    return {
        "cluster": cluster, "z": z_l, "beta_mean": beta, "beta2_mean": beta2,
        "sigma_crit_Msun_pc2": SIGMA_CRIT_PREFAC / float(cosmo.dA(z_l)) / beta / 1e12,
        "n_bins_used": int(keep.sum()), "r_min_mpc": float(r.min()), "r_max_mpc": float(r.max()),
        "M500c_ml": m500[ibest] / 1e14, "M500c_median": q(m500, 0.5) / 1e14,
        "M500c_lo": q(m500, 0.16) / 1e14, "M500c_hi": q(m500, 0.84) / 1e14,
        "M200c_ml": m[ibest] / 1e14, "M200c_median": q(m, 0.5) / 1e14,
        "M200c_lo": q(m, 0.16) / 1e14, "M200c_hi": q(m, 0.84) / 1e14,
        "c200c_ml": float(c[ibest]), "chi2_min": float(chi2.min()), "dof": int(keep.sum() - 1),
        "_r_mpc": r, "_g": g, "_ge": ge, "_model_best": model[:, ibest],
    }


def name_to_radec(name: str):
    m = re.search(r"J(\d\d)(\d\d)([-+])(\d\d)(\d\d)", name)
    hh, mm, sgn, dd, dm = m.groups()
    return 15 * (int(hh) + int(mm) / 60), (int(dd) + int(dm) / 60) * (-1 if sgn == "-" else 1)
