# Bundled data (provenance)

Small public FITS catalogues bundled so the tour works offline (total ~0.45 MB).
`tools.common.fetch_file` uses these copies first; everything else downloads on
first use into `~/.cache/cosmo-mcp/clusters-mcp-server/` (or `$COSMO_MCP_DATA`).

| file | source URL | citation |
|---|---|---|
| planck/HFI_PCCS_SZ-union_R2.08.fits.gz | https://irsa.ipac.caltech.edu/data/Planck/release_2/catalogs/HFI_PCCS_SZ-union_R2.08.fits.gz | Planck Collaboration 2016, A&A 594, A27 (arXiv:1502.01598) |
| spt/2500d_cluster_sample_Bocquet19.fits | https://pole.uchicago.edu/public/data/sptsz-clusters/2500d_cluster_sample_Bocquet19.fits | Bleem+2015 ApJS 216, 27; Bocquet+2019 ApJ 878, 55 (arXiv:1812.01679) |
| spt/sptpol100d_catalog_huang19.fits | https://pole.uchicago.edu/public/data/sptsz-clusters/sptpol100d_catalog_huang19.fits | Huang+2020 AJ 159, 110 (arXiv:1907.09621) |
| spt/sptecs_catalog_oct919.fits | https://pole.uchicago.edu/public/data/sptsz-clusters/sptecs_catalog_oct919.fits | Bleem+2020 ApJS 247, 25 (arXiv:1910.04121) |

Downloaded on demand (verified 2026-11-04): ACT DR6 (26 MB, LAMBDA), SPT-3G Main 5yr
(2.6 MB, LAMBDA), eRASS1 primary (24 MB .tgz) and cosmology (0.5 MB .tgz) from the
eROSITA DR1 portal (the bare .fits URLs return HTTP 403; the .fits.tgz work).
