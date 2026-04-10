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

import base64

import streamlit as st
import pandas as pd
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
st.set_page_config(
    page_title="Inntektsramme Dashboard",
    page_icon="⚡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.html("""
<style>
/* ── Typography ─────────────────────────────────────────────────────── */
h1 { font-size: 1.65rem !important; font-weight: 700 !important; letter-spacing: -0.01em; }
h2, [data-testid="stHeadingWithActionElements"] h2 { font-size: 1.15rem !important; font-weight: 700 !important; }
h3 { font-size: 1.0rem !important; font-weight: 600 !important; }

/* ── Metric cards ───────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #f0f4fa 0%, #ffffff 100%);
    border: 1px solid #d4dde8; border-radius: 10px;
    padding: 14px 18px 12px 18px;
}
[data-testid="stMetricLabel"] { font-size: 0.77rem !important; color: #5a6a7e !important; }
[data-testid="stMetricValue"] { font-size: 1.25rem !important; font-weight: 700 !important; color: #1e3a5f !important; }

/* ── Data editor / dataframe ────────────────────────────────────────── */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border: 1px solid #d4dde8; border-radius: 8px;
}

/* ── Buttons ────────────────────────────────────────────────────────── */
button[kind="primary"] { background-color: #1e3a5f !important; border: none !important; }
button[kind="primary"]:hover { background-color: #2d5a8e !important; }

/* ── Slider year labels ─────────────────────────────────────────────── */
.slider-year-label { text-align: center; font-size: 0.80rem; font-weight: 700; color: #1e3a5f; margin-bottom: -6px; }
.slider-value-label { text-align: center; font-size: 0.92rem; font-weight: 600; color: #2d5a8e; margin-top: -8px; }

/* ── Pipeline cards ─────────────────────────────────────────────────── */
.pl-wrap { display: flex; align-items: center; gap: 0; margin: 0 0 0.2rem 0; width: 100%; }
.pl-step {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: #1e3a5f; color: #fff; border-radius: 10px;
    padding: 10px 18px; flex: 1; min-height: 80px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.22); transition: all 0.15s ease;
}
.pl-step-active { background: #254e82; box-shadow: 0 3px 14px rgba(46,109,180,0.50); outline: 2.5px solid #5ba3f5; }
.pl-step .pl-icon { font-size: 1.3rem; margin-bottom: 3px; line-height: 1; }
.pl-step .pl-num  { font-size: 0.62rem; font-weight: 600; letter-spacing: 0.08em; opacity: 0.70; text-transform: uppercase; }
.pl-step .pl-lbl  { font-size: 0.90rem; font-weight: 700; }
.pl-arr { font-size: 1.3rem; color: #1e3a5f; padding: 0 8px; opacity: 0.40; user-select: none; }

/* ── Expanders ──────────────────────────────────────────────────────── */
section[data-testid="stExpander"] {
    border: 1px solid #d4dde8 !important; border-radius: 10px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
}
</style>
""")

st.title("Inntektsramme")

# ---------------------------------------------------------------------------
# Pipeline navigation  (session-state driven – no full page reload)
# ---------------------------------------------------------------------------
if "active_step" not in st.session_state:
    st.session_state.active_step = 1
active_step = st.session_state.active_step

# ── R logo (base64) ──────────────────────────────────────────────────
_r_logo_path = ROOT_DIR / "figures" / "r-logo.jpg"
_logo_img = "⚙️"
if _r_logo_path.exists():
    _r_logo_b64 = base64.b64encode(_r_logo_path.read_bytes()).decode()
    _logo_img = f'<img src="data:image/jpeg;base64,{_r_logo_b64}" style="height:32px;border-radius:4px;">'


def _card(step_n: int, icon_html: str, label: str) -> str:
    cls = "pl-step-active" if active_step == step_n else ""
    return (
        f'<div class="pl-step {cls}">'
        f'  <div class="pl-icon">{icon_html}</div>'
        f'  <div class="pl-num">Steg {step_n}</div>'
        f'  <div class="pl-lbl">{label}</div>'
        f'</div>'
    )


st.html(f"""
<div class="pl-wrap">
  {_card(1, _logo_img, "RME Modell & Inntektsramme 2026")}
  <div class="pl-arr">&#9654;</div>
  {_card(2, "📈", "Prognosebygger")}
</div>
""")

# Compact nav buttons
_nav = st.columns(2)
_labels = ["Steg 1 – RME Modell & Inntektsramme 2026", "Steg 2 – Prognosebygger"]
for i, col in enumerate(_nav):
    step_n = i + 1
    with col:
        if st.button(
            _labels[i], use_container_width=True, key=f"nav{step_n}",
            type="primary" if active_step == step_n else "secondary",
        ):
            st.session_state.active_step = step_n
            st.rerun()

st.divider()

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
            "🔄  Oppdater inntektsramme", key="refresh_ir",
            disabled=not _ir_loaded,
        )

    log_placeholder = st.empty()

    # ── Run full R pipeline ─────────────────────────────────────────
    if run_full:
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
                proc = subprocess.Popen(
                    [rscript, "IRiR.R"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    cwd=str(ROOT_DIR),
                )
                for line in proc.stdout:
                    log_lines.append(line.rstrip())
                    log_placeholder.text("\n".join(log_lines))
                proc.wait()

            elapsed = time.time() - start

            if proc.returncode == 0:
                r_ok = True
                st.success(f"RME Modell fullført på {elapsed:.1f} sekunder")

                # Auto-update config paths to the new run directory
                run_dirs = sorted(
                    [d for d in (ROOT_DIR / "Results").iterdir() if d.is_dir() and d.name.startswith("Run_")],
                    reverse=True,
                )
                if run_dirs:
                    latest = run_dirs[0]
                    candidates = {
                        "irir_results_path":       ["Til inntektsrammeark.xlsx"],
                        "data_resultater_ld_path": ["Data_Resultater_LD.xlsx", "Data_resultater_ld.xlsx"],
                        "data_resultater_rd_path": ["Data_Resultater_RD.xlsx", "Data_resultater_rd.xlsx"],
                    }
                    cfg_update = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
                    updated = {}
                    for cfg_key, filenames in candidates.items():
                        for fname in filenames:
                            found = latest / fname
                            if found.exists():
                                rel = found.relative_to(ROOT_DIR).as_posix()
                                cfg_update[cfg_key] = rel
                                updated[cfg_key] = rel
                                break
                    if updated:
                        CONFIG_PATH.write_text(
                            _yaml.dump(cfg_update, allow_unicode=True, sort_keys=False, default_flow_style=False),
                            encoding="utf-8",
                        )
                        st.success(
                            "📁 Filstier oppdatert i config.yaml:\n\n"
                            + "\n".join(f"- `{k}`: `{v}`" for k, v in updated.items())
                        )
                    else:
                        missing = [f for fnames in candidates.values() for f in fnames]
                        st.warning(
                            f"⚠️ Fant ingen kjente resultatfiler i `{latest.name}`. "
                            f"Forventet: {missing}. Filstier ikke oppdatert."
                        )

                    files = sorted(latest.iterdir())
                    file_lines = ("\n\n" + "\n".join(f"- `{f.name}` ({f.stat().st_size:,} bytes)" for f in files)) if files else ""
                    st.success(f"📁 Siste resultater lagret i: `{latest}`{file_lines}")
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

        _s1 = st.text_input("🔍 Filtrer", key="step1_search", placeholder="Søk etter selskap …")
        _disp1 = _r_df
        if _s1:
            _mask1 = _r_df.apply(
                lambda col: col.astype(str).str.contains(_s1, case=False, na=False)
            ).any(axis=1)
            _disp1 = _r_df[_mask1]
        st.dataframe(_disp1, use_container_width=True, height=480)

        _dl1, _dl2 = st.columns(2)
        with _dl1:
            st.download_button(
                "⬇  CSV (semikolon)", key="dl_csv1",
                data=_r_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name="inntektsrammer_etl.csv", mime="text/csv",
            )
        with _dl2:
            _buf1 = io.BytesIO()
            with pd.ExcelWriter(_buf1, engine="openpyxl") as w:
                _r_df.to_excel(w, index=False, sheet_name="ETL")
                _r_ir.to_excel(w, index=False, sheet_name="Grunnlagsdata")
            st.download_button(
                "⬇  Excel", key="dl_xlsx1",
                data=_buf1.getvalue(),
                file_name="inntektsrammer_etl.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        st.info(
            "Klikk **▶ Kjør RME Modell** for å kjøre R-modellen og beregne inntektsrammer for 2026."
        )

    # ── Konfigurasjon (expander) ─────────────────────────────────────
    st.divider()
    with st.expander("⚙️ Konfigurasjon", expanded=False):
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

        cs, cr = st.columns([1, 5])
        with cs:
            save = st.button("💾  Lagre konfigurasjon", type="primary", key="cfg_save")
        with cr:
            if st.button("↩  Tilbakestill", key="cfg_reset"):
                for key in ("fp_editor", "gen_editor", "ir_k", "renter", "p_irir", "p_ld", "p_rd"):
                    st.session_state.pop(key, None)
                st.rerun()

        if save:
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

        # ── Investeringer per selskap ────────────────────────────────
        _INV_CSV_PATH = ROOT_DIR / "Data" / "investeringer.csv"
        st.divider()
        st.subheader("Investeringer per selskap (% av BFV)")

        def _load_inv_csv() -> pd.DataFrame:
            if _INV_CSV_PATH.exists():
                return pd.read_csv(_INV_CSV_PATH, sep=";", dtype={"id": int})
            return pd.DataFrame()

        def _pivot_inv(df: pd.DataFrame, nettnivaa: str) -> pd.DataFrame:
            sub = df[df["nettnivaa"] == nettnivaa].copy()
            year_cols = [c for c in df.columns if c.isdigit()]
            result = sub[["selskap"] + year_cols].rename(columns={"selskap": "Selskap"})
            return result.reset_index(drop=True)

        def _unpivot_inv(wide: pd.DataFrame, id_series: pd.Series, nettnivaa: str) -> pd.DataFrame:
            year_cols = [c for c in wide.columns if c != "Selskap"]
            rows = []
            for i, row in wide.iterrows():
                rows.append({
                    "id": int(id_series.iloc[i]),
                    "selskap": row["Selskap"],
                    "nettnivaa": nettnivaa,
                    **{y: float(row[y]) for y in year_cols},
                })
            return pd.DataFrame(rows)

        _inv_df_full = _load_inv_csv()

        if _inv_df_full.empty:
            st.warning(
                "`Data/investeringer.csv` ikke funnet. "
                "Commit eller generer filen for å aktivere redigering her."
            )
        else:
            _year_cols = [c for c in _inv_df_full.columns if c.isdigit()]
            _col_cfg_inv = {y: st.column_config.NumberColumn(format="%.1f %%") for y in _year_cols}
            _id_dnett = _inv_df_full[_inv_df_full["nettnivaa"] == "dnett_pct"].reset_index(drop=True)["id"]
            _id_rnett = _inv_df_full[_inv_df_full["nettnivaa"] == "rnett_pct"].reset_index(drop=True)["id"]

            _tab_dn, _tab_rn = st.tabs(["Distribusjonsnett (dnett_pct)", "Regionalnett (rnett_pct)"])
            with _tab_dn:
                _dn_wide = _pivot_inv(_inv_df_full, "dnett_pct")
                _edited_dn = st.data_editor(
                    _dn_wide, use_container_width=True, hide_index=True,
                    disabled=["Selskap"], column_config=_col_cfg_inv, key="inv_csv_dn",
                )
            with _tab_rn:
                _rn_wide = _pivot_inv(_inv_df_full, "rnett_pct")
                _edited_rn = st.data_editor(
                    _rn_wide, use_container_width=True, hide_index=True,
                    disabled=["Selskap"], column_config=_col_cfg_inv, key="inv_csv_rn",
                )

            _ci_save, _ci_reset, _ = st.columns([1, 1, 5])
            with _ci_save:
                _save_inv_csv = st.button("💾  Lagre investeringer", type="primary", key="save_inv_csv")
            with _ci_reset:
                if st.button("↩  Tilbakestill", key="reset_inv_csv"):
                    st.session_state.pop("inv_csv_dn", None)
                    st.session_state.pop("inv_csv_rn", None)
                    st.rerun()

            if _save_inv_csv:
                _new_dn = _unpivot_inv(_edited_dn, _id_dnett, "dnett_pct")
                _new_rn = _unpivot_inv(_edited_rn, _id_rnett, "rnett_pct")
                _combined = pd.concat([_new_dn, _new_rn]).sort_values(["id", "nettnivaa"]).reset_index(drop=True)
                _INV_CSV_PATH.write_text(
                    _combined.to_csv(index=False, sep=";"),
                    encoding="utf-8",
                )
                st.success("Data/investeringer.csv lagret")


# ═══════════════════════════════════════════════════════════════════════
# STEG 2 – Prognosebygger
# ═══════════════════════════════════════════════════════════════════════
if active_step == 2:
    from prognose import (  # noqa: PLC0415
        PrognoseCalculator, FORECAST_YEARS,
        DEFAULT_FORUTSETNINGER, DEFAULT_INVESTERINGER, DEFAULT_DV_VEKST,
        load_investeringer_for_company,
    )

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
    _hdr_l, _hdr_r = st.columns([5, 1])
    with _hdr_l:
        if _loaded:
            _ts = st.session_state.get("prognose_loaded_at", "ukjent tid")
            st.caption(
                f"Beregningsgrunnlag lastet kl. {_ts}. "
                "Klikk **Oppdater** hvis du har endret konfigurasjon i Steg 1."
            )
        else:
            st.info(
                "Beregningsgrunnlaget er ikke lastet ennå. "
                "Gå til **Steg 1** og kjør RME Modell, eller klikk **Last inn** her."
            )
    with _hdr_r:
        _btn_label = "🔄  Oppdater" if _loaded else "▶  Last inn"
        if st.button(_btn_label, key="load_prog", type="primary"):
            with st.spinner("Kjører inntektsrammemodellen …"):
                try:
                    _load_base_data()
                    st.rerun()
                except Exception as _e:
                    st.error(f"Feil: {_e}")

    if not _loaded:
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
    _sel_comp = st.selectbox("Velg selskap", _all_comp, index=_default_idx, key="prog_comp")

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

    # ==================================================================
    #  TABS
    # ==================================================================
    tab_foru, tab_grunn, tab_res = st.tabs(
        ["📝 Forutsetninger", "📋 Grunnlagsdata", "📊 Resultater"]
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

        st.divider()

        # ── Investeringer per nettnivå ───────────────────────────────
        st.subheader("Investeringer per nettnivå (% av BFV)")
        # Priority: 1) session-saved override, 2) per-company CSV, 3) global default
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

        st.divider()

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

        st.divider()

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

        # ── Save / Reset ─────────────────────────────────────────────
        st.divider()
        _sa, _sb, _ = st.columns([1, 1, 4])
        with _sa:
            _save4 = st.button("💾  Lagre", type="primary", key="save4")
        with _sb:
            if st.button("↩  Tilbakestill", key="reset4"):
                for k in ("foru_editor", "inv_editor", "dv_editor",
                           "avs_sats4", "lab_ld", "lab_rd", "rho4"):
                    st.session_state.pop(k, None)
                st.rerun()

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
    )
    _forecast = _calc.build_forecast()

    # ──────────────────────────────────────────────────────────────────
    #  TAB 2 — Grunnlagsdata
    # ──────────────────────────────────────────────────────────────────
    with tab_grunn:
        st.subheader("Grunnlagsdata")
        _grunn = _calc.build_grunnlagsdata()
        _net_filter = st.multiselect(
            "Nettnivå", ["Distribusjon", "Regional", "Samlet"],
            default=["Distribusjon", "Regional", "Samlet"], key="grunn_net",
        )
        _grunn_disp = _grunn[_grunn["Nettnivå"].isin(_net_filter)] if _net_filter else _grunn
        _search_g = st.text_input("🔍 Søk", key="grunn_search", placeholder="Filtrer parameter …")
        if _search_g:
            _grunn_disp = _grunn_disp[
                _grunn_disp["Parameter"].str.contains(_search_g, case=False, na=False)
            ]
        st.dataframe(_grunn_disp, use_container_width=True, hide_index=True, height=480)

        _dl_g1, _dl_g2 = st.columns(2)
        with _dl_g1:
            st.download_button(
                "⬇  CSV", key="dl_grunn_csv",
                data=_grunn.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name=f"grunnlagsdata_{_sel_comp.replace(' ', '_')}.csv",
                mime="text/csv",
            )
        with _dl_g2:
            _buf_g = io.BytesIO()
            with pd.ExcelWriter(_buf_g, engine="openpyxl") as w:
                _grunn.to_excel(w, index=False, sheet_name="Grunnlagsdata")
            st.download_button(
                "⬇  Excel", key="dl_grunn_xlsx",
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

        _dl1, _dl2 = st.columns(2)
        with _dl1:
            st.download_button(
                "⬇  Prognose CSV", key="dl_prog_csv",
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
                "⬇  Excel (alle ark)", key="dl_prog_xlsx",
                data=_buf_r.getvalue(),
                file_name=f"prognose_{_sel_comp.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )