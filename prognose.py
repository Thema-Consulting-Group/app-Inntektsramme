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
    avs_sats : float
        Depreciation rate (% of BFV, default 4.0).
    labor_share_ld : float
        Labour share of D&V for Distribution (0–1, default 0.30).
    labor_share_rd : float
        Labour share of D&V for Regional (0–1, default 0.30).
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
    ):
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

        self._init_base(base_ir, base_etl)

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

        kp_base = self._get(self.f["kraftpris"], _BASE_YEAR, self.kraftpris_base)

        for i, year in enumerate(FORECAST_YEARS):
            nve_rente = self._get(self.f["nve_rente"], year, 7.0) / 100
            kraftpris = self._get(self.f["kraftpris"], year, 700)

            if i > 0:
                dv_gr = self._get(self.dv_v["dv_ekskl_lonn_pct"], year, 2.5) / 100
                lonn_gr = self._get(self.dv_v["lonn_ekskl_pensjon_pct"], year, 2.5) / 100
                kpi = self._get(self.f["kpi"], year, 2.0) / 100
                inv_ld = self._get(self.inv["dnett_pct"], year, 0) / 100
                inv_rd = self._get(self.inv["rnett_pct"], year, 0) / 100

                ld_dv_mat *= 1 + dv_gr
                ld_dv_lab *= 1 + lonn_gr
                rd_dv_mat *= 1 + dv_gr
                rd_dv_lab *= 1 + lonn_gr

                ld_bfv = ld_bfv * (1 + inv_ld - self.avs_sats_frac)
                rd_bfv = rd_bfv * (1 + inv_rd - self.avs_sats_frac)

                ld_kile *= 1 + kpi
                rd_kile *= 1 + kpi

            ld_dv_t = ld_dv_mat + ld_dv_lab
            rd_dv_t = rd_dv_mat + rd_dv_lab
            ld_akg_t = ld_bfv * 1.01
            rd_akg_t = rd_bfv * 1.01
            ld_avs_t = ld_bfv * self.avs_sats_frac
            rd_avs_t = rd_bfv * self.avs_sats_frac

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

            rows.append({
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
            })

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Grunnlagsdata (long-format table matching online tool)
    # ------------------------------------------------------------------

    def build_grunnlagsdata(self) -> pd.DataFrame:
        fc = self.build_forecast()
        sel = self.selskap

        mapping = [
            ("D&V-kostnader",    "LD D&V",              "Distribusjon", "kkr"),
            ("BFV",              "LD BFV",              "Distribusjon", "kkr"),
            ("AKG",              "LD AKG",              "Distribusjon", "kkr"),
            ("KILE",             "LD KILE",             "Distribusjon", "kkr"),
            ("Avskrivninger",    "LD AVS",              "Distribusjon", "kkr"),
            ("Nettap",           "LD Nettap MWh",       "Distribusjon", "MWh"),
            ("Nettapskostnad",   "LD Nettapskostnad",   "Distribusjon", "kkr"),
            ("Kostnadsgrunnlag", "LD Kostnadsgrunnlag", "Distribusjon", "kkr"),
            ("Kostnadsnorm",     "LD Kostnadsnorm",     "Distribusjon", "kkr"),
            ("D&V-kostnader",    "RD D&V",              "Regional",     "kkr"),
            ("BFV",              "RD BFV",              "Regional",     "kkr"),
            ("AKG",              "RD AKG",              "Regional",     "kkr"),
            ("KILE",             "RD KILE",             "Regional",     "kkr"),
            ("Avskrivninger",    "RD AVS",              "Regional",     "kkr"),
            ("Nettap",           "RD Nettap MWh",       "Regional",     "MWh"),
            ("Nettapskostnad",   "RD Nettapskostnad",   "Regional",     "kkr"),
            ("Kostnadsgrunnlag", "RD Kostnadsgrunnlag", "Regional",     "kkr"),
            ("Kostnadsnorm",     "RD Kostnadsnorm",     "Regional",     "kkr"),
        ]

        rows: list[dict] = []
        for param, col, net, unit in mapping:
            row: dict = {"Selskap": sel, "Parameter": param,
                         "Nettnivå": net, "Enhet": unit}
            for _, r in fc.iterrows():
                row[int(r["År"])] = r[col]
            rows.append(row)

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
