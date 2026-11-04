"""Cluster catalogue family: fetch / describe / count / plot / crossmatch / mass calibration.

Catalogues: Planck PSZ2, SPT-SZ 2500d (Bocquet+19), SPTpol 100d, SPT-ECS, SPT-3G
Main 5yr, ACT DR6, eROSITA eRASS1 (primary + cosmology). All FITS, downloaded on
first use, harmonised to name, ra, dec, z, M500 [1e14 Msun], snr, survey.
"""

from .fetch import compute_cluster_counts, describe_catalog_columns, fetch_cluster_catalog
from .plots import plot_cluster_sky_map, plot_mass_redshift
from .xmatch import compare_mass_calibration, crossmatch_catalogs

__all__ = [
    "fetch_cluster_catalog",
    "describe_catalog_columns",
    "plot_mass_redshift",
    "plot_cluster_sky_map",
    "compute_cluster_counts",
    "crossmatch_catalogs",
    "compare_mass_calibration",
]

DISPATCH_KERNELS: dict = {}
