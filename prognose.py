"""Prognoseberegning for inntektsramme – enkeltselskap.

Projiserer ett selskaps kostnadsgrunnlag og inntektsramme fremover
basert på bruker-angitte forutsetninger (prognose-seksjonen i config.yaml).

Forutsetninger:
- DEA-effektivitetsscore holdes konstant (ny kapital påvirker kostnadsgrunnlag,
  ikke effektivitetsscoren – "påvirker oppgaver men ikke effektivitet").
- IR/KG-ratioen fra basisåret brukes til å bestemme IR fra fremtidig KG.
- KILE holdes konstant på KPI-justert basisnivå.
- Alle beløp er i kkr (samme enhet som modellen).
"""

import pandas as pd

FORECAST_YEARS = [2026, 2027, 2028, 2029, 2030, 2031]
_BASE_YEAR = 2026


class PrognoseCalculator:
    """
    Projiserer inntektsramme for ett selskap over FORECAST_YEARS.

    Parameters
    ----------
    base_row : dict
        Rad fra ETL-dataframe for valgt selskap (inkl. "Kraftpris kr/MWh").
        Verdier er i kkr.
    params : dict
        config.yaml["prognose"] – brukervalgte prognose-forutsetninger.
    referanserente_base : float
        Fallback-referanserente (desimalform, f.eks. 0.072) brukt når
        ingen per-år-override er satt i params.
    """

    def __init__(self, base_row: dict, params: dict, referanserente_base: float):
        self.base = base_row
        self.p = params
        self.rho = params.get("rho", 0.7)
        self.ref_base = referanserente_base

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _kumulativ_inflasjon(self, year: int) -> float:
        """Cumulative inflation multiplier from base year 2026 to *year*."""
        inf_map = self.p.get("forutsetninger", {}).get("inflasjon_per_year", {})
        factor = 1.0
        for y in range(_BASE_YEAR + 1, year + 1):
            # Stored as percent (e.g. 2.5), so divide by 100
            factor *= 1.0 + inf_map.get(y, 2.5) / 100.0
        return factor

    def _synergy_factor(self, year: int) -> float:
        """DV cost-reduction fraction for the given year (linear phase-in)."""
        syn = self.p.get("synergi", {})
        if not syn.get("enabled", False):
            return 0.0
        max_frac = syn.get("kostnadsreduksjon_pst", 0.0) / 100.0
        start = syn.get("synergistart_aar", 9999)
        full = syn.get("full_synergi_aar", 9999)
        slutt = syn.get("synergiperiode_slutt", 9999)
        if year < start or year > slutt:
            return 0.0
        if year >= full:
            return max_frac
        span = max(full - start, 1)
        return max_frac * (year - start + 1) / span

    def _merger_cost(self, year: int, base_dv: float) -> float:
        """One-time restructuring cost (kkr) charged in fusjonsår."""
        fus = self.p.get("fusjon", {})
        if not fus.get("enabled", False) or year != fus.get("fusjonsaar"):
            return 0.0
        fast = fus.get("omstillingskostnad_fast_kkr", 0.0)
        variabel = base_dv * fus.get("omstillingskostnad_variabel_pst", 0.0) / 100.0
        return fast + variabel

    def _referanserente(self, year: int) -> float:
        """Referanserente for år (desimalform, f.eks. 0.072)."""
        rates = self.p.get("forutsetninger", {}).get("referanserente_per_year", {})
        val = rates.get(year)
        # Stored as percent (e.g. 7.2) → convert to fraction
        return (val / 100.0) if val is not None else self.ref_base

    def _kraftpris(self, year: int) -> float:
        """Kraftpris (kr/MWh) for år – brukes til nettapskostnad."""
        priser = self.p.get("forutsetninger", {}).get("kraftpris_per_year", {})
        return float(priser.get(year, self.base.get("Kraftpris kr/MWh", 500.0)))

    # ------------------------------------------------------------------
    # Main projection
    # ------------------------------------------------------------------

    def build_forecast(self) -> pd.DataFrame:
        """Return a DataFrame with one row per FORECAST_YEAR."""
        base_dv   = float(self.base.get("D&V-kostnader eks utredningskostnader", 0) or 0)
        base_avs  = float(self.base.get("AVS", 0) or 0)
        base_akg  = float(self.base.get("AKG (inkl 1 % arbeids-kapital)", 0) or 0)
        base_kile = float(self.base.get("KPI-justert KILE", 0) or 0)
        ld_nl     = float(self.base.get("Nettap MWh i LD", 0) or 0)
        rd_nl     = float(self.base.get("Nettap MWh i RD", 0) or 0)
        base_kg   = float(self.base.get("Kostnadsgrunnlag", 0) or 0)
        base_ir   = float(self.base.get("Inntektsramme etter kalibrering", 0) or 0)

        # DEA-effektivitet + kalibrering fanges av IR/KG-ratioen – holdes konstant
        ir_kg_ratio = (base_ir / base_kg) if base_kg else 1.0

        inv = self.p.get("investeringer", {})
        avs_sats = inv.get("avskrivningssats_pst", 4.0) / 100.0
        om_adj   = self.p.get("om_justering_pst", 0.0) / 100.0

        # Akkumulert netto nytt avkastningsgrunnlag fra prognoseinvesteringer
        extra_rab = 0.0
        rows = []

        for year in FORECAST_YEARS:
            ny_inv    = float(inv.get("nyinvesteringer_per_year",    {}).get(year, 0) or 0)
            reinv     = float(inv.get("reinvesteringer_per_year",    {}).get(year, 0) or 0)
            kunde_inv = float(inv.get("kundeinvesteringer_per_year", {}).get(year, 0) or 0)
            total_inv = ny_inv + reinv + kunde_inv

            # Avskrivning på akkumulert nytt RAB (begynnelse-av-år-konvensjon)
            dep_on_extra = extra_rab * avs_sats
            extra_rab    = extra_rab + total_inv - dep_on_extra

            avs_t = base_avs + dep_on_extra
            akg_t = base_akg + extra_rab * 1.01   # arbeidskapitalfaktor

            ref_t  = self._referanserente(year)
            inf_f  = self._kumulativ_inflasjon(year)
            syn_r  = self._synergy_factor(year)
            m_cost = self._merger_cost(year, base_dv)

            # DV: inflasjonsjustert + O&M-justering − synergibesparelse + fusjonskostnad
            dv_t     = base_dv * inf_f * (1 + om_adj) * (1 - syn_r) + m_cost
            nettap_t = (ld_nl + rd_nl) * self._kraftpris(year)
            kile_t   = base_kile

            kg_t = dv_t + avs_t + nettap_t + kile_t + akg_t * ref_t
            ir_t = kg_t * ir_kg_ratio

            rows.append({
                "År":                       year,
                "DV-kostnader":             round(dv_t),
                "Avskrivninger":            round(avs_t),
                "Avkastningsgrunnlag":      round(akg_t),
                "Nettapskostnad":           round(nettap_t),
                "KILE":                     round(kile_t),
                "Kostnadsgrunnlag":         round(kg_t),
                "Inntektsramme (prognose)": round(ir_t),
                "Referanserente %":         round(ref_t * 100, 2),
                "Kraftpris kr/MWh":         round(self._kraftpris(year), 1),
                "Synergieffekt % av DV":    round(self._synergy_factor(year) * 100, 2),
                "Fusjonskostnad":           round(m_cost),
            })

        return pd.DataFrame(rows)
