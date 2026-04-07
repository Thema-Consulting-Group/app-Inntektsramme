"""
Inntektsramme Dashboard – Streamlit app
Run from the repo root:
    streamlit run PostProcess/app.py
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
import yaml as _yaml

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
THIS_DIR = Path(__file__).resolve().parent          # …/PostProcess
ROOT_DIR = THIS_DIR.parent                          # …/Inntektsramme

# Make sure both directories are importable
for p in [str(THIS_DIR), str(ROOT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# PostProcess scripts use relative paths (kundetillegg.csv etc.)
# so we pin the working directory here when the module is first loaded.
os.chdir(THIS_DIR)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Inntektsramme Dashboard",
    page_icon= " ",
    layout="wide",
)

st.title("Inntektsramme")

# ---------------------------------------------------------------------------
# Pipeline navigation  (session-state driven – no full page reload)
# ---------------------------------------------------------------------------
if "active_step" not in st.session_state:
    st.session_state.active_step = 1
active_step = st.session_state.active_step

# ── R logo (base64 so it works inside inline HTML) ───────────────────────
_r_logo_path = ROOT_DIR / "figures" / "r-logo.jpg"
_logo_img = "⚙️"
if _r_logo_path.exists():
    _r_logo_b64 = base64.b64encode(_r_logo_path.read_bytes()).decode()
    _logo_img = f'<img src="data:image/jpeg;base64,{_r_logo_b64}" style="height:44px;margin-bottom:6px;border-radius:4px;">'

def _card(step_n: int, icon_html: str, label: str) -> str:
    active_cls = "pipeline-step-active" if active_step == step_n else ""
    return f"""
      <div class="pipeline-step {active_cls}">
        <div class="step-icon">{icon_html}</div>
        <div class="step-num">Steg {step_n}</div>
        <div class="step-label">{label}</div>
      </div>"""

st.html(f"""
<style>
.pipeline-wrapper {{
    display: flex;
    align-items: center;
    gap: 0;
    margin: 0.5rem 0 0 0;
    font-family: sans-serif;
    width: 100%;
}}
.pipeline-step {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #1e3a5f;
    color: #ffffff;
    border-radius: 12px;
    padding: 18px 36px;
    flex: 1;
    min-height: 120px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.28);
}}
.pipeline-step-active {{
    background: #254e82;
    box-shadow: 0 4px 16px rgba(46,109,180,0.55);
    outline: 3px solid #5ba3f5;
}}
.pipeline-step .step-num {{
    font-size: 0.70rem;
    font-weight: 600;
    letter-spacing: 0.09em;
    opacity: 0.75;
    margin-bottom: 3px;
    text-transform: uppercase;
}}
.pipeline-step .step-label {{
    font-size: 1.05rem;
    font-weight: 700;
}}
.pipeline-step .step-icon {{
    font-size: 1.6rem;
    margin-bottom: 6px;
    line-height: 1;
}}
.pipeline-arrow {{
    font-size: 1.8rem;
    color: #1e3a5f;
    padding: 0 14px;
    opacity: 0.55;
    user-select: none;
}}
</style>
<div class="pipeline-wrapper">
  {_card(1, _logo_img, "RME Modell")}
  <div class="pipeline-arrow">&#9654;</div>
  {_card(2, "📝", "Konfigurasjon")}
  <div class="pipeline-arrow">&#9654;</div>
  {_card(3, "📊", "Inntektsramme")}
  <div class="pipeline-arrow">&#9654;</div>
  {_card(4, "📈", "Prognose")}
</div>
""")

st.html("""
<style>
div[data-testid="stButton"]:has(button[kind="primaryFormSubmit"]),
div[data-testid="stButton"]:has(button[kind="secondaryFormSubmit"]),
div[data-testid="stButton"] > button {
    min-height: 120px !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
}
</style>
""")

_nav_cols = st.columns([3, 0.4, 3, 0.4, 3, 0.4, 3])
with _nav_cols[0]:
    if st.button("Steg 1 – R-Modell", use_container_width=True, key="nav1",
                 type="primary" if active_step == 1 else "secondary"):
        st.session_state.active_step = 1
        st.rerun()
with _nav_cols[1]:
    st.markdown('<p style="text-align:center;font-size:1.4rem;color:#1e3a5f;opacity:0.55;margin-top:4px">▶</p>', unsafe_allow_html=True)
with _nav_cols[2]:
    if st.button("Steg 2 – Konfigurasjon", use_container_width=True, key="nav2",
                 type="primary" if active_step == 2 else "secondary"):
        st.session_state.active_step = 2
        st.rerun()
with _nav_cols[3]:
    st.markdown('<p style="text-align:center;font-size:1.4rem;color:#1e3a5f;opacity:0.55;margin-top:4px">▶</p>', unsafe_allow_html=True)
with _nav_cols[4]:
    if st.button("Steg 3 – Inntektsramme", use_container_width=True, key="nav3",
                 type="primary" if active_step == 3 else "secondary"):
        st.session_state.active_step = 3
        st.rerun()
with _nav_cols[5]:
    st.markdown('<p style="text-align:center;font-size:1.4rem;color:#1e3a5f;opacity:0.55;margin-top:4px">▶</p>', unsafe_allow_html=True)
with _nav_cols[6]:
    if st.button("Steg 4 – Prognose", use_container_width=True, key="nav4",
                 type="primary" if active_step == 4 else "secondary"):
        st.session_state.active_step = 4
        st.rerun()

st.divider()

# ===========================================================================
# STEG 3 – Inntektsramme
# ===========================================================================
if active_step == 3:
    #st.header("Inntektsramme")

    run_pp = st.button("▶ Kjør pp_inntektsramme.py", key="run_pp")

    if run_pp:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with st.spinner("Kjører beregninger – vennligst vent …"):
            try:
                # Import here so we can display import-time errors cleanly
                from pp_inntektsramme import RevenueCapCalculator  # noqa: PLC0415

                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    calc = RevenueCapCalculator()
                    result_df: pd.DataFrame = calc.build_etl_dataframe()

                st.success("✅ Beregninger fullført!")

            except Exception as exc:
                st.error(f"❌ Feil oppstod: {exc}")
                result_df = None

        # Console output
        stdout_text = stdout_buf.getvalue()
        stderr_text = stderr_buf.getvalue()

        if stdout_text or stderr_text:
            with st.expander("🖥 Console output", expanded=True):
                if stdout_text:
                    st.code(stdout_text, language="text")
                if stderr_text:
                    st.code(stderr_text, language="text")

        # Results table
        if result_df is not None:
            st.subheader("Resultater")

            # Summary metrics row
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Antall selskaper", len(result_df))
            with col2:
                if "Kostnadsgrunnlag" in result_df.columns:
                    total_k = result_df["Kostnadsgrunnlag"].sum()
                    st.metric("Sum Kostnadsgrunnlag", f"{total_k:,.0f}")
            with col3:
                if "Inntektsramme før kalibrering" in result_df.columns:
                    total_ir = result_df["Inntektsramme før kalibrering"].sum()
                    st.metric("Sum IR (før kalibrering)", f"{total_ir:,.0f}")

            # Searchable, scrollable data table
            search = st.text_input("🔍 Filtrer på selskap", key="pp_search")
            display_df = result_df
            if search:
                mask = result_df.apply(
                    lambda col: col.astype(str).str.contains(search, case=False, na=False)
                ).any(axis=1)
                display_df = result_df[mask]

            st.dataframe(display_df, use_container_width=True, height=500)

            # Download
            st.divider()
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                csv_bytes = result_df.to_csv(index=False, sep=";").encode("utf-8-sig")
                st.download_button(
                    "⬇ Last ned CSV (semikolon)",
                    data=csv_bytes,
                    file_name="inntektsrammer_etl.csv",
                    mime="text/csv",
                )
            with col_dl2:
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
                    result_df.to_excel(writer, index=False, sheet_name="ETL")
                st.download_button(
                    "⬇ Last ned Excel",
                    data=excel_buf.getvalue(),
                    file_name="inntektsrammer_etl.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


# ===========================================================================
#  STEG 2 – Konfigurasjon
# ===========================================================================
CONFIG_PATH = THIS_DIR / "config.yaml"

if active_step == 2:
    #st.header("📝 Konfigurasjon – config.yaml")
    #st.markdown("Rediger parametere og klikk **💾 Lagre** før du kjører PostProcess.")

    cfg_raw: dict = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    foru = cfg_raw.get("forutsetninger", {})
    fp   = foru.get("finansparametere", {})
    cal  = cfg_raw.get("kalibrering", {})
    kpi  = foru.get("kpi_justering", {})
    wage = foru.get("aarslonn", {})

    # ── Finansparametere + Generelle forutsetninger side by side ─────────
    col_fp, col_gen = st.columns(2)

    with col_fp:
        st.subheader("Finansparametere")
        fp_df = pd.DataFrame(
            [{"Parameter": k, "Verdi": float(v)} for k, v in fp.items()],
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

        # Compute referanserente live from edited values
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
        st.dataframe(
            pd.DataFrame([{"Parameter": "referanserente (beregnet)", "Verdi": f"{_r * 100:.2f} %"}]),
            use_container_width=True,
            hide_index=True,
        )

    with col_gen:
        st.subheader("Generelle forutsetninger")
        gen_df = pd.DataFrame([
            {"Parameter": "rho",          "Verdi": float(foru.get("rho", 0.70))},
            {"Parameter": "KPI 2024",     "Verdi": float(kpi.get(2024, 133.6))},
            {"Parameter": "KPI 2026",     "Verdi": float(kpi.get(2026, 140.6))},
            {"Parameter": "Årslønn 2024", "Verdi": float(wage.get(2024, 129.9))},
            {"Parameter": "Årslønn 2026", "Verdi": float(wage.get(2026, 141.7))},
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
    
    # ── Kalibreringskonstanter + Filstier side by side ───────────────────
    col_kal, col_fil = st.columns(2)

    with col_kal:
        st.subheader("Kalibreringskonstanter (i prosent)")
        new_ir_k = st.number_input(
            "Sum (IR−K) / sum AKG  [%]",
            value=float(cal.get("sum_ir_k_per_sum_akg_pct", -0.023)),
            step=0.001, format="%.3f", key="ir_k",
        )
        new_renter = st.number_input(
            "Sum renter-avvik / sum AKG  [%]",
            value=float(cal.get("sum_renter_avvik_per_sum_akg_pct", -0.098)),
            step=0.001, format="%.3f", key="renter",
        )

    with col_fil:
        st.subheader("Filstier")
        new_irir = st.text_input("irir_results_path",       value=cfg_raw.get("irir_results_path", ""),       key="p_irir")
        new_ld   = st.text_input("data_resultater_ld_path", value=cfg_raw.get("data_resultater_ld_path", ""), key="p_ld")
        new_rd   = st.text_input("data_resultater_rd_path", value=cfg_raw.get("data_resultater_rd_path", ""), key="p_rd")

    # ── Save / reset ──────────────────────────────────────────────────────
    st.divider()
    col_save, col_reset = st.columns([1, 5])
    with col_save:
        save = st.button("💾 Lagre konfigurasjon", type="primary")
    with col_reset:
        if st.button("↩ Tilbakestill"):
            for key in ("fp_editor", "gen_editor", "ir_k", "renter", "p_irir", "p_ld", "p_rd"):
                st.session_state.pop(key, None)
            st.rerun()

    if save:
        # Rebuild finansparametere from edited table
        new_fp = {row["Parameter"]: row["Verdi"] for _, row in edited_fp.iterrows()}

        cfg_raw["irir_results_path"]        = new_irir
        cfg_raw["data_resultater_ld_path"]  = new_ld
        cfg_raw["data_resultater_rd_path"]  = new_rd
        cfg_raw["forutsetninger"]["rho"]    = new_rho
        cfg_raw["forutsetninger"]["finansparametere"] = new_fp
        cfg_raw["forutsetninger"]["kpi_justering"]    = {2024: new_kpi_2024, 2026: new_kpi_2026}
        cfg_raw["forutsetninger"]["aarslonn"]         = {2024: new_wage_2024, 2026: new_wage_2026}
        cfg_raw["kalibrering"]["sum_ir_k_per_sum_akg_pct"]       = new_ir_k
        cfg_raw["kalibrering"]["sum_renter_avvik_per_sum_akg_pct"] = new_renter

        CONFIG_PATH.write_text(
            _yaml.dump(cfg_raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        st.success("✅ config.yaml lagret!")

# ===========================================================================
#  STEG 1 – R-Modell
# ===========================================================================
if active_step == 1:
    #st.header("R-Modell")

    run_irir = st.button("▶ Kjør IRIR-pipeline", key="run_irir", type="primary")

    log_placeholder = st.empty()

    if run_irir:
        log_lines: list[str] = []
        start = time.time()

        irir_script = ROOT_DIR / "IRiR.R"
        if not irir_script.exists():
            st.error(f"Finner ikke IRiR.R i {ROOT_DIR}")
        else:
            import shutil
            rscript = shutil.which("Rscript") or r"C:\Users\jp117\AppData\Local\Programs\R\R-4.5.2\bin\Rscript.exe"
            if not rscript:
                st.error("Finner ikke Rscript på PATH. Sjekk R-installasjonen.")
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
                    # Update the log display every line
                    log_placeholder.text("\n".join(log_lines))

                proc.wait()

            elapsed = time.time() - start

            if proc.returncode == 0:
                st.success(f"Pipeline fullført på {elapsed:.1f} sekunder")

                # Auto-update config paths to the new run directory
                run_dirs = sorted(
                    [d for d in (ROOT_DIR / "Results").iterdir() if d.is_dir() and d.name.startswith("Run_")],
                    reverse=True,
                )
                if run_dirs:
                    latest = run_dirs[0]
                    # Candidate filenames produced by IRiR.R
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
            else:
                st.error(
                    f"❌ Pipeline feilet (exit code {proc.returncode}) etter {elapsed:.1f} sekunder."
                )

            # Show newly created results directory
            run_dirs = sorted(
                [d for d in (ROOT_DIR / "Results").iterdir() if d.is_dir() and d.name.startswith("Run_")],
                reverse=True,
            )
            if run_dirs:
                latest = run_dirs[0]
                files = sorted(latest.iterdir())
                file_lines = ("\n\n" + "\n".join(f"- `{f.name}` ({f.stat().st_size:,} bytes)" for f in files)) if files else ""
                st.success(f"📁 Siste resultater lagret i: `{latest}`{file_lines}")

            # Final, permanent log in an expander
            with st.expander("📋 Fullt logg", expanded=False):
                st.text("\n".join(log_lines))
    st.divider()

# ===========================================================================
#  STEG 4 – Prognose
# ===========================================================================
if active_step == 4:
    _YEARS = [2026, 2027, 2028, 2029, 2030, 2031]

    # Read prognose config (always fresh from disk so saves in other steps are visible)
    _cfg4_raw: dict = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    _prog_cfg: dict = _cfg4_raw.get("prognose", {})
    _foru4 = _prog_cfg.get("forutsetninger", {})
    _inv4  = _prog_cfg.get("investeringer", {})
    _fus4  = _prog_cfg.get("fusjon", {})
    _syn4  = _prog_cfg.get("synergi", {})

    # ── Load base data (once per session) ────────────────────────────
    if "prognose_base_df" not in st.session_state:
        st.info("Last inn beregningsresultater fra Steg 3 for å starte prognosen.")
        if st.button("🔄 Last inn base-data", key="load_prog"):
            with st.spinner("Laster inntektsrammeberegning …"):
                try:
                    from pp_inntektsramme import RevenueCapCalculator  # noqa: PLC0415
                    _rc = RevenueCapCalculator()
                    st.session_state.prognose_base_df  = _rc.build_etl_dataframe()
                    st.session_state.prognose_ref_base = _rc.cfg.referanserente
                    st.rerun()
                except Exception as _e:
                    st.error(f"❌ Kunne ikke laste base-data: {_e}")
        st.stop()

    _base_df: pd.DataFrame  = st.session_state.prognose_base_df
    _ref_base: float        = st.session_state.get("prognose_ref_base", 0.072)
    _ref_base_pct: float    = round(_ref_base * 100, 2)

    # ── Company selector ─────────────────────────────────────────────
    _all_comp = _base_df["Selskap"].tolist()
    _saved_id = _prog_cfg.get("selskap_id")
    _default_idx = 0
    if _saved_id and _saved_id in _base_df["ID"].tolist():
        _default_idx = _base_df["ID"].tolist().index(_saved_id)
    _sel_comp = st.selectbox("Velg selskap", _all_comp, index=_default_idx, key="prog_comp")
    _sel_mask = _base_df["Selskap"] == _sel_comp
    _base_row: dict = _base_df.loc[_sel_mask].iloc[0].to_dict()

    with st.expander("Basisår 2026 – Nøkkeltall", expanded=True):
        _sk = [
            "Kostnadsgrunnlag", "Inntektsramme etter kalibrering",
            "AKG (inkl 1 % arbeids-kapital)", "AVS",
            "D&V-kostnader eks utredningskostnader", "KPI-justert KILE",
            "Nettap MWh i LD", "Nettap MWh i RD", "Kraftpris kr/MWh",
        ]
        _sc = st.columns(3)
        for _i, _k in enumerate([k for k in _sk if k in _base_row]):
            _v = _base_row[_k]
            with _sc[_i % 3]:
                st.metric(_k, f"{_v:,.0f}" if isinstance(_v, (int, float)) else str(_v))

    st.divider()

    # ── Forutsetninger + Fusjon ───────────────────────────────────────
    _col_foru, _col_fus = st.columns(2)

    with _col_foru:
        st.subheader("Forutsetninger per år")
        _r_def  = {y: _ref_base_pct for y in _YEARS}
        _kp_def = {y: float(_base_row.get("Kraftpris kr/MWh", 500.0)) for y in _YEARS}
        _if_def = {y: 2.5 for y in _YEARS}
        _if_def[2026] = 2.55
        _foru4_df = pd.DataFrame({
            "År":               _YEARS,
            "Referanserente %": [_foru4.get("referanserente_per_year", _r_def).get(y, _r_def[y])  for y in _YEARS],
            "Kraftpris kr/MWh": [_foru4.get("kraftpris_per_year",      _kp_def).get(y, _kp_def[y]) for y in _YEARS],
            "Inflasjon %":      [_foru4.get("inflasjon_per_year",      _if_def).get(y, _if_def[y]) for y in _YEARS],
        })
        _edited_foru = st.data_editor(
            _foru4_df, hide_index=True, use_container_width=True, disabled=["År"],
            key="foru4_ed",
            column_config={
                "Referanserente %": st.column_config.NumberColumn(format="%.2f"),
                "Kraftpris kr/MWh": st.column_config.NumberColumn(format="%.1f"),
                "Inflasjon %":      st.column_config.NumberColumn(format="%.2f"),
            },
        )

    with _col_fus:
        st.subheader("Fusjon")
        _fus_en = st.checkbox("Aktivér fusjon", value=bool(_fus4.get("enabled", False)), key="fus_en")
        _cf1, _cf2, _cf3 = st.columns(3)
        with _cf1:
            _fus_aar  = st.selectbox("Fusjonsår", _YEARS[1:], disabled=not _fus_en,
                                     index=_YEARS[1:].index(_fus4.get("fusjonsaar", 2027))
                                     if _fus4.get("fusjonsaar", 2027) in _YEARS[1:] else 0,
                                     key="fus_aar")
        with _cf2:
            _fus_fast = st.number_input("Fast kostnad (kkr)", step=100.0, format="%.0f",
                                        value=float(_fus4.get("omstillingskostnad_fast_kkr", 1000)),
                                        disabled=not _fus_en, key="fus_fast")
        with _cf3:
            _fus_var  = st.number_input("Variabel (% av DV)", step=0.5, format="%.1f",
                                        value=float(_fus4.get("omstillingskostnad_variabel_pst", 5.0)),
                                        disabled=not _fus_en, key="fus_var")

        st.subheader("Synergieffekter")
        _syn_en = st.checkbox("Aktivér synergieffekter", value=bool(_syn4.get("enabled", False)), key="syn_en")
        _cs1, _cs2, _cs3, _cs4 = st.columns(4)
        with _cs1:
            _syn_red   = st.number_input("Reduksjon % av DV", step=0.5, format="%.1f",
                                         value=float(_syn4.get("kostnadsreduksjon_pst", 0.0)),
                                         disabled=not _syn_en, key="syn_red")
        with _cs2:
            _syn_start = st.selectbox("Start år", _YEARS[1:], disabled=not _syn_en,
                                      index=_YEARS[1:].index(_syn4.get("synergistart_aar", 2027))
                                      if _syn4.get("synergistart_aar", 2027) in _YEARS[1:] else 0,
                                      key="syn_start")
        with _cs3:
            _syn_full  = st.selectbox("Full synergi år", _YEARS[1:], disabled=not _syn_en,
                                      index=_YEARS[1:].index(_syn4.get("full_synergi_aar", 2029))
                                      if _syn4.get("full_synergi_aar", 2029) in _YEARS[1:] else 2,
                                      key="syn_full")
        with _cs4:
            _syn_slutt = st.selectbox("Periode slutt", _YEARS[1:], disabled=not _syn_en,
                                      index=_YEARS[1:].index(_syn4.get("synergiperiode_slutt", 2031))
                                      if _syn4.get("synergiperiode_slutt", 2031) in _YEARS[1:] else 4,
                                      key="syn_slutt")

    # ── Investeringer + O&M ──────────────────────────────────────────
    _col_inv, _col_om = st.columns([3, 1])

    with _col_inv:
        st.subheader("Investeringer per år (kkr)")
        _z = {y: 0 for y in _YEARS}
        _inv4_df = pd.DataFrame({
            "År":                 _YEARS,
            "Nyinvesteringer":    [_inv4.get("nyinvesteringer_per_year",    _z).get(y, 0) for y in _YEARS],
            "Reinvesteringer":    [_inv4.get("reinvesteringer_per_year",    _z).get(y, 0) for y in _YEARS],
            "Kundeinvesteringer": [_inv4.get("kundeinvesteringer_per_year", _z).get(y, 0) for y in _YEARS],
        })
        _edited_inv = st.data_editor(_inv4_df, hide_index=True, use_container_width=True,
                                     disabled=["År"], key="inv4_ed")

    with _col_om:
        st.subheader("Drift og vedlikehold")
        _om_adj   = st.number_input("O&M justering %\n(utover inflasjon)",
                                    value=float(_prog_cfg.get("om_justering_pst", 0.0)),
                                    step=0.5, format="%.1f", key="om4_adj")
        _avs_sats = st.number_input("Avskrivningssats %",
                                    value=float(_inv4.get("avskrivningssats_pst", 4.0)),
                                    step=0.5, format="%.1f", key="avs_sats4")

    # ── Save / Reset ─────────────────────────────────────────────────
    st.divider()
    _cs4a, _cs4b, _ = st.columns([1, 1, 4])
    with _cs4a:
        _save4 = st.button("💾 Lagre forutsetninger", type="primary", key="save4")
    with _cs4b:
        if st.button("↩ Tilbakestill", key="reset4"):
            for _rk in ["foru4_ed", "inv4_ed", "fus_en", "fus_aar", "fus_fast", "fus_var",
                        "syn_en", "syn_red", "syn_start", "syn_full", "syn_slutt",
                        "om4_adj", "avs_sats4"]:
                st.session_state.pop(_rk, None)
            st.rerun()

    if _save4:
        def _yd(series: "pd.Series") -> dict:
            return {int(k): float(v) for k, v in series.items()}

        def _yi(series: "pd.Series") -> dict:
            return {int(k): int(v) for k, v in series.items()}

        _sel_id4 = int(_base_df.loc[_sel_mask, "ID"].iloc[0])
        _cfg_write = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        _cfg_write["prognose"] = {
            "selskap_id": _sel_id4,
            "forutsetninger": {
                "referanserente_per_year": _yd(_edited_foru.set_index("År")["Referanserente %"]),
                "kraftpris_per_year":      _yd(_edited_foru.set_index("År")["Kraftpris kr/MWh"]),
                "inflasjon_per_year":      _yd(_edited_foru.set_index("År")["Inflasjon %"]),
            },
            "fusjon": {
                "enabled": bool(_fus_en),
                "fusjonsaar": int(_fus_aar),
                "omstillingskostnad_fast_kkr": float(_fus_fast),
                "omstillingskostnad_variabel_pst": float(_fus_var),
            },
            "synergi": {
                "enabled": bool(_syn_en),
                "kostnadsreduksjon_pst": float(_syn_red),
                "synergistart_aar": int(_syn_start),
                "full_synergi_aar": int(_syn_full),
                "synergiperiode_slutt": int(_syn_slutt),
            },
            "investeringer": {
                "avskrivningssats_pst": float(_avs_sats),
                "nyinvesteringer_per_year":    _yi(_edited_inv.set_index("År")["Nyinvesteringer"]),
                "reinvesteringer_per_year":    _yi(_edited_inv.set_index("År")["Reinvesteringer"]),
                "kundeinvesteringer_per_year": _yi(_edited_inv.set_index("År")["Kundeinvesteringer"]),
            },
            "om_justering_pst": float(_om_adj),
            "rho": float(_cfg4_raw.get("forutsetninger", {}).get("rho", 0.7)),
        }
        CONFIG_PATH.write_text(
            _yaml.dump(_cfg_write, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        st.success("✅ Prognose-forutsetninger lagret!")

    # ── Live prognoseresultater ───────────────────────────────────────
    st.divider()
    st.subheader("📈 Prognoseresultater")

    _params = {
        "rho": float(_cfg4_raw.get("forutsetninger", {}).get("rho", 0.7)),
        "forutsetninger": {
            "referanserente_per_year": {int(k): float(v) for k, v in _edited_foru.set_index("År")["Referanserente %"].items()},
            "kraftpris_per_year":      {int(k): float(v) for k, v in _edited_foru.set_index("År")["Kraftpris kr/MWh"].items()},
            "inflasjon_per_year":      {int(k): float(v) for k, v in _edited_foru.set_index("År")["Inflasjon %"].items()},
        },
        "fusjon": {
            "enabled": bool(_fus_en),
            "fusjonsaar": int(_fus_aar),
            "omstillingskostnad_fast_kkr": float(_fus_fast),
            "omstillingskostnad_variabel_pst": float(_fus_var),
        },
        "synergi": {
            "enabled": bool(_syn_en),
            "kostnadsreduksjon_pst": float(_syn_red),
            "synergistart_aar": int(_syn_start),
            "full_synergi_aar": int(_syn_full),
            "synergiperiode_slutt": int(_syn_slutt),
        },
        "investeringer": {
            "avskrivningssats_pst": float(_avs_sats),
            "nyinvesteringer_per_year":    {int(k): int(v) for k, v in _edited_inv.set_index("År")["Nyinvesteringer"].items()},
            "reinvesteringer_per_year":    {int(k): int(v) for k, v in _edited_inv.set_index("År")["Reinvesteringer"].items()},
            "kundeinvesteringer_per_year": {int(k): int(v) for k, v in _edited_inv.set_index("År")["Kundeinvesteringer"].items()},
        },
        "om_justering_pst": float(_om_adj),
    }

    from pp_prognose import PrognoseCalculator  # noqa: PLC0415
    _forecast = PrognoseCalculator(_base_row, _params, _ref_base).build_forecast()

    _ir_base4 = float(_forecast.loc[_forecast["År"] == 2026, "Inntektsramme (prognose)"].iloc[0])
    _ir_end4  = float(_forecast.loc[_forecast["År"] == _YEARS[-1], "Inntektsramme (prognose)"].iloc[0])
    _pct4     = (_ir_end4 / _ir_base4 - 1) * 100 if _ir_base4 else 0.0

    _m1, _m2, _m3 = st.columns(3)
    _m1.metric("IR 2026 (basis)",          f"{_ir_base4:,.0f} kkr")
    _m2.metric(f"IR {_YEARS[-1]} (prognose)", f"{_ir_end4:,.0f} kkr")
    _m3.metric("Endring 2026 → 2031",      f"{_pct4:+.1f} %")

    st.line_chart(
        _forecast.set_index("År")[["Kostnadsgrunnlag", "Inntektsramme (prognose)"]],
        use_container_width=True,
    )
    st.dataframe(_forecast, use_container_width=True, hide_index=True)

    _csv4 = _forecast.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "⬇ Last ned prognose CSV",
        data=_csv4,
        file_name=f"prognose_{_sel_comp.replace(' ', '_')}.csv",
        mime="text/csv",
        key="dl_prog",
    )