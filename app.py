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
  {_card(1, _logo_img, "RME Modell")}
  <div class="pl-arr">&#9654;</div>
  {_card(2, "📝", "Konfigurasjon")}
  <div class="pl-arr">&#9654;</div>
  {_card(3, "📊", "Inntektsramme")}
  <div class="pl-arr">&#9654;</div>
  {_card(4, "📈", "Prognose")}
</div>
""")

# Compact nav buttons
_nav = st.columns(4)
_labels = ["Steg 1 – RME Modell", "Steg 2 – Konfigurasjon", "Steg 3 – Inntektsramme", "Steg 4 – Prognose"]
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
# HELPER: slider-bar input (one slider per year, looks like a bar chart)
# ═══════════════════════════════════════════════════════════════════════
def slider_bar_input(
    label: str,
    years: list[int],
    defaults: dict[int, float],
    min_val: float,
    max_val: float,
    step: float,
    fmt: str = "%.1f",
    suffix: str = "",
    key_prefix: str = "",
) -> dict[int, float]:
    """Render a row of vertical sliders (one per year) that visually mimic a
    draggable bar chart. Returns {year: value}."""
    st.markdown(f"**{label}**")
    cols = st.columns(len(years))
    out = {}
    for j, y in enumerate(years):
        with cols[j]:
            st.html(f'<div class="slider-year-label">{y}</div>')
            val = st.slider(
                str(y), min_value=min_val, max_value=max_val,
                value=float(defaults.get(y, (min_val + max_val) / 2)),
                step=step, format=fmt, key=f"{key_prefix}_{y}",
                label_visibility="collapsed",
            )
            st.html(f'<div class="slider-value-label">{val:{fmt[1:]}}{suffix}</div>')
            out[y] = val
    return out

# ═══════════════════════════════════════════════════════════════════════
# HELPER: time-series point input (Plotly chart + per-year number inputs)
# ═══════════════════════════════════════════════════════════════════════
def ts_point_input(
    label: str,
    years: list[int],
    defaults: dict[int, float],
    min_val: float,
    max_val: float,
    step: float,
    fmt: str = "%.2f",
    suffix: str = "",
    key_prefix: str = "",
) -> dict[int, float]:
    """Interactive Plotly time-series with per-year ± number inputs below.
    The chart reads from session_state so it always reflects the current
    values on each re-run. Returns {year: value}."""
    # Resolve current values (session_state wins; falls back to defaults)
    current = {
        y: float(st.session_state.get(f"{key_prefix}_{y}", defaults.get(y, (min_val + max_val) / 2)))
        for y in years
    }
    _y_vals   = [current[y] for y in years]
    _y_range  = max_val - min_val
    _fmt_spec = fmt[1:]  # strip leading '%'

    # ── Plotly chart ─────────────────────────────────────────────────
    st.markdown(f"**{label}**")
    _fig = go.Figure(go.Scatter(
        x=list(years),
        y=_y_vals,
        mode="lines+markers+text",
        text=[f"{v:{_fmt_spec}}{suffix}" for v in _y_vals],
        textposition="top center",
        textfont=dict(size=11, color="#2d5a8e"),
        marker=dict(size=13, color="#2d5a8e", line=dict(width=2, color="#ffffff")),
        line=dict(color="#2d5a8e", width=2.5),
        hovertemplate="%{x}: <b>%{y:.4g}" + suffix + "</b><extra></extra>",
    ))
    _fig.update_layout(
        height=200,
        margin=dict(l=45, r=15, t=30, b=5),
        xaxis=dict(tickvals=years, ticktext=[str(y) for y in years], fixedrange=True),
        yaxis=dict(
            range=[min_val - _y_range * 0.05, max_val + _y_range * 0.18],
            showgrid=True, gridcolor="#eef0f4", fixedrange=True,
        ),
        plot_bgcolor="#fafbfd",
        showlegend=False,
    )
    st.plotly_chart(_fig, use_container_width=True, key=f"{key_prefix}_chart",
                    config=dict(displayModeBar=False))

    # ── Per-year number inputs ────────────────────────────────────────
    _cols = st.columns(len(years))
    out: dict[int, float] = {}
    for _j, _y in enumerate(years):
        with _cols[_j]:
            _v = st.number_input(
                str(_y),
                min_value=min_val, max_value=max_val,
                value=current[_y],
                step=step, format=fmt,
                key=f"{key_prefix}_{_y}",
            )
            out[_y] = _v
    return out


# ═══════════════════════════════════════════════════════════════════════
# STEG 3 – Inntektsramme
# ═══════════════════════════════════════════════════════════════════════
if active_step == 3:
    run_pp = st.button("▶  Kjør inntektsrammeberegning", key="run_pp", type="primary")

    if run_pp:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with st.spinner("Kjører beregninger …"):
            try:
                from inntektsramme import RevenueCapCalculator  # noqa: PLC0415
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    calc = RevenueCapCalculator()
                    result_df: pd.DataFrame = calc.build_etl_dataframe()
                st.success("Beregninger fullført")
            except Exception as exc:
                st.error(f"Feil: {exc}")
                result_df = None

        stdout_text = stdout_buf.getvalue()
        stderr_text = stderr_buf.getvalue()
        if stdout_text or stderr_text:
            with st.expander("Konsollutskrift", expanded=False):
                if stdout_text:
                    st.code(stdout_text, language="text")
                if stderr_text:
                    st.code(stderr_text, language="text")

        if result_df is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Antall selskaper", len(result_df))
            if "Kostnadsgrunnlag" in result_df.columns:
                c2.metric("Sum Kostnadsgrunnlag", f"{result_df['Kostnadsgrunnlag'].sum():,.0f}")
            if "Inntektsramme før kalibrering" in result_df.columns:
                c3.metric("Sum IR (før kal.)", f"{result_df['Inntektsramme før kalibrering'].sum():,.0f}")

            search = st.text_input("🔍 Filtrer", key="pp_search", placeholder="Søk etter selskap …")
            display_df = result_df
            if search:
                mask = result_df.apply(
                    lambda col: col.astype(str).str.contains(search, case=False, na=False)
                ).any(axis=1)
                display_df = result_df[mask]
            st.dataframe(display_df, use_container_width=True, height=480)

            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    "⬇  CSV (semikolon)", key="dl_csv3",
                    data=result_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                    file_name="inntektsrammer_etl.csv", mime="text/csv",
                )
            with dl2:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    result_df.to_excel(w, index=False, sheet_name="ETL")
                st.download_button(
                    "⬇  Excel", key="dl_xlsx3",
                    data=buf.getvalue(),
                    file_name="inntektsrammer_etl.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


# ═══════════════════════════════════════════════════════════════════════
# STEG 2 – Konfigurasjon
# ═══════════════════════════════════════════════════════════════════════
CONFIG_PATH = ROOT_DIR / "config.yaml"

if active_step == 2:
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
        st.metric("Referanserente (beregnet)", f"{_r * 100:.2f} %")

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

    st.divider()
    cs, cr = st.columns([1, 5])
    with cs:
        save = st.button("💾  Lagre", type="primary")
    with cr:
        if st.button("↩  Tilbakestill"):
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
        st.success("config.yaml lagret")

# ═══════════════════════════════════════════════════════════════════════
# STEG 1 – R-Modell
# ═══════════════════════════════════════════════════════════════════════
if active_step == 1:
    run_irir = st.button("▶  Kjør IRIR-pipeline", key="run_irir", type="primary")

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

# ═══════════════════════════════════════════════════════════════════════
# STEG 4 – Prognose
# ═══════════════════════════════════════════════════════════════════════
if active_step == 4:
    _YEARS = [2026, 2027, 2028, 2029, 2030, 2031]

    _cfg4_raw: dict = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    _prog_cfg: dict = _cfg4_raw.get("prognose", {})
    _foru4 = _prog_cfg.get("forutsetninger", {})
    _inv4  = _prog_cfg.get("investeringer", {})
    _fus4  = _prog_cfg.get("fusjon", {})
    _syn4  = _prog_cfg.get("synergi", {})

    # ── Load / refresh base data ─────────────────────────────────────
    def _load_base_data():
        from inntektsramme import RevenueCapCalculator  # noqa: PLC0415
        _rc = RevenueCapCalculator()
        st.session_state.prognose_base_df  = _rc.build_etl_dataframe()
        st.session_state.prognose_ref_base = _rc.cfg.referanserente
        import datetime
        st.session_state.prognose_loaded_at = datetime.datetime.now().strftime("%H:%M:%S")

    _loaded = "prognose_base_df" in st.session_state
    _hdr_l, _hdr_r = st.columns([5, 1])
    with _hdr_l:
        if _loaded:
            _ts = st.session_state.get("prognose_loaded_at", "ukjent tid")
            st.caption(
                f"Beregningsgrunnlag lastet kl. {_ts}. "
                "Klikk **Oppdater** hvis du har endret konfigurasjon i Steg 2."
            )
        else:
            st.info(
                "Beregningsgrunnlaget er ikke lastet ennå. "
                "Klikk **Last inn** for å kjøre inntektsrammemodellen og hente base-data for prognosen. "
                "Du trenger ikke kjøre Steg 3 separat — dette gjøres automatisk her."
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

    # ── Company selector ─────────────────────────────────────────────
    _all_comp = _base_df["Selskap"].tolist()
    _saved_id = _prog_cfg.get("selskap_id")
    _default_idx = 0
    if _saved_id and _saved_id in _base_df["ID"].tolist():
        _default_idx = _base_df["ID"].tolist().index(_saved_id)
    _sel_comp = st.selectbox("Velg selskap", _all_comp, index=_default_idx, key="prog_comp")
    _sel_mask = _base_df["Selskap"] == _sel_comp
    _base_row: dict = _base_df.loc[_sel_mask].iloc[0].to_dict()

    # ── Base year KPIs ───────────────────────────────────────────────
    with st.expander("Basisår 2026 – Nøkkeltall", expanded=False):
        _sk = [
            "Kostnadsgrunnlag", "Inntektsramme etter kalibrering",
            "AKG (inkl 1 % arbeids-kapital)", "AVS",
            "D&V-kostnader eks utredningskostnader", "KPI-justert KILE",
            "Nettap MWh i LD", "Nettap MWh i RD", "Kraftpris kr/MWh",
        ]
        _sc = st.columns(3)
        for _i, _k in enumerate([k for k in _sk if k in _base_row]):
            with _sc[_i % 3]:
                _v = _base_row[_k]
                st.metric(_k, f"{_v:,.0f}" if isinstance(_v, (int, float)) else str(_v))

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  FORUTSETNINGER — interactive slider bars
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    st.subheader("Forutsetninger")

    _r_def  = {y: _foru4.get("referanserente_per_year", {}).get(y, _ref_base_pct)  for y in _YEARS}
    _kp_def = {y: _foru4.get("kraftpris_per_year", {}).get(y, float(_base_row.get("Kraftpris kr/MWh", 500.0))) for y in _YEARS}
    _if_def = {y: _foru4.get("inflasjon_per_year", {}).get(y, 2.5) for y in _YEARS}

    _vals_ref = ts_point_input(
        "Referanserente (%)", _YEARS, _r_def,
        min_val=3.0, max_val=12.0, step=0.05, fmt="%.2f", suffix=" %",
        key_prefix="ts_ref",
    )
    _vals_kp = slider_bar_input(
        "Kraftpris (kr/MWh)", _YEARS, _kp_def,
        min_val=100.0, max_val=1200.0, step=5.0, fmt="%.0f", suffix="",
        key_prefix="sl_kp",
    )
    _vals_inf = slider_bar_input(
        "Inflasjon (%)", _YEARS, _if_def,
        min_val=0.0, max_val=8.0, step=0.1, fmt="%.1f", suffix=" %",
        key_prefix="sl_inf",
    )

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  FUSJON & SYNERGI
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    st.subheader("Fusjon og synergieffekter")
    _fcol, _scol = st.columns(2)

    with _fcol:
        _fus_en = st.toggle("Fusjon", value=bool(_fus4.get("enabled", False)), key="fus_en")
        if _fus_en:
            _cf1, _cf2, _cf3 = st.columns(3)
            with _cf1:
                _fus_aar = st.selectbox("År", _YEARS[1:],
                    index=_YEARS[1:].index(_fus4.get("fusjonsaar", 2027)) if _fus4.get("fusjonsaar", 2027) in _YEARS[1:] else 0,
                    key="fus_aar")
            with _cf2:
                _fus_fast = st.number_input("Fast (kkr)", step=100.0, format="%.0f",
                    value=float(_fus4.get("omstillingskostnad_fast_kkr", 1000)), key="fus_fast")
            with _cf3:
                _fus_var = st.number_input("Variabel (% DV)", step=0.5, format="%.1f",
                    value=float(_fus4.get("omstillingskostnad_variabel_pst", 5.0)), key="fus_var")
        else:
            _fus_aar = _fus4.get("fusjonsaar", 2027)
            _fus_fast = float(_fus4.get("omstillingskostnad_fast_kkr", 1000))
            _fus_var = float(_fus4.get("omstillingskostnad_variabel_pst", 5.0))

    with _scol:
        _syn_en = st.toggle("Synergieffekter", value=bool(_syn4.get("enabled", False)), key="syn_en")
        if _syn_en:
            _cs1, _cs2 = st.columns(2)
            with _cs1:
                _syn_red = st.slider("Kostnadsreduksjon (% av DV)", 0.0, 30.0,
                    value=float(_syn4.get("kostnadsreduksjon_pst", 0.0)), step=0.5, key="syn_red")
            with _cs2:
                _syn_start = st.selectbox("Start", _YEARS[1:],
                    index=_YEARS[1:].index(_syn4.get("synergistart_aar", 2027)) if _syn4.get("synergistart_aar", 2027) in _YEARS[1:] else 0,
                    key="syn_start")
            _cs3, _cs4 = st.columns(2)
            with _cs3:
                _syn_full = st.selectbox("Full synergi", _YEARS[1:],
                    index=_YEARS[1:].index(_syn4.get("full_synergi_aar", 2029)) if _syn4.get("full_synergi_aar", 2029) in _YEARS[1:] else 2,
                    key="syn_full")
            with _cs4:
                _syn_slutt = st.selectbox("Slutt", _YEARS[1:],
                    index=_YEARS[1:].index(_syn4.get("synergiperiode_slutt", 2031)) if _syn4.get("synergiperiode_slutt", 2031) in _YEARS[1:] else 4,
                    key="syn_slutt")
        else:
            _syn_red = float(_syn4.get("kostnadsreduksjon_pst", 0.0))
            _syn_start = _syn4.get("synergistart_aar", 2027)
            _syn_full = _syn4.get("full_synergi_aar", 2029)
            _syn_slutt = _syn4.get("synergiperiode_slutt", 2031)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  INVESTERINGER
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    st.subheader("Investeringer")
    _z = {y: 0 for y in _YEARS}
    _inv4_df = pd.DataFrame({
        "År":                 _YEARS,
        "Nyinvesteringer":    [_inv4.get("nyinvesteringer_per_year",    _z).get(y, 0) for y in _YEARS],
        "Reinvesteringer":    [_inv4.get("reinvesteringer_per_year",    _z).get(y, 0) for y in _YEARS],
        "Kundeinvesteringer": [_inv4.get("kundeinvesteringer_per_year", _z).get(y, 0) for y in _YEARS],
    })

    _ci, _com = st.columns([3, 1])
    with _ci:
        _edited_inv = st.data_editor(
            _inv4_df, hide_index=True, use_container_width=True, disabled=["År"],
            column_config={
                "Nyinvesteringer":    st.column_config.NumberColumn(format="%d kkr"),
                "Reinvesteringer":    st.column_config.NumberColumn(format="%d kkr"),
                "Kundeinvesteringer": st.column_config.NumberColumn(format="%d kkr"),
            },
            key="inv4_ed",
        )
    with _com:
        _om_adj   = st.slider("O&M justering %", -5.0, 15.0,
                               value=float(_prog_cfg.get("om_justering_pst", 0.0)),
                               step=0.5, key="om4_adj")
        _avs_sats = st.slider("Avskrivningssats %", 1.0, 10.0,
                               value=float(_inv4.get("avskrivningssats_pst", 4.0)),
                               step=0.5, key="avs_sats4")

    # ── Save / Reset ─────────────────────────────────────────────────
    st.divider()
    _sa, _sb, _ = st.columns([1, 1, 4])
    with _sa:
        _save4 = st.button("💾  Lagre", type="primary", key="save4")
    with _sb:
        if st.button("↩  Tilbakestill", key="reset4"):
            _reset_keys = (
                [f"ts_ref_{y}" for y in _YEARS]
                + ["ts_ref_chart"]
                + [f"sl_kp_{y}" for y in _YEARS]
                + [f"sl_inf_{y}" for y in _YEARS]
                + ["inv4_ed", "fus_en", "fus_aar", "fus_fast", "fus_var",
                   "syn_en", "syn_red", "syn_start", "syn_full", "syn_slutt",
                   "om4_adj", "avs_sats4"]
            )
            for _rk in _reset_keys:
                st.session_state.pop(_rk, None)
            st.rerun()

    if _save4:
        _sel_id4 = int(_base_df.loc[_sel_mask, "ID"].iloc[0])
        _cfg_write = _yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        _cfg_write["prognose"] = {
            "selskap_id": _sel_id4,
            "forutsetninger": {
                "referanserente_per_year": {int(k): float(v) for k, v in _vals_ref.items()},
                "kraftpris_per_year":      {int(k): float(v) for k, v in _vals_kp.items()},
                "inflasjon_per_year":      {int(k): float(v) for k, v in _vals_inf.items()},
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
                "nyinvesteringer_per_year":    {int(r["År"]): int(r["Nyinvesteringer"])    for _, r in _edited_inv.iterrows()},
                "reinvesteringer_per_year":    {int(r["År"]): int(r["Reinvesteringer"])    for _, r in _edited_inv.iterrows()},
                "kundeinvesteringer_per_year": {int(r["År"]): int(r["Kundeinvesteringer"]) for _, r in _edited_inv.iterrows()},
            },
            "om_justering_pst": float(_om_adj),
            "rho": float(_cfg4_raw.get("forutsetninger", {}).get("rho", 0.7)),
        }
        CONFIG_PATH.write_text(
            _yaml.dump(_cfg_write, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        st.success("Prognose-forutsetninger lagret")

    # ==================================================================
    #  RESULTS — live forecast with Plotly charts
    # ==================================================================
    st.divider()

    _params = {
        "rho": float(_cfg4_raw.get("forutsetninger", {}).get("rho", 0.7)),
        "forutsetninger": {
            "referanserente_per_year": {int(k): float(v) for k, v in _vals_ref.items()},
            "kraftpris_per_year":      {int(k): float(v) for k, v in _vals_kp.items()},
            "inflasjon_per_year":      {int(k): float(v) for k, v in _vals_inf.items()},
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
            "nyinvesteringer_per_year":    {int(r["År"]): int(r["Nyinvesteringer"])    for _, r in _edited_inv.iterrows()},
            "reinvesteringer_per_year":    {int(r["År"]): int(r["Reinvesteringer"])    for _, r in _edited_inv.iterrows()},
            "kundeinvesteringer_per_year": {int(r["År"]): int(r["Kundeinvesteringer"]) for _, r in _edited_inv.iterrows()},
        },
        "om_justering_pst": float(_om_adj),
    }

    from prognose import PrognoseCalculator  # noqa: PLC0415
    _forecast = PrognoseCalculator(_base_row, _params, _ref_base).build_forecast()

    _ir_base4 = float(_forecast.loc[_forecast["År"] == 2026, "Inntektsramme (prognose)"].iloc[0])
    _ir_end4  = float(_forecast.loc[_forecast["År"] == _YEARS[-1], "Inntektsramme (prognose)"].iloc[0])
    _pct4     = (_ir_end4 / _ir_base4 - 1) * 100 if _ir_base4 else 0.0

    _m1, _m2, _m3 = st.columns(3)
    _m1.metric("IR 2026 (basis)", f"{_ir_base4:,.0f} kkr")
    _m2.metric(f"IR {_YEARS[-1]} (prognose)", f"{_ir_end4:,.0f} kkr")
    _m3.metric("Endring", f"{_pct4:+.1f} %", delta=f"{_ir_end4 - _ir_base4:,.0f} kkr")

    # ── Plotly: Stacked area — cost components ───────────────────────
    _colors = {
        "DV-kostnader":    "#2d5a8e",
        "Avskrivninger":   "#5ba3f5",
        "Nettapskostnad":  "#8ecae6",
        "KILE":            "#b8d4e3",
        "Fusjonskostnad":  "#e76f51",
    }
    fig_stack = go.Figure()
    for _cc in ["DV-kostnader", "Avskrivninger", "Nettapskostnad", "KILE", "Fusjonskostnad"]:
        if _cc in _forecast.columns:
            fig_stack.add_trace(go.Scatter(
                x=_forecast["År"], y=_forecast[_cc],
                mode="lines", stackgroup="one", name=_cc,
                line=dict(width=0.5, color=_colors.get(_cc, "#999")),
                hovertemplate="%{y:,.0f} kkr<extra>" + _cc + "</extra>",
            ))
    fig_stack.add_trace(go.Scatter(
        x=_forecast["År"], y=_forecast["Inntektsramme (prognose)"],
        mode="lines+markers", name="Inntektsramme",
        line=dict(color="#e76f51", width=3), marker=dict(size=8),
        hovertemplate="%{y:,.0f} kkr<extra>IR</extra>",
    ))
    fig_stack.update_layout(
        title=dict(text=f"Kostnadskomponenter og IR – {_sel_comp}", font=dict(size=15)),
        xaxis=dict(title="", dtick=1), yaxis=dict(title="kkr", separatethousands=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=20, t=60, b=30), height=400,
        hovermode="x unified", plot_bgcolor="#fafbfd",
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    # ── Plotly: KG vs IR bar chart ───────────────────────────────────
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=_forecast["År"], y=_forecast["Kostnadsgrunnlag"],
        name="Kostnadsgrunnlag", marker_color="#2d5a8e",
        hovertemplate="%{y:,.0f} kkr<extra>KG</extra>",
    ))
    fig_bar.add_trace(go.Bar(
        x=_forecast["År"], y=_forecast["Inntektsramme (prognose)"],
        name="Inntektsramme", marker_color="#e76f51",
        hovertemplate="%{y:,.0f} kkr<extra>IR</extra>",
    ))
    fig_bar.update_layout(
        title=dict(text="Kostnadsgrunnlag vs. Inntektsramme", font=dict(size=15)),
        barmode="group", xaxis=dict(title="", dtick=1),
        yaxis=dict(title="kkr", separatethousands=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=20, t=60, b=30), height=350, plot_bgcolor="#fafbfd",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # ── Data table + download ────────────────────────────────────────
    with st.expander("Detaljert tabell", expanded=False):
        st.dataframe(_forecast, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇  Last ned prognose CSV",
        data=_forecast.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name=f"prognose_{_sel_comp.replace(' ', '_')}.csv",
        mime="text/csv", key="dl_prog",
    )