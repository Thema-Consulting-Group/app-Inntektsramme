"""Prognoseberegning for inntektsramme – per nettnivå.

Full revenue cap projection matching NVE's online prognosis tool.
Projects a company's costs and revenue cap 2026–2035 using:
  - KPI and KPI lønn as separate growth drivers
  - Per-network-level cost breakdowns (LD = Distribution, RD = Regional)
  - NVE-rente for capital returns
  - Investment rates per network level
  - Kraftpris for nettap costs

Usage:
    calc = PrognoseCalculator(base_ir, base_etl, forutsetninger, ...)
    forecast_df = calc.build_forecast()
    grunnlag_df = calc.build_grunnlagsdata()
"""

import os
import pandas as pd
import numpy as np

FORECAST_YEARS = list(range(2026, 2036))
_BASE_YEAR = 2026

# ---------------------------------------------------------------------------
# Default assumptions from NVE's online tool (April 2026)
# ---------------------------------------------------------------------------

DEFAULT_FORUTSETNINGER = {
    "kpi": {
        2026: 3.2, 2027: 2.4, 2028: 2.3, 2029: 1.9, 2030: 2.0,
        2031: 2.0, 2032: 2.0, 2033: 2.0, 2034: 2.0, 2035: 2.0,
    },
    "kpi_lonn": {
        2026: 3.6, 2027: 3.0, 2028: 2.85, 2029: 2.55, 2030: 2.57,
        2031: 2.56, 2032: 2.54, 2033: 2.53, 2034: 2.51, 2035: 2.5,
    },
    "nve_rente": {
        2026: 7.53, 2027: 7.48, 2028: 7.32, 2029: 7.27, 2030: 7.24,
        2031: 7.26, 2032: 7.25, 2033: 7.23, 2034: 7.2, 2035: 7.16,
    },
    "kraftpris": {
        2026: 786.0, 2027: 640.0, 2028: 633.0, 2029: 617.0, 2030: 643.0,
        2031: 744.0, 2032: 743.0, 2033: 746.0, 2034: 729.0, 2035: 715.0,
    },
}

DEFAULT_INVESTERINGER = {
    "dnett_pct": {
        2026: 8.5, 2027: 8.5, 2028: 8.4, 2029: 8.3, 2030: 8.1,
        2031: 8.0, 2032: 7.9, 2033: 7.8, 2034: 7.8, 2035: 7.5,
    },
    "rnett_pct": {
        2026: 0.0, 2027: 0.0, 2028: 0.0, 2029: 0.0, 2030: 0.0,
        2031: 0.0, 2032: 0.0, 2033: 0.0, 2034: 0.0, 2035: 0.0,
    },
}

DEFAULT_DV_VEKST = {
    "dv_ekskl_lonn_pct": {
        2026: 6.3, 2027: 3.6, 2028: 2.9, 2029: 2.7, 2030: 2.6,
        2031: 2.6, 2032: 2.6, 2033: 2.6, 2034: 2.6, 2035: 2.6,
    },
    "lonn_ekskl_pensjon_pct": {
        2026: 4.2, 2027: 3.7, 2028: 3.2, 2029: 2.9, 2030: 2.7,
        2031: 2.6, 2032: 2.6, 2033: 2.6, 2034: 2.6, 2035: 2.6,
    },
}

_INV_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Data", "investeringer.csv")
_INV_MODEL_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Data", "investeringer_from_model.csv")


def build_investeringer_from_model(
    grunnlagsdata_csv: str,
    forutsetninger: dict | None = None,
    output_path: str = _INV_MODEL_CSV,
    avs_sats_frac: float = 0.04,
    n_lookback: int = 5,
) -> pd.DataFrame:
    """Compute historical + forecast investments from grunnlagsdata.csv for all companies.

    Historical:  inv_sf_t = (bv.sf_t - bv.sf_{t-1}) + dep.sf_t  (1000 NOK)
    Forecast:    5-yr average bridged to base-year prices via KPI, then grown by KPI each year.

    Output columns: orgn; selskap; nettnivaa; komponent; {hist_inv_years}; avg_5yr; {forecast_years}
    Writes to output_path (semicolon CSV) and returns the DataFrame.
    """
    f = forutsetninger or DEFAULT_FORUTSETNINGER
    kpi_series: dict = f.get("kpi", DEFAULT_FORUTSETNINGER["kpi"])

    try:
        df = pd.read_csv(grunnlagsdata_csv).fillna(0)
    except Exception:
        return pd.DataFrame()

    all_hist_years = sorted(int(y) for y in df["y"].unique())
    # Investment can only be computed from the 2nd year onward (need prior year)
    inv_hist_years = all_hist_years[1:]

    rows = []
    for orgn, comp_df in df.groupby("orgn"):
        comp_name = str(comp_df["comp"].iloc[0]) if "comp" in comp_df.columns else str(orgn)
        comp_years = sorted(int(y) for y in comp_df["y"].unique())

        # Year-on-year investment per sf/gf component
        inv_data: dict[str, dict[int, float]] = {
            "ld_sf": {}, "ld_gf": {}, "rd_sf": {}, "rd_gf": {}
        }
        for idx in range(1, len(comp_years)):
            py, cy = comp_years[idx - 1], comp_years[idx]
            pr = comp_df[comp_df["y"] == py].iloc[0]
            cr = comp_df[comp_df["y"] == cy].iloc[0]

            def _g(r, col: str) -> float:
                return float(r.get(col, 0) or 0)

            inv_data["ld_sf"][cy] = (_g(cr, "ld_bv.sf") - _g(pr, "ld_bv.sf")) + _g(cr, "ld_dep.sf")
            inv_data["ld_gf"][cy] = (_g(cr, "ld_bv.gf") - _g(pr, "ld_bv.gf")) + _g(cr, "ld_dep.gf")
            inv_data["rd_sf"][cy] = (_g(cr, "rd_bv.sf") - _g(pr, "rd_bv.sf")) + _g(cr, "rd_dep.sf")
            inv_data["rd_gf"][cy] = (_g(cr, "rd_bv.gf") - _g(pr, "rd_bv.gf")) + _g(cr, "rd_dep.gf")

        for key in inv_data:
            nettnivaa, komponent = key.split("_")
            vals_map = inv_data[key]
            vals_list = [v for _, v in sorted(vals_map.items())]
            avg_raw = float(np.mean(vals_list[-n_lookback:])) if vals_list else 0.0

            # Forecast starts from last_hist + 1 (includes e.g. 2025 if hist ends at 2024)
            last_hist = max(vals_map.keys()) if vals_map else (_BASE_YEAR - 1)
            end_yr = max(FORECAST_YEARS)
            full_fcst_years = list(range(last_hist + 1, end_yr + 1))

            # Cumulative KPI growth from last_hist — no separate bridge needed
            kpi_cum = 1.0
            fcst: dict[int, float] = {}
            for yr in full_fcst_years:
                kpi_cum *= (1 + float(kpi_series.get(yr, 2.0)) / 100)
                fcst[yr] = round(avg_raw * kpi_cum, 1)

            row: dict = {
                "orgn": int(orgn),
                "selskap": comp_name,
                "nettnivaa": nettnivaa,
                "komponent": komponent,
                "avg_5yr_1000NOK": round(avg_raw, 1),
            }
            for yr in inv_hist_years:
                row[str(yr)] = round(vals_map.get(yr, 0.0), 1)
            for yr in full_fcst_years:
                row[str(yr)] = fcst[yr]

            rows.append(row)

    result_df = pd.DataFrame(rows)
    if output_path and not result_df.empty:
        result_df.to_csv(output_path, index=False, sep=";", encoding="utf-8-sig")
    return result_df


def load_investeringer_for_company(company_id: int, csv_path: str = _INV_CSV) -> dict:
    """Load per-company investment rates (% of BFV) from investeringer.csv.

    Returns a dict matching DEFAULT_INVESTERINGER format:
        {"dnett_pct": {year: value, ...}, "rnett_pct": {year: value, ...}}
    Falls back to DEFAULT_INVESTERINGER for any missing rows/companies.
    """
    result = {
        "dnett_pct": dict(DEFAULT_INVESTERINGER["dnett_pct"]),
        "rnett_pct": dict(DEFAULT_INVESTERINGER["rnett_pct"]),
    }
    if not os.path.exists(csv_path):
        return result
    try:
        df = pd.read_csv(csv_path, sep=";", dtype={"id": int})
        company_rows = df[df["id"] == company_id]
        year_cols = [c for c in df.columns if c.isdigit()]
        for _, row in company_rows.iterrows():
            key = str(row["nettnivaa"])
            if key in result:
                result[key] = {int(y): float(row[y]) for y in year_cols}
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# PrognoseCalculator
# ---------------------------------------------------------------------------

class PrognoseCalculator:
    """Project one company's revenue cap over FORECAST_YEARS.

    Parameters
    ----------
    base_ir : dict
        Row from IR DataFrame for the selected company (per-network detail).
    base_etl : dict
        Row from ETL DataFrame for the selected company (aggregated + DEA norms).
    forutsetninger : dict
        {kpi, kpi_lonn, nve_rente, kraftpris} — each mapping year → value.
        kpi/kpi_lonn/nve_rente in %, kraftpris in kr/MWh.
    investeringer : dict
        {dnett_pct, rnett_pct} — each mapping year → investment rate (% of BFV).
    dv_vekst : dict
        {dv_ekskl_lonn_pct, lonn_ekskl_pensjon_pct} — year → growth (%).
    rho : float
        Efficiency weight (default 0.7).
    grunnlagsdata_csv_path : str | None
        Path to grunnlagsdata.csv from the R pipeline run. When provided,
        sub-components (pension, salary, capitalised salary, sf/gf BFV split,
        infrastructure) are loaded and projected in build_grunnlagsdata().
    avs_sats : float
        Depreciation rate (% of BFV, default 4.0).
    labor_share_ld : float
        Labour share of D&V for Distribution (0–1, default 0.30).
    labor_share_rd : float
        Labour share of D&V for Regional (0–1, default 0.30).
    fusjon : dict | None
        Merger assumptions: {merge_yr, synergy_pct, one_off}.
        merge_yr    : int year the merger takes effect, or None.
        synergy_pct : long-run O&M reduction (%), phased in over 3 years.
        one_off     : one-off O&M addition (1000 NOK) in merge_yr.
        Default: no merger (all zeros).
    """

    def __init__(
        self,
        base_ir: dict,
        base_etl: dict,
        forutsetninger: dict | None = None,
        investeringer: dict | None = None,
        dv_vekst: dict | None = None,
        rho: float = 0.7,
        avs_sats: float = 4.0,
        labor_share_ld: float = 0.30,
        labor_share_rd: float = 0.30,
        fusjon: dict | None = None,
        grunnlagsdata_csv_path: str | None = None,
        use_historical_inv: bool = True,
        edited_inv_nok: dict | None = None,
    ):
        self.use_historical_inv = use_historical_inv
        self.edited_inv_nok = edited_inv_nok or {}  # {inv_sf_ld, inv_gf_ld, inv_sf_rd, inv_gf_rd} → {yr: nok}
        self.f = forutsetninger or DEFAULT_FORUTSETNINGER
        # If no override passed, look up per-company values from investeringer.csv
        if investeringer is None:
            _cid = int(base_etl.get("ID", 0))
            self.inv = load_investeringer_for_company(_cid)
        else:
            self.inv = investeringer
        self.dv_v = dv_vekst or DEFAULT_DV_VEKST
        self.rho = rho
        self.avs_sats_frac = avs_sats / 100.0
        self.labor_ld = labor_share_ld
        self.labor_rd = labor_share_rd

        f = fusjon or {}
        self.merge_yr: int | None = f.get("merge_yr") or None
        self.synergy_frac: float = (f.get("synergy_pct") or 0) / 100.0
        self.one_off: float = float(f.get("one_off") or 0)

        self._init_base(base_ir, base_etl)
        self._init_subcomponents(grunnlagsdata_csv_path, base_etl)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _v(d: dict, key: str, default: float = 0) -> float:
        val = d.get(key, default)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return 0.0
        return float(val)

    @staticmethod
    def _get(series: dict, year: int, default: float) -> float:
        return float(series.get(year, default))

    # ------------------------------------------------------------------
    # Base-year extraction
    # ------------------------------------------------------------------

    def _init_base(self, ir: dict, etl: dict):
        v = self._v

        # LD (Distribution)
        self.ld_dv = v(ir, "Lokalt Årslønnjusterte D&V-kostnader")
        self.ld_avs = v(ir, "Lokalt AVS")
        self.ld_akg = v(ir, "Lokalt AKG inkl 1% arbeids-kapital")
        self.ld_bfv = self.ld_akg / 1.01 if self.ld_akg else 0
        self.ld_kile = v(ir, "Lokalt KILE (fq)")
        self.ld_nl = v(ir, "Lokalt Nettap MWh")
        self.ld_nettap = v(ir, "Lokalt Nettapskostnad")
        self.ld_kg = v(ir, "Lokalt Kostnadsgrunnlag")

        # RD (Regional)
        self.rd_dv = v(ir, "Regionalt Årslønnjusterte D&V-kostnader uten utredningskostnader")
        self.rd_avs = v(ir, "Regionalt AVS")
        self.rd_akg = v(ir, "Regionalt AKG inkl 1% arbeids-kapital")
        self.rd_bfv = self.rd_akg / 1.01 if self.rd_akg else 0
        self.rd_kile = v(ir, "Regionalt KILE (fq)")
        self.rd_nl = v(ir, "Regionalt Nettap MWh")
        self.rd_nettap = v(ir, "Regionalt Nettapskostnad")
        self.rd_kg = v(ir, "Regionalt Kostnadsgrunnlag ")  # trailing space in model

        # DEA norms (from ETL)
        self.k_ld = v(etl, "K* lok distribusjonsnett")
        self.k_rd = v(etl, "K* reg distribusjonsnett")  # includes nettap
        self.total_kg = v(etl, "Kostnadsgrunnlag")
        self.total_ir = v(etl, "Inntektsramme etter kalibrering")
        self.kraftpris_base = v(etl, "Kraftpris kr/MWh") or 500
        self.kundetillegg = v(etl, "Tillegg i kostnadsnorm for kundevekst")
        self.selskap = etl.get("Selskap", "")

        # Base-year DEA efficiencies (constant through projection)
        self.eff_ld = self.k_ld / self.ld_kg if self.ld_kg else 1.0
        k_rd_excl = max(self.k_rd - self.rd_nettap, 0)
        self.eff_rd = k_rd_excl / self.rd_kg if self.rd_kg else 1.0

        # D&V material / labour split
        self.ld_dv_mat0 = self.ld_dv * (1 - self.labor_ld)
        self.ld_dv_lab0 = self.ld_dv * self.labor_ld
        self.rd_dv_mat0 = self.rd_dv * (1 - self.labor_rd)
        self.rd_dv_lab0 = self.rd_dv * self.labor_rd

    # ------------------------------------------------------------------
    # Sub-component extraction from grunnlagsdata.csv
    # ------------------------------------------------------------------

    def _init_subcomponents(self, csv_path: str | None, etl: dict):
        """Load granular sub-components from grunnlagsdata.csv (base year).

        Extracts per-company values for the DEA base year (latest year in CSV,
        typically y.cb = 2024) including:
          - Pension, salary, capitalised salary (for D&V breakdown)
          - BFV sf/gf split and depreciation sf/gf
          - Infrastructure variables (held constant in forecast)
        """
        v = self._v
        self._has_subcomponents = False

        # Defaults: derive from aggregated values
        self.ld_bfv_sf0 = self.ld_bfv
        self.ld_bfv_gf0 = 0.0
        self.rd_bfv_sf0 = self.rd_bfv
        self.rd_bfv_gf0 = 0.0
        self.ld_sf_ratio = 1.0
        self.rd_sf_ratio = 1.0

        # D&V sub-component defaults (pension/salary not split out)
        self.ld_pens0 = 0.0
        self.ld_sal0 = 0.0
        self.ld_sal_cap0 = 0.0
        self.ld_pens_eq0 = 0.0
        self.ld_impl0 = 0.0
        self.rd_pens0 = 0.0
        self.rd_sal0 = 0.0
        self.rd_sal_cap0 = 0.0
        self.rd_pens_eq0 = 0.0
        self.rd_impl0 = 0.0
        self.rd_utred0 = 0.0

        # Infrastructure defaults
        self.ld_hv0 = 0.0
        self.ld_ss0 = 0.0
        self.ld_sub0 = 0.0
        self.rd_wv_ol0 = 0.0
        self.rd_wv_uc0 = 0.0
        self.rd_wv_sc0 = 0.0
        self.rd_wv_ss0 = 0.0

        # Historical investment defaults (populated when grunnlagsdata is available)
        self._has_investment_history = False
        self.avg_inv_sf_ld = 0.0
        self.avg_inv_gf_ld = 0.0
        self.avg_inv_sf_rd = 0.0
        self.avg_inv_gf_rd = 0.0
        self.last_hist_year = _BASE_YEAR - 1

        if csv_path is None or not os.path.exists(csv_path):
            return

        try:
            df = pd.read_csv(csv_path).fillna(0)
        except Exception:
            return

        # Find company rows using orgn from etl
        orgn = int(etl.get("Org.nr", etl.get("orgn", 0)))
        if orgn == 0:
            return

        comp_df = df[df["orgn"] == orgn]
        if comp_df.empty:
            return

        # Use the latest year (DEA base year)
        base_yr = int(comp_df["y"].max())
        row = comp_df[comp_df["y"] == base_yr].iloc[0]

        def _g(col: str) -> float:
            return float(row.get(col, 0) or 0)

        self._has_subcomponents = True

        # BFV sf/gf split
        self.ld_bfv_sf0 = _g("ld_bv.sf")
        self.ld_bfv_gf0 = _g("ld_bv.gf")
        ld_bfv_total = self.ld_bfv_sf0 + self.ld_bfv_gf0
        self.ld_sf_ratio = self.ld_bfv_sf0 / ld_bfv_total if ld_bfv_total > 0 else 1.0

        self.rd_bfv_sf0 = _g("rd_bv.sf")
        self.rd_bfv_gf0 = _g("rd_bv.gf")
        rd_bfv_total = self.rd_bfv_sf0 + self.rd_bfv_gf0
        self.rd_sf_ratio = self.rd_bfv_sf0 / rd_bfv_total if rd_bfv_total > 0 else 1.0

        # D&V sub-components (nominal, base year)
        self.ld_pens0 = _g("ld_pens")
        self.ld_sal0 = _g("ld_sal")
        self.ld_sal_cap0 = _g("ld_sal.cap")
        self.ld_pens_eq0 = _g("ld_pens.eq")
        self.ld_impl0 = _g("ld_impl")
        self.rd_pens0 = _g("rd_pens")
        self.rd_sal0 = _g("rd_sal")
        self.rd_sal_cap0 = _g("rd_sal.cap")
        self.rd_pens_eq0 = _g("rd_pens.eq")
        self.rd_impl0 = _g("rd_impl")
        self.rd_utred0 = _g("rd_coord")

        # Infrastructure (held constant)
        self.ld_hv0 = _g("ld_hv")
        self.ld_ss0 = _g("ld_ss")
        self.ld_sub0 = _g("ld_sub")
        self.rd_wv_ol0 = _g("rd_wv.ol")
        self.rd_wv_uc0 = _g("rd_wv.uc")
        self.rd_wv_sc0 = _g("rd_wv.sc")
        self.rd_wv_ss0 = _g("rd_wv.ss")

        # Historical investment: avg of last 5 years (1000 NOK) per sf/gf split
        # Formula: inv_t = (bv_t - bv_{t-1}) + dep_t
        self.last_hist_year = base_yr
        all_years = sorted(comp_df["y"].unique())
        lookback = all_years[-6:]  # up to 6 years → up to 5 investment observations

        def _g2(r, col: str) -> float:
            return float(r.get(col, 0) or 0)

        _inv_sf_ld: list[float] = []
        _inv_gf_ld: list[float] = []
        _inv_sf_rd: list[float] = []
        _inv_gf_rd: list[float] = []

        for _idx in range(1, len(lookback)):
            _py, _cy = lookback[_idx - 1], lookback[_idx]
            _pr = comp_df[comp_df["y"] == _py].iloc[0]
            _cr = comp_df[comp_df["y"] == _cy].iloc[0]
            _inv_sf_ld.append((_g2(_cr, "ld_bv.sf") - _g2(_pr, "ld_bv.sf")) + _g2(_cr, "ld_dep.sf"))
            _inv_gf_ld.append((_g2(_cr, "ld_bv.gf") - _g2(_pr, "ld_bv.gf")) + _g2(_cr, "ld_dep.gf"))
            _inv_sf_rd.append((_g2(_cr, "rd_bv.sf") - _g2(_pr, "rd_bv.sf")) + _g2(_cr, "rd_dep.sf"))
            _inv_gf_rd.append((_g2(_cr, "rd_bv.gf") - _g2(_pr, "rd_bv.gf")) + _g2(_cr, "rd_dep.gf"))

        if _inv_sf_ld:
            self._has_investment_history = True
            self.avg_inv_sf_ld = float(np.mean(_inv_sf_ld[-5:]))
            self.avg_inv_gf_ld = float(np.mean(_inv_gf_ld[-5:]))
            self.avg_inv_sf_rd = float(np.mean(_inv_sf_rd[-5:]))
            self.avg_inv_gf_rd = float(np.mean(_inv_gf_rd[-5:]))

    # ------------------------------------------------------------------
    # Merger synergy
    # ------------------------------------------------------------------

    def _synergy_factor(self, year: int) -> float:
        """Return the fraction of synergy_frac to apply in this year.

        Phase-in schedule (matches the Excel model):
          merge_yr + 1 → 1/3 of synergy
          merge_yr + 2 → 1/2 of synergy
          merge_yr + 3+ → full synergy
          merge_yr or before → 0
        """
        if self.merge_yr is None or self.synergy_frac == 0:
            return 0.0
        diff = year - self.merge_yr
        if diff <= 0:
            return 0.0
        elif diff == 1:
            return self.synergy_frac / 3
        elif diff == 2:
            return self.synergy_frac / 2
        else:
            return self.synergy_frac

    # ------------------------------------------------------------------
    # Main projection
    # ------------------------------------------------------------------

    def build_forecast(self) -> pd.DataFrame:
        rows: list[dict] = []

        ld_dv_mat = self.ld_dv_mat0
        ld_dv_lab = self.ld_dv_lab0
        rd_dv_mat = self.rd_dv_mat0
        rd_dv_lab = self.rd_dv_lab0
        ld_bfv = self.ld_bfv
        rd_bfv = self.rd_bfv
        ld_kile = self.ld_kile
        rd_kile = self.rd_kile

        # Absolute investment mode: track sf/gf BFV separately
        _ld_bfv_sf = self.ld_bfv_sf0
        _ld_bfv_gf = self.ld_bfv_gf0
        _rd_bfv_sf = self.rd_bfv_sf0
        _rd_bfv_gf = self.rd_bfv_gf0

        # KPI bridge: bring avg investment from last_hist_year to _BASE_YEAR price level
        _default_kpi = self._get(self.f["kpi"], _BASE_YEAR, 2.0)
        _inv_kpi_bridge = 1.0
        for _yr in range(self.last_hist_year + 1, _BASE_YEAR + 1):
            _inv_kpi_bridge *= (1 + self._get(self.f["kpi"], _yr, _default_kpi) / 100)
        _inv_sf_ld_base = self.avg_inv_sf_ld * _inv_kpi_bridge
        _inv_gf_ld_base = self.avg_inv_gf_ld * _inv_kpi_bridge
        _inv_sf_rd_base = self.avg_inv_sf_rd * _inv_kpi_bridge
        _inv_gf_rd_base = self.avg_inv_gf_rd * _inv_kpi_bridge
        _inv_kpi_cum = 1.0  # accumulates KPI growth beyond _BASE_YEAR

        # Sub-component tracking (grown in parallel with mat/lab)
        ld_pens = self.ld_pens0
        ld_sal = self.ld_sal0
        ld_sal_cap = self.ld_sal_cap0
        ld_pens_eq = self.ld_pens_eq0
        ld_impl = self.ld_impl0
        rd_pens = self.rd_pens0
        rd_sal = self.rd_sal0
        rd_sal_cap = self.rd_sal_cap0
        rd_pens_eq = self.rd_pens_eq0
        rd_impl = self.rd_impl0
        rd_utred = self.rd_utred0

        kp_base = self._get(self.f["kraftpris"], _BASE_YEAR, self.kraftpris_base)

        for i, year in enumerate(FORECAST_YEARS):
            nve_rente = self._get(self.f["nve_rente"], year, 7.0) / 100
            kraftpris = self._get(self.f["kraftpris"], year, 700)

            if i > 0:
                dv_gr = self._get(self.dv_v["dv_ekskl_lonn_pct"], year, 2.5) / 100
                lonn_gr = self._get(self.dv_v["lonn_ekskl_pensjon_pct"], year, 2.5) / 100
                kpi = self._get(self.f["kpi"], year, 2.0) / 100

                ld_dv_mat *= 1 + dv_gr
                ld_dv_lab *= 1 + lonn_gr
                rd_dv_mat *= 1 + dv_gr
                rd_dv_lab *= 1 + lonn_gr

                # Sub-components: pension/impl grow with dv_gr, salary with lonn_gr
                ld_pens *= 1 + dv_gr
                ld_pens_eq *= 1 + dv_gr
                ld_impl *= 1 + dv_gr
                ld_sal *= 1 + lonn_gr
                ld_sal_cap *= 1 + lonn_gr
                rd_pens *= 1 + dv_gr
                rd_pens_eq *= 1 + dv_gr
                rd_impl *= 1 + dv_gr
                rd_sal *= 1 + lonn_gr
                rd_sal_cap *= 1 + lonn_gr
                rd_utred *= 1 + dv_gr

                # BFV: edited investments (absolute NOK) → historical avg (KPI-grown) → fallback % of BFV
                _inv_kpi_cum *= (1 + kpi)
                if self.edited_inv_nok:
                    # User has edited investments in absolute NOK — use those directly
                    _ld_inv_sf = self.edited_inv_nok.get("inv_sf_ld", {}).get(year, 0)
                    _ld_inv_gf = self.edited_inv_nok.get("inv_gf_ld", {}).get(year, 0)
                    _rd_inv_sf = self.edited_inv_nok.get("inv_sf_rd", {}).get(year, 0)
                    _rd_inv_gf = self.edited_inv_nok.get("inv_gf_rd", {}).get(year, 0)
                    _ld_bfv_sf = _ld_bfv_sf + _ld_inv_sf - _ld_bfv_sf * self.avs_sats_frac
                    _ld_bfv_gf = _ld_bfv_gf + _ld_inv_gf - _ld_bfv_gf * self.avs_sats_frac
                    _rd_bfv_sf = _rd_bfv_sf + _rd_inv_sf - _rd_bfv_sf * self.avs_sats_frac
                    _rd_bfv_gf = _rd_bfv_gf + _rd_inv_gf - _rd_bfv_gf * self.avs_sats_frac
                    ld_bfv = _ld_bfv_sf + _ld_bfv_gf
                    rd_bfv = _rd_bfv_sf + _rd_bfv_gf
                elif self.use_historical_inv and self._has_investment_history:
                    _ld_inv_sf = _inv_sf_ld_base * _inv_kpi_cum
                    _ld_inv_gf = _inv_gf_ld_base * _inv_kpi_cum
                    _rd_inv_sf = _inv_sf_rd_base * _inv_kpi_cum
                    _rd_inv_gf = _inv_gf_rd_base * _inv_kpi_cum
                    _ld_bfv_sf = _ld_bfv_sf + _ld_inv_sf - _ld_bfv_sf * self.avs_sats_frac
                    _ld_bfv_gf = _ld_bfv_gf + _ld_inv_gf - _ld_bfv_gf * self.avs_sats_frac
                    _rd_bfv_sf = _rd_bfv_sf + _rd_inv_sf - _rd_bfv_sf * self.avs_sats_frac
                    _rd_bfv_gf = _rd_bfv_gf + _rd_inv_gf - _rd_bfv_gf * self.avs_sats_frac
                    ld_bfv = _ld_bfv_sf + _ld_bfv_gf
                    rd_bfv = _rd_bfv_sf + _rd_bfv_gf
                else:
                    inv_ld = self._get(self.inv["dnett_pct"], year, 0) / 100
                    inv_rd = self._get(self.inv["rnett_pct"], year, 0) / 100
                    ld_bfv = ld_bfv * (1 + inv_ld - self.avs_sats_frac)
                    rd_bfv = rd_bfv * (1 + inv_rd - self.avs_sats_frac)

                ld_kile *= 1 + kpi
                rd_kile *= 1 + kpi

            ld_dv_t = ld_dv_mat + ld_dv_lab
            rd_dv_t = rd_dv_mat + rd_dv_lab

            # Merger: synergy reduction + one-off cost in merge_yr
            syn = self._synergy_factor(year)
            one_off_t = self.one_off if (self.merge_yr is not None and year == self.merge_yr) else 0.0
            ld_dv_t = ld_dv_t * (1 - syn) + one_off_t
            rd_dv_t = rd_dv_t * (1 - syn)
            ld_akg_t = ld_bfv * 1.01
            rd_akg_t = rd_bfv * 1.01
            ld_avs_t = ld_bfv * self.avs_sats_frac
            rd_avs_t = rd_bfv * self.avs_sats_frac

            # BFV sf/gf split
            if self.use_historical_inv and self._has_investment_history:
                ld_bfv_sf = _ld_bfv_sf
                ld_bfv_gf = _ld_bfv_gf
                rd_bfv_sf = _rd_bfv_sf
                rd_bfv_gf = _rd_bfv_gf
            else:
                ld_bfv_sf = ld_bfv * self.ld_sf_ratio
                ld_bfv_gf = ld_bfv * (1 - self.ld_sf_ratio)
                rd_bfv_sf = rd_bfv * self.rd_sf_ratio
                rd_bfv_gf = rd_bfv * (1 - self.rd_sf_ratio)
            ld_avs_sf = ld_bfv_sf * self.avs_sats_frac
            ld_avs_gf = ld_bfv_gf * self.avs_sats_frac
            rd_avs_sf = rd_bfv_sf * self.avs_sats_frac
            rd_avs_gf = rd_bfv_gf * self.avs_sats_frac

            kp_ratio = kraftpris / kp_base if kp_base else 1
            ld_nettap_t = self.ld_nettap * kp_ratio
            rd_nettap_t = self.rd_nettap * kp_ratio

            ld_kg_t = ld_dv_t + ld_avs_t + ld_nettap_t + ld_kile + ld_akg_t * nve_rente
            rd_kg_t = rd_dv_t + rd_avs_t + rd_nettap_t + rd_kile + rd_akg_t * nve_rente
            total_kg_t = ld_kg_t + rd_kg_t

            k_ld_t = self.eff_ld * ld_kg_t
            k_rd_excl = self.eff_rd * (rd_kg_t - rd_nettap_t)
            k_rd_t = k_rd_excl + rd_nettap_t

            # Base year (2026): use the actual calibrated inntektsramme from the model
            if i == 0:
                ir_t = self.total_ir
            else:
                ir_t = (1 - self.rho) * total_kg_t + self.rho * (k_ld_t + k_rd_t)

            eff_ld_pct = (k_ld_t / ld_kg_t * 100) if ld_kg_t else 0
            eff_rd_pct = (k_rd_t / rd_kg_t * 100) if rd_kg_t else 0
            eff_w_pct = ((k_ld_t + k_rd_t) / total_kg_t * 100) if total_kg_t else 0

            total_akg = ld_akg_t + rd_akg_t
            non_capital = (ld_dv_t + rd_dv_t + ld_avs_t + rd_avs_t
                           + ld_nettap_t + rd_nettap_t + ld_kile + rd_kile)
            avkastning_pct = ((ir_t - non_capital) / total_akg * 100) if total_akg else 0

            driftsresultat = ir_t - total_kg_t
            rammevilkar_pct = (driftsresultat / total_kg_t * 100) if total_kg_t else 0

            row_data = {
                "År": year,
                "KPI %": round(self._get(self.f["kpi"], year, 2.0), 2),
                "KPI lønn %": round(self._get(self.f["kpi_lonn"], year, 2.5), 2),
                "NVE-rente %": round(nve_rente * 100, 2),
                "Kraftpris kr/MWh": round(kraftpris, 1),
                "LD D&V": round(ld_dv_t),
                "LD AVS": round(ld_avs_t),
                "LD BFV": round(ld_bfv),
                "LD AKG": round(ld_akg_t),
                "LD KILE": round(ld_kile),
                "LD Nettap MWh": round(self.ld_nl),
                "LD Nettapskostnad": round(ld_nettap_t),
                "LD Kostnadsgrunnlag": round(ld_kg_t),
                "LD Kostnadsnorm": round(k_ld_t),
                "RD D&V": round(rd_dv_t),
                "RD AVS": round(rd_avs_t),
                "RD BFV": round(rd_bfv),
                "RD AKG": round(rd_akg_t),
                "RD KILE": round(rd_kile),
                "RD Nettap MWh": round(self.rd_nl),
                "RD Nettapskostnad": round(rd_nettap_t),
                "RD Kostnadsgrunnlag": round(rd_kg_t),
                "RD Kostnadsnorm": round(k_rd_t),
                "Kostnadsgrunnlag": round(total_kg_t),
                "Kostnadsnorm": round(k_ld_t + k_rd_t),
                "Inntektsramme": round(ir_t),
                "Driftsresultat": round(driftsresultat),
                "Rammevilkårsjustering %": round(rammevilkar_pct, 2),
                "Effektivitet Dnett %": round(eff_ld_pct, 2),
                "Effektivitet Rnett %": round(eff_rd_pct, 2),
                "Effektivitet vektet %": round(eff_w_pct, 2),
                "Avkastning NVE %": round(avkastning_pct, 2),
                # Sub-components (granular Grunnlagsdata rows)
                "LD D&V ekskl. lønn": round(ld_dv_mat * (1 - syn)),
                "LD Lønnskost. ekskl. pensjon": round(ld_sal * (1 - syn)),
                "LD Aktiverte lønnskost.": round(ld_sal_cap * (1 - syn)),
                "LD Pensjonskost. periodisert": round(ld_pens * (1 - syn)),
                "LD Pensjonkost. ført mot egenkapital: impl": round(ld_impl * (1 - syn)),
                "LD Pensjonkost. ført mot egenkapital: estimatavvik": round(ld_pens_eq * (1 - syn)),
                "LD Andre driftsinntekter": 0,
                "LD BFV sf": round(ld_bfv_sf),
                "LD BFV gf": round(ld_bfv_gf),
                "LD AVS sf": round(ld_avs_sf, 1),
                "LD AVS gf": round(ld_avs_gf, 1),
                "LD Høyspentnett km": round(self.ld_hv0, 2),
                "LD Nettstasjoner": round(self.ld_ss0, 2),
                "LD Nettkunder": round(self.ld_sub0),
                "RD D&V ekskl. lønn": round(rd_dv_mat * (1 - syn)),
                "RD Lønnskost. ekskl. pensjon": round(rd_sal * (1 - syn)),
                "RD Aktiverte lønnskost.": round(rd_sal_cap * (1 - syn)),
                "RD Pensjonskost. periodisert": round(rd_pens * (1 - syn)),
                "RD Pensjonkost. ført mot egenkapital: impl": round(rd_impl * (1 - syn)),
                "RD Pensjonkost. ført mot egenkapital: estimatavvik": round(rd_pens_eq * (1 - syn)),
                "RD Andre driftsinntekter": 0,
                "RD Utredningskostnader": round(rd_utred * (1 - syn)),
                "RD BFV sf": round(rd_bfv_sf),
                "RD BFV gf": round(rd_bfv_gf),
                "RD AVS sf": round(rd_avs_sf, 1),
                "RD AVS gf": round(rd_avs_gf, 1),
                "RD Vekt luftlinjer": round(self.rd_wv_ol0, 1),
                "RD Vekt jordkabler": round(self.rd_wv_uc0, 2),
                "RD Vekt sjøkabler": round(self.rd_wv_sc0, 1),
                "RD Vekt stasjonsvariabel": round(self.rd_wv_ss0, 1),
            }
            rows.append(row_data)

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Grunnlagsdata (long-format table matching online tool)
    # ------------------------------------------------------------------

    def build_grunnlagsdata(self) -> pd.DataFrame:
        fc = self.build_forecast()
        sel = self.selskap

        # Granular mapping matching the existing app's Grunnlagsdata view.
        # Each tuple: (display_name, forecast_col, nettnivaa, unit)
        mapping = [
            # --- Distribusjon ---
            ("Andre driftsinntekter",                    "LD Andre driftsinntekter",                    "Distribusjon", "kkr"),
            ("D&V-kost. ekskl. lønn",                   "LD D&V ekskl. lønn",                         "Distribusjon", "kkr"),
            ("Bokførte verdier kundefinansiert",         "LD BFV gf",                                  "Distribusjon", "kkr"),
            ("Bokførte verdier egenfinansiert",          "LD BFV sf",                                  "Distribusjon", "kkr"),
            ("KILE",                                     "LD KILE",                                    "Distribusjon", "kkr"),
            ("Avskrivninger kundefinansiert",            "LD AVS gf",                                  "Distribusjon", "kkr"),
            ("Avskrivninger egenfinansiert",             "LD AVS sf",                                  "Distribusjon", "kkr"),
            ("Høyspentnett",                             "LD Høyspentnett km",                         "Distribusjon", "km"),
            ("Pensjonkost. ført mot egenkapital: impl",  "LD Pensjonkost. ført mot egenkapital: impl", "Distribusjon", "kkr"),
            ("Nettap",                                   "LD Nettap MWh",                              "Distribusjon", "MWh"),
            ("Pensjonskost. periodisert",                "LD Pensjonskost. periodisert",               "Distribusjon", "kkr"),
            ("Pensjonkost. ført mot egenkapital: estimatavvik", "LD Pensjonkost. ført mot egenkapital: estimatavvik", "Distribusjon", "kkr"),
            ("Lønnskost. ekskl. pensjon",                "LD Lønnskost. ekskl. pensjon",               "Distribusjon", "kkr"),
            ("Aktiverte lønnskost.",                      "LD Aktiverte lønnskost.",                    "Distribusjon", "kkr"),
            ("Nettstasjoner",                            "LD Nettstasjoner",                           "Distribusjon", "stk"),
            ("Nettkunder",                               "LD Nettkunder",                              "Distribusjon", "stk"),
            # --- Regional ---
            ("Andre driftsinntekter",                    "RD Andre driftsinntekter",                   "Regional",     "kkr"),
            ("D&V-kost. ekskl. lønn",                   "RD D&V ekskl. lønn",                         "Regional",     "kkr"),
            ("Bokførte verdier kundefinansiert",         "RD BFV gf",                                  "Regional",     "kkr"),
            ("Bokførte verdier egenfinansiert",          "RD BFV sf",                                  "Regional",     "kkr"),
            ("KILE",                                     "RD KILE",                                    "Regional",     "kkr"),
            ("Utredningskostnader",                      "RD Utredningskostnader",                     "Regional",     "kkr"),
            ("Avskrivninger kundefinansiert",            "RD AVS gf",                                  "Regional",     "kkr"),
            ("Avskrivninger egenfinansiert",             "RD AVS sf",                                  "Regional",     "kkr"),
            ("Pensjonkost. ført mot egenkapital: impl",  "RD Pensjonkost. ført mot egenkapital: impl", "Regional",     "kkr"),
            ("Nettap",                                   "RD Nettap MWh",                              "Regional",     "MWh"),
            ("Pensjonskost. periodisert",                "RD Pensjonskost. periodisert",               "Regional",     "kkr"),
            ("Pensjonkost. ført mot egenkapital: estimatavvik", "RD Pensjonkost. ført mot egenkapital: estimatavvik", "Regional", "kkr"),
            ("Lønnskost. ekskl. pensjon",                "RD Lønnskost. ekskl. pensjon",               "Regional",     "kkr"),
            ("Aktiverte lønnskost.",                      "RD Aktiverte lønnskost.",                    "Regional",     "kkr"),
            ("Vekt luftlinjer",                          "RD Vekt luftlinjer",                         "Regional",     ""),
            ("Vekt sjøkabler",                           "RD Vekt sjøkabler",                          "Regional",     ""),
            ("Vekt stasjonsvariabel",                    "RD Vekt stasjonsvariabel",                   "Regional",     ""),
            ("Vekt jordkabler",                          "RD Vekt jordkabler",                         "Regional",     ""),
        ]

        rows: list[dict] = []
        for param, col, net, unit in mapping:
            row: dict = {"Selskap": sel, "Parameter": param,
                         "Nettnivå": net, "Enhet": unit}
            for _, r in fc.iterrows():
                row[int(r["År"])] = r.get(col, 0)
            rows.append(row)

        # Samlet (aggregated) rows
        for param, col, unit in [
            ("Kostnadsgrunnlag", "Kostnadsgrunnlag", "kkr"),
            ("Kostnadsnorm",     "Kostnadsnorm",     "kkr"),
            ("Inntektsramme",    "Inntektsramme",    "kkr"),
            ("Driftsresultat",   "Driftsresultat",   "kkr"),
        ]:
            row = {"Selskap": sel, "Parameter": param,
                   "Nettnivå": "Samlet", "Enhet": unit}
            for _, r in fc.iterrows():
                row[int(r["År"])] = r[col]
            rows.append(row)

        return pd.DataFrame(rows)
