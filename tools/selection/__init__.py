"""Selection-function / completeness tools for Planck PSZ2, ACT DR6, and SPT-SZ.

These are summary-statistic products: completeness as a function of the
survey observable (Y500, theta500, SNR) or (Q, RMS noise), derived from the
published survey characterisation data. Also the SPT-SZ Megacam weak-lensing
shear profiles (Dietrich+19) and an NFW mass fit to them (fit_cluster_wl_mass).
"""

from .selfn import (
    fetch_cluster_selection_function,
    fetch_cluster_wl_profiles,
    fit_cluster_wl_mass,
    plot_completeness,
)

__all__ = [
    "fetch_cluster_selection_function",
    "fetch_cluster_wl_profiles",
    "fit_cluster_wl_mass",
    "plot_completeness",
]

DISPATCH_KERNELS: dict = {}
