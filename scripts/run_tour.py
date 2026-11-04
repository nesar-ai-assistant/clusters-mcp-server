"""Run the clusters-tour skill end to end in plain Python (no MCP client).

    MPLBACKEND=Agg .venv/bin/python scripts/run_tour.py [output_dir]
"""

import json
import sys
import time
import warnings

warnings.filterwarnings("ignore")

from tools.catalogs import (  # noqa: E402
    compare_mass_calibration,
    compute_cluster_counts,
    crossmatch_catalogs,
    describe_catalog_columns,
    fetch_cluster_catalog,
    plot_cluster_sky_map,
    plot_mass_redshift,
)
from tools.lcdm import plot_counts_vs_prediction, predict_cluster_counts_lcdm  # noqa: E402
from tools.meta import list_clusters_datasets  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "output/tour"
t0 = time.time()
summary = {"datasets": list(list_clusters_datasets().metadata["datasets"])}
summary["psz2_conventions"] = describe_catalog_columns("psz2", show_native=False).metadata["conventions"][:80]
csv = {}
for key in ["psz2", "spt_sz", "act_dr6", "erass1", "spt3g_5yr"]:
    r = fetch_cluster_catalog(out, key, require_redshift=True, require_mass=True)
    csv[key] = r.files[0]
    summary[f"fetch_{key}"] = [r.metadata["n_catalog"], r.metadata["n_selected"], r.metadata["m500_median_1e14"]]
summary["mz"] = plot_mass_redshift(out, list(csv.values())).metadata["per_survey"]
summary["sky"] = plot_cluster_sky_map(out, list(csv.values())).metadata["counts"]
summary["counts"] = compute_cluster_counts(out, [csv["spt_sz"], csv["act_dr6"]], m500_min=4).metadata["summary"]
x = crossmatch_catalogs(out, csv["act_dr6"], csv["psz2"], radius_arcmin=3.0)
c = compare_mass_calibration(out, x.files[0])
summary["act_psz2"] = {"n": x.metadata["n_matched"], **c.metadata["overall"]}
x = crossmatch_catalogs(out, csv["spt_sz"], csv["erass1"], radius_arcmin=2.0)
c = compare_mass_calibration(out, x.files[0])
summary["spt_erass1"] = {"n": x.metadata["n_matched"], **c.metadata["overall"]}
p = predict_cluster_counts_lcdm(out, m500_min=5.0, z_edges=[0.25, 0.4, 0.55, 0.7, 0.85, 1.0, 1.2, 1.5],
                                observed_catalog="spt_sz", sigma8_scan=[0.7, 0.75, 0.8, 0.85])
summary["lcdm_spt"] = {k: p.metadata.get(k) for k in ("N_pred_total", "N_obs_total", "ratio_obs_pred_total", "sigma8_best")}
p2 = predict_cluster_counts_lcdm(out, m500_min=3.0, z_edges=[0.25, 0.4, 0.55, 0.7, 0.85, 1.0, 1.2, 1.5],
                                 observed_catalog="spt3g_5yr", sigma8_scan=[0.7, 0.75, 0.8, 0.85])
summary["lcdm_spt3g"] = {k: p2.metadata.get(k) for k in ("N_pred_total", "N_obs_total", "ratio_obs_pred_total", "sigma8_best")}
plot_counts_vs_prediction(out, [p.files[1], p2.files[1]])
summary["seconds"] = round(time.time() - t0, 1)
print(json.dumps(summary, indent=1, default=str))
