"""LCDM cluster-count prediction family (Tinker+08 HMF x Eisenstein-Hu P(k), pure numpy/scipy).

predict_cluster_counts_lcdm is heavy and dispatchable: the kernel
lcdm.kernels.predict_counts imports only numpy + scipy.
"""

try:
    from .tools import plot_counts_vs_prediction, predict_cluster_counts_lcdm
except ImportError:  # imported as top-level ``lcdm`` on a dispatch node: only lcdm.kernels is needed there
    pass

__all__ = ["predict_cluster_counts_lcdm", "plot_counts_vs_prediction"]

DISPATCH_KERNELS = {
    "predict_counts": {
        "function": "lcdm.kernels.predict_counts",
        "args_shape": ("z_edges (list), m_min_1e14 (float|list), area_deg2 (float), cosmology {Om0,Ob0,h,ns,sigma8}, "
                       "mass_def '500c'|'200c'|'200m', observed_counts (list|None), sigma8_grid (list|None)"),
        "pip_deps": ["numpy", "scipy"],
        "duration_hint_s": 900,
        "returns": "z_lo/z_hi/z_mid, N_pred, dNdz_pred, N_pred_total; with observed_counts: N_obs, pull, "
                   "poisson_m2lnL; with sigma8_grid: sigma8_m2lnL, sigma8_best, sigma8_err_1sig",
    },
}
