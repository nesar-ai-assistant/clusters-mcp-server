"""Dispatchable LCDM cluster-count kernels (numpy + scipy only, JSON in -> JSON out).

Halo mass function: Tinker et al. (2008, ApJ 688, 709), Table 2 parameters
interpolated in log10(Delta_mean), with the paper's redshift evolution
(eqs. 5-8). Linear power: Eisenstein & Hu (1998, ApJ 496, 605) zero-baryon
("no-wiggle") transfer function, normalised to sigma8. Growth: exact linear
growth for flat LCDM (Heath 1977 integral). Radiation is neglected.

Units: halo masses in Msun/h inside the kernel; the public API takes/returns
masses in 1e14 Msun (h70 catalogue convention) and converts with ``h``.
Comoving volumes in (Mpc/h)^3. These choices make the predictions good to a
few per cent against colossus for the same cosmology (see tests), which is
far below the cluster mass-calibration systematics.
"""

from __future__ import annotations

import numpy as np
from scipy import integrate, interpolate

C_KMS = 299792.458
RHO_CRIT0 = 2.77536627e11  # h^2 Msun / Mpc^3

# Tinker+08 Table 2 (Delta w.r.t. the MEAN matter density)
_T08_DELTA = np.array([200, 300, 400, 600, 800, 1200, 1600, 2400, 3200], float)
_T08_A = np.array([0.186, 0.200, 0.212, 0.218, 0.248, 0.255, 0.260, 0.260, 0.260])
_T08_a = np.array([1.47, 1.52, 1.56, 1.61, 1.87, 2.13, 2.30, 2.53, 2.66])
_T08_b = np.array([2.57, 2.25, 2.05, 1.87, 1.59, 1.51, 1.46, 1.44, 1.41])
_T08_c = np.array([1.19, 1.27, 1.34, 1.45, 1.58, 1.80, 1.97, 2.24, 2.44])

FIDUCIAL = {"Om0": 0.3, "Ob0": 0.049, "h": 0.7, "ns": 0.965, "sigma8": 0.8}


# ------------------------------------------------------------------ background
def efunc(z, Om0):
    z = np.asarray(z, float)
    return np.sqrt(Om0 * (1 + z) ** 3 + (1 - Om0))


def omega_m_z(z, Om0):
    return Om0 * (1 + np.asarray(z, float)) ** 3 / efunc(z, Om0) ** 2


def comoving_distance(z, Om0):
    """Line-of-sight comoving distance in Mpc/h (flat)."""
    z = np.atleast_1d(np.asarray(z, float))
    zz = np.linspace(0, max(z.max(), 1e-4), 4000)
    chi = integrate.cumulative_trapezoid(1.0 / efunc(zz, Om0), zz, initial=0.0) * (C_KMS / 100.0)
    return np.interp(z, zz, chi)


def dvdz_dsr(z, Om0):
    """Comoving volume element dV/dz/dOmega in (Mpc/h)^3 / sr."""
    chi = comoving_distance(z, Om0)
    return chi ** 2 * (C_KMS / 100.0) / efunc(z, Om0)


def growth_factor(z, Om0):
    """Linear growth D(z)/D(0) for flat LCDM (Heath integral, tabulated on 0<=z<=10 and interpolated)."""
    z = np.atleast_1d(np.asarray(z, float))
    key = round(float(Om0), 10)
    if key not in _GROWTH_TAB:
        zz = np.linspace(0.0, 10.0, 201)

        def unnorm(zi):
            a = 1.0 / (1.0 + zi)
            val, _ = integrate.quad(lambda x: 1.0 / (x * efunc(1 / x - 1, Om0)) ** 3, 0.0, a)
            return 2.5 * Om0 * efunc(zi, Om0) * val

        d = np.array([unnorm(zi) for zi in zz])
        _GROWTH_TAB[key] = interpolate.CubicSpline(zz, d / d[0])
    return _GROWTH_TAB[key](z)


_GROWTH_TAB: dict = {}


# ------------------------------------------------------------------ power spectrum
def eh_nowiggle_transfer(k, Om0, Ob0, h, Tcmb=2.7255):
    """Eisenstein & Hu (1998) zero-baryon transfer function; k in h/Mpc."""
    k = np.asarray(k, float)
    omh2 = Om0 * h * h
    obh2 = Ob0 * h * h
    fb = Ob0 / Om0
    theta = Tcmb / 2.7
    s = 44.5 * np.log(9.83 / omh2) / np.sqrt(1 + 10 * obh2 ** 0.75)  # Mpc
    alpha = 1 - 0.328 * np.log(431 * omh2) * fb + 0.38 * np.log(22.3 * omh2) * fb ** 2
    kh = k * h  # 1/Mpc
    gamma_eff = Om0 * h * (alpha + (1 - alpha) / (1 + (0.43 * kh * s) ** 4))
    q = k * theta ** 2 / gamma_eff
    L0 = np.log(2 * np.e + 1.8 * q)
    C0 = 14.2 + 731.0 / (1 + 62.5 * q)
    return L0 / (L0 + C0 * q * q)


class LinearPower:
    """sigma(R) machinery for one cosmology (z = 0, normalised to sigma8)."""

    def __init__(self, Om0, Ob0, h, ns, sigma8):
        self.Om0, self.Ob0, self.h, self.ns, self.sigma8 = Om0, Ob0, h, ns, sigma8
        self.lnk = np.linspace(np.log(1e-5), np.log(1e3), 3000)
        k = np.exp(self.lnk)
        self.pk_unnorm = k ** ns * eh_nowiggle_transfer(k, Om0, Ob0, h) ** 2
        self.norm = 1.0
        self.norm = sigma8 ** 2 / self._sigma2(np.array([8.0]))[0]
        self.rho_m = RHO_CRIT0 * Om0  # h^2 Msun / Mpc^3 (comoving)

    @staticmethod
    def _w(x):
        x = np.asarray(x, float)
        out = np.empty_like(x)
        small = x < 1e-3
        out[small] = 1 - x[small] ** 2 / 10
        xs = x[~small]
        out[~small] = 3 * (np.sin(xs) - xs * np.cos(xs)) / xs ** 3
        return out

    def _sigma2(self, R):
        k = np.exp(self.lnk)
        res = []
        for r in np.atleast_1d(R):
            integrand = self.norm * self.pk_unnorm * k ** 3 * self._w(k * r) ** 2 / (2 * np.pi ** 2)
            res.append(integrate.simpson(integrand, x=self.lnk))
        return np.array(res)

    def _spline(self):
        if not hasattr(self, "_lnsig_spl"):
            lnm = np.linspace(np.log(1e9), np.log(1e17), 400)
            R = (3 * np.exp(lnm) / (4 * np.pi * self.rho_m)) ** (1 / 3)
            k = np.exp(self.lnk)
            integrand = self.norm * self.pk_unnorm * k ** 3 * self._w(np.outer(R, k)) ** 2 / (2 * np.pi ** 2)
            lnsig = 0.5 * np.log(integrate.simpson(integrand, x=self.lnk, axis=1))
            self._lnsig_spl = interpolate.CubicSpline(lnm, lnsig)
        return self._lnsig_spl

    def sigma_of_m(self, M):
        """sigma(M, z=0); M in Msun/h (cubic spline in ln M over 1e9-1e17)."""
        return np.exp(self._spline()(np.log(np.asarray(M, float))))

    def dlnsigma_dlnm(self, M):
        return self._spline()(np.log(np.asarray(M, float)), 1)


# ------------------------------------------------------------------ mass definitions
def _nfw_mu(x):
    return np.log1p(x) - x / (1 + x)


def convert_mass(M, delta_in, delta_out, z, Om0, conc=None):
    """Convert spherical-overdensity masses between definitions with an NFW profile.

    delta_* are strings like '500c', '200c', '200m'. ``conc`` is the
    concentration for the INPUT definition (default: Duffy et al. 2008 full
    sample for 200c, applied approximately to the input definition).
    """
    if delta_in == delta_out:
        return np.asarray(M, float)
    from scipy.optimize import brentq

    def rho_ref(d):
        val, ref = float(d[:-1]), d[-1]
        return val * (omega_m_z(z, Om0) if ref == "m" else 1.0)  # in units of rho_crit(z)

    din, dout = rho_ref(delta_in), rho_ref(delta_out)
    M = np.atleast_1d(np.asarray(M, float))
    if conc is None:  # Duffy+08 (200c, full sample), M in Msun/h
        conc = 5.71 * (M / 2e12) ** -0.084 * (1 + z) ** -0.47
    conc = np.broadcast_to(conc, M.shape)
    out = np.empty_like(M)
    for i, (m, c) in enumerate(zip(M, conc, strict=True)):
        # mean density inside x*r_s (units rho_crit) ~ din * mu(x)/mu(c) * (c/x)^3
        f = lambda x, c=c: din * _nfw_mu(x) / _nfw_mu(c) * (c / x) ** 3 - dout  # noqa: E731
        x = brentq(f, 1e-3, 100.0)
        out[i] = m * _nfw_mu(x) / _nfw_mu(c)
    return out


# ------------------------------------------------------------------ Tinker08
def tinker08_params(delta_mean, z):
    ld = np.log10(_T08_DELTA)
    x = np.log10(np.clip(delta_mean, 200, 3200))
    A0, a0, b0, c0 = (interpolate.CubicSpline(ld, arr)(x) for arr in (_T08_A, _T08_a, _T08_b, _T08_c))
    alpha = 10 ** (-((0.75 / np.log10(delta_mean / 75.0)) ** 1.2))
    return (A0 * (1 + z) ** -0.14, a0 * (1 + z) ** -0.06, b0 * (1 + z) ** -alpha, c0)


def dndlnm_tinker08(M, z, lp: LinearPower, mass_def="500c"):
    """Comoving dn/dlnM [(h/Mpc)^3] at masses M [Msun/h] in definition ``mass_def``."""
    M = np.asarray(M, float)
    val, ref = float(mass_def[:-1]), mass_def[-1]
    delta_mean = val if ref == "m" else val / float(omega_m_z(z, lp.Om0))
    A, a, b, c = tinker08_params(delta_mean, z)
    D = growth_factor(z, lp.Om0)[0]
    sig = lp.sigma_of_m(M) * D
    dlnsinv_dlnm = -lp.dlnsigma_dlnm(M)
    f = A * ((sig / b) ** (-a) + 1) * np.exp(-c / sig ** 2)
    return f * lp.rho_m / M * dlnsinv_dlnm


# ------------------------------------------------------------------ public kernel
def predict_counts(z_edges: list, m_min_1e14: float | list, area_deg2: float,
                   cosmology: dict | None = None, mass_def: str = "500c",
                   observed_counts: list | None = None, sigma8_grid: list | None = None,
                   n_z_sub: int = 8, n_mass: int = 60) -> dict:
    """Predicted cluster counts per redshift bin above a mass threshold (Tinker08 x EH98).

    Args (JSON):
      z_edges: redshift bin edges (len N+1).
      m_min_1e14: mass threshold in 1e14 Msun (h70-style physical units, i.e. NOT /h);
        scalar or one value per bin.
      area_deg2: survey area in deg^2.
      cosmology: {Om0, Ob0, h, ns, sigma8}; missing keys take FIDUCIAL values.
      mass_def: '500c' | '200c' | '200m'.
      observed_counts: optional observed N per bin -> Poisson -2lnL and per-bin pulls.
      sigma8_grid: optional list of sigma8 values -> Poisson -2lnL profile (Om0 fixed),
        best-fit sigma8 (requires observed_counts).
    Returns JSON dict with z_mid, N_pred, dNdz_pred, and the comparison blocks.
    """
    cosmo = {**FIDUCIAL, **(cosmology or {})}
    z_edges = np.asarray(z_edges, float)
    nb = len(z_edges) - 1
    if nb < 1 or np.any(np.diff(z_edges) <= 0) or z_edges[0] < 0:
        raise ValueError("z_edges must be increasing, non-negative, with >= 2 entries")
    mmin = np.broadcast_to(np.asarray(m_min_1e14, float), (nb,)).copy()
    h = cosmo["h"]
    omega_sr = area_deg2 * (np.pi / 180.0) ** 2

    def counts_for(sigma8):
        lp = LinearPower(cosmo["Om0"], cosmo["Ob0"], h, cosmo["ns"], sigma8)
        n_bins = np.zeros(nb)
        for i in range(nb):
            zs = np.linspace(z_edges[i], z_edges[i + 1], n_z_sub)
            zs[0] = max(zs[0], 1e-3)
            mlo = mmin[i] * 1e14 * h  # Msun/h
            lnm = np.linspace(np.log(mlo), np.log(1e16 * h), n_mass)
            nz = np.array([integrate.simpson(dndlnm_tinker08(np.exp(lnm), zi, lp, mass_def), x=lnm) for zi in zs])
            dndz = omega_sr * dvdz_dsr(zs, cosmo["Om0"]) * nz
            n_bins[i] = integrate.simpson(dndz, x=zs)
        return n_bins

    n_pred = counts_for(cosmo["sigma8"])
    dz = np.diff(z_edges)
    out = {
        "z_lo": z_edges[:-1].tolist(), "z_hi": z_edges[1:].tolist(),
        "z_mid": (0.5 * (z_edges[1:] + z_edges[:-1])).tolist(),
        "m_min_1e14": mmin.tolist(), "N_pred": n_pred.tolist(), "dNdz_pred": (n_pred / dz).tolist(),
        "N_pred_total": float(n_pred.sum()), "area_deg2": float(area_deg2), "mass_def": mass_def,
        "cosmology": cosmo,
        "model": "Tinker08 HMF x Eisenstein-Hu 1998 no-wiggle P(k), flat LCDM, no selection/scatter",
    }
    if observed_counts is not None:
        obs = np.asarray(observed_counts, float)
        if obs.shape != (nb,):
            raise ValueError("observed_counts must have one entry per z bin")

        def m2lnl(pred):
            pred = np.maximum(pred, 1e-12)
            return float(2 * np.sum(pred - obs + np.where(obs > 0, obs * np.log(np.where(obs > 0, obs, 1) / pred), 0)))

        out["N_obs"] = obs.tolist()
        out["N_obs_total"] = float(obs.sum())
        out["ratio_obs_pred_total"] = float(obs.sum() / max(n_pred.sum(), 1e-12))
        out["pull"] = ((obs - n_pred) / np.sqrt(np.maximum(n_pred, 1e-12))).tolist()
        out["poisson_m2lnL"] = m2lnl(n_pred)
        if sigma8_grid:
            grid = np.asarray(sigma8_grid, float)
            prof = np.array([m2lnl(counts_for(s8)) for s8 in grid])
            out["sigma8_grid"] = grid.tolist()
            out["sigma8_m2lnL"] = prof.tolist()
            j = int(np.argmin(prof))
            best = float(grid[j])
            if 0 < j < len(grid) - 1:  # parabolic refinement
                y0, y1, y2 = prof[j - 1:j + 2]
                x0, x1, x2 = grid[j - 1:j + 2]
                den = (x0 - x1) * (x0 - x2) * (x1 - x2)
                A_ = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / den
                B_ = (x2 ** 2 * (y0 - y1) + x1 ** 2 * (y2 - y0) + x0 ** 2 * (y1 - y2)) / den
                if A_ > 0:
                    best = float(-B_ / (2 * A_))
                    out["sigma8_err_1sig"] = float(1 / np.sqrt(A_))
            out["sigma8_best"] = best
    return out
