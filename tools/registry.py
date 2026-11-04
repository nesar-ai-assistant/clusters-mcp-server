"""Single source of truth for the datasets this server exposes.

Keys are short dataset ids used by every tool's ``dataset`` argument.
"access" is "bundled" (file in data/), "download" (fetched on first use
into the data cache) or "remote-query" (live service).

Every catalogue here is a FITS table downloaded on first use; ``columns`` maps
the native columns onto the harmonised schema of tools.catalogs.io
(name, ra, dec, z, z_err, M500 [1e14 Msun], M500_err_lo/hi, snr, survey).
All URLs were verified by download on 2026-11-04.

Products are keyed by data kind:
  catalog           – per-object catalogs
  summary_statistic – selection functions, binned counts, stacked WL profiles
  published_result  – published S8/Om posteriors (comparison only)
"""

SKY_DEG2 = 41252.96

_CAT = ["fetch_cluster_catalog", "describe_catalog_columns", "plot_mass_redshift", "plot_cluster_sky_map",
        "compute_cluster_counts", "crossmatch_catalogs", "compare_mass_calibration",
        "predict_cluster_counts_lcdm", "plot_counts_vs_prediction"]

_SELFN = ["fetch_cluster_selection_function", "plot_completeness"]

DATASETS: dict[str, dict] = {
    "psz2": {
        "title": "Planck PSZ2 union catalogue (Planck 2015 XXVII), 1653 SZ detections",
        "survey": "Planck PSZ2",
        "products": {
            "catalog": ["SZ-detected cluster catalog (1653 objects, SNR, MSZ, z)"],
            "summary_statistic": ["survey completeness C(Y500, theta500) for MMF3-cosmology and union-survey masks"],
        },
        "access": "download",
        "urls": ["https://irsa.ipac.caltech.edu/data/Planck/release_2/catalogs/HFI_PCCS_SZ-union_R2.08.fits.gz"],
        "file": {"url": "https://irsa.ipac.caltech.edu/data/Planck/release_2/catalogs/HFI_PCCS_SZ-union_R2.08.fits.gz",
                 "subdir": "planck"},
        "n_rows": 1653,
        "area_deg2": 34487.0,
        "area_note": "union catalogue covers 83.6% of the sky after masking (0.836 x 41253 deg^2)",
        "columns": {"name": "NAME", "ra": "RA", "dec": "DEC", "z": "REDSHIFT", "M500": "MSZ",
                    "M500_err_lo": "MSZ_ERR_LOW", "M500_err_hi": "MSZ_ERR_UP", "snr": "SNR"},
        "conventions": "MSZ = M500c [1e14 Msun] from the Planck Y-M relation (Arnaud+10 based, hydrostatic; "
                       "no (1-b) correction), only for the 1093 entries with a redshift. REDSHIFT=-1 means no "
                       "redshift. snr = SNR of the union detection. COSMO=True flags the 439 cosmology-sample members.",
        "citation": "Planck Collaboration 2016, A&A 594, A27 (Planck 2015 results XXVII), arXiv:1502.01598",
        "selection_function": {
            "files": {
                "MMF3_cosmology": {
                    "url": "https://irsa.ipac.caltech.edu/data/Planck/release_2/catalogs/HFI_PCCS_SZ-selfunc-MMF3-cosmolog_R2.08.fits",
                    "size_bytes": 402773760,
                    "note": "65% sky cosmology mask, MMF3 pipeline. 403 MB: HDU 0 = Nside-2048 HEALPix noise map, tail HDUs = completeness(Y500, theta500, SNR_cut).",
                },
                "union_survey": {
                    "url": "https://irsa.ipac.caltech.edu/data/Planck/release_2/catalogs/HFI_PCCS_SZ-selfunc-union-survey_R2.08.fits",
                    "size_bytes": 402773760,
                    "note": "83.7% sky survey mask, union pipeline.",
                },
            },
            "completeness_shape": "(12 SNR_cuts, 32 theta500 bins, 30 Y500 bins)",
            "citation": "Planck 2015 results XXVII (arXiv:1502.01598), section 2 & Appendix A",
        },
        "tools": _CAT + _SELFN,
    },
    "spt_sz": {
        "title": "SPT-SZ 2500 deg^2 cluster catalogue, Bocquet+2019 masses (677 candidates, xi>4.5)",
        "survey": "SPT-SZ",
        "products": {
            "catalog": ["SZ-detected cluster catalog (677 candidates, xi, M500c, z)"],
            "summary_statistic": [
                "field-by-field survey areas and noise corrections (19 fields, Bocquet+19)",
                "Megacam/HST weak-lensing shear profiles for 32 clusters (Dietrich+19, Schrabback+18)",
            ],
        },
        "access": "download",
        "urls": ["https://pole.uchicago.edu/public/data/sptsz-clusters/2500d_cluster_sample_Bocquet19.fits"],
        "file": {"url": "https://pole.uchicago.edu/public/data/sptsz-clusters/2500d_cluster_sample_Bocquet19.fits",
                 "subdir": "spt"},
        "n_rows": 677,
        "area_deg2": 2500.0,
        "columns": {"name": "SPT_ID", "ra": "RA", "dec": "DEC", "z": "REDSHIFT", "z_err": "REDSHIFT_UNC",
                    "M500": "M500", "M500_err_lo": "M500_lerr", "M500_err_hi": "M500_uerr", "snr": "XI"},
        "conventions": "M500 = M500c [1e14 Msun/h70] from the WL+X-ray calibrated xi-mass relation of Bocquet+19 "
                       "at fixed cosmology; only for the 516 confirmed clusters with redshift. snr = xi "
                       "(SPT detection significance); 409 candidates have xi>5. REDSHIFT=0 -> no redshift "
                       "(REDSHIFT_LIMIT gives lower limits for some).",
        "citation": "Bleem et al. 2015, ApJS 216, 27 (arXiv:1409.0850); Bocquet et al. 2019, ApJ 878, 55 "
                    "(arXiv:1812.01679)",
        "wl_data": {
            "url": "https://pole.uchicago.edu/public/data/sptsz-clusters/SPT_SZ_cluster_likelihood-0.0.tar.gz",
            "subdir": "spt",
            "archive_member_prefix": "SPT_SZ_cluster_likelihood-0.0/data/",
            "megacam_clusters": 20,
            "hst_clusters": 13,
            "columns_megacam": "r_deg, gt (tangential shear), Delta_gt, kbin",
            "columns_hst": "r_deg, shear, shearerr per radial bin, per magnitude bin",
            "citation": "Dietrich et al. 2019 (MNRAS 483, 2871); Schrabback et al. 2018 (MNRAS 474, 2635)",
        },
        "selection_function": {
            "type": "field_noise",
            "n_fields": 19,
            "note": "SPT-SZ completeness is encoded as field-by-field areas and noise correction factors. "
                    "The detection probability for a cluster of true significance zeta in field f is "
                    "P(xi > xi_cut | zeta) = erfc((xi_cut - gamma_f * zeta) / sqrt(2)) / 2, "
                    "where gamma_f are the field correction factors from SPTcluster_data.py.",
            "citation": "Bocquet et al. 2019 (arXiv:1812.01679); de Haan et al. 2016 (ApJ 832, 95)",
        },
        "tools": _CAT + _SELFN + ["fetch_cluster_wl_profiles"],
    },
    "sptpol_100d": {
        "title": "SPTpol 100 deg^2 cluster catalogue (Huang+2020), 89 candidates xi>4.6",
        "survey": "SPTpol 100d",
        "products": {"catalog": ["SZ-detected cluster catalog"]},
        "access": "download",
        "urls": ["https://pole.uchicago.edu/public/data/sptsz-clusters/sptpol100d_catalog_huang19.fits"],
        "file": {"url": "https://pole.uchicago.edu/public/data/sptsz-clusters/sptpol100d_catalog_huang19.fits",
                 "subdir": "spt"},
        "n_rows": 89,
        "area_deg2": 100.0,
        "columns": {"name": "SPT_ID", "ra": "RA", "dec": "Dec", "z": "redshift", "z_err": "redshift_unc",
                    "M500": "M500", "M500_err_lo": "M500_lerr", "M500_err_hi": "M500_uerr", "snr": "xi"},
        "conventions": "M500 = M500c [1e14 Msun/h70] (xi-mass relation, fixed LCDM Om=0.3 h=0.7 s8=0.8). snr = xi.",
        "citation": "Huang et al. 2020, AJ 159, 110, arXiv:1907.09621",
        "tools": _CAT,
    },
    "spt_ecs": {
        "title": "SPTpol Extended Cluster Survey (SPT-ECS, Bleem+2020), 470 candidates in 2770 deg^2",
        "survey": "SPT-ECS",
        "products": {"catalog": ["SZ-detected cluster catalog"]},
        "access": "download",
        "urls": ["https://pole.uchicago.edu/public/data/sptsz-clusters/sptecs_catalog_oct919.fits"],
        "file": {"url": "https://pole.uchicago.edu/public/data/sptsz-clusters/sptecs_catalog_oct919.fits",
                 "subdir": "spt"},
        "n_rows": 470,
        "area_deg2": 2770.0,
        "columns": {"name": "SPT_ID", "ra": "RA", "dec": "DEC", "z": "REDSHIFT", "z_err": "REDSHIFT_UNC",
                    "M500": "M500", "M500_err_lo": "M500_LERR", "M500_err_hi": "M500_UERR", "snr": "XI"},
        "conventions": "M500 = M500c [1e14 Msun/h70] (xi-mass relation, fixed LCDM). snr = xi. 448 confirmed.",
        "citation": "Bleem et al. 2020, ApJS 247, 25, arXiv:1910.04121",
        "tools": _CAT,
    },
    "spt3g_5yr": {
        "title": "SPT-3G Main field 5-year SZ cluster catalogue (Bleem+2026), 8892 candidates xi>4",
        "survey": "SPT-3G",
        "products": {"catalog": ["SZ-detected cluster catalog"]},
        "access": "download",
        "urls": ["https://lambda.gsfc.nasa.gov/data/suborbital/SPT/spt_3gsz/spt3g_main_field_5yr_clusters_070126.fits",
                 "https://lambda.gsfc.nasa.gov/product/spt/spt3g_5yr_main_field_cat_get.html"],
        "file": {"url": "https://lambda.gsfc.nasa.gov/data/suborbital/SPT/spt_3gsz/"
                        "spt3g_main_field_5yr_clusters_070126.fits", "subdir": "spt"},
        "n_rows": 8892,
        "area_deg2": 1604.0,
        "columns": {"name": "SPT_ID", "ra": "RA", "dec": "DEC", "z": "REDSHIFT", "z_err": "REDSHIFT_UNC",
                    "M500": "M500C", "M500_err_lo": "M500C_LERR", "M500_err_hi": "M500C_UERR", "snr": "XI"},
        "conventions": "M500C [1e14 Msun/h70]; 7190 confirmed clusters have z and mass, median M500c 1.65e14, "
                       "median z 0.73. snr = xi; 4480 candidates at xi>=5.",
        "citation": "Bleem et al. 2026, arXiv:2607.01175",
        "tools": _CAT,
    },
    "act_dr6": {
        "title": "ACT DR6 SZ-selected cluster catalogue (ACT-DES-HSC 2025), 10040 clusters SNR>4",
        "survey": "ACT DR6",
        "products": {
            "catalog": ["SZ-detected cluster catalog (10040 objects, fixed_SNR, M500c, z)"],
            "summary_statistic": [
                "Q(theta500, z) filter mismatch per tile (QFit.fits, 293 tiles x 55 rows)",
                "tile noise levels (RMSTab, 13515 rows, areaDeg2 + y0RMS per tile)",
            ],
        },
        "access": "download",
        "urls": ["https://lambda.gsfc.nasa.gov/data/suborbital/ACT/actadv_dr6_cluster_cat/DR6_cluster-catalog_v1.0.fits",
                 "https://lambda.gsfc.nasa.gov/product/act/actadv_dr6_szcluster_catalog_get.html"],
        "file": {"url": "https://lambda.gsfc.nasa.gov/data/suborbital/ACT/actadv_dr6_cluster_cat/"
                        "DR6_cluster-catalog_v1.0.fits", "subdir": "act"},
        "n_rows": 10040,
        "area_deg2": 16293.0,
        "columns": {"name": "name", "ra": "RADeg", "dec": "decDeg", "z": "redshift", "z_err": "redshiftErr",
                    "M500": "M500c", "M500_err_lo": "M500c_errMinus", "M500_err_hi": "M500c_errPlus", "snr": "SNR"},
        "conventions": "M500c [1e14 Msun] with the WL-consistent scaling normalisation 10^A0 = 3.0e-5 and Eddington-"
                       "bias correction (the catalogue default). For Planck-like masses use the native column "
                       "A10_M500cUncorr (Arnaud+10, no Eddington correction). snr = SNR optimised over filter scales. "
                       "All 10040 have redshifts; SNR>5 gives a sample 90% complete above 5e14 Msun.",
        "citation": "ACT-DES-HSC Collaboration (Hilton et al.) 2025, arXiv:2507.21459",
        "selection_function": {
            "tarball_url": "https://lambda.gsfc.nasa.gov/data/suborbital/ACT/actadv_dr6_cluster_cat/DR6_nemo-products_v1.0.tgz",
            "tarball_size_bytes": 7412247304,
            "extracted_files": {
                "QFit.fits": "Q(theta500Arcmin, z) per tile (293 HDUs, 55 rows each; ~1.7 MB)",
                "RMSTab_maxFlags0.fits": "tile area + y0 RMS noise (13515 rows; ~250 KB)",
                "config.yml": "nemo pipeline config: scaling relation params, SNR cut, bias model",
                "tileAreas.txt": "tile names + areas in deg^2 (293 tiles)",
            },
            "note": "The 7.4 GB tarball also contains HEALPix RMS maps and flag masks. "
                    "Only the small selection-function tables (QFit, RMSTab, config) are fetched by this server.",
        },
        "tools": _CAT + _SELFN,
    },
    "erass1": {
        "title": "eROSITA eRASS1 primary cluster catalogue (Bulbul+2024), 12247 optically confirmed groups/clusters",
        "survey": "eRASS1",
        "products": {"catalog": ["X-ray selected cluster catalog"]},
        "access": "download",
        "urls": ["https://erosita.mpe.mpg.de/dr1/AllSkySurveyData_dr1/Catalogues_dr1/BulbulE_DR1/"
                 "erass1cl_primary_v3.2.fits.tgz"],
        "file": {"url": "https://erosita.mpe.mpg.de/dr1/AllSkySurveyData_dr1/Catalogues_dr1/BulbulE_DR1/"
                        "erass1cl_primary_v3.2.fits.tgz", "subdir": "erosita",
                 "archive_member": "erass1cl_primary_v3.2.fits"},
        "n_rows": 12247,
        "area_deg2": 13116.0,
        "columns": {"name": "NAME", "ra": "RA", "dec": "DEC", "z": "BEST_Z", "z_err": "BEST_ZERR",
                    "M500": "M500", "M500_err_lo": "M500_L", "M500_err_hi": "M500_H", "snr": "EXT_LIKE",
                    "mass_scale": 0.1, "M500_lo_is_bound": True},
        "conventions": "Native M500 is in 1e13 Msun (converted x0.1 to 1e14 Msun); M500_L/M500_H are 1-sigma "
                       "BOUNDS (converted to errors). Masses come from the count-rate-mass relation of the "
                       "eRASS1 cosmology analysis (WL calibrated). ~1800 entries have M500<=0 (no mass) -> NaN. "
                       "snr = EXT_LIKE (extent likelihood), not an S/N. The raw .fits URL returns HTTP 403; the "
                       ".fits.tgz is used (23.8 MB, 50 MB unpacked).",
        "citation": "Bulbul et al. 2024, A&A 685, A106, arXiv:2402.08452",
        "tools": _CAT,
    },
    "erass1_cosmo": {
        "title": "eROSITA eRASS1 cosmology cluster sample (Bulbul+2024), 5259 clusters, ~95% purity",
        "survey": "eRASS1 cosmo",
        "products": {
            "catalog": ["cosmology subsample (5259 clusters)"],
            "published_result": ["S8 = 0.86 +/- 0.01, Om = 0.29 +0.01/-0.02 (Ghirardini+24, WL-calibrated eRASS1 counts)"],
        },
        "access": "download",
        "urls": ["https://erosita.mpe.mpg.de/dr1/AllSkySurveyData_dr1/Catalogues_dr1/BulbulE_DR1/"
                 "erass1cl_cosmology_v1.1.fits.tgz"],
        "file": {"url": "https://erosita.mpe.mpg.de/dr1/AllSkySurveyData_dr1/Catalogues_dr1/BulbulE_DR1/"
                        "erass1cl_cosmology_v1.1.fits.tgz", "subdir": "erosita",
                 "archive_member": "erass1cl_cosmology_v1.1.fits"},
        "n_rows": 5259,
        "area_deg2": 12791.0,
        "columns": {"name": "NAME", "ra": "RA", "dec": "DEC", "z": "Z_LAMBDA", "z_err": "Z_LAMBDA_E"},
        "conventions": "z = Z_LAMBDA (redMaPPer-like photometric). The cosmology file has no M500 or EXT_LIKE: "
                       "they are joined from the primary catalogue on DETUID (5196 of 5259 match; the rest are NaN).",
        "citation": "Bulbul et al. 2024, A&A 685, A106; Ghirardini et al. 2024, A&A 689, A298",
        "tools": _CAT,
    },
}

# Published cluster-cosmology constraints (comparison only)
PUBLISHED_CONSTRAINTS: dict[str, dict] = {
    "planck_2015_xxiv": {
        "title": "Planck 2015 cluster counts (Planck Collab. XXIV)",
        "parameters": {
            "sigma8_Om0.31_0.3": {"value": 0.774, "error": 0.034, "note": "CCCP+BAO+BBN baseline"},
            "Om0": {"value": 0.33, "error": 0.03},
            "sigma8": {"value": 0.76, "error": 0.03},
        },
        "citation": "Planck Collaboration 2016, A&A 594, A24 (arXiv:1502.01597)",
    },
    "bocquet_2019": {
        "title": "SPT-SZ + WL + Chandra (Bocquet+19)",
        "parameters": {
            "sigma8_Om0.3_0.2": {"value": 0.766, "error": 0.025},
            "Om0": {"value": 0.276, "error": 0.047},
            "sigma8": {"value": 0.781, "error": 0.037},
        },
        "citation": "Bocquet et al. 2019, ApJ 878, 55 (arXiv:1812.01679)",
    },
    "bocquet_2024": {
        "title": "SPT-SZ+SPTpol+SPT-3G x DES+HST WL (Bocquet+24)",
        "parameters": {
            "sigma8_Om0.3_0.25": {"value": 0.805, "error": 0.016},
            "S8": {"value": 0.795, "error": 0.029},
            "Om0": {"value": 0.286, "error": 0.032},
            "sigma8": {"value": 0.817, "error": 0.026},
        },
        "citation": "Bocquet et al. 2024, Phys. Rev. D 110, 083510 (arXiv:2401.02075)",
    },
    "ghirardini_2024": {
        "title": "eRASS1 cluster counts (Ghirardini+24)",
        "parameters": {
            "S8": {"value": 0.86, "error": 0.01},
            "Om0": {"value": 0.29, "error_lo": 0.02, "error_hi": 0.01},
            "sigma8": {"value": 0.88, "error": 0.02},
        },
        "citation": "Ghirardini et al. 2024, A&A 689, A298 (arXiv:2402.08458)",
    },
}

# survey -> plotting colour (stable across tools)
SURVEY_COLORS = {"Planck PSZ2": "#1f77b4", "SPT-SZ": "#d62728", "SPTpol 100d": "#9467bd", "SPT-ECS": "#e377c2",
                 "SPT-3G": "#ff7f0e", "ACT DR6": "#2ca02c", "eRASS1": "#7f7f7f", "eRASS1 cosmo": "#8c564b"}
