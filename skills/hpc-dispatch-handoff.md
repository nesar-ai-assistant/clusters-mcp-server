---
name: hpc-dispatch-handoff
description: Run this server's heavy kernels (likelihood scans, fits, large downloads + reductions) on ALCF Polaris or NERSC Perlmutter through the hep-genesis IRI engine - client-side pack export (hosted) or server-side set_dispatch (own machine)
---

# HPC dispatch handoff

This server holds NO facility credentials, project, workdir or environment
settings. All facility access goes through IRI (job submission) and Globus /
the IRI filesystem API (staging) via the hep-genesis engine; nothing here
writes batch scripts or opens SSH sessions. Tool names `set_dispatch`,
`get_dispatch`, `auth_status`, `export_dispatch_pack` are a cross-server
convention matched by the hep-genesis harness.

## Client-side (hosted servers - recommended)
1. `export_dispatch_pack` -> the client saves `files` locally (do NOT echo
   their contents) and reads `kernels`: each has `function`, `args_shape`,
   `pip_deps`, `duration_hint_s`, `returns`.
2. On the client's facility server call
   `run_pack_kernel(pack=<saved>/tools, function=<kernel function>,
   args={...}, pip_deps=<kernel pip_deps>, duration>=duration_hint_s,
   artifact_dir=<run dir>)`.
3. Long or parallel jobs: `wait=False`, then `find_dispatched_jobs` /
   `collect_dispatched_job(record=...)`.

## Server-side (server runs on the user's own machine)
1. `auth_status` -> IRI + transfer tokens must be "available".
2. `set_dispatch("perlmutter" | "polaris")`. Heavy tools now run each call
   as one facility job; light tools stay local. `set_dispatch("local")` to undo.
3. Never blind-retry a failed dispatch: surface the error. A walltime
   rejection may be resubmitted ONCE with a shorter duration.

## This server's kernels
| kernel key | function | pip_deps | duration_hint_s | used by |
|---|---|---|---|---|
| predict_counts | `lcdm.kernels.predict_counts` | numpy, scipy | 900 | `predict_cluster_counts_lcdm` |

The kernel takes JSON only and NO file paths:
- `z_edges`, `m_min_1e14`, `area_deg2`
- `cosmology` {Om0, Ob0, h, ns, sigma8}, `mass_def`
- `observed_counts`: the N(z) histogram as a list
- `sigma8_grid`

The server computes `observed_counts` locally from the catalogue before dispatching.
On the client-side path, compute it with `compute_cluster_counts` (counts_nz.csv,
column N) and pass it inline. One prediction takes about 0.2 s locally. Dispatch only
pays off for large grids, e.g. many (Om0, sigma8) or many surveys/thresholds: loop
`run_pack_kernel` with `wait=False`.

The catalogue tools (fetch, crossmatch, plots) are light and always run locally.
