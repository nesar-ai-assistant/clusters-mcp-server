"""Tests for DES Y6 WaZP, the completeness-plot labels and the SPT Megacam WL tools.

Offline tests use small synthetic stand-ins (monkeypatched readers) or pure registry
data; network tests download the real files (WaZP 80 MB, footprint 540 MB, SPT
likelihood tarball 2.7 MB) and are cached after the first run.
"""

import json

import numpy as np
import pandas as pd
import pytest

from tools.catalogs import compute_cluster_counts, compute_wazp_footprint_area, fetch_cluster_catalog
from tools.catalogs.io import HARMONISED, load_catalog
from tools.registry import DATASETS


# ---------------------------------------------------------------- WaZP (offline: registry + area table)
def test_wazp_registry_entry():
    d = DATASETS["des_y6_wazp"]
    assert d["mass_proxy"] == "richness" and "M500" not in d["columns"]
    assert {"richness", "z_spec", "in_cosmo"} <= set(d["extra_columns"])
    assert set(d["products"]) == {"catalog", "summary_statistic"}
    assert 4000 < d["area_deg2"] < 5000
    fp = d["footprint"]
    assert fp["nside"] == 4096 and fp["ordering"] == "NESTED"
    areas = [fp["area_zmax_gt_deg2"][z] for z in sorted(fp["area_zmax_gt_deg2"])]
    assert areas == sorted(areas, reverse=True)  # area with ZMAX > z can only shrink with z
    assert "2507.05360" in d["citation"] and "Aguena" in d["citation"]


def test_wazp_footprint_area_table(tmp_path):
    r = compute_wazp_footprint_area(str(tmp_path), z_values=[0.3, 0.6, 0.8, 1.0])
    df = pd.read_csv(r.files[0])
    assert np.isclose(df["area_zmax_gt_z_deg2"].iloc[0], 4544.7)
    assert 3000 < df["area_zmax_gt_z_deg2"].iloc[2] < 3300  # z=0.8: ~3176 deg^2
    assert df["area_zmax_gt_z_deg2"].iloc[3] == 0.0
    with pytest.raises(ValueError):
        compute_wazp_footprint_area(str(tmp_path), dataset="psz2")


def test_footprint_reduction_synthetic(tmp_path):
    """reduce_footprint derives nside/ordering from the header and weights by DETFRAC."""
    from astropy.io import fits

    from tools.catalogs.footprint import area_above_z, reduce_footprint
    n = 1000
    cols = [fits.Column("PIXEL", "K", array=np.arange(n)), fits.Column("DETFRAC", "D", array=np.full(n, 0.5)),
            fits.Column("ZMAX", "D", array=np.linspace(0.5, 1.0, n))]
    h = fits.BinTableHDU.from_columns(cols)
    h.header["NSIDE"], h.header["ORDERING"] = 4096, "NESTED"
    path = tmp_path / "fp.fits"
    h.writeto(path)
    red = reduce_footprint(path)
    pa = 4 * np.pi * (180 / np.pi) ** 2 / (12 * 4096**2)
    assert red["nside"] == 4096 and red["ordering"] == "NESTED"
    assert np.isclose(red["effective_area_deg2"], 0.5 * n * pa)
    assert np.isclose(area_above_z(red, 0.75)[0], 0.25 * n * pa, rtol=0.02)


def test_wazp_rejects_mass_cuts(tmp_path):
    with pytest.raises(ValueError, match="richness"):
        fetch_cluster_catalog(str(tmp_path), "des_y6_wazp", m500_min=3.0)


# ---------------------------------------------------------------- WaZP (network)
@pytest.mark.network
def test_wazp_catalogue_columns_and_counts(tmp_path):
    df = load_catalog("des_y6_wazp")
    assert len(df) == 416947  # Benoist+25: 416,947 clusters with NGALS >= 5
    assert list(df.columns[:len(HARMONISED)]) == HARMONISED
    assert {"richness", "richness_err", "z_spec", "in_cosmo", "cover_frac"} <= set(df.columns)
    assert df["M500"].isna().all() and (df["richness"] >= 5).all()
    assert df["ra"].between(0, 360).all() and df["dec"].between(-70, 10).all()
    assert 0 < df["z"].min() and df["z"].max() < 1.4
    assert df["in_cosmo"].sum() == 301406
    r = fetch_cluster_catalog(str(tmp_path), "des_y6_wazp", richness_min=25, in_cosmo_only=True)
    assert r.metadata["n_selected"] == 33304  # Benoist+25: "33k clusters" (cosmology sample, NGALS >= 25)
    c = compute_cluster_counts(str(tmp_path), [r.files[0]], z_edges=[0.1, 0.3, 0.5, 0.7], richness_min=25)
    nz = pd.read_csv(c.files[0])
    assert nz["N"].sum() > 25000
    dens = nz["N_per_deg2"].to_numpy()
    assert np.all((dens > 0.3) & (dens < 5))  # a few rich clusters per deg^2 per dz=0.2
    nr = pd.read_csv([f for f in c.files if f.endswith("counts_nrich.csv")][0])
    assert nr["N_gt_richness"].is_monotonic_decreasing


@pytest.mark.network
def test_wazp_footprint_file_area():
    from tools.catalogs.footprint import area_above_z, footprint_summary
    s = footprint_summary("des_y6_wazp")
    assert s["nside"] == 4096 and s["ordering"] == "NESTED"
    assert 4000 < s["effective_area_deg2"] < 5000
    assert abs(s["effective_area_deg2"] - 4545) < 5  # Benoist+25 quote 4,545 deg^2
    assert abs(area_above_z(s, 0.8)[0] - DATASETS["des_y6_wazp"]["footprint"]["area_zmax_gt_deg2"][0.8]) < 2


# ---------------------------------------------------------------- completeness plot labels
def test_psz2_completeness_axis_labels(tmp_path, monkeypatch):
    """Y500 grid is in arcmin^2 (1e-4..0.07): the axis must say so, without a 1e-4 scaling."""
    from tools.selection import selfn
    fake = {"snr_thresholds": np.array([4.5, 6.0, 7.0]), "theta500_grid": np.logspace(0, 1.5, 6),
            "y500_grid": np.logspace(np.log10(1.1e-4), np.log10(0.072), 8),
            "completeness": np.random.default_rng(0).uniform(0, 1, (3, 6, 8))}
    monkeypatch.setattr(selfn, "_planck_completeness", lambda variant="MMF3_cosmology": fake)
    r = selfn.plot_completeness(str(tmp_path), "psz2")
    labels = r.metadata["axis_labels"]
    assert labels["xlabel"] == r"$Y_{500}$ [arcmin$^2$]"
    assert "10^{-4}" not in labels["xlabel"] and "1e-4" not in labels["xlabel"]
    assert labels["ylabel"] == r"$\theta_{500}$ [arcmin]"
    assert np.isclose(r.metadata["y500_range_arcmin2"][0], 1.1e-4)


# ---------------------------------------------------------------- SPT Megacam WL
def test_wl_model_limits():
    """NFW reduced-shear model: positive, falling with radius, rising with mass; M500 < M200."""
    from tools.selection import wl
    cosmo = wl.FlatLCDM()
    g, c = wl.reduced_shear_model(np.array([0.8, 1.5, 2.4]), np.array([3e14, 1e15]), 0.4, 0.5, 0.27,
                                  "duffy08", cosmo)
    assert (g > 0).all() and (np.diff(g[:, 0]) < 0).all() and (g[:, 1] > g[:, 0]).all()
    m500 = wl.m_delta_from_200c(np.array([1e15]), c[1:])
    assert 0.6 < m500[0] / 1e15 < 0.75
    nz = np.column_stack([np.arange(0.0125, 5, 0.025), np.ones(200)])
    b, b2 = wl.beta_moments(nz, 0.4, cosmo)
    assert 0 < b2 < b < 1


@pytest.mark.network
def test_wl_profiles_summary_is_explicit(tmp_path):
    from tools.selection import fetch_cluster_wl_profiles
    r = fetch_cluster_wl_profiles(str(tmp_path))
    assert r.metadata["n_clusters"] == 19
    assert "real" in r.metadata["data_origin"] and "not simulated" in r.metadata["data_origin"]
    assert {"r_deg", "gt", "gt_err", "kbin", "n_src", "r_mpc"} <= set(r.metadata["columns"])
    assert "lensing.py" in r.metadata["kbin_note"]
    readme = json.loads(open([f for f in r.files if f.endswith("README.json")][0]).read())
    assert readme["source_url"].endswith("SPT_SZ_cluster_likelihood-0.0.tar.gz")
    for p in readme["profiles"]:
        assert p["n_bins"] == 8 and 0.7 < p["r_min_mpc"] < 1.0 and 2.2 < p["r_max_mpc"] < 2.6
        assert 0.25 < p["z_cluster"] < 0.7
        assert (tmp_path / p["nz_csv"]).is_file()
    prof = pd.read_csv(tmp_path / readme["profiles"][0]["profile_csv"])
    assert list(prof.columns) == ["r_deg", "gt", "gt_err", "kbin", "n_src", "r_mpc"]


@pytest.mark.network
def test_wl_beta_matches_dietrich19():
    from tools.selection import wl
    data = wl.read_megacam()
    z = wl.spt_redshifts(list(data))
    cosmo = wl.FlatLCDM()
    for n, (b_ref, b2_ref, _) in wl.D19_SOURCE_TABLE.items():
        b, b2 = wl.beta_moments(data[n]["nz"], z[n], cosmo)
        assert abs(b - b_ref) <= 0.015 and abs(b2 - b2_ref) <= 0.015, n  # table rounded to 0.01


@pytest.mark.network
def test_wl_masses_reproduce_dietrich19(tmp_path):
    from tools.selection import fit_cluster_wl_mass
    r = fit_cluster_wl_mass(str(tmp_path), concentration_model="diemer15")
    v = r.metadata["validation_vs_D19"]
    assert v["n_compared"] == 5 and v["n_within_1sigma"] == 5
    assert all(0.9 < x < 1.1 for x in v["ratio_ml_over_D19"].values())
    df = pd.read_csv(r.files[0])
    assert len(df) == 19 and (df["M500c_ml"] < df["M200c_ml"]).all()
    assert ((df["M500c_lo"] <= df["M500c_median"]) & (df["M500c_median"] <= df["M500c_hi"])).all()
    r2 = fit_cluster_wl_mass(str(tmp_path), clusters=["SPT-CLJ2032-5627"], concentration_model="duffy08")
    assert 0.85 < r2.metadata["validation_vs_D19"]["median_ratio"] < 1.15
