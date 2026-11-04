"""Selection-function / completeness tools for Planck PSZ2, ACT DR6, and SPT-SZ.

These are summary-statistic products: completeness as a function of the
survey observable (Y500, theta500, SNR) or (Q, RMS noise), derived from the
published survey characterisation data.
"""

from .selfn import (
    fetch_cluster_selection_function,
    fetch_cluster_wl_profiles,
    plot_completeness,
)

__all__ = [
    "fetch_cluster_selection_function",
    "fetch_cluster_wl_profiles",
    "plot_completeness",
]

DISPATCH_KERNELS: dict = {}
