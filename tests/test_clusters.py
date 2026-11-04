"""Science tests for the cluster catalogue + LCDM families.

Offline tests use the bundled Planck/SPT FITS (data/); network tests download
ACT DR6, SPT-3G and eRASS1 (cached after the first run).
"""

import json

import numpy as np
import pandas as pd
import pytest

from tools.catalogs import (
    compare_mass_calibration,
    compute_cluster_counts,
    crossmatch_catalogs,
    describe_catalog_columns,
    fetch_cluster_catalog,
    plot_cluster_sky_map,
    plot_mass_redshift,
)
from tools.catalogs.io import HARMONISED, load_catalog
from tools.lcdm import plot_counts_vs_prediction, predict_cluster_counts_lcdm
from tools.lcdm import kernels as K
from tools.registry import DATASETS


# ---------------------------------------------------------------- bundled catalogues (offline)
def test_psz2_has_1653_entries():
    df = load_catalog("psz2")
    assert len(df) == 1653 == DATASETS["psz2"]["n_rows"]
    assert list(df.columns) == HARMONISED
    assert df["z"].notna().sum() == 1093 and df["M500"].notna().sum() == 1093
    assert 4.0 < df["M500"].median() < 5.5


def test_spt_sz_has_677_candidates():
    df = load_catalog("spt_sz")
    assert len(df) == 677
    assert df["M500"].notna().sum() == 516
    assert (df["snr"] >= 4.5).all() and (df["snr"] > 5).sum() == 409


def test_fetch_cuts_and_csv(tmp_path):
    r = fetch_cluster_catalog(str(tmp_path), "spt_sz", z_min=0.25, m500_min=5.0)
    df = pd.read_csv(r.files[0])
    assert r.metadata["n_selected"] == len(df) > 50
    assert (df["z"] >= 0.25).all() and (df["M500"] >= 5).all()
    assert list(df.columns) == HARMONISED


def test_describe_columns():
    r = describe_catalog_columns("psz2")
    cols = {c["column"] for c in r.metadata["native_columns"]}
    assert {"MSZ", "REDSHIFT", "SNR"} <= cols
    with pytest.raises(ValueError):
        describe_catalog_columns("nope")


def test_plots_and_counts(tmp_path):
    a = fetch_cluster_catalog(str(tmp_path), "psz2", require_mass=True).files[0]
    b = fetch_cluster_catalog(str(tmp_path), "spt_sz", require_mass=True).files[0]
    r = plot_mass_redshift(str(tmp_path), [a, b])
    assert r.files[0].endswith(".png") and r.metadata["per_survey"]["SPT-SZ"]["n_plotted"] == 516
    r = plot_cluster_sky_map(str(tmp_path), [a, b], coords="galactic")
    assert r.metadata["counts"]["Planck PSZ2"] == 1093
    r = compute_cluster_counts(str(tmp_path), [a, b], m500_min=4.0)
    nz = pd.read_csv(r.files[0])
    assert set(nz["survey"]) == {"Planck PSZ2", "SPT-SZ"}


def test_crossmatch_planck_spt_mass_bias(tmp_path):
    """Planck hydrostatic MSZ is ~20% below the WL-calibrated SPT masses (1-b ~ 0.8)."""
    a = fetch_cluster_catalog(str(tmp_path), "spt_sz", require_mass=True).files[0]
    b = fetch_cluster_catalog(str(tmp_path), "psz2", require_mass=True).files[0]
    x = crossmatch_catalogs(str(tmp_path), a, b, radius_arcmin=3.0, max_dz=0.1)
    assert x.metadata["n_matched"] > 80
    m = pd.read_csv(x.files[0])
    assert (m["sep_arcmin"] <= 3.0).all() and not m["name_a"].duplicated().any()
    c = compare_mass_calibration(str(tmp_path), x.files[0])
    assert 0.6 < c.metadata["overall"]["median_ratio"] < 0.95


# ---------------------------------------------------------------- LCDM kernel
def test_kernel_background_and_growth():
    # D(z=1) for Om=0.3 flat LCDM = 0.6118 (colossus); comoving distance to z=1 ~ 2314 Mpc/h
    assert K.growth_factor(1.0, 0.3)[0] == pytest.approx(0.6118, abs=2e-3)
    assert K.comoving_distance(1.0, 0.3)[0] == pytest.approx(2314, rel=5e-3)
    lp = K.LinearPower(0.3, 0.049, 0.7, 0.965, 0.8)
    R8 = 8.0
    m8 = 4 / 3 * np.pi * R8 ** 3 * lp.rho_m
    assert lp.sigma_of_m(m8) == pytest.approx(0.8, rel=2e-3)


def test_tinker_vs_colossus():
    colossus = pytest.importorskip("colossus")  # noqa: F841
    from colossus.cosmology import cosmology
    from colossus.lss import mass_function
    c = cosmology.setCosmology("t08test", {"flat": True, "H0": 70, "Om0": 0.3, "Ob0": 0.049, "sigma8": 0.8,
                                           "ns": 0.965, "relspecies": False, "power_law": False})
    c.power_spectrum_model = "eisenstein98_zb"
    lp = K.LinearPower(0.3, 0.049, 0.7, 0.965, 0.8)
    M = np.logspace(13.5, 15.0, 4)
    for z in (0.1, 0.6):
        ours = K.dndlnm_tinker08(M, z, lp, "500c")
        ref = mass_function.massFunction(M, z, mdef="500c", model="tinker08", q_out="dndlnM")
        assert np.allclose(ours / ref, 1, atol=0.04)


def test_kernel_importable_from_pack_root(tmp_path):
    """Dispatch nodes import 'lcdm.kernels' with tools/ as the root (no tools.common, no astropy)."""
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "tools"
    code = ("import sys; import lcdm.kernels as k; "
            "r = k.predict_counts([0.3, 0.6], 5.0, 100.0); "
            "assert r['N_pred_total'] > 0; assert 'astropy' not in sys.modules and 'pandas' not in sys.modules")
    subprocess.run([sys.executable, "-c", code], cwd=root, check=True)


def test_predict_counts_scaling():
    base = K.predict_counts([0.2, 0.5, 0.8], 5.0, 1000.0)
    double = K.predict_counts([0.2, 0.5, 0.8], 5.0, 2000.0)
    hi = K.predict_counts([0.2, 0.5, 0.8], 5.0, 1000.0, cosmology={"sigma8": 0.9})
    assert double["N_pred_total"] == pytest.approx(2 * base["N_pred_total"], rel=1e-9)
    assert hi["N_pred_total"] > 1.5 * base["N_pred_total"]
    json.dumps(base)


def test_predict_vs_spt_sigma8(tmp_path):
    """SPT-SZ M500>5e14, z>0.25: obs/pred ~0.75 at s8=0.8, profile prefers s8 ~0.78 (Bocquet+19: 0.77)."""
    r = predict_cluster_counts_lcdm(str(tmp_path), m500_min=5.0, z_edges=[0.25, 0.4, 0.55, 0.7, 0.85, 1.0, 1.2, 1.5],
                                    observed_catalog="spt_sz", sigma8_scan=[0.7, 0.75, 0.8, 0.85])
    assert r.metadata["area_deg2"] == 2500.0 and r.metadata["ran_on"] == "local"
    assert 110 < r.metadata["N_pred_total"] < 170
    assert r.metadata["N_obs_total"] == 105
    assert 0.74 < r.metadata["sigma8_best"] < 0.82
    p = plot_counts_vs_prediction(str(tmp_path), [r.files[1]])
    assert p.files[0].endswith(".png")


# ---------------------------------------------------------------- downloaded catalogues
@pytest.mark.network
def test_erass1_has_12247_clusters():
    df = load_catalog("erass1")
    assert len(df) == 12247
    assert df["M500"].notna().sum() > 10000
    assert 1.5 < df["M500"].median() < 2.5  # native 1e13 -> 1e14 conversion
    cosmo = load_catalog("erass1_cosmo")
    assert len(cosmo) == 5259 and cosmo["M500"].notna().sum() > 4900


@pytest.mark.network
def test_act_dr6_and_spt3g():
    act = load_catalog("act_dr6")
    assert len(act) == 10040 and (act["snr"] > 5).sum() == 6521
    g = load_catalog("spt3g_5yr")
    assert len(g) == 8892 and g["M500"].notna().sum() >= 7190


@pytest.mark.network
def test_sz_vs_erosita_crossmatch(tmp_path):
    a = fetch_cluster_catalog(str(tmp_path), "erass1", require_mass=True, require_redshift=True).files[0]
    b = fetch_cluster_catalog(str(tmp_path), "act_dr6").files[0]
    x = crossmatch_catalogs(str(tmp_path), a, b, radius_arcmin=2.0)
    assert x.metadata["n_matched"] > 1000
    assert 0.8 < x.metadata["mass_ratio"]["median_ratio"] < 1.25
