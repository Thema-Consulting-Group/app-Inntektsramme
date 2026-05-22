"""
Inntektsramme Dashboard – Streamlit app
Run from the repo root:
    streamlit run app.py
"""

import io
import os
import sys
import subprocess
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yaml as _yaml

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent          # …/Inntektsramme

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.chdir(ROOT_DIR)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
_favicon_path = ROOT_DIR / "figures" / "favicon.ico"

st.set_page_config(
    page_title="Inntektsramme Dashboard",
    page_icon=str(_favicon_path) if _favicon_path.exists() else None,
    layout="wide",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.html("""
<style>
/* ── Typography ── */
h1 { font-size: 1.5rem !important; font-weight: 700 !important; letter-spacing: -0.02em; }
h2, [data-testid="stHeadingWithActionElements"] h2 { font-size: 1.05rem !important; font-weight: 600 !important; }
h3 { font-size: 0.92rem !important; font-weight: 600 !important; }

/* ── Metric cards ── */
[data-testid="stMetric"] {
    border: 1px solid #d1d5db; border-radius: 10px;
    padding: 14px 18px 12px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; text-transform: uppercase; letter-spacing: 0.03em; }
[data-testid="stMetricValue"] { font-size: 1.15rem !important; font-weight: 700 !important; }

/* ── Data tables – force light mode inside iframes ── */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border: 1px solid #d1d5db; border-radius: 8px; overflow: hidden;
}
[data-testid="stDataFrame"] iframe,
[data-testid="stDataEditor"] iframe { color-scheme: light !important; }

/* ── Buttons ── */
/* primary colour comes from config.toml primaryColor – only need hover here */
button[kind="primary"] { border-radius: 6px !important; font-weight: 600 !important; }
button[kind="secondary"] { border-radius: 6px !important; background: #e8eaef !important; color: #1f2937 !important; border: 1px solid #c9cdd4 !important; }
button[kind="secondary"]:hover { background: #dcdfe5 !important; }

/* ── Expanders – background from config secondaryBackgroundColor, add border ── */
section[data-testid="stExpander"] {
    border: 1px solid #d1d5db !important; border-radius: 10px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
}

/* ── Tabs – active colour from config primaryColor ── */
button[data-baseweb="tab"] { font-weight: 600 !important; }

/* ── Dividers ── */
hr { border-color: #d1d5db !important; }
</style>
""")

st.title("Inntektsramme")

# ---------------------------------------------------------------------------
# Pipeline navigation
# ---------------------------------------------------------------------------
if "active_step" not in st.session_state:
    st.session_state.active_step = 1
active_step = st.session_state.active_step

_nav_cols = st.columns(4)
for _ni, (_nlbl, _ncol) in enumerate(zip(
    ["1 · RME Modell", "2 · Prognosebygger", "3 · Kostnader", "4 · Frontselskapsanalyse"], _nav_cols,
)):
    with _ncol:
        if st.button(
            _nlbl, use_container_width=True, key=f"nav{_ni + 1}",
            type="primary" if active_step == _ni + 1 else "secondary",
        ):
            st.session_state.active_step = _ni + 1
            st.rerun()

CONFIG_PATH = ROOT_DIR / "config.yaml"


# ═══════════════════════════════════════════════════════════════════════
# STEG 1 – RME Modell & Inntektsramme 2026
# ═══════════════════════════════════════════════════════════════════════
if active_step == 1:

    def _run_python_calc():
        """Run inntektsramme Python calc and populate session state."""
        from inntektsramme import RevenueCapCalculator  # noqa: PLC0415
        rc = RevenueCapCalculator()
        result_df = rc.build_etl_dataframe()
        ir_df = rc.build_ir_dataframe()
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        # Step 1 results
        st.session_state.ir_all_df = result_df
        st.session_state.ir_base_df = ir_df
        st.session_state.ir_loaded_at = ts
        # Pre-populate Step 2 (prognose) so it doesn't need a separate load
        st.session_state.prognose_base_df = result_df
        st.session_state.prognose_ir_df = ir_df
        st.session_state.prognose_ref_base = rc.cfg.referanserente
        st.session_state.prognose_loaded_at = ts

    # ── Action buttons ───────────────────────────────────────────────
    _b1, _b2, _ = st.columns([2, 2, 4])
    with _b1:
        run_full = st.button("▶  Kjør RME Modell", key="run_full", type="primary")
    with _b2:
        _ir_loaded = "ir_all_df" in st.session_state
        refresh_ir = st.button(
            "Oppdater inntektsramme", key="refresh_ir",
            disabled=not _ir_loaded,
        )

    # ── Grunnlagsdata drag-and-drop ──────────────────────────────────
    with st.expander(
        "📂 Last opp grunnlagsdata (valgfritt – erstatter BaseData fra R-kjøring)",
        expanded="uploaded_grunnlagsdata_csv" in st.session_state,
    ):
        _uploaded_file = st.file_uploader(
            "Dra og slipp en grunnlagsdata CSV-fil her, eller klikk for å velge",
            type=["csv"],
            key="grunnlagsdata_uploader",
            label_visibility="collapsed",
            help="Filen skal ha samme kolonnestruktur som grunnlagsdata.csv fra en R-kjøring (orgn, y, id, comp, ld_*, rd_*, …)",
        )
        if _uploaded_file is not None:
            _upload_dest = ROOT_DIR / "Data" / "grunnlagsdata_uploaded.csv"
            _upload_dest.write_bytes(_uploaded_file.getvalue())
            st.session_state["uploaded_grunnlagsdata_csv"] = str(_upload_dest)
            st.success(f"Lastet opp: **{_uploaded_file.name}** → brukes som grunnlagsdata")
        elif "uploaded_grunnlagsdata_csv" in st.session_state:
            _existing = Path(st.session_state["uploaded_grunnlagsdata_csv"])
            _col_info, _col_btn = st.columns([4, 1])
            _col_info.caption(f"Aktiv fil: `{_existing.name}`")
            if _col_btn.button("Fjern", key="remove_uploaded_grunn"):
                del st.session_state["uploaded_grunnlagsdata_csv"]
                if _existing.exists():
                    _existing.unlink()
                st.rerun()

    _status_container = st.container()

    # ── Run full R pipeline ─────────────────────────────────────────
    if run_full:
        with _status_container:
            st.info("Starter R-pipeline – dette kan ta flere minutter …")
        log_lines: list[str] = []
        start = time.time()
        irir_script = ROOT_DIR / "IRiR.R"
        r_ok = False

        if not irir_script.exists():
            st.error(f"Finner ikke IRiR.R i {ROOT_DIR}")
        else:
            import shutil
            rscript = shutil.which("Rscript")
            if not rscript:
                st.error(
                    "Finner ikke **Rscript** på PATH. "
                    "Installer R (https://cran.r-project.org) og legg til `bin/` i PATH."
                )
                st.stop()

            with st.spinner("Kjører Rscript IRiR.R – dette kan ta lang tid …"):
                # Patterns to suppress (package startup noise)
                _suppress_patterns = (
                    "── Attaching", "✔ ", "✖ ", "── Conflicts", "ℹ ", "Registered S3",
                    "The following object", "The following packages", "tidyverse",
                    "Loading required package:", "character(0)",
                    '[1] "C:/', '[1] "/',
                )
                proc = subprocess.Popen(
                    [rscript, "--quiet", "IRiR.R"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    cwd=str(ROOT_DIR),
                )
                for line in proc.stdout:
                    _stripped = line.rstrip()
                    if _stripped and not any(_stripped.startswith(p) or p in _stripped for p in _suppress_patterns):
                        log_lines.append(_stripped)
                    _status_container.text("\n".join(log_lines[-20:]))
                proc.wait()

            elapsed = time.time() - start

            if proc.returncode == 0:
                r_ok = True
                st.success(f"RME Modell fullført på {elapsed:.1f} sekunder")

                # Show the new run directory and its files
                run_dirs = sorted(
                    [d for d in (ROOT_DIR / "Results").iterdir() if d.is_dir() and d.name.startswith("Run_")],
                    reverse=True,
                )
                if run_dirs:
                    latest = run_dirs[0]
                    files = sorted(latest.iterdir())
                    file_lines = ("\n\n" + "\n".join(f"- `{f.name}` ({f.stat().st_size:,} bytes)" for f in files)) if files else ""
                    st.success(f"📁 Siste resultater lagret i: `{latest.name}`{file_lines}")
            else:
                st.error(f"❌ Pipeline feilet (exit code {proc.returncode}) etter {elapsed:.1f} sekunder.")

            with st.expander("📋 Fullt logg", expanded=False):
                st.text("\n".join(log_lines))

        # Auto-run Python calc after successful R run
        if r_ok:
            with st.spinner("Beregner inntektsramme …"):
                try:
                    _run_python_calc()
                    st.rerun()
                except Exception as _e:
                    st.error(f"Feil i inntektsrammeberegning: {_e}")

    # ── Refresh Python calc only ────────────────────────────────────
    if refresh_ir:
        with st.spinner("Beregner inntektsramme …"):
            try:
                _run_python_calc()
                st.rerun()
            except Exception as _e:
                st.error(f"Feil: {_e}")

    # ── Inntektsramme 2026 – Resultater ────────────────────────────
    if "ir_all_df" in st.session_state:
        _ts1 = st.session_state.get("ir_loaded_at", "ukjent tid")
        st.caption(f"Beregnet kl. {_ts1}. Endre konfigurasjon nedenfor og klikk **Oppdater inntektsramme**.")

        _r_df: pd.DataFrame = st.session_state.ir_all_df
        _r_ir: pd.DataFrame = st.session_state.ir_base_df

        _rc1, _rc2, _rc3 = st.columns(3)
        _rc1.metric("Antall selskaper", len(_r_df))
        if "Kostnadsgrunnlag" in _r_df.columns:
            _rc2.metric("Sum Kostnadsgrunnlag", f"{_r_df['Kostnadsgrunnlag'].sum():,.0f}")
        if "Inntektsramme etter kalibrering" in _r_df.columns:
            _rc3.metric("Sum IR (etter kalibrering)", f"{_r_df['Inntektsramme etter kalibrering'].sum():,.0f}")

        st.dataframe(_r_df, use_container_width=True, height=480)
        _dl1c, _dl2c, _ = st.columns([1, 1, 5])
        with _dl1c:
            st.download_button(
                "CSV", key="dl_csv1",
                data=_r_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name="inntektsrammer_etl.csv", mime="text/csv",
            )
        with _dl2c:
            _buf1 = io.BytesIO()
            with pd.ExcelWriter(_buf1, engine="openpyxl") as w:
                _r_df.to_excel(w, index=False, sheet_name="ETL")
                _r_ir.to_excel(w, index=False, sheet_name="Grunnlagsdata")
            st.download_button(
                "Excel", key="dl_xlsx1",
                data=_buf1.getvalue(),
                file_name="inntektsrammer_etl.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        st.info(
            "Klikk **Kjør RME Modell** for å kjøre R-modellen og beregne inntektsrammer for 2026."
        )

    # ── Konfigurasjon ────────────────────────────────────────────────
    with st.expander("Konfigurasjon", expanded=False):
        _cfg_raw: dict = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        _foru = _cfg_raw.get("forutsetninger", {})
        _fp   = _foru.get("finansparametere", {})
        _cal  = _cfg_raw.get("kalibrering", {})
        _kpi  = _foru.get("kpi_justering", {})
        _wage = _foru.get("aarslonn", {})

        col_fp, col_gen = st.columns(2)

        with col_fp:
            st.subheader("Finansparametere")
            fp_df = pd.DataFrame(
                [{"Parameter": k, "Verdi": float(v)} for k, v in _fp.items()],
                columns=["Parameter", "Verdi"],
            )
            edited_fp = st.data_editor(
                fp_df,
                use_container_width=True,
                hide_index=True,
                disabled=["Parameter"],
                column_config={"Verdi": st.column_config.NumberColumn(format="%.4f")},
                key="fp_editor",
            )
            _ev = edited_fp.set_index("Parameter")["Verdi"]
            try:
                _r = (
                    (1 - _ev["gjeldsandel"])
                    * (_ev["noytral_realrente"] + _ev["inflasjon"] + _ev["ek-beta"] * _ev["markedspremie"])
                    / (1 - _ev["skatt"])
                    + _ev["gjeldsandel"] * (_ev["swap"] + _ev["kredittpremie"])
                ) / 100
            except KeyError:
                _r = float("nan")
            st.metric("Referanserente (beregnet)", f"{_r * 100:.2f} %")

        with col_gen:
            st.subheader("Generelle forutsetninger")
            gen_df = pd.DataFrame([
                {"Parameter": "rho",          "Verdi": float(_foru.get("rho", 0.70))},
                {"Parameter": "KPI 2024",     "Verdi": float(_kpi.get(2024, 133.6))},
                {"Parameter": "KPI 2026",     "Verdi": float(_kpi.get(2026, 140.6))},
                {"Parameter": "Årslønn 2024", "Verdi": float(_wage.get(2024, 129.9))},
                {"Parameter": "Årslønn 2026", "Verdi": float(_wage.get(2026, 141.7))},
            ])
            edited_gen = st.data_editor(
                gen_df,
                use_container_width=True,
                hide_index=True,
                disabled=["Parameter"],
                column_config={"Verdi": st.column_config.NumberColumn(format="%.2f")},
                key="gen_editor",
            )
            new_rho       = float(edited_gen.loc[edited_gen["Parameter"] == "rho",          "Verdi"].iloc[0])
            new_kpi_2024  = float(edited_gen.loc[edited_gen["Parameter"] == "KPI 2024",     "Verdi"].iloc[0])
            new_kpi_2026  = float(edited_gen.loc[edited_gen["Parameter"] == "KPI 2026",     "Verdi"].iloc[0])
            new_wage_2024 = float(edited_gen.loc[edited_gen["Parameter"] == "Årslønn 2024", "Verdi"].iloc[0])
            new_wage_2026 = float(edited_gen.loc[edited_gen["Parameter"] == "Årslønn 2026", "Verdi"].iloc[0])

        col_kal, col_fil = st.columns(2)

        with col_kal:
            st.subheader("Kalibreringskonstanter (i prosent)")
            new_ir_k = st.number_input(
                "Sum (IR−K) / sum AKG  [%]",
                value=float(_cal.get("sum_ir_k_per_sum_akg_pct", -0.023)),
                step=0.001, format="%.3f", key="ir_k",
            )
            new_renter = st.number_input(
                "Sum renter-avvik / sum AKG  [%]",
                value=float(_cal.get("sum_renter_avvik_per_sum_akg_pct", -0.098)),
                step=0.001, format="%.3f", key="renter",
            )

        with col_fil:
            st.subheader("Filstier")
            new_irir = st.text_input("irir_results_path",       value=_cfg_raw.get("irir_results_path", ""),       key="p_irir")
            new_ld   = st.text_input("data_resultater_ld_path", value=_cfg_raw.get("data_resultater_ld_path", ""), key="p_ld")
            new_rd   = st.text_input("data_resultater_rd_path", value=_cfg_raw.get("data_resultater_rd_path", ""), key="p_rd")

        cs, cr, c_toggle = st.columns([1, 1, 2])
        with cs:
            save = st.button("Lagre konfigurasjon", type="primary", key="cfg_save")
        with cr:
            if st.button("Tilbakestill", key="cfg_reset"):
                for key in ("fp_editor", "gen_editor", "ir_k", "renter", "p_irir", "p_ld", "p_rd"):
                    st.session_state.pop(key, None)
                st.rerun()
        with c_toggle:
            _save_to_file = st.toggle("Lagre til config.yaml", value=False, key="cfg_save_to_file",
                                      help="AV = kun session, PÅ = persisterer til config.yaml")

        if save:
            if _save_to_file:
                new_fp = {row["Parameter"]: row["Verdi"] for _, row in edited_fp.iterrows()}
                _cfg_raw["irir_results_path"]        = new_irir
                _cfg_raw["data_resultater_ld_path"]  = new_ld
                _cfg_raw["data_resultater_rd_path"]  = new_rd
                _cfg_raw["forutsetninger"]["rho"]    = new_rho
                _cfg_raw["forutsetninger"]["finansparametere"] = new_fp
                _cfg_raw["forutsetninger"]["kpi_justering"]    = {2024: new_kpi_2024, 2026: new_kpi_2026}
                _cfg_raw["forutsetninger"]["aarslonn"]         = {2024: new_wage_2024, 2026: new_wage_2026}
                _cfg_raw["kalibrering"]["sum_ir_k_per_sum_akg_pct"]       = new_ir_k
                _cfg_raw["kalibrering"]["sum_renter_avvik_per_sum_akg_pct"] = new_renter
                CONFIG_PATH.write_text(
                    _yaml.dump(_cfg_raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
                    encoding="utf-8",
                )
                st.success("config.yaml lagret — klikk **Oppdater inntektsramme** for å rekalkulere.")
            else:
                st.info("Endringer lagret for denne sesjonen (config.yaml ikke endret)")



# ═══════════════════════════════════════════════════════════════════════
# STEG 2 – Prognosebygger
# ═══════════════════════════════════════════════════════════════════════
if active_step == 2:
    from prognose import (  # noqa: PLC0415
        PrognoseCalculator, FORECAST_YEARS,
        DEFAULT_FORUTSETNINGER, DEFAULT_INVESTERINGER, DEFAULT_DV_VEKST,
        load_investeringer_for_company, build_investeringer_from_model,
    )

    def _prepend_historical(grunn_df: pd.DataFrame, csv_path: str, etl_row: dict) -> pd.DataFrame:
        """Prepend historical year columns from grunnlagsdata.csv to the forecast table."""
        try:
            raw = pd.read_csv(csv_path).fillna(0)
        except Exception:
            return grunn_df

        orgn = int(etl_row.get("Org.nr", etl_row.get("orgn", 0)))
        if orgn == 0:
            return grunn_df
        comp = raw[raw["orgn"] == orgn]
        if comp.empty:
            return grunn_df

        hist_years = sorted(comp["y"].unique())
        forecast_year_cols = [c for c in grunn_df.columns if isinstance(c, int)]
        # Only keep historical years not already in the forecast
        hist_years = [y for y in hist_years if int(y) not in forecast_year_cols]
        if not hist_years:
            return grunn_df

        # Mapping from (Parameter, Nettnivå) → how to compute from raw columns
        # Uses the same raw column names as grunnlagsdata.csv
        _hist_formula: dict[tuple[str, str], list[tuple[str, int]]] = {
            ("D&V-kost. ekskl. lønn", "Distribusjon"): [("ld_OPEXxS", +1)],
            ("Lønnskost. ekskl. pensjon", "Distribusjon"): [("ld_sal", +1)],
            ("Aktiverte lønnskost.", "Distribusjon"): [("ld_sal.cap", +1)],
            ("Pensjonskost. periodisert", "Distribusjon"): [("ld_pens", +1)],
            ("Pensjonkost. ført mot egenkapital: impl", "Distribusjon"): [("ld_impl", +1)],
            ("Pensjonkost. ført mot egenkapital: estimatavvik", "Distribusjon"): [("ld_pens.eq", +1)],
            ("Bokførte verdier egenfinansiert", "Distribusjon"): [("ld_bv.sf", +1)],
            ("Bokførte verdier kundefinansiert", "Distribusjon"): [("ld_bv.gf", +1)],
            ("Avskrivninger egenfinansiert", "Distribusjon"): [("ld_dep.sf", +1)],
            ("Avskrivninger kundefinansiert", "Distribusjon"): [("ld_dep.gf", +1)],
            ("KILE", "Distribusjon"): [("ld_cens", +1)],
            ("Nettap", "Distribusjon"): [("ld_nl", +1)],
            ("Høyspentnett", "Distribusjon"): [("ld_hv", +1)],
            ("Nettstasjoner", "Distribusjon"): [("ld_ss", +1)],
            ("Nettkunder", "Distribusjon"): [("ld_sub", +1)],
            ("Andre driftsinntekter", "Distribusjon"): [],
            ("D&V-kost. ekskl. lønn", "Regional"): [("rd_OPEXxS", +1)],
            ("Lønnskost. ekskl. pensjon", "Regional"): [("rd_sal", +1)],
            ("Aktiverte lønnskost.", "Regional"): [("rd_sal.cap", +1)],
            ("Pensjonskost. periodisert", "Regional"): [("rd_pens", +1)],
            ("Pensjonkost. ført mot egenkapital: impl", "Regional"): [("rd_impl", +1)],
            ("Pensjonkost. ført mot egenkapital: estimatavvik", "Regional"): [("rd_pens.eq", +1)],
            ("Bokførte verdier egenfinansiert", "Regional"): [("rd_bv.sf", +1)],
            ("Bokførte verdier kundefinansiert", "Regional"): [("rd_bv.gf", +1)],
            ("Avskrivninger egenfinansiert", "Regional"): [("rd_dep.sf", +1)],
            ("Avskrivninger kundefinansiert", "Regional"): [("rd_dep.gf", +1)],
            ("KILE", "Regional"): [("rd_cens", +1)],
            ("Nettap", "Regional"): [("rd_nl", +1)],
            ("Utredningskostnader", "Regional"): [("rd_coord", +1)],
            ("Vekt luftlinjer", "Regional"): [("rd_wv.ol", +1)],
            ("Vekt jordkabler", "Regional"): [("rd_wv.uc", +1)],
            ("Vekt sjøkabler", "Regional"): [("rd_wv.sc", +1)],
            ("Vekt stasjonsvariabel", "Regional"): [("rd_wv.ss", +1)],
            ("Andre driftsinntekter", "Regional"): [],
        }

        for idx, row in grunn_df.iterrows():
            key = (row["Parameter"], row["Nettnivå"])
            formula = _hist_formula.get(key)
            if formula is None:
                continue
            for yr in hist_years:
                yr_row = comp[comp["y"] == yr]
                if yr_row.empty:
                    continue
                yr_data = yr_row.iloc[0]
                val = sum(sign * float(yr_data.get(col, 0) or 0) for col, sign in formula)
                grunn_df.at[idx, int(yr)] = round(val, 2)

        # Reorder columns: meta + historical years + forecast years
        meta = [c for c in grunn_df.columns if not isinstance(c, int)]
        year_cols = sorted([c for c in grunn_df.columns if isinstance(c, int)])
        grunn_df = grunn_df[meta + year_cols]
        return grunn_df

    _YEARS = FORECAST_YEARS  # 2026–2035

    _cfg4_raw: dict = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    _prog_cfg: dict = _cfg4_raw.get("prognose", {})

    # ── Load / refresh base data ─────────────────────────────────────
    def _load_base_data():
        from inntektsramme import RevenueCapCalculator  # noqa: PLC0415
        _rc = RevenueCapCalculator()
        _result = _rc.build_etl_dataframe()
        _ir = _rc.build_ir_dataframe()
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        st.session_state.prognose_base_df  = _result
        st.session_state.prognose_ir_df    = _ir
        st.session_state.prognose_ref_base = _rc.cfg.referanserente
        st.session_state.prognose_loaded_at = ts
        # Keep Step 1 results in sync
        st.session_state.ir_all_df = _result
        st.session_state.ir_base_df = _ir
        st.session_state.ir_loaded_at = ts

    _loaded = "prognose_base_df" in st.session_state
    if not _loaded:
        st.info("Beregningsgrunnlaget er ikke lastet. Gå til **Steg 1** eller klikk **Last inn**.")
        if st.button("Last inn", key="load_prog", type="primary"):
            with st.spinner("Kjører inntektsrammemodellen …"):
                try:
                    _load_base_data()
                    st.rerun()
                except Exception as _e:
                    st.error(f"Feil: {_e}")
        st.stop()

    _base_df: pd.DataFrame  = st.session_state.prognose_base_df
    _ref_base: float        = st.session_state.get("prognose_ref_base", 0.072)
    _ref_base_pct: float    = round(_ref_base * 100, 2)

    _ir_df: pd.DataFrame    = st.session_state.get("prognose_ir_df", _base_df)

    # ── Company selector ─────────────────────────────────────────────
    _all_comp = _base_df["Selskap"].tolist()
    _saved_id = _prog_cfg.get("selskap_id")
    _default_idx = 0
    if _saved_id and _saved_id in _base_df["ID"].tolist():
        _default_idx = _base_df["ID"].tolist().index(_saved_id)
    _sel_comp = st.selectbox("Velg selskap", _all_comp, index=_default_idx, key="prog_comp", label_visibility="collapsed")

    # Detect company change and clear editor widget states so they
    # pick up fresh defaults for the newly selected company.
    if "prev_prog_comp" not in st.session_state:
        st.session_state.prev_prog_comp = _sel_comp
    elif st.session_state.prev_prog_comp != _sel_comp:
        for _k in ("foru_editor", "inv_editor", "dv_editor",
                    "avs_sats4", "lab_ld", "lab_rd", "rho4"):
            st.session_state.pop(_k, None)
        st.session_state.prev_prog_comp = _sel_comp
        st.rerun()

    _sel_mask = _base_df["Selskap"] == _sel_comp
    _base_etl_row: dict = _base_df.loc[_sel_mask].iloc[0].to_dict()
    _base_ir_row: dict  = _ir_df.loc[_ir_df["Selskap"] == _sel_comp].iloc[0].to_dict()

    # Resolve grunnlagsdata.csv early so tab_foru can reference it
    # Prefer user-uploaded file if present
    _grunnlagsdata_csv: str | None = st.session_state.get("uploaded_grunnlagsdata_csv")
    if _grunnlagsdata_csv and not Path(_grunnlagsdata_csv).exists():
        # Stale path (file was removed externally) – clear session state
        del st.session_state["uploaded_grunnlagsdata_csv"]
        _grunnlagsdata_csv = None
    if not _grunnlagsdata_csv:
        _irir_path_early = _cfg4_raw.get("irir_results_path", "")
        if _irir_path_early:
            _run_dir_early = (ROOT_DIR / _irir_path_early).parent
            _csv_early = sorted(_run_dir_early.glob("*grunnlagsdata.csv"), reverse=True)
            if _csv_early:
                _grunnlagsdata_csv = str(_csv_early[0])
    if not _grunnlagsdata_csv:
        _run_dirs_early = sorted(
            [d for d in (ROOT_DIR / "Results").iterdir() if d.is_dir() and d.name.startswith("Run_")],
            reverse=True,
        )
        for _rd_early in _run_dirs_early:
            _cands = sorted(_rd_early.glob("*grunnlagsdata.csv"), reverse=True)
            if _cands:
                _grunnlagsdata_csv = str(_cands[0])
                break

    # Generate/refresh investeringer_from_model.csv whenever grunnlagsdata is available
    if _grunnlagsdata_csv:
        _inv_model_path = str(ROOT_DIR / "Data" / "investeringer_from_model.csv")
        if ("_inv_model_generated" not in st.session_state
                or st.session_state.get("_inv_model_source") != _grunnlagsdata_csv):
            try:
                build_investeringer_from_model(
                    grunnlagsdata_csv=_grunnlagsdata_csv,
                    forutsetninger=_prog_cfg.get("forutsetninger"),
                    output_path=_inv_model_path,
                )
                st.session_state["_inv_model_generated"] = True
                st.session_state["_inv_model_source"] = _grunnlagsdata_csv
            except Exception:
                pass

    # ==================================================================
    #  TABS
    # ==================================================================
    tab_foru, tab_grunn, tab_res = st.tabs(
        ["Forutsetninger", "Grunnlagsdata", "Resultater"]
    )

    # Saved prognose sub-keys — only reuse when the saved company matches
    _sel_id4 = int(_base_df.loc[_sel_mask, "ID"].iloc[0])
    _saved_matches = (_prog_cfg.get("selskap_id") == _sel_id4)
    _saved_f   = _prog_cfg.get("forutsetninger", {})            # assumptions are company-agnostic
    _saved_inv = _prog_cfg.get("investeringer", {}) if _saved_matches else {}
    _saved_dv  = _prog_cfg.get("dv_vekst", {})     if _saved_matches else {}

    # ──────────────────────────────────────────────────────────────────
    #  TAB 1 — Forutsetninger
    # ──────────────────────────────────────────────────────────────────
    with tab_foru:
        # ── Base year KPIs ───────────────────────────────────────────────
        with st.expander("Basisår 2026 – Nøkkeltall", expanded=False):
            _sk = [
                "Kostnadsgrunnlag", "Inntektsramme etter kalibrering",
                "AKG (inkl 1 % arbeids-kapital)", "AVS",
                "D&V-kostnader eks utredningskostnader", "KPI-justert KILE",
                "Nettap MWh i LD", "Nettap MWh i RD", "Kraftpris kr/MWh",
            ]
            _sc = st.columns(3)
            for _i, _k in enumerate([k for k in _sk if k in _base_etl_row]):
                with _sc[_i % 3]:
                    _vv = _base_etl_row[_k]
                    st.metric(_k, f"{_vv:,.0f}" if isinstance(_vv, (int, float)) else str(_vv))
        st.subheader("Forutsetninger")

        # Build editable table: rows = parameters, cols = years
        _foru_params = ["KPI (%)", "KPI lønn (%)", "NVE-rente (%)", "Kraftpris (kr/MWh)"]
        _foru_keys = ["kpi", "kpi_lonn", "nve_rente", "kraftpris"]

        _foru_data: dict[str, list] = {"Parameter": _foru_params}
        for y in _YEARS:
            col_vals = []
            for fk in _foru_keys:
                saved_val = _saved_f.get(fk, {}).get(y)
                default_val = DEFAULT_FORUTSETNINGER[fk].get(y, 0)
                col_vals.append(float(saved_val) if saved_val is not None else float(default_val))
            _foru_data[str(y)] = col_vals

        _foru_df = pd.DataFrame(_foru_data)
        _edited_foru = st.data_editor(
            _foru_df, use_container_width=True, hide_index=True,
            disabled=["Parameter"],
            column_config={str(y): st.column_config.NumberColumn(format="%.2f") for y in _YEARS},
            key="foru_editor",
        )

        # Parse back into dicts
        def _parse_foru_row(row_idx: int) -> dict[int, float]:
            return {y: float(_edited_foru.at[row_idx, str(y)]) for y in _YEARS}

        _f_kpi      = _parse_foru_row(0)
        _f_kpi_lonn = _parse_foru_row(1)
        _f_nve      = _parse_foru_row(2)
        _f_kraft    = _parse_foru_row(3)

        forutsetninger_dict = {
            "kpi": _f_kpi, "kpi_lonn": _f_kpi_lonn,
            "nve_rente": _f_nve, "kraftpris": _f_kraft,
        }

        # ── Investeringer per nettnivå ───────────────────────────────
        st.subheader("Investeringer per nettnivå")

        _inv_model_csv_path = ROOT_DIR / "Data" / "investeringer_from_model.csv"
        _sel_orgn = int(_base_etl_row.get("Org.nr", _base_etl_row.get("orgn", 0)))
        _has_model_inv = False
        _model_inv_years: list[int] = []
        _model_ld: dict[int, float] = {}
        _model_rd: dict[int, float] = {}
        _bfv_ld: dict[int, float] = {}
        _bfv_rd: dict[int, float] = {}
        _inv_nok_dict: dict = {}  # Will hold edited NOK investments if model data exists

        # Company-specific session state keys for edited investments
        _inv_ld_key = f"inv_edited_ld_{_sel_id4}"
        _inv_rd_key = f"inv_edited_rd_{_sel_id4}"

        # Load BFV values from grunnlagsdata for % calculation
        if _grunnlagsdata_csv:
            try:
                _gdf = pd.read_csv(_grunnlagsdata_csv).fillna(0)
                _gdf_comp = _gdf[_gdf["orgn"] == _sel_orgn]
                if not _gdf_comp.empty:
                    for _, _gr in _gdf_comp.iterrows():
                        _yr = int(_gr.get("y", 0))
                        _bfv_ld[_yr] = float(_gr.get("ld_bv.sf", 0)) + float(_gr.get("ld_bv.gf", 0))
                        _bfv_rd[_yr] = float(_gr.get("rd_bv.sf", 0)) + float(_gr.get("rd_bv.gf", 0))
            except Exception:
                pass

        if _inv_model_csv_path.exists() and _sel_orgn:
            try:
                _mdf = pd.read_csv(_inv_model_csv_path, sep=";").fillna(0)
                _mdf_comp = _mdf[_mdf["orgn"] == _sel_orgn]
                if not _mdf_comp.empty:
                    _yr_cols = [c for c in _mdf_comp.columns if c.isdigit()]
                    _model_inv_years = [int(c) for c in _yr_cols]
                    for _yr in _model_inv_years:
                        _ld_rows = _mdf_comp[_mdf_comp["nettnivaa"] == "ld"]
                        _rd_rows = _mdf_comp[_mdf_comp["nettnivaa"] == "rd"]
                        _model_ld[_yr] = float(_ld_rows[str(_yr)].sum())
                        _model_rd[_yr] = float(_rd_rows[str(_yr)].sum())
                    _has_model_inv = True
            except Exception:
                pass

        if _has_model_inv:
            _hist_yr_cols = [y for y in _model_inv_years if y < _YEARS[0]]
            _fcst_yr_cols = [y for y in _model_inv_years if y >= _YEARS[0]]
            
            # Initialize session state for edited investments (company-specific keys)
            if _inv_ld_key not in st.session_state:
                st.session_state[_inv_ld_key] = {y: _model_ld.get(y, 0) for y in _model_inv_years}
            if _inv_rd_key not in st.session_state:
                st.session_state[_inv_rd_key] = {y: _model_rd.get(y, 0) for y in _model_inv_years}

            # Editable investment table (NOK) – only historical years editable, forecast auto-calc from 5yr avg
            _inv_edit_df = pd.DataFrame({
                "År": _model_inv_years,
                "Dnett (1000 NOK)": [st.session_state[_inv_ld_key].get(y, _model_ld.get(y, 0)) for y in _model_inv_years],
                "Rnett (1000 NOK)": [st.session_state[_inv_rd_key].get(y, _model_rd.get(y, 0)) for y in _model_inv_years],
            })

            _c_inv, _c_inv_chart = st.columns([2, 3])
            with _c_inv:
                st.caption("Rediger alle år direkte. Klikk **Auto-beregn** for å beregne prognoseår fra 5-årig historisk gjennomsnitt.")
                _auto_calc_btn = st.button("Auto-beregn", key=f"auto_inv_{_sel_id4}", help="Beregner prognoseår fra 5-årig historisk gjennomsnitt")
                _inv_edit_cols = {"År": st.column_config.NumberColumn(format="%d", disabled=True)}
                for _col in ["Dnett (1000 NOK)", "Rnett (1000 NOK)"]:
                    _inv_edit_cols[_col] = st.column_config.NumberColumn(format="%.0f")
                _inv_edited = st.data_editor(
                    _inv_edit_df, hide_index=True, use_container_width=True,
                    column_config=_inv_edit_cols, key=f"inv_nok_editor_{_sel_id4}",
                )
                
                # Update session state from edited values
                for _, _row in _inv_edited.iterrows():
                    _yr = int(_row["År"])
                    _ld_val = float(_row["Dnett (1000 NOK)"])
                    _rd_val = float(_row["Rnett (1000 NOK)"])
                    st.session_state[_inv_ld_key][_yr] = _ld_val
                    st.session_state[_inv_rd_key][_yr] = _rd_val
                
                # Recalculate forecast years from edited dataframe (not session state to avoid caching issues)
                _ld_hist = [float(_inv_edited.loc[_inv_edited["År"] == y, "Dnett (1000 NOK)"].iloc[0]) 
                            if y in _inv_edited["År"].values else _model_ld.get(y, 0) for y in _hist_yr_cols]
                _rd_hist = [float(_inv_edited.loc[_inv_edited["År"] == y, "Rnett (1000 NOK)"].iloc[0])
                            if y in _inv_edited["År"].values else _model_rd.get(y, 0) for y in _hist_yr_cols]
                _ld_avg_5yr = float(np.mean(_ld_hist[-5:] if len(_ld_hist) >= 5 else _ld_hist)) if _ld_hist else 0
                _rd_avg_5yr = float(np.mean(_rd_hist[-5:] if len(_rd_hist) >= 5 else _rd_hist)) if _rd_hist else 0
                
                # Build auto-calc forecast values (for chart + auto-beregn button)
                _kpi_series = forutsetninger_dict.get("kpi", {})
                _kpi_cum = 1.0
                _fcst_ld_vals = {}
                _fcst_rd_vals = {}
                for _yr in _fcst_yr_cols:
                    _kpi_pct = float(_kpi_series.get(_yr, 2.0)) / 100
                    _kpi_cum *= (1 + _kpi_pct)
                    _fcst_ld_vals[_yr] = round(_ld_avg_5yr * _kpi_cum, 1)
                    _fcst_rd_vals[_yr] = round(_rd_avg_5yr * _kpi_cum, 1)

                # Reactively update forecast rows when historical values change
                _hist_hash = hash(tuple(
                    (y, round(_ld_hist[i], 1), round(_rd_hist[i], 1))
                    for i, y in enumerate(_hist_yr_cols)
                ))
                _hist_hash_key = f"inv_hist_hash_{_sel_id4}"
                if st.session_state.get(_hist_hash_key) != _hist_hash:
                    st.session_state[_hist_hash_key] = _hist_hash
                    for _yr in _fcst_yr_cols:
                        st.session_state[_inv_ld_key][_yr] = _fcst_ld_vals[_yr]
                        st.session_state[_inv_rd_key][_yr] = _fcst_rd_vals[_yr]
                    st.session_state.pop(f"inv_nok_editor_{_sel_id4}", None)
                    st.rerun()

                # Auto-beregn button also resets forecast rows
                if _auto_calc_btn:
                    for _yr in _fcst_yr_cols:
                        st.session_state[_inv_ld_key][_yr] = _fcst_ld_vals[_yr]
                        st.session_state[_inv_rd_key][_yr] = _fcst_rd_vals[_yr]
                    st.session_state.pop(f"inv_nok_editor_{_sel_id4}", None)
                    st.rerun()

            with _c_inv_chart:
                # Toggle: absolute vs percent
                _c_tog1, _c_tog2 = st.columns([1, 1])
                with _c_tog1:
                    _show_pct = st.toggle("Vis % av BFV", value=False, key="inv_pct_toggle")
                
                # Calculate % values if shown
                if _show_pct:
                    _ld_pct = {}
                    _rd_pct = {}
                    for _yr in _hist_yr_cols:
                        _bfv_ld_yr = _bfv_ld.get(_yr, 1)
                        _bfv_rd_yr = _bfv_rd.get(_yr, 1)
                        _ld_val = float(_inv_edited.loc[_inv_edited["År"] == _yr, "Dnett (1000 NOK)"].iloc[0]) if _yr in _inv_edited["År"].values else 0
                        _rd_val = float(_inv_edited.loc[_inv_edited["År"] == _yr, "Rnett (1000 NOK)"].iloc[0]) if _yr in _inv_edited["År"].values else 0
                        _ld_pct[_yr] = (_ld_val / _bfv_ld_yr * 100) if _bfv_ld_yr > 0 else 0
                        _rd_pct[_yr] = (_rd_val / _bfv_rd_yr * 100) if _bfv_rd_yr > 0 else 0
                    for _yr in _fcst_yr_cols:
                        _bfv_ld_yr = _bfv_ld.get(_yr, 1)
                        _bfv_rd_yr = _bfv_rd.get(_yr, 1)
                        _ld_v2 = float(_inv_edited.loc[_inv_edited["År"] == _yr, "Dnett (1000 NOK)"].iloc[0]) if _yr in _inv_edited["År"].values else _fcst_ld_vals.get(_yr, 0)
                        _rd_v2 = float(_inv_edited.loc[_inv_edited["År"] == _yr, "Rnett (1000 NOK)"].iloc[0]) if _yr in _inv_edited["År"].values else _fcst_rd_vals.get(_yr, 0)
                        _ld_pct[_yr] = (_ld_v2 / _bfv_ld_yr * 100) if _bfv_ld_yr > 0 else 0
                        _rd_pct[_yr] = (_rd_v2 / _bfv_rd_yr * 100) if _bfv_rd_yr > 0 else 0
                    
                    _fig_inv = go.Figure()
                    _fig_inv.add_trace(go.Bar(
                        x=_hist_yr_cols,
                        y=[_ld_pct.get(y, 0) for y in _hist_yr_cols],
                        name="Dnett hist.", marker_color="#aac4b0", opacity=0.8,
                    ))
                    _fig_inv.add_trace(go.Bar(
                        x=_hist_yr_cols,
                        y=[_rd_pct.get(y, 0) for y in _hist_yr_cols],
                        name="Rnett hist.", marker_color="#d4e8da", opacity=0.8,
                    ))
                    _fig_inv.add_trace(go.Scatter(
                        x=_fcst_yr_cols, y=[_ld_pct.get(y, 0) for y in _fcst_yr_cols],
                        mode="lines+markers", name="Dnett prognose",
                        line=dict(color="#1a5632", width=2), marker=dict(size=7),
                    ))
                    _fig_inv.add_trace(go.Scatter(
                        x=_fcst_yr_cols, y=[_rd_pct.get(y, 0) for y in _fcst_yr_cols],
                        mode="lines+markers", name="Rnett prognose",
                        line=dict(color="#7ec89b", width=2), marker=dict(size=7),
                    ))
                    _fig_inv.update_layout(
                        height=260, margin=dict(l=40, r=15, t=25, b=25),
                        yaxis=dict(title="% av BFV", ticksuffix=" %"), xaxis=dict(dtick=1),
                        barmode="stack",
                        legend=dict(orientation="h", y=1.12), plot_bgcolor="#fafbfd",
                    )
                else:
                    # Absolute view (NOK) – use edited historical values + recalculated forecast
                    _fig_inv = go.Figure()
                    _fig_inv.add_trace(go.Bar(
                        x=_hist_yr_cols,
                        y=[float(_inv_edited.loc[_inv_edited["År"] == y, "Dnett (1000 NOK)"].iloc[0]) if y in _inv_edited["År"].values else 0 for y in _hist_yr_cols],
                        name="Dnett hist.", marker_color="#aac4b0", opacity=0.8,
                    ))
                    _fig_inv.add_trace(go.Bar(
                        x=_hist_yr_cols,
                        y=[float(_inv_edited.loc[_inv_edited["År"] == y, "Rnett (1000 NOK)"].iloc[0]) if y in _inv_edited["År"].values else 0 for y in _hist_yr_cols],
                        name="Rnett hist.", marker_color="#d4e8da", opacity=0.8,
                    ))
                    _fig_inv.add_trace(go.Scatter(
                        x=_fcst_yr_cols, y=[float(_inv_edited.loc[_inv_edited["År"] == y, "Dnett (1000 NOK)"].iloc[0]) if y in _inv_edited["År"].values else _fcst_ld_vals.get(y, 0) for y in _fcst_yr_cols],
                        mode="lines+markers", name="Dnett prognose",
                        line=dict(color="#1a5632", width=2), marker=dict(size=7),
                    ))
                    _fig_inv.add_trace(go.Scatter(
                        x=_fcst_yr_cols, y=[float(_inv_edited.loc[_inv_edited["År"] == y, "Rnett (1000 NOK)"].iloc[0]) if y in _inv_edited["År"].values else _fcst_rd_vals.get(y, 0) for y in _fcst_yr_cols],
                        mode="lines+markers", name="Rnett prognose",
                        line=dict(color="#7ec89b", width=2), marker=dict(size=7),
                    ))
                    _fig_inv.update_layout(
                        height=260, margin=dict(l=40, r=15, t=25, b=25),
                        yaxis=dict(title="1000 NOK"), xaxis=dict(dtick=1),
                        barmode="stack",
                        legend=dict(orientation="h", y=1.12), plot_bgcolor="#fafbfd",
                    )
                st.plotly_chart(_fig_inv, use_container_width=True)

            # Build edited investment dict for PrognoseCalculator — use what's in the table (edited or auto-calc)
            _inv_nok_dict = {
                "inv_sf_ld": {}, "inv_gf_ld": {}, "inv_sf_rd": {}, "inv_gf_rd": {}
            }
            for _yr in _YEARS:  # Forecast years only
                _ld_v = float(_inv_edited.loc[_inv_edited["År"] == _yr, "Dnett (1000 NOK)"].iloc[0]) if _yr in _inv_edited["År"].values else _fcst_ld_vals.get(_yr, 0)
                _rd_v = float(_inv_edited.loc[_inv_edited["År"] == _yr, "Rnett (1000 NOK)"].iloc[0]) if _yr in _inv_edited["År"].values else _fcst_rd_vals.get(_yr, 0)
                _inv_nok_dict["inv_sf_ld"][_yr] = _ld_v
                _inv_nok_dict["inv_gf_ld"][_yr] = 0
                _inv_nok_dict["inv_sf_rd"][_yr] = _rd_v
                _inv_nok_dict["inv_gf_rd"][_yr] = 0

            # Use % fallback as investeringer_dict (for old code)
            investeringer_dict = {"dnett_pct": {y: 0 for y in _YEARS}, "rnett_pct": {y: 0 for y in _YEARS}}

        else:
            # Fallback: no model data, show editable % table
            st.info("Historiske investeringsdata ikke tilgjengelig. Bruker % av BFV.", icon="⚠️")
            _sel_id_for_inv = int(_base_df.loc[_sel_mask, "ID"].iloc[0])
            _csv_inv = load_investeringer_for_company(_sel_id_for_inv)
            _inv_data = {"År": _YEARS}
            for net_key, net_label in [("dnett_pct", "Dnett"), ("rnett_pct", "Rnett")]:
                _inv_data[net_label] = [
                    float(_saved_inv.get(net_key, {}).get(y,
                          _csv_inv[net_key].get(y,
                          DEFAULT_INVESTERINGER[net_key].get(y, 0))))
                    for y in _YEARS
                ]
            _inv_df = pd.DataFrame(_inv_data)
            _c_inv, _c_inv_chart = st.columns([2, 3])
            with _c_inv:
                _edited_inv_df = st.data_editor(
                    _inv_df, hide_index=True, use_container_width=True, disabled=["År"],
                    column_config={
                        "Dnett": st.column_config.NumberColumn(format="%.1f %%"),
                        "Rnett": st.column_config.NumberColumn(format="%.1f %%"),
                    },
                    key="inv_editor",
                )
            with _c_inv_chart:
                _fig_inv = go.Figure()
                _fig_inv.add_trace(go.Scatter(
                    x=_edited_inv_df["År"], y=_edited_inv_df["Dnett"],
                    mode="lines+markers", name="Dnett",
                    line=dict(color="#1a5632", width=2), marker=dict(size=7),
                ))
                _fig_inv.add_trace(go.Scatter(
                    x=_edited_inv_df["År"], y=_edited_inv_df["Rnett"],
                    mode="lines+markers", name="Rnett",
                    line=dict(color="#7ec89b", width=2), marker=dict(size=7),
                ))
                _fig_inv.update_layout(
                    height=220, margin=dict(l=40, r=15, t=25, b=25),
                    yaxis=dict(title="%", ticksuffix=" %"), xaxis=dict(dtick=1),
                    legend=dict(orientation="h", y=1.12), plot_bgcolor="#fafbfd",
                )
                st.plotly_chart(_fig_inv, use_container_width=True)

            investeringer_dict = {
                "dnett_pct": {int(r["År"]): float(r["Dnett"]) for _, r in _edited_inv_df.iterrows()},
                "rnett_pct": {int(r["År"]): float(r["Rnett"]) for _, r in _edited_inv_df.iterrows()},
            }
            _inv_nok_dict = {}  # No edited NOK investments in fallback path

        # ── D&V vekst ────────────────────────────────────────────────
        st.subheader("Drifts- og vedlikeholdskostnader (vekst %)")
        _dv_data = {"År": _YEARS}
        for dk, dl in [("dv_ekskl_lonn_pct", "D&V ekskl. lønn"), ("lonn_ekskl_pensjon_pct", "Lønn ekskl. pensjon")]:
            _dv_data[dl] = [
                float(_saved_dv.get(dk, {}).get(y,
                      DEFAULT_DV_VEKST[dk].get(y, 2.5)))
                for y in _YEARS
            ]
        _dv_df = pd.DataFrame(_dv_data)
        _c_dv, _c_dv_chart = st.columns([2, 3])
        with _c_dv:
            _edited_dv_df = st.data_editor(
                _dv_df, hide_index=True, use_container_width=True, disabled=["År"],
                column_config={
                    "D&V ekskl. lønn": st.column_config.NumberColumn(format="%.1f %%"),
                    "Lønn ekskl. pensjon": st.column_config.NumberColumn(format="%.1f %%"),
                },
                key="dv_editor",
            )
        with _c_dv_chart:
            _fig_dv = go.Figure()
            _fig_dv.add_trace(go.Scatter(
                x=_edited_dv_df["År"], y=_edited_dv_df["D&V ekskl. lønn"],
                mode="lines+markers", name="D&V ekskl. lønn",
                line=dict(color="#e8a838", width=2), marker=dict(size=7),
            ))
            _fig_dv.add_trace(go.Scatter(
                x=_edited_dv_df["År"], y=_edited_dv_df["Lønn ekskl. pensjon"],
                mode="lines+markers", name="Lønn ekskl. pensjon",
                line=dict(color="#7eb8d4", width=2), marker=dict(size=7),
            ))
            _fig_dv.update_layout(
                height=220, margin=dict(l=40, r=15, t=25, b=25),
                yaxis=dict(title="%", ticksuffix=" %"), xaxis=dict(dtick=1),
                legend=dict(orientation="h", y=1.12), plot_bgcolor="#fafbfd",
            )
            st.plotly_chart(_fig_dv, use_container_width=True)

        dv_vekst_dict = {
            "dv_ekskl_lonn_pct": {int(r["År"]): float(r["D&V ekskl. lønn"]) for _, r in _edited_dv_df.iterrows()},
            "lonn_ekskl_pensjon_pct": {int(r["År"]): float(r["Lønn ekskl. pensjon"]) for _, r in _edited_dv_df.iterrows()},
        }

        # ── Advanced options ─────────────────────────────────────────
        with st.expander("Avanserte innstillinger", expanded=False):
            _ac1, _ac2, _ac3, _ac4 = st.columns(4)
            with _ac1:
                _avs_sats = st.number_input("Avskrivningssats %", 1.0, 10.0,
                    value=float(_prog_cfg.get("avs_sats", 4.0)), step=0.5, key="avs_sats4")
            with _ac2:
                _labor_ld = st.number_input("Lønnsandel D&V (LD)", 0.0, 1.0,
                    value=float(_prog_cfg.get("labor_share_ld", 0.30)), step=0.05, format="%.2f", key="lab_ld")
            with _ac3:
                _labor_rd = st.number_input("Lønnsandel D&V (RD)", 0.0, 1.0,
                    value=float(_prog_cfg.get("labor_share_rd", 0.30)), step=0.05, format="%.2f", key="lab_rd")
            with _ac4:
                _rho4 = st.number_input("Rho", 0.0, 1.0,
                    value=float(_cfg4_raw.get("forutsetninger", {}).get("rho", 0.7)),
                    step=0.05, format="%.2f", key="rho4")

        # ── Save / Reset / Download ──────────────────────────────────
        _sa, _sb, _sc, _ = st.columns([1, 1, 1, 4])
        with _sa:
            _save4 = st.button("Lagre", type="primary", key="save4")
        with _sb:
            if st.button("Tilbakestill", key="reset4"):
                for k in ("foru_editor", "inv_editor", "dv_editor",
                           "avs_sats4", "lab_ld", "lab_rd", "rho4"):
                    st.session_state.pop(k, None)
                st.rerun()
        with _sc:
            st.download_button(
                "CSV",
                data=_edited_foru.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name=f"forutsetninger_{_sel_comp.replace(' ', '_')}.csv",
                mime="text/csv",
                key="dl_foru_csv",
            )

        if _save4:
            _cfg_w = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
            _cfg_w["prognose"] = {
                "selskap_id": _sel_id4,
                "forutsetninger": forutsetninger_dict,
                "investeringer": investeringer_dict,
                "dv_vekst": dv_vekst_dict,
                "avs_sats": float(_avs_sats),
                "labor_share_ld": float(_labor_ld),
                "labor_share_rd": float(_labor_rd),
            }
            CONFIG_PATH.write_text(
                _yaml.dump(_cfg_w, allow_unicode=True, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
            st.success("Prognose-forutsetninger lagret")

    # ==================================================================
    #  RUN PROGNOSIS (reactive — runs on every parameter change)
    # ==================================================================
    # Resolve grunnlagsdata.csv path from the same run directory as irir_results_path
    _calc = PrognoseCalculator(
        base_ir=_base_ir_row,
        base_etl=_base_etl_row,
        forutsetninger=forutsetninger_dict,
        investeringer=investeringer_dict,
        dv_vekst=dv_vekst_dict,
        rho=_rho4,
        avs_sats=_avs_sats,
        labor_share_ld=_labor_ld,
        labor_share_rd=_labor_rd,
        fusjon=_cfg4_raw.get("fusjoner", {}).get(_sel_id4),
        grunnlagsdata_csv_path=_grunnlagsdata_csv,
        edited_inv_nok=_inv_nok_dict if _inv_nok_dict else {},
    )
    _forecast = _calc.build_forecast()

    # ──────────────────────────────────────────────────────────────────
    #  TAB 2 — Grunnlagsdata
    # ──────────────────────────────────────────────────────────────────
    with tab_grunn:
        _grunn = _calc.build_grunnlagsdata()

        _gh1, _gh2, _gh3 = st.columns([2.5, 3, 1])
        with _gh1:
            _net_filter = st.multiselect(
                "Nettnivå", ["Distribusjon", "Regional", "Samlet"],
                default=["Distribusjon", "Regional", "Samlet"], key="grunn_net",
            )
        with _gh2:
            _search_g = st.text_input("Søk", key="grunn_search", placeholder="Filtrer parameter …", label_visibility="collapsed")
        with _gh3:
            _show_hist = st.toggle("Historisk", value=False, key="grunn_hist_toggle")

        if _show_hist and _grunnlagsdata_csv:
            _grunn = _prepend_historical(_grunn, _grunnlagsdata_csv, _base_etl_row)

        _grunn_disp = _grunn[_grunn["Nettnivå"].isin(_net_filter)] if _net_filter else _grunn
        if _search_g:
            _grunn_disp = _grunn_disp[
                _grunn_disp["Parameter"].str.contains(_search_g, case=False, na=False)
            ]
        st.dataframe(_grunn_disp, use_container_width=True, hide_index=True, height=480)

        _dl_g1, _dl_g2, _ = st.columns([1, 1, 5])
        with _dl_g1:
            st.download_button(
                "CSV", key="dl_grunn_csv",
                data=_grunn.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name=f"grunnlagsdata_{_sel_comp.replace(' ', '_')}.csv",
                mime="text/csv",
            )
        with _dl_g2:
            _buf_g = io.BytesIO()
            with pd.ExcelWriter(_buf_g, engine="openpyxl") as w:
                _grunn.to_excel(w, index=False, sheet_name="Grunnlagsdata")
            st.download_button(
                "Excel", key="dl_grunn_xlsx",
                data=_buf_g.getvalue(),
                file_name=f"grunnlagsdata_{_sel_comp.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    # ──────────────────────────────────────────────────────────────────
    #  TAB 3 — Resultater
    # ──────────────────────────────────────────────────────────────────
    with tab_res:
        # ── Summary metrics ──────────────────────────────────────────
        _ir_first = float(_forecast.loc[_forecast["År"] == _YEARS[0], "Inntektsramme"].iloc[0])
        _ir_last  = float(_forecast.loc[_forecast["År"] == _YEARS[-1], "Inntektsramme"].iloc[0])
        _pct_chg  = ((_ir_last / _ir_first) - 1) * 100 if _ir_first else 0

        _m1, _m2, _m3 = st.columns(3)
        _m1.metric("IR 2026 (etter kalibrering)", f"{_ir_first:,.0f} kkr")
        _m2.metric(f"IR {_YEARS[-1]} (prognose)", f"{_ir_last:,.0f} kkr")
        _m3.metric("Endring", f"{_pct_chg:+.1f} %", delta=f"{_ir_last - _ir_first:,.0f} kkr")

        # ── 2×2 Efficiency charts ────────────────────────────────────
        st.subheader("Effektivitet og avkastning")
        _eff_specs = [
            ("Effektivitet Dnett", "Effektivitet Dnett %", "#1a5632"),
            ("Effektivitet Rnett", "Effektivitet Rnett %", "#1a5632"),
            ("Effektivitet vektet", "Effektivitet vektet %", "#1a5632"),
            ("Avkastning (NVE)", "Avkastning NVE %", "#1a5632"),
        ]
        _ec1, _ec2 = st.columns(2)
        for idx, (title, col, color) in enumerate(_eff_specs):
            with [_ec1, _ec2, _ec1, _ec2][idx]:
                _fig_e = go.Figure(go.Scatter(
                    x=_forecast["År"], y=_forecast[col],
                    mode="lines+markers",
                    line=dict(color=color, width=2), marker=dict(size=7, color=color),
                    hovertemplate="%{y:.2f} %<extra></extra>",
                ))
                _y_min = _forecast[col].min()
                _y_max = _forecast[col].max()
                _y_pad = max((_y_max - _y_min) * 0.15, 0.5)
                _ref_val = 100.0 if "Avkastning" not in title else None
                _shapes = []
                if _ref_val is not None:
                    _shapes.append(dict(
                        type="line", x0=_YEARS[0], x1=_YEARS[-1],
                        y0=_ref_val, y1=_ref_val,
                        line=dict(color="grey", width=1, dash="dash"),
                    ))
                _fig_e.update_layout(
                    title=dict(text=title, font=dict(size=13)),
                    height=250, margin=dict(l=50, r=15, t=35, b=25),
                    xaxis=dict(dtick=1),
                    yaxis=dict(
                        ticksuffix=" %",
                        range=[_y_min - _y_pad, _y_max + _y_pad],
                    ),
                    shapes=_shapes,
                    plot_bgcolor="#fafbfd", showlegend=False,
                )
                st.plotly_chart(_fig_e, use_container_width=True)

        # ── Stacked area: cost components + IR line ──────────────────
        st.subheader(f"Kostnadskomponenter og IR – {_sel_comp}")
        _stack_cols = {
            "LD D&V":           "#1a5632",
            "RD D&V":           "#7ec89b",
            "LD AVS":           "#2d5a8e",
            "RD AVS":           "#5ba3f5",
            "LD Nettapskostnad": "#8ecae6",
            "RD Nettapskostnad": "#b8d4e3",
            "LD KILE":          "#e8a838",
            "RD KILE":          "#f0d080",
        }
        fig_stack = go.Figure()
        for cc, clr in _stack_cols.items():
            if cc in _forecast.columns:
                fig_stack.add_trace(go.Scatter(
                    x=_forecast["År"], y=_forecast[cc],
                    mode="lines", stackgroup="one", name=cc,
                    line=dict(width=0.5, color=clr),
                    hovertemplate="%{y:,.0f} kkr<extra>" + cc + "</extra>",
                ))
        fig_stack.add_trace(go.Scatter(
            x=_forecast["År"], y=_forecast["Inntektsramme"],
            mode="lines+markers", name="Inntektsramme",
            line=dict(color="#e76f51", width=3), marker=dict(size=8),
            hovertemplate="%{y:,.0f} kkr<extra>IR</extra>",
        ))
        fig_stack.update_layout(
            xaxis=dict(dtick=1), yaxis=dict(title="kkr", separatethousands=True),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=60, r=20, t=30, b=30), height=400,
            hovermode="x unified", plot_bgcolor="#fafbfd",
        )
        st.plotly_chart(fig_stack, use_container_width=True)

        # ── KG vs IR bar chart ───────────────────────────────────────
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=_forecast["År"], y=_forecast["Kostnadsgrunnlag"],
            name="Kostnadsgrunnlag", marker_color="#2d5a8e",
            hovertemplate="%{y:,.0f} kkr<extra>KG</extra>",
        ))
        fig_bar.add_trace(go.Bar(
            x=_forecast["År"], y=_forecast["Inntektsramme"],
            name="Inntektsramme", marker_color="#e76f51",
            hovertemplate="%{y:,.0f} kkr<extra>IR</extra>",
        ))
        fig_bar.update_layout(
            title=dict(text="Kostnadsgrunnlag vs. Inntektsramme", font=dict(size=15)),
            barmode="group", xaxis=dict(dtick=1),
            yaxis=dict(title="kkr", separatethousands=True),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=60, r=20, t=60, b=30), height=350, plot_bgcolor="#fafbfd",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # ── Results table ────────────────────────────────────────────
        st.subheader("Resultater")
        _res_cols = [
            "År", "Driftsresultat", "Rammevilkårsjustering %",
            "LD Kostnadsnorm", "LD Kostnadsgrunnlag",
            "RD Kostnadsnorm", "RD Kostnadsgrunnlag",
            "Kostnadsnorm", "Kostnadsgrunnlag", "Inntektsramme",
            "Effektivitet Dnett %", "Effektivitet Rnett %",
            "Effektivitet vektet %", "Avkastning NVE %",
        ]
        _res_disp = _forecast[[c for c in _res_cols if c in _forecast.columns]]

        # Pivot to match online tool: rows = parameters, cols = years
        _res_long_rows: list[dict] = []
        for col in _res_disp.columns:
            if col == "År":
                continue
            row: dict = {"Parameter": col}
            for _, r in _res_disp.iterrows():
                row[int(r["År"])] = r[col]
            _res_long_rows.append(row)
        _res_long = pd.DataFrame(_res_long_rows)
        st.dataframe(_res_long, use_container_width=True, hide_index=True)

        # ── Full detail table + downloads ────────────────────────────
        with st.expander("Detaljert tabell (alle kolonner)", expanded=False):
            st.dataframe(_forecast, use_container_width=True, hide_index=True)

        _dl1, _dl2, _ = st.columns([1, 1, 5])
        with _dl1:
            st.download_button(
                "CSV", key="dl_prog_csv",
                data=_forecast.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name=f"prognose_{_sel_comp.replace(' ', '_')}.csv",
                mime="text/csv",
            )
        with _dl2:
            _buf_r = io.BytesIO()
            with pd.ExcelWriter(_buf_r, engine="openpyxl") as w:
                _forecast.to_excel(w, index=False, sheet_name="Prognose")
                _calc.build_grunnlagsdata().to_excel(w, index=False, sheet_name="Grunnlagsdata")
            st.download_button(
                "Excel", key="dl_prog_xlsx",
                data=_buf_r.getvalue(),
                file_name=f"prognose_{_sel_comp.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


# ═══════════════════════════════════════════════════════════════════════
# STEG 3 – RME Rapporteringstabell
# ═══════════════════════════════════════════════════════════════════════
if active_step == 3:
    from kostnader import grunnlagsdata_to_rme, rme_table_with_forecast  # noqa: PLC0415

    _cfg3_raw: dict = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    # ── Resolve grunnlagsdata.csv from the configured run directory ───
    _rme_csv_path: str | None = None
    _irir3 = _cfg3_raw.get("irir_results_path", "")
    if _irir3:
        _run_dir3 = (ROOT_DIR / _irir3).parent
        _csv3_candidates = sorted(_run_dir3.glob("*grunnlagsdata.csv"), reverse=True)
        if _csv3_candidates:
            _rme_csv_path = str(_csv3_candidates[0])
    if not _rme_csv_path:
        # Fallback: scan Results/Run_* dirs newest-first
        _run_dirs3 = sorted(
            [d for d in (ROOT_DIR / "Results").iterdir() if d.is_dir() and d.name.startswith("Run_")],
            reverse=True,
        )
        for _rd3 in _run_dirs3:
            _candidates3 = sorted(_rd3.glob("*grunnlagsdata.csv"), reverse=True)
            if _candidates3:
                _rme_csv_path = str(_candidates3[0])
                break

    if not _rme_csv_path:
        st.warning(
            "Finner ikke grunnlagsdata.csv.  "
            "Kjør **Steg 1 – RME Modell** først for å generere resultatfiler."
        )
        st.stop()

    # ── Cache the table build (expensive for all companies) ──────────
    @st.cache_data(show_spinner="Bygger RME-tabell …")
    def _build_rme(csv_path: str, config_path: str) -> pd.DataFrame:
        return rme_table_with_forecast(
            csv_path=csv_path,
            config_path=config_path,
        )

    _rme_df = _build_rme(_rme_csv_path, str(CONFIG_PATH))

    # ── Filters ──────────────────────────────────────────────────────
    _fc1, _fc2, _fc3 = st.columns([2, 2, 2])
    with _fc1:
        _all_companies = sorted(_rme_df["Company"].unique())
        _sel_companies = st.multiselect(
            "Selskap", _all_companies, default=[], key="rme_comp",
            placeholder="Alle",
        )
    with _fc2:
        _all_vars = _rme_df["Variable"].unique().tolist()
        _sel_vars = st.multiselect(
            "Variabel", _all_vars, default=[], key="rme_var",
            placeholder="Alle",
        )
    with _fc3:
        _all_nets = sorted(_rme_df["Nettnivaa"].unique())
        _sel_nets = st.multiselect(
            "Nettnivå", _all_nets, default=[], key="rme_net",
            placeholder="Alle",
        )

    _rme_disp = _rme_df.copy()
    if _sel_companies:
        _rme_disp = _rme_disp[_rme_disp["Company"].isin(_sel_companies)]
    if _sel_vars:
        _rme_disp = _rme_disp[_rme_disp["Variable"].isin(_sel_vars)]
    if _sel_nets:
        _rme_disp = _rme_disp[_rme_disp["Nettnivaa"].isin(_sel_nets)]

    _year_cols_rme = sorted([c for c in _rme_disp.columns if isinstance(c, (int, float))])
    st.caption(
        f"{_rme_disp['NVE_ID'].nunique()} selskaper · {len(_rme_disp)} rader"
        + (f" · {int(min(_year_cols_rme))}–{int(max(_year_cols_rme))}" if _year_cols_rme else "")
    )

    # ── Table ────────────────────────────────────────────────────────
    st.dataframe(_rme_disp, use_container_width=True, hide_index=True, height=560)

    # ── Downloads ────────────────────────────────────────────────────
    _dl_r1, _dl_r2, _ = st.columns([1, 1, 5])
    with _dl_r1:
        st.download_button(
            "CSV", key="dl_rme_csv",
            data=_rme_disp.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name="rme_rapporteringstabell.csv",
            mime="text/csv",
        )
    with _dl_r2:
        _buf_rme = io.BytesIO()
        with pd.ExcelWriter(_buf_rme, engine="openpyxl") as w:
            _rme_disp.to_excel(w, index=False, sheet_name="RME Tabell")
        st.download_button(
            "Excel", key="dl_rme_xlsx",
            data=_buf_rme.getvalue(),
            file_name="rme_rapporteringstabell.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# ═══════════════════════════════════════════════════════════════════════
# STEG 4 – Frontselskapsanalyse
# ═══════════════════════════════════════════════════════════════════════
if active_step == 4:
    from frontselskap import (  # noqa: PLC0415
        load_ld_dea_inputs, run_ld_scenario, get_peer_shares, get_frontier_companies,
    )

    st.header("Frontselskapsanalyse – LD")
    st.caption(
        "Analysen viser hvor langt et selskap er fra å bli frontselskap i DEA-modellen (trinn 1). "
        "Trinn 2-geokorreksjon er tilnærmet ved å beholde det opprinnelige (eff_s2 − eff_s1)-avviket. "
        "Selskaper som fjernes forsvinner helt fra DEA-en (både som referanse og som evaluert selskap) — "
        "dette tilsvarer en fusjon eller utgang fra markedet."
    )

    # ── Resolve paths ─────────────────────────────────────────────────
    _cfg4_raw = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    _results_dir4 = ROOT_DIR / "Results"
    # Try to find ld_InputDEA.csv and Data_Resultater_LD.xlsx
    _dea_csv_path: Path | None = None
    _ld_xlsx_path: Path | None = None

    _irir4 = _cfg4_raw.get("irir_results_path", "")
    if _irir4:
        _run_dir4 = (ROOT_DIR / _irir4).parent
        _cand_dea  = _results_dir4 / "ld_InputDEA.csv"
        _cand_xlsx = _run_dir4 / "Data_Resultater_LD.xlsx"
        if _cand_dea.exists():
            _dea_csv_path = _cand_dea
        if _cand_xlsx.exists():
            _ld_xlsx_path = _cand_xlsx

    if _dea_csv_path is None and (_results_dir4 / "ld_InputDEA.csv").exists():
        _dea_csv_path = _results_dir4 / "ld_InputDEA.csv"

    if _ld_xlsx_path is None:
        _run_dirs4 = sorted(
            [d for d in _results_dir4.iterdir() if d.is_dir() and d.name.startswith("Run_")],
            reverse=True,
        )
        for _rd4 in _run_dirs4:
            _cand4 = _rd4 / "Data_Resultater_LD.xlsx"
            if _cand4.exists():
                _ld_xlsx_path = _cand4
                break

    if _dea_csv_path is None or _ld_xlsx_path is None:
        st.warning(
            "Finner ikke ld_InputDEA.csv eller Data_Resultater_LD.xlsx. "
            "Kjør **Steg 1 – RME Modell** for å generere resultatfiler."
        )
        st.stop()

    # ── Load data (cached) ─────────────────────────────────────────────
    @st.cache_data(show_spinner=False)
    def _load_dea_data(dea_path: str, ld_path: str):
        dea_df = load_ld_dea_inputs(Path(dea_path).parent)
        res_ld = pd.read_excel(ld_path, sheet_name="Resultater_LD")
        return dea_df, res_ld

    _dea_df4, _res_ld4 = _load_dea_data(str(_dea_csv_path), str(_ld_xlsx_path))
    _id_to_comp4: dict[int, str] = _res_ld4.set_index("id")["comp"].to_dict()
    _all_comp_options = sorted(
        [(row["id"], row["comp"]) for _, row in _res_ld4.iterrows()],
        key=lambda x: x[1],
    )
    _comp_label_map = {comp: rid for rid, comp in _all_comp_options}

    # ── Controls ───────────────────────────────────────────────────────
    _ctrl1, _ctrl2 = st.columns([2, 3])

    with _ctrl1:
        st.subheader("Fokusselskap")
        _focus_options = [comp for _, comp in _all_comp_options]
        _default_focus = "NETTSELSKAPET AS" if "NETTSELSKAPET AS" in _focus_options else _focus_options[0]
        _focus_comp = st.selectbox(
            "Velg selskap å analysere",
            options=_focus_options,
            index=_focus_options.index(_default_focus),
            key="fs_focus",
        )
        _focus_id = _comp_label_map[_focus_comp]

    with _ctrl2:
        st.subheader("Fjern fra referansesettet")
        _excl_options = [comp for _, comp in _all_comp_options]
        _default_excl = []
        _excl_comps = st.multiselect(
            "Velg selskaper som skal ut av DEA-en (simulerer fusjon/utgang)",
            options=_excl_options,
            default=_default_excl,
            key="fs_exclude",
            help="Disse selskapene fjernes helt fra DEA-en — de verken evalueres eller brukes som referanse. Tilsvarer en fusjon (f.eks. Rakkestad → Elvia).",
        )
        _excl_ids = [_comp_label_map[c] for c in _excl_comps]

    st.divider()

    # ── Run scenario (cached on exclude set) ──────────────────────────
    @st.cache_data(show_spinner="Kjører DEA-scenario …")
    def _run_scenario(dea_path: str, ld_path: str, excl_ids_key: tuple[int, ...], _v: int = 2) -> pd.DataFrame:
        # _v bumped to 2: excluded companies now removed from eval set too (merger scenario)
        dea_df = load_ld_dea_inputs(Path(dea_path).parent)
        res_ld = pd.read_excel(ld_path, sheet_name="Resultater_LD")
        return run_ld_scenario(dea_df, res_ld, exclude_ids=list(excl_ids_key))

    _excl_key = tuple(sorted(_excl_ids))
    _scenario_df = _run_scenario(str(_dea_csv_path), str(_ld_xlsx_path), _excl_key)

    # Pull out the focus company row
    _focus_row = _scenario_df[_scenario_df["id"] == _focus_id]
    if _focus_row.empty:
        st.error(f"Fant ikke {_focus_comp} (id={_focus_id}) i DEA-dataene.")
        st.stop()
    _fr = _focus_row.iloc[0]

    # ── Key metrics ────────────────────────────────────────────────────
    st.subheader(f"Nøkkeltall — {_focus_comp}")
    _m1, _m2, _m3, _m4 = st.columns(4)

    _s1_base  = _fr["eff_s1_baseline"]
    _s1_scen  = _fr["eff_s1_scenario"]
    _s2_base  = _fr["eff_s2_approx_base"]
    _s2_scen  = _fr["eff_s2_approx_scenario"]
    _gap_base = _fr["gap_mnok_baseline"]
    _gap_scen = _fr["gap_mnok_scenario"]
    _excl_label = ", ".join(_excl_comps) if _excl_comps else "ingen"

    with _m1:
        st.metric(
            "Eff. trinn 1 – nåsituasjon",
            f"{_s1_base:.1%}",
            help="Stage-1 CRS DEA. 100 % = på fronten.",
        )
    with _m2:
        _delta_s1 = _s1_scen - _s1_base
        st.metric(
            "Eff. trinn 1 – scenario",
            f"{_s1_scen:.1%}",
            delta=f"{_delta_s1:+.1%}",
            delta_color="normal",
            help=f"Etter fjerning av: {_excl_label}",
        )
    with _m3:
        st.metric(
            "Eff. trinn 2 – nåsituasjon (approx.)",
            f"{_s2_base:.1%}",
            help="Stage-1 + original geokorreksjon-offset fra R-kjøringen.",
        )
    with _m4:
        _delta_s2 = _s2_scen - _s2_base
        st.metric(
            "Eff. trinn 2 – scenario (approx.)",
            f"{_s2_scen:.1%}",
            delta=f"{_delta_s2:+.1%}",
            delta_color="normal",
        )

    _g1, _g2 = st.columns(2)
    with _g1:
        st.metric(
            "Kostnadsgap til fronten – nåsituasjon",
            f"{_gap_base:.1f} MNOK",
            help="Kostnader som må kuttes (trinn 1) for å nå eff = 100 %.",
        )
    with _g2:
        _delta_gap = _gap_scen - _gap_base
        st.metric(
            "Kostnadsgap til fronten – scenario",
            f"{_gap_scen:.1f} MNOK",
            delta=f"{_delta_gap:+.1f} MNOK",
            delta_color="inverse",
            help=f"Etter fjerning av: {_excl_label}",
        )

    st.divider()

    # ── Charts ─────────────────────────────────────────────────────────
    _chart1, _chart2 = st.columns(2)

    # --- Peer weights pie charts ---
    with _chart1:
        st.subheader("Referanseselskaper (peers)")

        # Current peers from res_ld NCS columns
        _ncs_cols = [c for c in _res_ld4.columns if c.startswith("ld_ncs_")]
        _focus_res_row = _res_ld4[_res_ld4["id"] == _focus_id]
        if not _focus_res_row.empty and _ncs_cols:
            _ncs_vals = _focus_res_row.iloc[0][_ncs_cols]
            _ncs_nonzero = {
                col.replace("ld_ncs_", ""): float(v)
                for col, v in _ncs_vals.items()
                if float(v) > 1e-6
            }
        else:
            _ncs_nonzero = {}

        _peers_scen = get_peer_shares(_fr, _id_to_comp4)

        if not _excl_ids:
            # No scenario — show R results directly (no tabs)
            if _ncs_nonzero:
                _pie_base = go.Figure(go.Pie(
                    labels=list(_ncs_nonzero.keys()),
                    values=list(_ncs_nonzero.values()),
                    hole=0.4,
                    textinfo="label+percent",
                    hovertemplate="%{label}: %{value:.3f}<extra></extra>",
                ))
                _pie_base.update_layout(
                    margin=dict(t=20, b=20, l=20, r=20),
                    height=300,
                    showlegend=False,
                )
                st.plotly_chart(_pie_base, use_container_width=True)
                st.caption("Peer-vekter fra R-modellen (NCS-kolonner).")
            else:
                st.info("Ingen peer-vekter funnet for dette selskapet i R-resultatene.")
        else:
            # Scenario active — show before/after tabs
            _pie_tab_base, _pie_tab_scen = st.tabs(["Nåsituasjon (R-resultater)", "Etter fusjon (LP)"])

            with _pie_tab_base:
                if _ncs_nonzero:
                    _pie_base = go.Figure(go.Pie(
                        labels=list(_ncs_nonzero.keys()),
                        values=list(_ncs_nonzero.values()),
                        hole=0.4,
                        textinfo="label+percent",
                        hovertemplate="%{label}: %{value:.3f}<extra></extra>",
                    ))
                    _pie_base.update_layout(
                        margin=dict(t=20, b=20, l=20, r=20),
                        height=300,
                        showlegend=False,
                    )
                    st.plotly_chart(_pie_base, use_container_width=True)
                else:
                    st.info("Ingen peer-vekter funnet for dette selskapet i R-resultatene.")

            with _pie_tab_scen:
                if not _peers_scen.empty:
                    _excl_note = f" (uten {_excl_label})" if _excl_comps else ""
                    _pie_scen = go.Figure(go.Pie(
                        labels=_peers_scen["comp"].tolist(),
                        values=_peers_scen["lambda"].tolist(),
                        hole=0.4,
                        textinfo="label+percent",
                        hovertemplate="%{label}: lambda=%{value:.3f}<extra></extra>",
                    ))
                    _pie_scen.update_layout(
                        margin=dict(t=20, b=20, l=20, r=20),
                        height=300,
                        showlegend=False,
                    )
                    st.plotly_chart(_pie_scen, use_container_width=True)
                    st.caption(
                        f"Rå DEA-lambda-vekter{_excl_note}. "
                        "Merk: disse er ikke identiske med NCS-kolonnene fra R (som er kalibrert)."
                    )
                else:
                    st.info(
                        f"{_focus_comp} er på fronten i scenariet (ingen peers)."
                        if _s1_scen >= 0.9999
                        else "Ingen peer-vekter funnet i scenariet."
                    )

    # --- Efficiency bar chart (all companies) ---
    with _chart2:
        st.subheader("Effektivitetsoversikt – alle selskaper")
        if _excl_ids:
            st.caption(
                f"Viser {len(_scenario_df)} selskaper. "
                f"{len(_excl_ids)} selskap(er) er fjernet fra DEA-en og vises ikke."
            )

        _bar_df = _scenario_df.copy()
        _bar_df["label"] = _bar_df["comp"].fillna(_bar_df["id"].astype(str))
        _bar_df = _bar_df.sort_values("eff_s1_baseline", ascending=True)

        _bar_focus_mask = _bar_df["id"] == _focus_id

        _bar_fig = go.Figure()
        _bar_fig.add_trace(go.Bar(
            name="Nåsituasjon",
            y=_bar_df["label"],
            x=_bar_df["eff_s1_baseline"],
            orientation="h",
            marker_color=[
                "#e63946" if is_focus else "#4361ee"
                for is_focus in _bar_focus_mask
            ],
            hovertemplate="%{y}: %{x:.3f}<extra>Nåsituasjon</extra>",
        ))
        if _excl_ids:
            _bar_fig.add_trace(go.Bar(
                name="Etter fusjon",
                y=_bar_df["label"],
                x=_bar_df["eff_s1_scenario"],
                orientation="h",
                marker_color=[
                    "#ff6b6b" if is_focus else "#90e0ef"
                    for is_focus in _bar_focus_mask
                ],
                hovertemplate="%{y}: %{x:.3f}<extra>Etter fusjon</extra>",
            ))
        _bar_fig.add_vline(x=1.0, line_dash="dash", line_color="green", line_width=1.5,
                           annotation_text="Front", annotation_position="top right")
        _bar_fig.update_layout(
            barmode="overlay",
            height=max(400, len(_bar_df) * 16),
            margin=dict(t=20, b=20, l=20, r=20),
            xaxis_title="Effektivitet (trinn 1)",
            yaxis_title=None,
            legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
            xaxis=dict(range=[0, 1.1]),
        )
        st.plotly_chart(_bar_fig, use_container_width=True)

    st.divider()

    # ── Frontier composition ───────────────────────────────────────────
    st.subheader("Frontkomposisjon")
    st.caption("Selskaper som faktisk definerer effektivitetsfronten (har positiv lambda-vekt for minst ett annet selskap).")

    @st.cache_data(show_spinner=False)
    def _get_frontiers(dea_path: str, excl_key: tuple[int, ...], _v: int = 2):
        # _v=2: consistent with run_ld_scenario v2 (exclude from both ref+eval)
        _df = load_ld_dea_inputs(Path(dea_path).parent)
        base_ids = get_frontier_companies(_df, [])
        scen_ids = get_frontier_companies(_df, list(excl_key))
        return base_ids, scen_ids

    _base_front_ids, _scen_front_ids = _get_frontiers(str(_dea_csv_path), _excl_key)

    _new_ids     = _scen_front_ids - _base_front_ids
    _dropped_ids = _base_front_ids - _scen_front_ids
    _stable_ids  = _base_front_ids & _scen_front_ids

    _fc1, _fc2, _fc3 = st.columns(3)

    with _fc1:
        st.markdown("**Stabile frontselskaper**")
        for _rid in sorted(_stable_ids, key=lambda r: _id_to_comp4.get(r, str(r))):
            st.markdown(f"- {_id_to_comp4.get(_rid, _rid)}")

    with _fc2:
        _excl_lbl = ", ".join(_excl_comps) if _excl_comps else "ingen"
        st.markdown(f"**Faller ut** (fjernet: {_excl_lbl})")
        if _dropped_ids:
            for _rid in sorted(_dropped_ids, key=lambda r: _id_to_comp4.get(r, str(r))):
                st.markdown(f"- :red[{_id_to_comp4.get(_rid, _rid)}]")
        else:
            st.markdown("_Ingen_")

    with _fc3:
        st.markdown("**Nye frontselskaper i scenariet**")
        if _new_ids:
            for _rid in sorted(_new_ids, key=lambda r: _id_to_comp4.get(r, str(r))):
                st.markdown(f"- :green[{_id_to_comp4.get(_rid, _rid)}]")
        else:
            st.markdown("_Ingen endring_")

    st.divider()

    # ── Full results table ─────────────────────────────────────────────
    with st.expander("Fulltabell – alle selskaper"):
        _tbl_cols = [
            "comp", "X_cb",
            "eff_s1_baseline", "eff_s1_scenario",
            "eff_s2_approx_base", "eff_s2_approx_scenario",
            "gap_mnok_baseline", "gap_mnok_scenario",
        ]
        _tbl_df = (
            _scenario_df[_tbl_cols]
            .copy()
            .sort_values("eff_s1_scenario", ascending=False)
            .rename(columns={
                "comp":                   "Selskap",
                "X_cb":                   "Kostgrunnlag (kNOK)",
                "eff_s1_baseline":        "Eff. s1 (nå)",
                "eff_s1_scenario":        "Eff. s1 (scenario)",
                "eff_s2_approx_base":     "Eff. s2 approx (nå)",
                "eff_s2_approx_scenario": "Eff. s2 approx (scenario)",
                "gap_mnok_baseline":      "Gap MNOK (nå)",
                "gap_mnok_scenario":      "Gap MNOK (scenario)",
            })
        )
        st.dataframe(
            _tbl_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Eff. s1 (nå)":             st.column_config.NumberColumn(format="%.3f"),
                "Eff. s1 (scenario)":       st.column_config.NumberColumn(format="%.3f"),
                "Eff. s2 approx (nå)":      st.column_config.NumberColumn(format="%.3f"),
                "Eff. s2 approx (scenario)": st.column_config.NumberColumn(format="%.3f"),
                "Gap MNOK (nå)":            st.column_config.NumberColumn(format="%.1f"),
                "Gap MNOK (scenario)":      st.column_config.NumberColumn(format="%.1f"),
            },
        )

        _dl4_1, _dl4_2, _ = st.columns([1, 1, 5])
        with _dl4_1:
            st.download_button(
                "CSV", key="dl_fs_csv",
                data=_tbl_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name="frontselskapsanalyse.csv",
                mime="text/csv",
            )
        with _dl4_2:
            _buf4 = io.BytesIO()
            with pd.ExcelWriter(_buf4, engine="openpyxl") as _w4:
                _tbl_df.to_excel(_w4, index=False, sheet_name="Frontselskapsanalyse")
            st.download_button(
                "Excel", key="dl_fs_xlsx",
                data=_buf4.getvalue(),
                file_name="frontselskapsanalyse.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )