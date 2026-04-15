"""
RME reporting table — mapping, converter, and forecast.

Maps grunnlagsdata.csv column names (from the R pipeline) to the NVE/RME
wide-format table used in official reporting, and projects values forward
using the same formula as the THEMA cost forecast Excel.

Usage
-----
    from kostnader import grunnlagsdata_to_rme, rme_table_with_forecast

    # Historical only (2020-2024)
    hist = grunnlagsdata_to_rme("Results/Run_.../2026-04-14_grunnlagsdata.csv")

    # Historical + forecast (2020-2033)
    full = rme_table_with_forecast(
        csv_path="Results/Run_.../2026-04-14_grunnlagsdata.csv",
        config_path="config.yaml",
    )
    full.to_excel("rme_table_forecast.xlsx", index=False)
"""

import os
import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------
# Each entry: (variable, nettnivaa, unit, formula)
# formula = list of (column_name, sign) pairs, e.g. (col, +1) or (col, -1)
# Columns refer to grunnlagsdata.csv from the R pipeline.
#
# NOTE: O&M costs include capitalised salaries subtracted (sal.cap has sign -1).
# The resulting values are within ~0.3 % of the original RME-reported nominals
# for most companies/years. Larger deviations (up to ~4 %) may occur when
# unusual items (usla, cga) or elhub treatment differs by year.

_LD_OM: list[tuple[str, int]] = [
    ("ld_OPEXxS",   +1),   # Non-salary OPEX
    ("ld_sal",      +1),   # Salaries
    ("ld_sal.cap",  -1),   # Capitalised salaries (subtracted)
    ("ld_pens",     +1),   # Pensions
    ("ld_pens.eq",  +1),   # Pension equalisation
    ("ld_impl",     +1),   # Implementation costs
    ("ld_391",      +1),   # §391 costs
    ("ld_elhub",    +1),   # Elhub
    ("ld_usla",     +1),   # Unusual items
]

_RD_OM: list[tuple[str, int]] = [
    ("rd_OPEXxS",     +1),
    ("rd_sal",        +1),
    ("rd_sal.cap",    -1),
    ("rd_pens",       +1),
    ("rd_pens.eq",    +1),
    ("rd_impl",       +1),
    ("rd_391",        +1),
    ("rd_elhub",      +1),
    ("rd_cga",        +1),   # Co-generation agreement costs
    ("rd_cga_tidl",   +1),   # Previous-period CGA correction
    ("rd_usla",       +1),
]

# Ordered list — order determines row order in the output table.
RME_MAPPING: list[tuple[str, str, str, list[tuple[str, int]]]] = [
    # variable                              nettnivaa        unit            formula
    # --- O&M costs (Total added automatically as LD + RD) ---
    ("O&M costs",                         "Distributional", "1000 NOK",     _LD_OM),
    ("O&M costs",                         "Regional",       "1000 NOK",     _RD_OM),
    # --- Grid loss ---
    ("Grid loss",                         "Distributional", "MWh",          [("ld_nl", +1)]),
    ("Grid loss",                         "Regional",       "MWh",          [("rd_nl", +1)]),
    # --- CENS / KILE ---
    ("CENS cost",                         "Distributional", "1000 NOK",     [("ld_cens", +1)]),
    ("CENS cost",                         "Regional",       "1000 NOK",     [("rd_cens", +1)]),
    # --- Internally funded capital ---
    ("Internally funded capital",         "Distributional", "1000 NOK",     [("ld_bv.sf", +1)]),
    ("Depreciation on internal capital",  "Distributional", "1000 NOK",     [("ld_dep.sf", +1)]),
    ("Internally funded capital",         "Regional",       "1000 NOK",     [("rd_bv.sf", +1)]),
    ("Depreciation on internal capital",  "Regional",       "1000 NOK",     [("rd_dep.sf", +1)]),
    # --- Externally funded capital ---
    ("Externally funded capital",         "Distributional", "1000 NOK",     [("ld_bv.gf", +1)]),
    ("Depreciation on external capital",  "Distributional", "1000 NOK",     [("ld_dep.gf", +1)]),
    ("Externally funded capital",         "Regional",       "1000 NOK",     [("rd_bv.gf", +1)]),
    ("Depreciation on external capital",  "Regional",       "1000 NOK",     [("rd_dep.gf", +1)]),
    # --- RKSU ---
    ("RKSU",                              "Regional",       "1000 NOK",     [("rd_coord", +1)]),
    # --- Infrastructure — Distributional ---
    ("Customers",                         "Distributional", "number",       [("ld_sub",  +1)]),
    ("High voltage",                      "Distributional", "km lines",     [("ld_hv",   +1)]),
    ("Substations",                       "Distributional", "number",       [("ld_ss",   +1)]),
    ("High voltage overhead",             "Distributional", "km lines",     [("ld_hvoh", +1)]),
    ("High voltage underground",          "Distributional", "km lines",     [("ld_hvug", +1)]),
    ("High voltage submarine",            "Distributional", "km lines",     [("ld_hvsc", +1)]),
    # --- Infrastructure — Regional ---
    ("Above ground lines",                "Regional",       "weighted cost",[("rd_wv.ol", +1)]),
    ("Underground cables",                "Regional",       "weighted cost",[("rd_wv.uc", +1)]),
    ("Submarine cables",                  "Regional",       "weighted cost",[("rd_wv.sc", +1)]),
    ("Interface components",              "Regional",       "weighted cost",[("rd_wv.ss", +1)]),
]

# Row-order for sorting: "Total" before "Distributional" before "Regional"
_NETTNIVAA_ORDER = {"Total": 0, "Distributional": 1, "Regional": 2}

# variable → sort position (based on mapping order, with Total variant inserted after each base variable)
_VAR_ORDER = {v: i for i, (v, *_) in enumerate(RME_MAPPING)}
_VAR_ORDER["O&M costs"] = -1   # Total O&M goes first


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------

def _load_nve_id_map(csv_path: str) -> dict[int, int]:
    """Return {orgn: NVE_ID} by looking for Data_Resultater_LD.xlsx in the same folder."""
    import os
    folder = os.path.dirname(os.path.abspath(csv_path))
    xl_path = os.path.join(folder, "Data_Resultater_LD.xlsx")
    if not os.path.exists(xl_path):
        return {}
    ref = pd.read_excel(xl_path, sheet_name="Datagrunnlag_LD", usecols=["orgn", "id"])
    return dict(zip(ref["orgn"].astype(int), ref["id"].astype(int)))


def grunnlagsdata_to_rme(
    csv_path: str,
    years: list[int] | None = None,
    company_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Convert grunnlagsdata.csv to the RME wide-format reporting table.

    Parameters
    ----------
    csv_path : str
        Path to grunnlagsdata.csv produced by the R pipeline.
        The function automatically looks for Data_Resultater_LD.xlsx in the
        same folder to resolve orgn → NVE_ID.
    years : list[int] | None
        Filter to these years only. Default: all years present.
    company_ids : list[int] | None
        Filter to these NVE IDs only. Default: all companies.

    Returns
    -------
    pd.DataFrame
        Columns: NVE_ID, Company, Variable, Nettnivaa, Unit, <year>, ...
        One row per (company, variable, nettnivaa) combination.
    """
    df = pd.read_csv(csv_path).fillna(0)

    # Resolve NVE_ID from orgn via Data_Resultater_LD.xlsx in the same folder
    id_map = _load_nve_id_map(csv_path)
    if id_map:
        df["id"] = df["orgn"].astype(int).map(id_map)
    else:
        df["id"] = df["orgn"]   # fallback: use orgn as identifier

    if years is not None:
        df = df[df["y"].isin(years)]
    if company_ids is not None:
        df = df[df["id"].isin(company_ids)]

    # --- Compute each metric as a named column on a clean working frame ---
    work = df[["id", "comp", "y"]].copy()

    for variable, nettnivaa, unit, formula in RME_MAPPING:
        key = f"{variable}|{nettnivaa}"
        series = pd.Series(0.0, index=df.index)
        for col, sign in formula:
            if col in df.columns:
                series = series + sign * df[col].fillna(0)
        work[key] = series

    # O&M Total = Distributional + Regional
    work["O&M costs|Total"] = (
        work["O&M costs|Distributional"] + work["O&M costs|Regional"]
    )

    # --- Melt to long format ---
    value_cols = [c for c in work.columns if "|" in c]
    long = work.melt(
        id_vars=["id", "comp", "y"],
        value_vars=value_cols,
        var_name="key",
        value_name="value",
    )

    long[["Variable", "Nettnivaa"]] = long["key"].str.split("|", n=1, expand=True)

    # Attach unit lookup
    unit_map: dict[str, str] = {
        f"{v}|{n}": u for v, n, u, _ in RME_MAPPING
    }
    unit_map["O&M costs|Total"] = "1000 NOK"
    long["Unit"] = long["key"].map(unit_map)

    long = long.drop(columns="key")

    # --- Pivot wide: one column per year ---
    wide = long.pivot_table(
        index=["id", "comp", "Variable", "Nettnivaa", "Unit"],
        columns="y",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    wide = wide.rename(columns={"id": "NVE_ID", "comp": "Company"})

    # --- Sort rows to match RME order ---
    wide["_var_idx"] = wide["Variable"].map(_VAR_ORDER).fillna(999)
    wide["_net_idx"] = wide["Nettnivaa"].map(_NETTNIVAA_ORDER).fillna(9)
    wide = (
        wide.sort_values(["NVE_ID", "_var_idx", "_net_idx"])
        .drop(columns=["_var_idx", "_net_idx"])
        .reset_index(drop=True)
    )

    # Integer year columns — round non-monetary values to avoid float noise
    year_cols = [c for c in wide.columns if isinstance(c, (int, float))]
    wide[year_cols] = wide[year_cols].round(2)


    return wide


# ---------------------------------------------------------------------------
# Forecast helpers
# ---------------------------------------------------------------------------

def _load_cfg(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_cpi_cumulative(config: dict, max_year: int) -> dict[int, float]:
    """CPI cumulative factor relative to 2024 = 1.0 for years 2024 … max_year."""
    foru = config.get("forutsetninger", {})
    kpi_idx = foru.get("kpi_justering", {2024: 133.6, 2026: 140.6})
    idx_2024 = float(kpi_idx.get(2024, 133.6))
    idx_2026 = float(kpi_idx.get(2026, 140.6))

    # Annual KPI growth rates (%) from prognose config
    raw_rates: dict = config.get("prognose", {}).get("forutsetninger", {}).get("kpi", {})
    kpi_rates = {int(k): float(v) for k, v in raw_rates.items()}
    fallback = float(max(kpi_rates.values(), default=2.0))

    out: dict[int, float] = {2024: 1.0}
    # 2025: geometric midpoint between 2024 and 2026 index levels
    out[2025] = (idx_2026 / idx_2024) ** 0.5
    # 2026: direct index ratio
    out[2026] = idx_2026 / idx_2024
    # 2027+: compound from 2026 using annual rates
    prev = out[2026]
    for y in range(2027, max_year + 1):
        prev = prev * (1 + kpi_rates.get(y, fallback) / 100)
        out[y] = prev
    return out


def _synergy_factor(merge_yr: int | None, synergy_frac: float, forecast_yr: int) -> float:
    """O&M synergy phase-in fraction for a given forecast year (matches prognose.py)."""
    if merge_yr is None or synergy_frac == 0.0:
        return 0.0
    diff = forecast_yr - merge_yr
    if diff <= 0:
        return 0.0
    elif diff == 1:
        return synergy_frac / 3
    elif diff == 2:
        return synergy_frac / 2
    return synergy_frac


def _get_inv_rates(
    config: dict, company_id: int, forecast_years: list[int]
) -> tuple[dict[int, float], dict[int, float]]:
    """Return (dnett_pct, rnett_pct) dicts keyed by year for a company.

    Loads per-company rates from investeringer.csv via prognose module,
    falling back to the config prognose block, then to 0.
    """
    try:
        from prognose import load_investeringer_for_company, DEFAULT_INVESTERINGER
        inv_csv = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "Data", "investeringer.csv"
        )
        inv = load_investeringer_for_company(company_id, inv_csv)
    except Exception:
        inv = {"dnett_pct": {}, "rnett_pct": {}}

    # Fill missing years from config prognose block, then default 0
    cfg_inv = config.get("prognose", {}).get("investeringer", {})
    dn, rn = {}, {}
    for y in forecast_years:
        dn[y] = inv["dnett_pct"].get(y) or float(cfg_inv.get("dnett_pct", {}).get(y, 0))
        rn[y] = inv["rnett_pct"].get(y) or float(cfg_inv.get("rnett_pct", {}).get(y, 0))
    return dn, rn


# ---------------------------------------------------------------------------
# Main forecast function
# ---------------------------------------------------------------------------

def rme_table_with_forecast(
    csv_path: str,
    config_path: str = "config.yaml",
    forecast_years: list[int] | None = None,
    company_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Return the RME table extended with forecast columns for 2025–2033.

    Historical columns (2020–2024) come directly from grunnlagsdata.csv.
    Forecast columns are computed using the same approach as the THEMA
    cost forecast Excel model:

    O&M costs
        3-year average of the last 3 historical years, CPI-inflated to each
        forecast year, with merger synergy phased in and one-off cost in
        merge_yr.  Formula (matching Excel):
            base = mean(om[y-3 … y-1])     # fixed at last 3 hist. years
            om_t = base * cpi_t * (1 − synergy_factor_t) + one_off_t

    Capital (BFV) and depreciation
        Total BFV for each network level is grown by the investment rate
        (from investeringer.csv / config) minus the depreciation rate.
        The internal/external split is preserved at the last-historical ratio.
            BFV_total_t = BFV_total_{t-1} * (1 + inv_pct_t − avs_sats)
            BFV_sf_t    = BFV_total_t * sf_ratio
            dep_sf_t    = BFV_sf_t * avs_sats

    Grid loss, RKSU, infrastructure
        Held constant at the last historical year value.

    CENS cost
        Grown by KPI each year from last historical value.

    Parameters
    ----------
    csv_path : str
        Path to grunnlagsdata.csv from the latest R pipeline run.
    config_path : str
        Path to config.yaml (for KPI, avs_sats, fusjoner).
    forecast_years : list[int] | None
        Years to forecast. Default: 2025–2033.
    company_ids : list[int] | None
        Subset of NVE IDs. Default: all companies.

    Returns
    -------
    pd.DataFrame
        Same format as grunnlagsdata_to_rme() but with extra year columns.
    """
    if forecast_years is None:
        forecast_years = list(range(2025, 2034))
    forecast_years = sorted(forecast_years)

    config = _load_cfg(config_path)
    avs_sats = float(config.get("prognose", {}).get("avs_sats", 4.0)) / 100
    fusjoner: dict = config.get("fusjoner", {})
    cpi = _build_cpi_cumulative(config, max(forecast_years))

    # Historical table (all years, all companies)
    hist = grunnlagsdata_to_rme(csv_path, company_ids=company_ids)

    # Identify historical year columns present in the table
    hist_year_cols = sorted([c for c in hist.columns if isinstance(c, (int, float))])
    last_hist_yr = int(max(hist_year_cols))

    # Only forecast years that aren't already in the historical data
    fcst_years = [y for y in forecast_years if y not in hist_year_cols]
    if not fcst_years:
        return hist

    # Use last 3 historical years as the O&M base window (fixed, not sliding)
    om_base_years = sorted(hist_year_cols)[-3:]

    # Pre-index historical data: (NVE_ID, Company, Variable, Nettnivaa, Unit) -> row
    hist_idx = hist.set_index(["NVE_ID", "Company", "Variable", "Nettnivaa", "Unit"])

    # Pre-compute BFV projections for all companies and levels up front.
    # Structure: bfv_proj[(nve_id, company, nettnivaa)][year] = {"sf": float, "gf": float}
    # This avoids state-ordering issues when iterating over variable rows.
    def _precompute_bfv(
        nve_id: int, company: str, nettnivaa: str,
        inv_dn: dict[int, float], inv_rn: dict[int, float],
    ) -> dict[int, dict[str, float]]:
        def _h(var_name: str) -> float:
            try:
                return float(hist_idx.loc[
                    (nve_id, company, var_name, nettnivaa, "1000 NOK"), last_hist_yr
                ] or 0)
            except KeyError:
                return 0.0

        bv_sf = _h("Internally funded capital")
        bv_gf = _h("Externally funded capital")
        bv_total = bv_sf + bv_gf
        sf_ratio = bv_sf / bv_total if bv_total > 0 else 0.5

        yearly: dict[int, dict[str, float]] = {}
        for y in fcst_years:
            inv_pct = (inv_dn.get(y, 0) if nettnivaa == "Distributional"
                       else inv_rn.get(y, 0)) / 100
            bv_total = bv_total * (1 + inv_pct - avs_sats)
            bv_sf = bv_total * sf_ratio
            bv_gf = bv_total * (1 - sf_ratio)
            yearly[y] = {"sf": bv_sf, "gf": bv_gf}
        return yearly

    # Cache for precomputed BFV: keyed by (nve_id, company, nettnivaa)
    _bfv_cache: dict[tuple, dict[int, dict[str, float]]] = {}

    result_rows: list[dict] = []

    for (nve_id, company, variable, nettnivaa, unit), row in hist_idx.iterrows():
        # Merge parameters for this company
        fus = fusjoner.get(int(nve_id), {}) or {}
        merge_yr: int | None = fus.get("merge_yr") or None
        synergy_frac = float(fus.get("synergy_pct", 0)) / 100
        one_off_val = float(fus.get("one_off", 0))

        # Investment rates (only needed for capital variables)
        inv_dn, inv_rn = None, None

        new_row: dict = {
            "NVE_ID": nve_id,
            "Company": company,
            "Variable": variable,
            "Nettnivaa": nettnivaa,
            "Unit": unit,
        }
        # Copy historical columns
        for y in hist_year_cols:
            new_row[int(y)] = row.get(y)

        # --- Project each forecast year ---
        prev_val = float(row.get(last_hist_yr) or 0)

        for y in fcst_years:
            val: float

            if variable == "O&M costs":
                # 3-yr average of last historical years, CPI-grown, synergy applied
                base_vals = [float(row.get(by) or 0) for by in om_base_years]
                base_avg = sum(base_vals) / len(base_vals) if base_vals else 0.0
                syn = _synergy_factor(merge_yr, synergy_frac, y)
                one_off_t = one_off_val if (merge_yr is not None and y == merge_yr) else 0.0
                val = base_avg * cpi[y] * (1 - syn) + one_off_t

            elif variable in ("Internally funded capital", "Externally funded capital",
                              "Depreciation on internal capital", "Depreciation on external capital"):
                if inv_dn is None:
                    inv_dn, inv_rn = _get_inv_rates(config, int(nve_id), fcst_years)

                bfv_key = (int(nve_id), company, nettnivaa)
                if bfv_key not in _bfv_cache:
                    _bfv_cache[bfv_key] = _precompute_bfv(
                        int(nve_id), company, nettnivaa, inv_dn, inv_rn
                    )

                yr_bfv = _bfv_cache[bfv_key][y]

                if variable == "Internally funded capital":
                    val = yr_bfv["sf"]
                elif variable == "Externally funded capital":
                    val = yr_bfv["gf"]
                elif variable == "Depreciation on internal capital":
                    val = yr_bfv["sf"] * avs_sats
                else:  # Depreciation on external capital
                    val = yr_bfv["gf"] * avs_sats

            elif variable == "CENS cost":
                val = prev_val * (cpi[y] / cpi[y - 1])

            else:
                # Grid loss, RKSU, infrastructure — hold constant
                val = float(row.get(last_hist_yr) or 0)

            new_row[y] = round(val, 2)
            prev_val = val

        result_rows.append(new_row)

    out = pd.DataFrame(result_rows)

    # Sort columns: metadata first, then years in order
    meta_cols = ["NVE_ID", "Company", "Variable", "Nettnivaa", "Unit"]
    year_cols_out = sorted([c for c in out.columns if isinstance(c, int)])
    out = out[meta_cols + year_cols_out]

    # Re-apply row sort
    out["_var_idx"] = out["Variable"].map(_VAR_ORDER).fillna(999)
    out["_net_idx"] = out["Nettnivaa"].map(_NETTNIVAA_ORDER).fillna(9)
    out = (
        out.sort_values(["NVE_ID", "_var_idx", "_net_idx"])
        .drop(columns=["_var_idx", "_net_idx"])
        .reset_index(drop=True)
    )

    return out




if __name__ == "__main__":
    df = rme_table_with_forecast(
        csv_path="Results/Run_2026-04-14_12-27-29/2026-04-14_grunnlagsdata.csv",
        config_path="config.yaml",
        forecast_years=list(range(2025, 2034)),
        company_ids=None,
    )
    df.to_excel("rme_table_forecast.xlsx", index=False)
    print("Written rme_table_forecast.xlsx —", df.shape)
