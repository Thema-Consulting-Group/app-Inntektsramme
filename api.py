"""
Inntektsramme – FastAPI backend
Run:  uvicorn api:app --reload --port 8000
Then open:  http://localhost:8000
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, AsyncGenerator

import numpy as np
import pandas as pd
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

app = FastAPI(title="Inntektsramme API", docs_url="/api/docs")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None for JSON serialisation."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    for col in df.columns:
        if df[col].dtype in (float, np.float64, np.float32):
            df[col] = df[col].where(pd.notna(df[col]), other=None)
    return _clean(df.to_dict(orient="records"))


def _latest_run_paths(run_name: str | None = None) -> tuple[Path, Path, Path] | None:
    """Return (irir_path, ld_path, rd_path) from a specific or the latest complete Run_* dir."""
    results_dir = ROOT / "Results"
    if not results_dir.is_dir():
        return None

    if run_name:
        # Validate: only allow Run_YYYY-MM-DD_HH-MM-SS style names (prevents path traversal)
        if not re.match(r'^Run_[\d\-_]+$', run_name):
            return None
        d = results_dir / run_name
        if not d.is_dir():
            return None
        irir = next((f for pat in ("*grunnlagsdata*.xlsx", "*grunnlagsdata*.xls", "*grunnlagsdata*.csv") for f in d.glob(pat)), None)
        ld   = next(d.glob("Data_Resultater_LD*"), None)
        rd   = next(d.glob("Data_Resultater_RD*"), None)
        return (irir, ld, rd) if (irir and ld and rd) else None

    run_dirs = sorted(
        [d for d in results_dir.iterdir() if d.is_dir() and d.name.startswith("Run_")],
        reverse=True,
    )
    for d in run_dirs:
        irir = next((f for pat in ("*grunnlagsdata*.xlsx", "*grunnlagsdata*.xls", "*grunnlagsdata*.csv") for f in d.glob(pat)), None)
        ld   = next(d.glob("Data_Resultater_LD*"), None)
        rd   = next(d.glob("Data_Resultater_RD*"), None)
        if irir and ld and rd:
            return irir, ld, rd
    return None


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ConfigUpdate(BaseModel):
    content: str  # raw YAML text


class ScenarioRequest(BaseModel):
    exclude_ids: list[int] = []
    focus_id: int
    run_name: str | None = None


class PrognoseRequest(BaseModel):
    orgn: int
    forutsetninger: dict | None = None
    investeringer: dict | None = None
    dv_vekst: dict | None = None
    rho: float = 0.7
    avs_sats: float = 4.0
    labor_share_ld: float = 0.30
    labor_share_rd: float = 0.30
    merge_yr: int | None = None
    synergy_pct: float = 0.0
    one_off: float = 0.0
    run_name: str | None = None


# ---------------------------------------------------------------------------
# /api/runs
# ---------------------------------------------------------------------------

@app.get("/api/runs")
def get_runs():
    results_dir = ROOT / "Results"
    if not results_dir.is_dir():
        return {"runs": []}
    runs = []
    for d in sorted(results_dir.iterdir(), reverse=True):
        if not (d.is_dir() and d.name.startswith("Run_")):
            continue
        files = [{"name": f.name, "size": f.stat().st_size} for f in sorted(d.iterdir()) if f.is_file()]
        complete = bool(
            next((f for pat in ("*grunnlagsdata*.xlsx", "*grunnlagsdata*.xls", "*grunnlagsdata*.csv") for f in d.glob(pat)), None)
            and next(d.glob("Data_Resultater_LD*"), None)
            and next(d.glob("Data_Resultater_RD*"), None)
        )
        runs.append({"name": d.name, "files": files, "complete": complete})
    return {"runs": runs}


# ---------------------------------------------------------------------------
# /api/config
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        raise HTTPException(404, "config.yaml not found")
    return {"content": cfg_path.read_text(encoding="utf-8")}


@app.put("/api/config")
def update_config(body: ConfigUpdate):
    try:
        yaml.safe_load(body.content)  # validate YAML
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Ugyldig YAML: {e}")
    cfg_path = ROOT / "config.yaml"
    cfg_path.write_text(body.content, encoding="utf-8")
    return {"ok": True}


# ---------------------------------------------------------------------------
# /api/ir-table  — revenue cap calculation
# ---------------------------------------------------------------------------

@app.get("/api/ir-table")
def get_ir_table(run_name: str | None = Query(default=None)):
    try:
        from inntektsramme import RevenueCapCalculator  # noqa: PLC0415
        rc = RevenueCapCalculator(run_name=run_name)
        result_df = rc.build_etl_dataframe()
        ir_df = rc.build_ir_dataframe()
    except Exception as e:
        raise HTTPException(500, str(e))

    return {
        "table": _df_to_records(result_df),
        "ir": _df_to_records(ir_df),
        "meta": {
            "n_companies": len(result_df),
            "sum_kostnadsgrunnlag": _clean(
                float(result_df["Kostnadsgrunnlag"].sum())
                if "Kostnadsgrunnlag" in result_df.columns else None
            ),
            "sum_ir": _clean(
                float(result_df["Inntektsramme etter kalibrering"].sum())
                if "Inntektsramme etter kalibrering" in result_df.columns else None
            ),
        },
    }


# ---------------------------------------------------------------------------
# /api/run-pipeline  — SSE streaming of R pipeline
# ---------------------------------------------------------------------------

_SUPPRESS = (
    "── Attaching", "✔ ", "✖ ", "── Conflicts", "ℹ ", "Registered S3",
    "The following object", "The following packages", "tidyverse",
    "Loading required package:", "character(0)", '[1] "C:/', '[1] "/',
)

async def _pipeline_generator() -> AsyncGenerator[str, None]:
    rscript = shutil.which("Rscript")
    if not rscript:
        yield f"data: {json.dumps({'error': 'Finner ikke Rscript på PATH'})}\n\n"
        return

    proc = subprocess.Popen(
        [rscript, "--quiet", "IRiR.R"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=str(ROOT),
    )

    for line in proc.stdout:  # type: ignore[union-attr]
        stripped = line.rstrip()
        if stripped and not any(stripped.startswith(p) or p in stripped for p in _SUPPRESS):
            yield f"data: {json.dumps({'line': stripped})}\n\n"

    proc.wait()
    yield f"data: {json.dumps({'done': True, 'code': proc.returncode})}\n\n"


@app.get("/api/run-pipeline")
async def run_pipeline():
    return StreamingResponse(
        _pipeline_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# /api/companies  — list all companies from latest run
# ---------------------------------------------------------------------------

@app.get("/api/companies")
def get_companies(run_name: str | None = Query(default=None)):
    paths = _latest_run_paths(run_name)
    if not paths:
        raise HTTPException(404, "Ingen resultater funnet. Kjør RME Modell først.")
    _, ld_path, _ = paths
    try:
        df = pd.read_excel(ld_path, sheet_name="Resultater_LD")
        companies = (
            df[["id", "comp"]]
            .drop_duplicates()
            .sort_values("comp")
            .rename(columns={"comp": "name"})
            .to_dict(orient="records")
        )
        return {"companies": companies}
    except Exception as e:
        # Fallback: use ld_InputDEA.csv
        try:
            from frontselskap import load_ld_dea_inputs  # noqa: PLC0415
            dea_df = load_ld_dea_inputs(ROOT / "Results")
            return {"companies": [{"id": int(r["id"]), "name": str(r["id"])} for _, r in dea_df.iterrows()]}
        except Exception as e2:
            raise HTTPException(500, str(e2))


# ---------------------------------------------------------------------------
# /api/prognose  — revenue cap forecast for one company
# ---------------------------------------------------------------------------

@app.post("/api/prognose")
def run_prognose(body: PrognoseRequest):
    try:
        from inntektsramme import RevenueCapCalculator  # noqa: PLC0415
        from prognose import PrognoseCalculator, FORECAST_YEARS  # noqa: PLC0415

        rc = RevenueCapCalculator(run_name=body.run_name)
        etl_df = rc.build_etl_dataframe()
        ir_df  = rc.build_ir_dataframe()

        etl_row = etl_df[etl_df["Org.nr"] == body.orgn]
        ir_row  = ir_df[ir_df["Org.nr"] == body.orgn]
        if etl_row.empty:
            raise HTTPException(404, f"Selskap med org.nr {body.orgn} ikke funnet")

        paths = _latest_run_paths(body.run_name)
        grunn_csv = str(paths[0]) if paths else None

        calc = PrognoseCalculator(
            base_ir=ir_row.iloc[0].to_dict() if not ir_row.empty else {},
            base_etl=etl_row.iloc[0].to_dict(),
            forutsetninger=body.forutsetninger,
            investeringer=body.investeringer,
            dv_vekst=body.dv_vekst,
            rho=body.rho,
            avs_sats=body.avs_sats,
            labor_share_ld=body.labor_share_ld,
            labor_share_rd=body.labor_share_rd,
            fusjon={"merge_yr": body.merge_yr, "synergy_pct": body.synergy_pct, "one_off": body.one_off},
            grunnlagsdata_csv_path=grunn_csv,
        )
        forecast_df  = calc.build_forecast()
        grunn_df     = calc.build_grunnlagsdata()

        # Convert integer year columns to strings for JSON
        grunn_df.columns = [str(c) for c in grunn_df.columns]

        # Summary series for chart (from forecast, keyed by string year)
        summary_rows = []
        for param, col in [
            ("Kostnadsgrunnlag", "Kostnadsgrunnlag"),
            ("Kostnadsnorm",     "Kostnadsnorm"),
            ("Inntektsramme",    "Inntektsramme"),
            ("Driftsresultat",   "Driftsresultat"),
            ("Effektivitet Dnett %",   "Effektivitet Dnett %"),
            ("Effektivitet vektet %",  "Effektivitet vektet %"),
            ("Avkastning NVE %",       "Avkastning NVE %"),
        ]:
            row: dict = {"Parameter": param, "Nettnivå": "Samlet", "Enhet": "kkr"}
            for _, fr in forecast_df.iterrows():
                row[str(int(fr["År"]))] = fr[col]
            summary_rows.append(row)

        all_year_cols = sorted([c for c in grunn_df.columns if c.isdigit()], key=int)
        return {
            "forecast": _df_to_records(grunn_df),
            "summary":  summary_rows,
            "years": [str(y) for y in FORECAST_YEARS],
            "all_years": all_year_cols,
            "company_name": str(etl_row.iloc[0].get("Selskap", body.orgn)),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# /api/kostnader  — cost breakdown table (RME format)
# ---------------------------------------------------------------------------

@app.get("/api/kostnader")
def get_kostnader(orgn: int | None = Query(default=None), run_name: str | None = Query(default=None)):
    paths = _latest_run_paths(run_name)
    if not paths:
        raise HTTPException(404, "Ingen resultater funnet.")
    grunn_csv = str(paths[0])
    try:
        from kostnader import grunnlagsdata_to_rme, _load_nve_id_map  # noqa: PLC0415
        company_ids = None
        if orgn is not None:
            id_map = _load_nve_id_map(grunn_csv)
            nve_id = id_map.get(orgn, orgn)
            company_ids = [nve_id]
        df = grunnlagsdata_to_rme(grunn_csv, company_ids=company_ids)
        df.columns = [str(c) for c in df.columns]
        return {"table": _df_to_records(df)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# /api/task-elasticities  — pooled industry-wide Δtask/MNOK estimates
# ---------------------------------------------------------------------------

@app.get("/api/task-elasticities")
def get_task_elasticities(run_name: str | None = Query(default=None)):
    paths = _latest_run_paths(run_name)
    if not paths:
        raise HTTPException(404, "Ingen resultater funnet.")
    grunn_csv = str(paths[0])
    try:
        from prognose import estimate_task_elasticities  # noqa: PLC0415
        return estimate_task_elasticities(grunn_csv)
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# /api/ld-dea  — DEA inputs for frontier analysis
# ---------------------------------------------------------------------------

@app.get("/api/ld-dea")
def get_ld_dea(run_name: str | None = Query(default=None)):
    paths = _latest_run_paths(run_name)
    if not paths:
        raise HTTPException(404, "Ingen resultater funnet.")
    _, ld_path, _ = paths
    try:
        from frontselskap import load_ld_dea_inputs  # noqa: PLC0415
        dea_df = load_ld_dea_inputs(ROOT / "Results")
        res_ld = pd.read_excel(ld_path, sheet_name="Resultater_LD")
        id_to_comp = res_ld.set_index("id")["comp"].to_dict()
        records = _df_to_records(dea_df)
        for r in records:
            r["comp"] = id_to_comp.get(r["id"], str(r["id"]))
        return {"companies": records}
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# /api/frontier-scenario  — DEA scenario
# ---------------------------------------------------------------------------

@app.post("/api/frontier-scenario")
def run_frontier_scenario(body: ScenarioRequest):
    paths = _latest_run_paths(body.run_name)
    if not paths:
        raise HTTPException(404, "Ingen resultater funnet.")
    _, ld_path, _ = paths
    try:
        from frontselskap import (  # noqa: PLC0415
            load_ld_dea_inputs, run_ld_scenario, get_frontier_companies, get_peer_shares,
        )
        dea_df = load_ld_dea_inputs(ROOT / "Results")
        res_ld = pd.read_excel(ld_path, sheet_name="Resultater_LD")
        id_to_comp: dict = res_ld.set_index("id")["comp"].to_dict()

        # NCS peer weights from R results
        ncs_cols = [c for c in res_ld.columns if c.startswith("ld_ncs_")]

        scenario_df = run_ld_scenario(dea_df, res_ld, exclude_ids=body.exclude_ids)
        base_frontier = get_frontier_companies(dea_df, [])
        scen_frontier = get_frontier_companies(dea_df, body.exclude_ids)

        focus_row_df = scenario_df[scenario_df["id"] == body.focus_id]
        focus_peers_r: dict = {}
        focus_peers_lp: list[dict] = []

        if not focus_row_df.empty:
            fr = focus_row_df.iloc[0]
            focus_peers_lp = get_peer_shares(fr, id_to_comp).to_dict(orient="records")
            # R NCS peers
            r_row = res_ld[res_ld["id"] == body.focus_id]
            if not r_row.empty and ncs_cols:
                for col in ncs_cols:
                    v = float(r_row.iloc[0][col])
                    if v > 1e-6:
                        focus_peers_r[col.replace("ld_ncs_", "")] = v

        return {
            "scenario": _df_to_records(scenario_df),
            "frontier_base": [
                {"id": i, "name": id_to_comp.get(i, str(i))}
                for i in sorted(base_frontier)
            ],
            "frontier_scenario": [
                {"id": i, "name": id_to_comp.get(i, str(i))}
                for i in sorted(scen_frontier)
            ],
            "focus_peers_r": focus_peers_r,
            "focus_peers_lp": _clean(focus_peers_lp),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Static files — must be last
# ---------------------------------------------------------------------------

static_dir = ROOT / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
