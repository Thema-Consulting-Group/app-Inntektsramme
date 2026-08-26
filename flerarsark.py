"""Flerårig inntektsrammeark — projeksjon av inntektsrammearket, ett ark per år.

Bygger på de eksisterende byggeklossene:

  * ``inntektsramme.RevenueCapCalculator`` gir basisåret (2026) — kostnadsgrunnlag,
    DEA-resultater og kalibrert inntektsramme for alle selskaper.
  * ``prognose.PrognoseCalculator`` framskriver ett selskap per nettnivå (LD/RD).
  * ``inntektsramme.DEANorm`` gjenbrukes *per prognoseår* slik at normberegningen
    (DEAnorm + tillegg i norm fordelt etter RAB-andel) blir identisk med basisårets.

Hovedpoenget med modulen er at kalibreringen i inntektsrammearket er en
*bransjeoperasjon*: både tillegg i norm og kalibreringsleddet
``AKG * (N100 + N93) / rho`` avhenger av summer over alle selskaper.  En
selskaps-for-selskaps prognose (slik Steg 2 i appen gjør) kan derfor ikke
rekalibrere.  Denne modulen kjører alle selskaper samtidig og kan dermed
rekalibrere hvert enkelt prognoseår.

Bruk:
    ark = build_flerarsark()
    ark.to_excel("Flerårig inntektsrammeark.xlsx")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from inntektsramme import DEANorm, RevenueCapCalculator
from prognose import (
    FORECAST_YEARS,
    PrognoseCalculator,
    load_forutsetninger_from_csv,
)

logger = logging.getLogger(__name__)

# Basisåret i inntektsrammearket (y.rc).  Prognosen "pinner" dette året til
# arkets egne tall, slik at 2026-arket skal reprodusere RME-modellen eksakt.
ARK_BASE_YEAR = 2026

# Standard årsspenn for flerårsarket.  FORECAST_YEARS starter på 2025, men det
# året er en *tilbakeskriving* (deflatert fra 2026) og ikke et modellresultat,
# så det holdes utenfor med mindre kaller ber om det eksplisitt.
DEFAULT_YEARS = [y for y in FORECAST_YEARS if y >= ARK_BASE_YEAR]


# ---------------------------------------------------------------------------
# Arkoppsett — kolonnerekkefølge per årsark
# ---------------------------------------------------------------------------

# (kolonnenavn i arket, nøkkel i den interne lange tabellen)
_ARK_LAYOUT: list[tuple[str, str]] = [
    ("Org.nr",                                                    "orgn"),
    ("ID",                                                        "id"),
    ("Selskap",                                                   "selskap"),
    ("År",                                                        "aar"),
    ("rho",                                                       "rho"),
    ("sum ir k per sum akg",                                      "n100"),
    ("sum renter avvik",                                          "n93"),
    # --- aggregerte kostnader ---
    ("Årslønn-justerte D&V-kostnader eks utredningskostnader",    "dv"),
    ("Årslønn-justerte kostnader knyttet til utred.ansvar og KDS", "utred"),
    ("AVS",                                                       "avs"),
    ("BFV",                                                       "bfv"),
    ("AKG (inkl 1 % arbeids-kapital)",                            "akg"),
    ("Nettap MWh i LD",                                           "ld_nl"),
    ("Nettap MWh i RD",                                           "rd_nl"),
    ("Nettaps- kostnad i LD",                                     "ld_nettap"),
    ("Nettaps- kostnad i RD",                                     "rd_nettap"),
    ("KILE",                                                      "kile"),
    ("Sum kostnader",                                             "sum_kostnader"),
    ("Kostnadsgrunnlag",                                          "kg"),
    # --- norm og inntektsramme ---
    ("K* lok distribusjonsnett",                                  "k_ld"),
    ("K* reg distribusjonsnett",                                  "k_rd"),
    ("Inntektsramme før kalibrering",                             "ir_foer"),
    ("Tillegg i kostnadsnorm for kundevekst",                     "kundetillegg"),
    ("K* etter kalibrering",                                      "k_etter"),
    ("Inntektsramme etter kalibrering",                           "ir_etter"),
    ("Kraftpris kr/MWh",                                          "kraftpris"),
    # --- nøkkeltall ---
    ("Driftsresultat",                                            "driftsresultat"),
    ("Effektivitet Dnett %",                                      "eff_ld_pct"),
    ("Effektivitet Rnett %",                                      "eff_rd_pct"),
    ("Effektivitet vektet %",                                     "eff_w_pct"),
    ("Avkastning NVE %",                                          "avkastning_pct"),
    # --- detaljer per nettnivå ---
    ("Lokalt Årslønnjusterte D&V-kostnader",                      "ld_dv"),
    ("Lokalt AVS",                                                "ld_avs"),
    ("Lokalt BFV",                                                "ld_bfv"),
    ("Lokalt AKG inkl 1% arbeids-kapital",                        "ld_akg"),
    ("Lokalt AKG inkl 17b",                                       "ld_rab17b"),
    ("Lokalt KILE (fq)",                                          "ld_kile"),
    ("Lokalt Nettapskostnad",                                     "ld_nettap"),
    ("Lokalt Kostnadsgrunnlag",                                   "ld_kg"),
    ("Regionalt Årslønnjusterte D&V-kostnader uten utredningskostnader", "rd_dv"),
    ("Regionalt AVS",                                             "rd_avs"),
    ("Regionalt BFV",                                             "rd_bfv"),
    ("Regionalt AKG inkl 1% arbeids-kapital",                     "rd_akg"),
    ("Regionalt AKG inkl 17b",                                    "rd_rab17b"),
    ("Regionalt KILE (fq)",                                       "rd_kile"),
    ("Regionalt Nettapskostnad",                                  "rd_nettap"),
    ("Regionalt Kostnadsgrunnlag",                                "rd_kg"),
]

# Kolonner i sammendragsarket som summeres over selskaper (resten er nøkkeltall).
_SUM_COLS = [
    "dv", "utred", "avs", "bfv", "akg", "kile", "sum_kostnader", "kg",
    "k_ld", "k_rd", "ir_foer", "kundetillegg", "k_etter", "ir_etter",
    "ld_nettap", "rd_nettap", "driftsresultat",
]


# ---------------------------------------------------------------------------
# Resultatobjekt
# ---------------------------------------------------------------------------

@dataclass
class FlerarsArk:
    """Resultatet av en flerårskjøring."""

    long: pd.DataFrame                      # én rad per (selskap, år), interne nøkler
    sheets: dict[int, pd.DataFrame]         # år -> ark med arkets kolonnenavn
    summary: pd.DataFrame                   # bransjetotaler per år
    diagnostics: dict = field(default_factory=dict)

    @property
    def years(self) -> list[int]:
        return sorted(self.sheets)

    # ------------------------------------------------------------------
    def to_bytes(self) -> bytes:
        """Samme regneark som ``to_excel``, men som bytes (for nedlasting)."""
        import io
        buf = io.BytesIO()
        self.to_excel(buf)
        buf.seek(0)
        return buf.getvalue()

    # ------------------------------------------------------------------
    def to_excel(self, path) -> str:
        """Skriv ett regneark med Sammendrag + ett ark per år.

        ``path`` kan være en filbane eller et binært buffer.
        """
        with pd.ExcelWriter(path, engine="xlsxwriter") as xl:
            self.summary.to_excel(xl, sheet_name="Sammendrag", index=False)
            for year in self.years:
                self.sheets[year].to_excel(xl, sheet_name=str(year), index=False)

            # Litt formatering: frys toppraden og gi tallkolonnene fornuftig bredde
            book = xl.book
            num = book.add_format({"num_format": "# ##0"})
            for name in ["Sammendrag", *[str(y) for y in self.years]]:
                ws = xl.sheets[name]
                ws.freeze_panes(1, 3)
                ws.set_column(0, 2, 22)
                ws.set_column(3, 60, 14, num)
        return path


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

def _align_rente_path(forutsetninger: dict, referanserente_pct: float) -> tuple[dict, float]:
    """Forskyv NVE-rentebanen slik at basisåret treffer arkets referanserente.

    Arket bruker referanserenten for 2026 (config: ``forutsetninger.referanserente``),
    mens prognosen bruker sin egen NVE-rentebane.  Uten justering får man et
    nivåsprang mellom 2026 (som er pinnet til arket) og 2027.  Vi beholder formen
    på rentebanen og flytter hele banen med samme differanse.
    """
    rente = dict(forutsetninger.get("nve_rente") or {})
    if ARK_BASE_YEAR not in rente:
        return forutsetninger, 0.0
    delta = referanserente_pct - rente[ARK_BASE_YEAR]
    out = dict(forutsetninger)
    out["nve_rente"] = {y: v + delta for y, v in rente.items()}
    return out, delta


def _scale_kile(base_ir: dict, factor: float) -> dict:
    """KPI-juster basisårets KILE slik at nivået matcher arkets konvensjon.

    Arket bruker ``KILE * kpi_ratio`` (2024→2026) i kostnadsgrunnlaget, mens
    prognosen framskriver rå KILE.  Basisåret er pinnet, så uten dette blir
    2027+ liggende ~5 % for lavt på KILE.
    """
    out = dict(base_ir)
    for key in ("Lokalt KILE (fq)", "Regionalt KILE (fq)"):
        if key in out and out[key] is not None:
            try:
                out[key] = float(out[key]) * factor
            except (TypeError, ValueError):
                pass
    return out


def _nansum(s: pd.Series) -> float:
    return float(np.nansum(s.to_numpy(dtype="float64")))


# ---------------------------------------------------------------------------
# Hovedfunksjon
# ---------------------------------------------------------------------------

def build_flerarsark(
    run_name: str | None = None,
    config_path: str = "config.yaml",
    forutsetninger: dict | None = None,
    dv_vekst: dict | None = None,
    rho: float | None = None,
    avs_sats: float = 4.0,
    labor_share_ld: float = 0.30,
    labor_share_rd: float = 0.30,
    recalibrate: bool = True,
    n93_per_year: dict | None = None,
    align_basis: bool = True,
    base_year_from_ark: bool = True,
    bfv_rebase: str = "both",
    include_utred: bool = True,
    years: list[int] | None = None,
    grunnlagsdata_csv_path: str | None = None,
    progress=None,
) -> FlerarsArk:
    """Framskriv inntektsrammearket for alle selskaper, ett ark per år.

    Parameters
    ----------
    run_name
        Run_*-mappe under Results/.  None = nyeste komplette kjøring.
    forutsetninger
        {kpi, kpi_lonn, nve_rente, kraftpris}, hver med år -> verdi.  None laster
        fra Data/BaseData/kraftpris_soner.csv.
    rho
        Effektivitetsvekt.  None = verdien i config.yaml.
    recalibrate
        True  : rekalibrer hvert prognoseår — tillegg i norm fordeles på nytt og
                N100 beregnes på nytt av det framskrevne bransjeaggregatet.
        False : behold basisårets kalibreringskonstanter (config) og prognosens
                fastlåste DEA-effektivitet — tillegg i norm fordeles ikke på nytt
                og N100 beregnes ikke om.  Kalibreringsleddet legges likevel på,
                i motsetning til Steg 2, som rapporterer IR *før* kalibrering.
    n93_per_year
        Renteavvik (N93, i prosent) per år.  N93 er en *ekstern* størrelse —
        avviket mellom referanserente og faktiske rentekostnader — og kan ikke
        utledes av prognosen.  None = hold config-verdien konstant.
    align_basis
        Juster KILE-nivå og rentebane til arkets konvensjon, slik at overgangen
        2026 -> 2027 ikke får et kunstig nivåsprang.  Se ``_align_rente_path``
        og ``_scale_kile``.
    bfv_rebase
        Skaler grunnlagsdatas BFV-nivå til arkets kapitalbase — se
        ``prognose.PrognoseCalculator._rebase_to_ark_bfv``.  Uten dette får
        kapitalbasen et sprang på ~27 % (LD) mellom basisåret og året etter.
        "both" (standard) bevarer den observerte investeringstakten,
        "bfv" bare nivået, "none" er prognosens uendrede oppførsel.
    include_utred
        Ta utrednings-/koordineringskostnader (RKSU) med i RD-kostnadsgrunnlaget,
        slik arket gjør.  Prognosens egen formel utelot dem, så uten dette faller
        de ut av grunnlaget fra året etter basisåret (~0,35 % av kostnadsgrunnlaget).
    base_year_from_ark
        Hent basisårets ark direkte fra RME-modellen i stedet for å regne det
        fram på nytt gjennom prognosen.  Da blir 2026-arket identisk med
        tabellen i Steg 1.  Prognosen treffer basisåret innenfor ~1 kkr uansett,
        men avrunder utdata og bruker den avrundede N100 fra config.
    years
        Årsspenn.  None = 2026..2035 (2025 utelates, se DEFAULT_YEARS).
    progress
        Valgfri callback ``fn(done, total, label)`` for framdrift.
    """
    years = sorted(years or DEFAULT_YEARS)

    # --- 1. Basisåret fra RME-modellen -------------------------------------
    rc = RevenueCapCalculator(config_path, run_name=run_name)
    etl_df = rc.build_etl_dataframe()
    ir_df = rc.build_ir_dataframe()
    rho = rc.cfg.rho if rho is None else rho

    if forutsetninger is None:
        forutsetninger = load_forutsetninger_from_csv()
    if forutsetninger is None:
        raise RuntimeError(
            "Fant ikke forutsetninger (Data/BaseData/kraftpris_soner.csv). "
            "Send inn `forutsetninger` eksplisitt."
        )

    rente_delta = 0.0
    if align_basis:
        forutsetninger, rente_delta = _align_rente_path(
            forutsetninger, rc.cfg.referanserente * 100
        )

    if grunnlagsdata_csv_path is None:
        grunnlagsdata_csv_path = _find_grunnlagsdata(rc, run_name)

    # --- 2. Framskriv hvert selskap ----------------------------------------
    ir_by_orgn = {int(r["Org.nr"]): r.to_dict() for _, r in ir_df.iterrows()}
    rows: list[dict] = []
    total = len(etl_df)
    skipped: list[str] = []

    for n, (_, etl_row) in enumerate(etl_df.iterrows(), start=1):
        etl = etl_row.to_dict()
        orgn = int(etl["Org.nr"])
        base_ir = ir_by_orgn.get(orgn, {})
        if align_basis and base_ir:
            base_ir = _scale_kile(base_ir, rc.cfg.kpi_ratio)

        if progress:
            progress(n, total, str(etl.get("Selskap", orgn)))

        try:
            calc = PrognoseCalculator(
                base_ir=base_ir,
                base_etl=etl,
                forutsetninger=forutsetninger,
                dv_vekst=dv_vekst,
                rho=rho,
                avs_sats=avs_sats,
                labor_share_ld=labor_share_ld,
                labor_share_rd=labor_share_rd,
                grunnlagsdata_csv_path=grunnlagsdata_csv_path,
                bfv_rebase=bfv_rebase,
                include_utred=include_utred,
            )
            fc = calc.build_forecast()
        except Exception as exc:  # noqa: BLE001 — én selskapsfeil skal ikke velte kjøringen
            logger.warning("Prognose feilet for %s (%s): %s", etl.get("Selskap"), orgn, exc)
            skipped.append(f"{etl.get('Selskap', orgn)} ({orgn}): {exc}")
            continue

        fc = fc[fc["År"].isin(years)]
        akg_base = float(etl.get("AKG (inkl 1 % arbeids-kapital)") or 0)
        # prognose.build_forecast() "pinner" RD-kostnadsgrunnlaget til arkets verdi
        # i basisåret, men bare når den er ulik null (`if self.rd_kg:`).  Arkets
        # verdi er EKSKL. nettap, mens prognosens egen formel er INKL. nettap.
        # Kolonnen betyr derfor to ulike ting, og vi må vite hvilken som gjelder.
        rd_kg_pinned = float(base_ir.get("Regionalt Kostnadsgrunnlag ") or 0) != 0

        for _, f in fc.iterrows():
            ld_akg = float(f["LD AKG"])
            rd_akg = float(f["RD AKG"])
            # RAB inkl. 17b framskrives proporsjonalt med AKG på samme nettnivå.
            # 17b-tilleggene rapporteres ikke i prognosen, så andelen holdes fast.
            ld_akg0 = float(base_ir.get("Lokalt AKG inkl 1% arbeids-kapital") or 0)
            rd_akg0 = float(base_ir.get("Regionalt AKG inkl 1% arbeids-kapital") or 0)
            ld_rab0 = float(base_ir.get("Lokalt AKG inkl 17b") or 0)
            rd_rab0 = float(base_ir.get("Regionalt AKG inkl 17b") or 0)
            ld_rab = ld_rab0 * (ld_akg / ld_akg0) if ld_akg0 else 0.0
            rd_rab = rd_rab0 * (rd_akg / rd_akg0) if rd_akg0 else 0.0

            # Normaliser RD-kostnadsgrunnlaget til arkets konvensjon (ekskl. nettap).
            _rd_kg_raw = float(f["RD Kostnadsgrunnlag"])
            if int(f["År"]) == ARK_BASE_YEAR and rd_kg_pinned:
                _rd_kg_ark = _rd_kg_raw          # allerede arkets verdi, ekskl. nettap
            else:
                _rd_kg_ark = _rd_kg_raw - float(f["RD Nettapskostnad"])

            rows.append({
                "orgn": orgn,
                "id": int(etl.get("ID") or 0),
                "selskap": etl.get("Selskap", ""),
                "aar": int(f["År"]),
                "rho": rho,
                "ld_dv": float(f["LD D&V"]),
                "rd_dv": float(f["RD D&V"]),
                "utred": float(f.get("RD Utredningskostnader") or 0),
                "ld_avs": float(f["LD AVS"]),
                "rd_avs": float(f["RD AVS"]),
                "ld_bfv": float(f["LD BFV"]),
                "rd_bfv": float(f["RD BFV"]),
                "ld_akg": ld_akg,
                "rd_akg": rd_akg,
                "ld_rab17b": ld_rab,
                "rd_rab17b": rd_rab,
                "ld_kile": float(f["LD KILE"]),
                "rd_kile": float(f["RD KILE"]),
                "ld_nl": float(f["LD Nettap MWh"]),
                "rd_nl": float(f["RD Nettap MWh"]),
                "ld_nettap": float(f["LD Nettapskostnad"]),
                "rd_nettap": float(f["RD Nettapskostnad"]),
                "ld_kg": float(f["LD Kostnadsgrunnlag"]),
                # Arkets RD-kostnadsgrunnlag EKSKLUDERER nettap — nettapskostnaden
                # er et gjennomslag som legges til normen, ikke en del av DEA-
                # grunnlaget (se inntektsramme.CostCalculator.rd_kostnadsgrunnlag).
                "rd_kg": _rd_kg_ark,
                "rd_kg_inkl_nettap": _rd_kg_ark + float(f["RD Nettapskostnad"]),
                "kg": float(f["Kostnadsgrunnlag"]),
                "kraftpris": float(f["Kraftpris kr/MWh"]),
                "kundetillegg": float(etl.get("Tillegg i kostnadsnorm for kundevekst") or 0),
                "akg_base": akg_base,
                # prognosens egne norm-/IR-tall (brukes når recalibrate=False)
                "k_ld_frozen": float(f["LD Kostnadsnorm"]),
                "k_rd_frozen": float(f["RD Kostnadsnorm"]),
                "ir_frozen": float(f["Inntektsramme"]),
            })

    if not rows:
        raise RuntimeError("Ingen selskaper ble framskrevet — se logg for årsak.")

    long = pd.DataFrame(rows)
    long["dv"] = long["ld_dv"] + long["rd_dv"]
    long["avs"] = long["ld_avs"] + long["rd_avs"]
    long["bfv"] = long["ld_bfv"] + long["rd_bfv"]
    long["akg"] = long["ld_akg"] + long["rd_akg"]
    long["kile"] = long["ld_kile"] + long["rd_kile"]
    long["sum_kostnader"] = (
        long["dv"] + long["avs"] + long["ld_nettap"] + long["rd_nettap"] + long["kile"]
    )

    # Norm- og IR-kolonnene fylles i bransjepasset under, men må finnes allerede
    # nå slik at basisårets arkverdier kan skrives inn.
    for _c in ("k_ld", "k_rd", "ir_foer", "k_etter", "ir_etter"):
        long[_c] = np.nan

    # Basisåret: bytt ut de framregnede verdiene med arkets egne.
    use_ark_base = base_year_from_ark and ARK_BASE_YEAR in years
    if use_ark_base:
        ark_base = _ark_base_year_rows(rc, etl_df, ir_df)
        mask = long["aar"] == ARK_BASE_YEAR
        idx = long.loc[mask, "orgn"]
        for col in ark_base.columns:
            if col in long.columns:
                long.loc[mask, col] = ark_base[col].reindex(idx).to_numpy()

    # --- 3. Bransjepass per år: norm, tillegg, kalibrering -----------------
    n93_default = rc.cfg.sum_renter_avvik_per_akg * 100
    n93_per_year = {int(k): float(v) for k, v in (n93_per_year or {}).items()}

    diagnostics: dict = {
        "run_name": run_name,
        "n_companies": int(long["orgn"].nunique()),
        "years": years,
        "rho": rho,
        "recalibrate": recalibrate,
        "align_basis": align_basis,
        "bfv_rebase": bfv_rebase,
        "include_utred": include_utred,
        "base_year_from_ark": base_year_from_ark,
        "rente_delta_pp": round(rente_delta, 4),
        "kile_kpi_factor": round(rc.cfg.kpi_ratio, 5) if align_basis else 1.0,
        "referanserente_pct": round(rc.cfg.referanserente * 100, 4),
        "n93_pct_default": n93_default,
        "skipped": skipped,
        "per_year": {},
    }

    parts: list[pd.DataFrame] = []
    for year in years:
        y = long[long["aar"] == year].copy().reset_index(drop=True)
        ids = y["id"]
        n93 = n93_per_year.get(year, n93_default) / 100.0

        if use_ark_base and year == ARK_BASE_YEAR:
            # Norm og inntektsramme er allerede arkets egne tall; bruk arkets
            # kalibreringskonstant slik at 2026 blir bit-identisk med Steg 1.
            n100 = rc.cfg.sum_ir_k_per_akg
            n93 = rc.cfg.sum_renter_avvik_per_akg
        elif recalibrate:
            # Gjenbruk arkets egen DEANorm slik at norm + tillegg beregnes
            # identisk med basisåret, men på framskrevet kostnadsgrunnlag.
            dea_ld = DEANorm(
                ids=ids, eff_col="ld_eff.s2.cb", results_df=rc.data.res_ld,
                kostnadsgrunn=y["ld_kg"], rab17b=y["ld_rab17b"],
                overrides=rc.cfg.dea_ld_overrides,
            )
            dea_rd = DEANorm(
                ids=ids, eff_col="rd_eff.s2.cb", results_df=rc.data.res_rd,
                kostnadsgrunn=y["rd_kg"], rab17b=y["rd_rab17b"],
                overrides=rc.cfg.dea_rd_overrides,
            )
            y["k_ld"] = dea_ld.kalibrert
            y["k_rd"] = dea_rd.kalibrert + y["rd_nettap"]

            y["ir_foer"] = (1 - rho) * y["kg"].fillna(0) + rho * (
                y["k_ld"].fillna(0) + y["k_rd"].fillna(0)
            )
            # N100 = sum(IR før kalibrering − K) / sum(AKG), beregnet på nytt
            # av det framskrevne bransjeaggregatet for dette året.
            n100 = (_nansum(y["ir_foer"]) - _nansum(y["kg"])) / _nansum(y["akg"])
            y["k_etter"] = (
                y["k_ld"].fillna(0) + y["k_rd"].fillna(0)
                - y["akg"] * (n100 + n93) / rho
                + y["kundetillegg"]
            )
            y["ir_etter"] = (1 - rho) * y["kg"].fillna(0) + rho * y["k_etter"]
        else:
            # Fastlåst kalibrering: bruk prognosens norm (basisårets DEA-effektivitet
            # med basisårets tillegg innbakt) og basisårets kalibreringskonstant fra
            # config, i stedet for å regne dem om for hvert år.
            # NB: prognosens egen "Inntektsramme" er IR *før* kalibrering — vi legger
            # kalibreringsleddet på her, ellers ville 2027+ vært ukalibrert.
            n100 = rc.cfg.sum_ir_k_per_akg
            y["k_ld"] = y["k_ld_frozen"]
            y["k_rd"] = y["k_rd_frozen"]
            y["ir_foer"] = (1 - rho) * y["kg"].fillna(0) + rho * (y["k_ld"] + y["k_rd"])
            y["k_etter"] = (
                y["k_ld"].fillna(0) + y["k_rd"].fillna(0)
                - y["akg"] * (n100 + n93) / rho
                + y["kundetillegg"]
            )
            y["ir_etter"] = (1 - rho) * y["kg"].fillna(0) + rho * y["k_etter"]

        y["n100"] = n100
        y["n93"] = n93
        y["driftsresultat"] = y["ir_etter"] - y["kg"]
        y["eff_ld_pct"] = np.where(y["ld_kg"] > 0, y["k_ld"] / y["ld_kg"] * 100, 0.0)
        y["eff_rd_pct"] = np.where(
            y["rd_kg_inkl_nettap"] > 0,
            y["k_rd"] / y["rd_kg_inkl_nettap"] * 100, 0.0,
        )
        y["eff_w_pct"] = np.where(
            y["kg"] > 0, (y["k_ld"].fillna(0) + y["k_rd"].fillna(0)) / y["kg"] * 100, 0.0
        )
        non_capital = (
            y["dv"] + y["avs"] + y["ld_nettap"] + y["rd_nettap"] + y["kile"]
        )
        y["avkastning_pct"] = np.where(
            y["akg"] > 0, (y["ir_etter"] - non_capital) / y["akg"] * 100, 0.0
        )

        diagnostics["per_year"][year] = {
            "n100_pct": round(n100 * 100, 6),
            "n93_pct": round(n93 * 100, 6),
            "sum_kg": round(_nansum(y["kg"]), 1),
            "sum_akg": round(_nansum(y["akg"]), 1),
            "sum_ir_foer": round(_nansum(y["ir_foer"]), 1),
            "sum_ir_etter": round(_nansum(y["ir_etter"]), 1),
            "sum_norm": round(_nansum(y["k_ld"]) + _nansum(y["k_rd"]), 1),
        }
        parts.append(y)

    long = pd.concat(parts, ignore_index=True)

    # --- 4. Bygg ett ark per år + sammendrag -------------------------------
    sheets: dict[int, pd.DataFrame] = {}
    for year in years:
        y = long[long["aar"] == year]
        sheet = pd.DataFrame({
            name: y[key].to_numpy() for name, key in _ARK_LAYOUT if key in y.columns
        })
        sheet = sheet.sort_values("Selskap").reset_index(drop=True)
        sheets[year] = sheet

    summary = _build_summary(long, years)

    logger.info(
        "Flerårsark: %d selskaper, %d år (%d–%d), recalibrate=%s",
        diagnostics["n_companies"], len(years), years[0], years[-1], recalibrate,
    )
    return FlerarsArk(long=long, sheets=sheets, summary=summary, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
def _ark_base_year_rows(rc: RevenueCapCalculator,
                        etl_df: pd.DataFrame,
                        ir_df: pd.DataFrame) -> pd.DataFrame:
    """Basisårets rader hentet direkte fra RME-modellen, med interne nøkler.

    Prognosen reproduserer basisåret til under 1 kkr, men avrunder utdata og
    bruker den avrundede kalibreringskonstanten fra config.  Basisårsarket bør
    være *selve* inntektsrammearket, slik at Steg 1 og flerårsarket viser
    identiske tall for 2026.
    """
    e = etl_df.set_index("Org.nr")
    i = ir_df.set_index("Org.nr")
    kpi = rc.cfg.kpi_ratio

    out = pd.DataFrame(index=e.index)
    out["dv"] = e["Årslønn-justerte D&V-kostnader eks utredningskostnader"]
    out["utred"] = e["Årslønn-justerte kostnader knyttet til utred.ansvar og KDS"]
    out["avs"] = e["AVS"]
    out["bfv"] = e["BFV"]
    out["akg"] = e["AKG (inkl 1 % arbeids-kapital)"]
    out["ld_nl"] = e["Nettap MWh i LD"]
    out["rd_nl"] = e["Nettap MWh i RD"]
    out["ld_nettap"] = e["Nettaps- kostnad i LD"]
    out["rd_nettap"] = e["Nettaps- kostnad i RD"]
    # KG bygger på KPI-justert KILE, så det er den som rapporteres
    out["kile"] = e["KPI-justert KILE"]
    out["sum_kostnader"] = e["Sum kostnader"]
    out["kg"] = e["Kostnadsgrunnlag"]
    out["kraftpris"] = e["Kraftpris kr/MWh"]
    out["kundetillegg"] = e["Tillegg i kostnadsnorm for kundevekst"]
    out["k_ld"] = e["K* lok distribusjonsnett"]
    out["k_rd"] = e["K* reg distribusjonsnett"]
    out["ir_foer"] = e["Inntektsramme før kalibrering"]
    out["k_etter"] = e["K* etter kalibrering"]
    out["ir_etter"] = e["Inntektsramme etter kalibrering"]

    out["ld_dv"] = i["Lokalt Årslønnjusterte D&V-kostnader"]
    out["ld_avs"] = i["Lokalt AVS"]
    out["ld_akg"] = i["Lokalt AKG inkl 1% arbeids-kapital"]
    out["ld_rab17b"] = i["Lokalt AKG inkl 17b"]
    out["ld_kile"] = i["Lokalt KILE (fq)"] * kpi
    out["ld_kg"] = i["Lokalt Kostnadsgrunnlag"]
    out["rd_dv"] = i["Regionalt Årslønnjusterte D&V-kostnader uten utredningskostnader"]
    out["rd_avs"] = i["Regionalt AVS"]
    out["rd_akg"] = i["Regionalt AKG inkl 1% arbeids-kapital"]
    out["rd_rab17b"] = i["Regionalt AKG inkl 17b"]
    out["rd_kile"] = i["Regionalt KILE (fq)"] * kpi
    out["rd_kg"] = i["Regionalt Kostnadsgrunnlag "]  # etterfølgende mellomrom i modellen
    out["ld_bfv"] = out["ld_akg"] / rc.cfg.arbeidskapital_faktor
    out["rd_bfv"] = out["rd_akg"] / rc.cfg.arbeidskapital_faktor
    out["rd_kg_inkl_nettap"] = out["rd_kg"] + out["rd_nettap"]
    return out


# ---------------------------------------------------------------------------
def _build_summary(long: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Bransjetotaler per år — én rad per størrelse, én kolonne per år."""
    labels = {key: name for name, key in _ARK_LAYOUT}
    rows: list[dict] = []

    for key in _SUM_COLS:
        if key not in long.columns:
            continue
        row = {"Parameter": labels.get(key, key), "Enhet": "kkr"}
        for year in years:
            row[str(year)] = round(_nansum(long.loc[long["aar"] == year, key]), 1)
        rows.append(row)

    # Nøkkeltall: vektede/beregnede størrelser, ikke summer
    for label, fn in [
        ("Effektivitet vektet %", lambda y: (
            (_nansum(y["k_ld"]) + _nansum(y["k_rd"])) / _nansum(y["kg"]) * 100
            if _nansum(y["kg"]) else 0.0)),
        ("Avkastning NVE %", lambda y: (
            (_nansum(y["ir_etter"]) - (_nansum(y["dv"]) + _nansum(y["avs"])
             + _nansum(y["ld_nettap"]) + _nansum(y["rd_nettap"]) + _nansum(y["kile"])))
            / _nansum(y["akg"]) * 100 if _nansum(y["akg"]) else 0.0)),
        ("sum ir k per sum akg", lambda y: float(y["n100"].iloc[0]) * 100 if len(y) else 0.0),
        ("sum renter avvik", lambda y: float(y["n93"].iloc[0]) * 100 if len(y) else 0.0),
    ]:
        row = {"Parameter": label, "Enhet": "%"}
        for year in years:
            row[str(year)] = round(fn(long[long["aar"] == year]), 4)
        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def _find_grunnlagsdata(rc: RevenueCapCalculator, run_name: str | None) -> str | None:
    """Finn *_grunnlagsdata.csv i samme Run_*-mappe som resultatfilene."""
    try:
        irir_path, _, _ = rc.cfg.resolve_paths()
    except Exception:
        return None
    run_dir = os.path.dirname(irir_path)
    try:
        hits = sorted(f for f in os.listdir(run_dir) if f.endswith("grunnlagsdata.csv"))
    except OSError:
        return None
    return os.path.join(run_dir, hits[-1]) if hits else None


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ark = build_flerarsark()
    out = ark.to_excel("Flerårig inntektsrammeark.xlsx")
    d = ark.diagnostics
    print(f"\nSkrev {out}")
    print(f"{d['n_companies']} selskaper, år {d['years'][0]}–{d['years'][-1]}")
    print(f"rente-justering: {d['rente_delta_pp']} pp   KILE-faktor: {d['kile_kpi_factor']}")
    if d["skipped"]:
        print(f"\nHoppet over {len(d['skipped'])}:")
        for s in d["skipped"]:
            print("  ", s)
    print("\nBransjetotaler:")
    print(ark.summary.to_string(index=False))
