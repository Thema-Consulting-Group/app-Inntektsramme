"""
Post-processing of inntektsrammer (revenue caps).

Refactored version — composition over inheritance, modular calculations,
config-driven overrides.
"""

import os
import logging
import numpy as np
import pandas as pd
from utils import Util

logger = logging.getLogger(__name__)

pd.set_option("display.float_format", "{:.2f}".format)

# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------

class Config:
    """Load YAML and expose derived parameters."""

    def __init__(self, path: str = "config.yaml"):
        self._raw: dict = Util.load_config(path)
        self.base_dir: str = os.path.dirname(os.path.abspath(__file__))

        fp = self.f  # shorthand
        # Pre-compute reference rate once
        self.referanserente: float = self._calc_referanserente()

        # Convenience scalars
        self.rho: float = fp["rho"]
        kpi = fp["kpi_justering"]
        wage = fp["aarslonn"]
        self.kpi_ratio: float = kpi[2026] / kpi[2024]
        self.wage_ratio: float = wage[2026] / wage[2024]

        # Calibration constants (temporary hacks — kept in config)
        cal = self._raw["kalibrering"]
        self.sum_ir_k_per_akg: float = cal["sum_ir_k_per_sum_akg_pct"] / 100
        self.sum_renter_avvik_per_akg: float = cal["sum_renter_avvik_per_sum_akg_pct"] / 100

        # DEA manual overrides (id -> value, None means NaN)
        dea = self._raw["dea_overrides"]
        self.dea_ld_overrides: dict = dea["ld"]
        self.dea_rd_overrides: dict = dea["rd"]

        # Working capital adjustment factor for BFV
        self.arbeidskapital_faktor: float = 1.01

        # Paths
        self.kundetillegg_path: str = os.path.join(
            self.base_dir, self._raw.get("kundetillegg_path", "Data/kundetillegg.csv")
        )

    # --- forutsetninger shorthand ---
    @property
    def f(self) -> dict:
        return self._raw["forutsetninger"]

    # --- file paths resolved from config ---
    def resolve_paths(self):
        """Return (irir_path, ld_path, rd_path) as absolute paths."""
        cfg = self._raw
        if not cfg.get("irir_results_path"):
            results_dir = os.path.join(self.base_dir, "Results")
            run_dirs = sorted(
                d for d in os.listdir(results_dir)
                if d.startswith("Run_") and os.path.isdir(os.path.join(results_dir, d))
            )
            if not run_dirs:
                raise FileNotFoundError("No run directories found in Results.")
            latest = run_dirs[-1]
            irir = os.path.join(results_dir, latest, "Til inntektsrammeark.xlsx")
            ld = os.path.join(results_dir, latest, "Data_Resultater_LD.xlsx")
            rd = os.path.join(results_dir, latest, "Data_Resultater_RD.xlsx")
        else:
            irir = os.path.join(self.base_dir, cfg["irir_results_path"])
            ld = os.path.join(self.base_dir, cfg["data_resultater_ld_path"])
            rd = os.path.join(self.base_dir, cfg["data_resultater_rd_path"])
        return os.path.abspath(irir), os.path.abspath(ld), os.path.abspath(rd)

    def _calc_referanserente(self) -> float:
        """r = (1-G)*(Rf + Infl + beta*MP)/(1-s) + G*(Swap + KP)  (fraction)."""
        fp = self.f["finansparametere"]
        r = (
            (1 - fp["gjeldsandel"])
            * (fp["noytral_realrente"] + fp["inflasjon"] + fp["ek-beta"] * fp["markedspremie"])
            / (1 - fp["skatt"])
            + fp["gjeldsandel"] * (fp["swap"] + fp["kredittpremie"])
        )
        return r / 100.0


# ---------------------------------------------------------------------------
# 2. DataLoader — read Excel files once
# ---------------------------------------------------------------------------

class DataLoader:
    """Load the three Excel sources and expose raw Series by short name."""

    def __init__(self, cfg: Config):
        irir_path, ld_path, rd_path = cfg.resolve_paths()
        irir = pd.read_excel(irir_path)
        self.res_ld = pd.read_excel(ld_path, sheet_name="Resultater_LD")
        self.res_rd = pd.read_excel(rd_path, sheet_name="Resultater_RD")

        # Identity columns
        self.orgn: pd.Series = irir["orgn"]
        self.id: pd.Series = irir["id"]
        self.comp: pd.Series = irir["comp"]

        # Local distribution (LD)
        self.ld_opex: pd.Series = irir["fp_ld_OPEX"]
        self.ld_avs: pd.Series = irir["ld_dep.sf"]
        self.ld_akg: pd.Series = irir["ld_rab.sf"]
        self.ld_rab17b: pd.Series = irir["ld_RAB"]
        self.ld_nl: pd.Series = irir["ld_nl"]
        self.ld_kile: pd.Series = irir["ld_cens"]

        # Regional distribution (RD)
        self.rd_opex: pd.Series = irir["fp_rd_OPEX"]
        self.rd_avs: pd.Series = irir["rd_dep.sf"]
        self.rd_akg: pd.Series = irir["rd_rab.sf"]
        self.rd_rab17b: pd.Series = irir["rd_RAB"]
        self.rd_nl: pd.Series = irir["rd_nl"]
        self.rd_kile: pd.Series = irir["rd_cens"]
        self.rd_cga: pd.Series = irir["rd_cga"]  # utredningsansvar

        # Transmission (T)
        self.t_opex: pd.Series = irir["fp_t_OPEX"]
        self.t_avs: pd.Series = irir["t_dep.sf"]
        self.t_akg: pd.Series = irir["t_rab.sf"]
        self.t_kile: pd.Series = irir["t_cens"]

        # Other
        self.kraftpris: pd.Series = irir["pnl.rc"]

        # Kundetillegg
        kt_df = pd.read_csv(
            cfg.kundetillegg_path,
            sep=";",
            encoding="utf-8-sig",
            dtype={"id": int},
        )
        kt_map = kt_df.set_index("id")["Tillegg i K*"]
        self.kundetillegg: pd.Series = self.id.map(kt_map).fillna(0).astype(int)


# ---------------------------------------------------------------------------
# 3. CostCalculator — all intermediate cost Series
# ---------------------------------------------------------------------------

class CostCalculator:
    """Compute derived cost columns from raw data + config."""

    def __init__(self, data: DataLoader, cfg: Config):
        self.d = data
        self.c = cfg

    # --- Aggregated totals ---
    @property
    def dv_total(self) -> pd.Series:
        return self.d.ld_opex + self.d.rd_opex + self.d.t_opex

    @property
    def dv_total_incl_utred(self) -> pd.Series:
        return self.dv_total + self.d.rd_cga

    @property
    def avs(self) -> pd.Series:
        return self.d.ld_avs + self.d.rd_avs + self.d.t_avs

    @property
    def akg(self) -> pd.Series:
        return self.d.ld_akg + self.d.rd_akg + self.d.t_akg

    @property
    def bfv(self) -> pd.Series:
        return (self.akg / self.c.arbeidskapital_faktor).round(0).astype(int)

    @property
    def kile(self) -> pd.Series:
        return self.d.ld_kile + self.d.rd_kile + self.d.t_kile

    @property
    def kile_kpi(self) -> pd.Series:
        return self.kile * self.c.kpi_ratio

    @property
    def dv_wage_adj(self) -> pd.Series:
        """DV (excl. utredning) wage-adjusted."""
        return self.dv_total * self.c.wage_ratio

    # --- LD ---
    @property
    def ld_dv_wage(self) -> pd.Series:
        return self.d.ld_opex * self.c.wage_ratio

    @property
    def ld_nettap(self) -> pd.Series:
        return self.d.ld_nl * self.d.kraftpris

    @property
    def ld_sum_kostnader(self) -> pd.Series:
        return self.ld_dv_wage + self.d.ld_avs + self.ld_nettap + self.d.ld_kile * self.c.kpi_ratio

    @property
    def ld_kostnadsgrunnlag(self) -> pd.Series:
        return self.ld_sum_kostnader + self.d.ld_akg * self.c.referanserente

    # --- RD ---
    @property
    def rd_dv_wage(self) -> pd.Series:
        return self.d.rd_opex * self.c.wage_ratio

    @property
    def rd_nettap(self) -> pd.Series:
        return self.d.rd_nl * self.d.kraftpris

    @property
    def rd_kostnadsgrunnlag(self) -> pd.Series:
        return (
            self.rd_dv_wage
            + self.d.rd_kile * self.c.wage_ratio
            + self.d.rd_avs
            + self.d.rd_akg * self.c.referanserente
        )

    # --- Transmission ---
    @property
    def t_kostnadsgrunnlag(self) -> pd.Series:
        return (
            self.d.t_opex * self.c.wage_ratio
            + self.d.t_avs
            + self.d.t_akg * self.c.referanserente
            + self.d.t_kile * self.c.kpi_ratio
        )

    # --- Combined ---
    @property
    def sum_kostnader(self) -> pd.Series:
        return (
            self.dv_wage_adj + self.avs
            + self.ld_nettap + self.rd_nettap
            + self.kile_kpi + self.d.rd_cga
        )

    @property
    def kostnadsgrunnlag(self) -> pd.Series:
        return self.sum_kostnader + self.akg * self.c.referanserente


# ---------------------------------------------------------------------------
# 4. DEANorm — single reusable class for LD / RD
# ---------------------------------------------------------------------------

class DEANorm:
    """
    Calibrated DEA norm for one network level (LD or RD).

    Parameters
    ----------
    ids           : company id Series
    eff_col       : bootstrap efficiency column name in results df
    results_df    : DataFrame from Data_Resultater_LD/RD
    kostnadsgrunn : cost basis Series (same index as ids)
    rab17b        : RAB incl 17b Series (same index as ids)
    overrides     : {id: value} manual efficiency overrides (None → NaN)
    """

    def __init__(
        self,
        ids: pd.Series,
        eff_col: str,
        results_df: pd.DataFrame,
        kostnadsgrunn: pd.Series,
        rab17b: pd.Series,
        overrides: dict,
    ):
        # Build efficiency mapping: bootstrap results + overrides
        eff_map = results_df.set_index("id")[eff_col].to_dict()
        eff_map.update(overrides)  # overrides take precedence
        self.efficiency = ids.map(eff_map)

        self.kostnadsgrunn = kostnadsgrunn
        self.dea_norm = kostnadsgrunn * self.efficiency
        self.tillegg = (rab17b / rab17b.sum()) * (
            kostnadsgrunn.sum() - np.nansum(self.dea_norm)
        )
        self.kalibrert = self.dea_norm + self.tillegg
        self.kalibrert_resultat = self.kalibrert / kostnadsgrunn

    def to_dataframe(self, ids: pd.Series, comp: pd.Series) -> pd.DataFrame:
        return pd.DataFrame({
            "id": ids,
            "Selskap": comp,
            "Kostnadsgrunnlag": self.kostnadsgrunn,
            "Resultat": self.efficiency,
            "DEAnorm": self.dea_norm,
            "Tillegg i norm": self.tillegg,
            "Kalibrert DEAnorm": self.kalibrert,
            "Kalibrert DEA-resultat": self.kalibrert_resultat,
        })


# ---------------------------------------------------------------------------
# 5. RevenueCapCalculator — orchestrates everything, builds output
# ---------------------------------------------------------------------------

class RevenueCapCalculator:
    """
    Main entry point.  Loads data, computes costs, DEA norms,
    calibration, and produces the final ETL DataFrame.
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.cfg = Config(config_path)
        self.data = DataLoader(self.cfg)
        self.costs = CostCalculator(self.data, self.cfg)
        self._build_dea_norms()

    # ------------------------------------------------------------------
    def _build_dea_norms(self):
        d = self.data
        c = self.costs
        self.dea_ld = DEANorm(
            ids=d.id,
            eff_col="ld_eff.s2.cb",
            results_df=d.res_ld,
            kostnadsgrunn=c.ld_kostnadsgrunnlag,
            rab17b=d.ld_rab17b,
            overrides=self.cfg.dea_ld_overrides,
        )
        self.dea_rd = DEANorm(
            ids=d.id,
            eff_col="rd_eff.s2.cb",
            results_df=d.res_rd,
            kostnadsgrunn=c.rd_kostnadsgrunnlag,
            rab17b=d.rd_rab17b,
            overrides=self.cfg.dea_rd_overrides,
        )

    # ------------------------------------------------------------------
    def calc_ir_foer_kalibrering(self) -> pd.Series:
        rho = self.cfg.rho
        kg = self.costs.kostnadsgrunnlag.fillna(0)
        dea_ld = self.dea_ld.kalibrert.fillna(0)
        dea_rd = self.dea_rd.kalibrert.fillna(0)
        return (1 - rho) * kg + (dea_ld + dea_rd) * rho

    # ------------------------------------------------------------------
    def calc_k_etter_kalibrering(
        self,
        k_norm_ld: pd.Series,
        k_norm_rd: pd.Series,
        tillegg_kundevekst: pd.Series,
    ) -> pd.Series:
        """
        K* etter kalibrering = (S + T + U) - AKG * (N100 + N93) / rho + W

        Variable mapping (from the NVE regulatory methodology):
          S   = k_norm_ld           — kalibrert DEAnorm for lokalt distribusjonsnett
          T   = k_norm_rd           — kalibrert DEAnorm for regionalt distribusjonsnett
                                      (inkl. nettapskostnad)
          U   = k_norm_t = 0        — transmisjonsnorm (ikke implementert ennå)
          W   = tillegg_kundevekst  — tillegg i kostnadsnorm for kundevekst
          AKG = avkastningsgrunnlag (sum over alle nettnivåer)
          N100 = sum_ir_k_per_akg   — kalibreringskonstant: sum(IR−K) / sum(AKG)
          N93  = sum_renter_avvik_per_akg — kalibreringskonstant: sum(renter-avvik) / sum(AKG)
          rho = effektivitetsvekt (andel norm vs. kostnadsgrunnlag)
        """
        k_norm_t: float = 0
        akg = self.costs.akg
        cal_sum = self.cfg.sum_ir_k_per_akg + self.cfg.sum_renter_avvik_per_akg
        rho = self.cfg.rho
        # fillna(0): companies without LD or RD activity have no norm for that level
        return (
            (k_norm_ld.fillna(0) + k_norm_rd.fillna(0) + k_norm_t)
            - akg * cal_sum / rho
            + tillegg_kundevekst
        )

    # ------------------------------------------------------------------
    def calc_ir_etter_kalibrering(
        self,
        kostnadsgrunnlag: pd.Series,
        k_etter_kalibrering: pd.Series,
    ) -> pd.Series:
        """
        =(1 - rho) * Kostnadsgrunnlag + rho * K* etter kalibrering
        """
        rho = self.cfg.rho
        return (1 - rho) * kostnadsgrunnlag.fillna(0) + rho * k_etter_kalibrering

    # ------------------------------------------------------------------
    # IR data output (same as create_IR_DataFrame in original)
    # ------------------------------------------------------------------
    def build_ir_dataframe(self) -> pd.DataFrame:
        d = self.data
        c = self.costs
        return pd.DataFrame({
            "Org.nr": d.orgn,
            "ID": d.id,
            "Selskap": d.comp,
            "År": 2024,
            "DV inkl.utrednings-ansvar": c.dv_total_incl_utred,
            "Kostnader knyttet til utrednings- og koordineringsansvar": d.rd_cga,
            "DV uten kostnader knyttet til utrednings-ansvar": c.dv_total,
            "Avskrivninger": c.avs,
            "Bokførte verdier": c.bfv,
            "Avkastningsgrunnlag": c.akg,
            "Krafttap MWh i Dnett": d.ld_nl,
            "Krafttap MWh i Rnett": d.rd_nl,
            "Kile": c.kile,
            "Lokalt D&V-kostnader": d.ld_opex,
            "Lokalt AVS": d.ld_avs,
            "Lokalt AKG inkl 1% arbeids-kapital": d.ld_akg,
            "Lokalt AKG inkl 17b": d.ld_rab17b,
            "Lokalt Nettap MWh": d.ld_nl,
            "Lokalt KILE (fq)": d.ld_kile,
            "Regionalt D&V-kostnader uten utredningskostnader": d.rd_opex,
            "Regionalt AVS": d.rd_avs,
            "Regionalt AKG inkl 17b": d.rd_rab17b,
            "Regionalt Nettap MWh": d.rd_nl,
            "Regionalt KILE (fq)": d.rd_kile,
            "Transmisjonsnett D&V-kostnader": d.t_opex,
            "Transmisjonsnett AVS": d.t_avs,
            "Transmisjonsnett AKG inkl 1% arbeids-kapital": d.t_akg,
            "Transmisjonsnett KILE (fq)": d.t_kile,
            "Kraftpris 2026": d.kraftpris,
            "Lokalt Årslønnjusterte D&V-kostnader": c.ld_dv_wage,
            "Lokalt Nettapskostnad": c.ld_nettap,
            "Lokalt Sum kostnader": c.ld_sum_kostnader,
            "Lokalt Kostnadsgrunnlag": c.ld_kostnadsgrunnlag,
            "Regionalt Årslønnjusterte D&V-kostnader uten utredningskostnader": c.rd_dv_wage,
            "Regionalt Nettapskostnad": c.rd_nettap,
            "Regionalt Kostnadsgrunnlag ": c.rd_kostnadsgrunnlag,
            "Transmisjonsnett Kostnadsgrunnlag": c.t_kostnadsgrunnlag,
        })

    # ------------------------------------------------------------------
    # ETL data output (same column names as original create_ETL_DataFrame)
    # ------------------------------------------------------------------
    def build_etl_dataframe(self) -> pd.DataFrame:
        d = self.data
        c = self.costs
        cfg = self.cfg

        k_norm_ld = self.dea_ld.kalibrert
        k_norm_rd = self.dea_rd.kalibrert + c.rd_nettap
        tillegg = d.kundetillegg
        ir_foer = self.calc_ir_foer_kalibrering()
        k_etter = self.calc_k_etter_kalibrering(k_norm_ld, k_norm_rd, tillegg)
        ir_etter = self.calc_ir_etter_kalibrering(c.kostnadsgrunnlag, k_etter)

        logger.info(
            "Sum IR: %.2f  Sum K: %.2f  Sum IR-K: %.2f  "
            "sum_ir_k/AKG (config): %s  sum_renter/AKG (config): %s  AKG total: %.2f",
            np.nansum(ir_foer),
            np.nansum(c.kostnadsgrunnlag),
            np.nansum(ir_foer) - np.nansum(c.kostnadsgrunnlag),
            cfg.sum_ir_k_per_akg,
            cfg.sum_renter_avvik_per_akg,
            np.nansum(c.akg),
        )

        df = pd.DataFrame({
            "Org.nr": d.orgn,
            "ID": d.id,
            "Selskap": d.comp,
            "rho": cfg.rho,
            "sum ir k per sum akg": cfg.sum_ir_k_per_akg,
            "sum renter avvik": cfg.sum_renter_avvik_per_akg,
            "inntektsramme 2026": pd.Series([pd.NA] * len(d.id)),
            "D&V-kostnader eks utredningskostnader": c.dv_total,
            "Årslønn-justerte D&V-kostnader eks utredningskostnader": c.dv_wage_adj,
            "AVS": c.avs,
            "BFV": c.bfv,
            "AKG (inkl 1 % arbeids-kapital)": c.akg,
            "Nettap MWh i LD": d.ld_nl,
            "Nettap MWh i RD": d.rd_nl,
            "Nettaps- kostnad i LD": c.ld_nettap,
            "Nettaps- kostnad i RD": c.rd_nettap,
            "KILE": c.kile,
            "KPI-justert KILE": c.kile_kpi,
            "Årslønn-justerte kostnader knyttet til utred.ansvar og KDS": d.rd_cga,
            "Sum kostnader": c.sum_kostnader,
            "Kostnadsgrunnlag": c.kostnadsgrunnlag,
            "K* lok distribusjonsnett": k_norm_ld,
            "K* reg distribusjonsnett": k_norm_rd,
            "Inntektsramme før kalibrering": ir_foer,
            "Tillegg i kostnadsnorm for kundevekst": tillegg,
            "K* etter kalibrering": k_etter,
            "Inntektsramme etter kalibrering": ir_etter,
            "Kraftpris kr/MWh": d.kraftpris,
        })

        return df


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    calc = RevenueCapCalculator()

    # Build both outputs
    ir_df = calc.build_ir_dataframe()
    etl_df = calc.build_etl_dataframe()

    # Show a quick slice of the ETL output
    print("\n--- ETL sample (first 5 rows) ---")
    with pd.option_context("display.max_columns", None, "display.width", 300):
        print(etl_df.head().to_string(index=False))

    etl_df.to_csv("inntektsrammer_kalibrert.csv", index=False, encoding="utf-8-sig")