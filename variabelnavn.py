"""Full names for the grunnlagsdata variables, and which of them are key.

The column names in grunnlagsdata are R abbreviations (``ld_OPEXxS``,
``rd_wv.ol``) that cannot be read without a key. The key lives here, in one
place, and is used three ways: as the column headers in the edit panel, as the
label row in the downloadable CSV, and via ``/api/variabelnavn`` in the browser.

``NOKKELVARIABLER`` is the selection shown in «Rediger grunnlagsdata» — the
costs and tasks the model actually measures on. The remaining columns (framework
conditions, totals, DEA outputs) are edited in the CSV/Excel file.

The names themselves stay Norwegian: they are what the user reads on screen.
"""

from __future__ import annotations

VARIABELNAVN: dict[str, str] = {
    # Identifiers
    'id'  : "ID",
    'orgn': "Organisasjonsnr",
    'y'   : "År",
    'comp': "Selskap",

    # DEA outputs, distribution grid
    'fha_ld_TOTXDEA': "LD Total kostnad ekskl. nettap (1000 kr)",
    'fha_ld_sub'    : "LD Abonnenter",
    'fha_ld_hv'     : "LD Høyspentnett (km)",
    'fha_ld_ss'     : "LD Lavspentnett (km)",

    # DEA outputs, regional grid
    'fha_rd_TOTXDEA': "RD Total kostnad ekskl. nettap (1000 kr)",
    'fha_rd_wv.ol'  : "RD Vekt luftlinjer",
    'fha_rd_wv.uc'  : "RD Vekt jordkabler",
    'fha_rd_wv.sc'  : "RD Vekt sjøkabler",
    'fha_rd_wv.ss'  : "RD Vekt lavspentnett",

    # Distribution grid
    'ld_OPEXxS' : "LD OPEX ekskl. lønn (1000 kr)",
    'ld_sal'    : "LD Lønnskost (1000 kr)",
    'ld_sal.cap': "LD Aktivert lønn (1000 kr)",
    'ld_pens'   : "LD Pensjonskost (1000 kr)",
    'ld_pens.eq': "LD Pensjon egenkapital (1000 kr)",
    'ld_impl'   : "LD Pensjon impl. (1000 kr)",
    'ld_391'    : "LD §391 (1000 kr)",
    'ld_elhub'  : "LD Elhub (1000 kr)",
    'ld_usla'   : "LD Utestående saldo (1000 kr)",
    'ld_bv.sf'  : "LD BV selvfinansiert (1000 kr)",
    'ld_dep.sf' : "LD AVS selvfinansiert (1000 kr)",
    'ld_bv.gf'  : "LD BV gjennomfinansiert (1000 kr)",
    'ld_dep.gf' : "LD AVS gjennomfinansiert (1000 kr)",
    'ld_cens'   : "LD Nettleie (1000 kr)",
    'ld_nl'     : "LD Nettap (1000 kr)",
    'ld_sub'    : "LD Abonnenter",
    'ld_hvoh'   : "LD Høyspentnett luftlinjer (km)",
    'ld_hvug'   : "LD Høyspentnett jordkabler (km)",
    'ld_hvsc'   : "LD Høyspentnett sjøkabler (km)",
    'ld_hv'     : "LD Høyspentnett totalt (km)",
    'ld_ss'     : "LD Lavspentnett (km)",

    # Regional grid
    'rd_OPEXxS'  : "RD OPEX ekskl. lønn (1000 kr)",
    'rd_sal'     : "RD Lønnskost (1000 kr)",
    'rd_sal.cap' : "RD Aktivert lønn (1000 kr)",
    'rd_pens'    : "RD Pensjonskost (1000 kr)",
    'rd_pens.eq' : "RD Pensjon egenkapital (1000 kr)",
    'rd_impl'    : "RD Pensjon impl. (1000 kr)",
    'rd_391'     : "RD §391 (1000 kr)",
    'rd_elhub'   : "RD Elhub (1000 kr)",
    'rd_cga'     : "RD CGA (1000 kr)",
    'rd_cga_tidl': "RD CGA tidligere år (1000 kr)",
    'rd_coord'   : "RD Koordineringskost (1000 kr)",
    'rd_usla'    : "RD Utestående saldo (1000 kr)",
    'rd_bv.sf'   : "RD BV selvfinansiert (1000 kr)",
    'rd_dep.sf'  : "RD AVS selvfinansiert (1000 kr)",
    'rd_bv.gf'   : "RD BV gjennomfinansiert (1000 kr)",
    'rd_dep.gf'  : "RD AVS gjennomfinansiert (1000 kr)",
    'rd_cens'    : "RD Nettleie (1000 kr)",
    'rd_nl'      : "RD Nettap (1000 kr)",
    'rd_wv.ol'   : "RD Vekt luftlinjer",
    'rd_wv.uc'   : "RD Vekt jordkabler",
    'rd_wv.sc'   : "RD Vekt sjøkabler",
    'rd_wv.ss'   : "RD Vekt lavspentnett",

    # Totals
    't_OPEXxS': "Totalt OPEX ekskl. lønn (1000 kr)",
    't_sal'   : "Totalt lønn (1000 kr)",
    't_cens'  : "Totalt nettleie (1000 kr)",
    't_bv.sf' : "Totalt BV selvfinansiert (1000 kr)",
    't_dep.sf': "Totalt AVS selvfinansiert (1000 kr)",

    # Framework conditions (z variables)
    'ldz_salt'             : "Z: Saltholdighet",
    'ldz_coast_wind'       : "Z: Kystv ind",
    'ldz_water'            : "Z: Vassdrag",
    'ldz_incline'          : "Z: Terrenghelning",
    'ldz_prod'             : "Z: Produksjon",
    'ldz_snow_trees'       : "Z: Snø/tre",
    'ldz_forest_broadleaf' : "Z: Løvskog",
    'ldz_snowdrift'        : "Z: Snøfokk",
    'ldz_snow_400'         : "Z: Snø 400m",
    'ldz_wind_99'          : "Z: Vind 99-pst",
    'ldz_frosthours'       : "Z: Frosttimer",
    'ldz_forest_mixed_conf': "Z: Blandingsskog",
    'ldz_mgc'              : "Z: MGC",

    # Area prices
    'ap.t_2': "Avkastningsparameter t-2",
    'pnl.rc': "PnL referansekost",
}

# Columns present in grunnlagsdata but missing from the map above — added here
# so no column in the downloadable file is left without a label.
VARIABELNAVN.update({
    't_sal.cap':  "Totalt aktivert lønn (1000 kr)",
    't_pens':     "Totalt pensjonskost (1000 kr)",
    't_pens.eq':  "Totalt pensjon egenkapital (1000 kr)",
    't_impl':     "Totalt pensjon impl. (1000 kr)",
    't_391':      "Totalt §391 (1000 kr)",
    't_elhub':    "Totalt Elhub (1000 kr)",
    't_usla':     "Totalt utestående saldo (1000 kr)",
    't_bv.gf':    "Totalt BV gjennomfinansiert (1000 kr)",
    't_dep.gf':   "Totalt AVS gjennomfinansiert (1000 kr)",
    't_nl':       "Totalt nettap (1000 kr)",
    '_slett':     "Fjern selskapet fra kjøringen (1 = fjern)",
})

# Identifier columns — always included, whichever group is selected.
ID_KOLONNER: tuple[str, ...] = ('orgn', 'y', 'comp')

# The key variables, grouped as they appear in «Rediger grunnlagsdata».
# The order here is the order the columns get in the panel.
NOKKELVARIABLER: dict[str, list[str]] = {
    "kostnader": [
        'ld_OPEXxS', 'ld_sal', 'ld_pens', 'ld_cens', 'ld_nl',
        'ld_bv.sf', 'ld_dep.sf', 'ld_bv.gf', 'ld_dep.gf',
        'rd_OPEXxS', 'rd_sal', 'rd_pens', 'rd_coord', 'rd_cens', 'rd_nl',
        'rd_bv.sf', 'rd_dep.sf', 'rd_bv.gf', 'rd_dep.gf',
    ],
    "oppgaver": [
        'ld_sub', 'ld_hvoh', 'ld_hvug', 'ld_hvsc', 'ld_hv', 'ld_ss',
        'rd_wv.ol', 'rd_wv.uc', 'rd_wv.sc', 'rd_wv.ss',
    ],
    "priser": [
        'pnl.rc', 'ap.t_2',
    ],
}

GRUPPENAVN: dict[str, str] = {
    "kostnader": "Kostnader",
    "oppgaver":  "Oppgaver",
    "priser":    "Områdepriser",
}


def navn(kolonne: str) -> str:
    """The full name for a column, or the column name itself when unmapped."""
    return VARIABELNAVN.get(kolonne, kolonne)
