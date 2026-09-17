"""
Inntektsramme – FastAPI backend
Run:  uvicorn api:app --reload --port 8000
Then open:  http://localhost:8000
"""

from __future__ import annotations

import asyncio
import sys

# Windows: SelectorEventLoop (default) doesn't support subprocesses.
# Switch to ProactorEventLoop before uvicorn starts the loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import glob
import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, AsyncGenerator

import numpy as np
import pandas as pd
import yaml
import secrets
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import fusjon_grunnlagsdata  # noqa: E402  (needs ROOT on sys.path)
import variabelnavn  # noqa: E402  (needs ROOT on sys.path)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional HTTP Basic Auth  (set APP_USER + APP_PASS env vars to enable)
# ---------------------------------------------------------------------------
_AUTH_USER = os.environ.get("APP_USER", "")
_AUTH_PASS = os.environ.get("APP_PASS", "")
_http_security = HTTPBasic(auto_error=False)


def _check_auth(credentials: HTTPBasicCredentials | None = Depends(_http_security)):
    if not _AUTH_USER:
        return  # auth disabled
    if credentials is None:
        raise HTTPException(
            401, "Authentication required",
            headers={"WWW-Authenticate": "Basic realm='Inntektsramme'"},
        )
    ok = (
        secrets.compare_digest(credentials.username.encode(), _AUTH_USER.encode())
        and secrets.compare_digest(credentials.password.encode(), _AUTH_PASS.encode())
    )
    if not ok:
        raise HTTPException(
            401, "Invalid credentials",
            headers={"WWW-Authenticate": "Basic realm='Inntektsramme'"},
        )


# Re-create app with global auth dependency so every route is protected.
app = FastAPI(
    title="Inntektsramme API",
    docs_url="/api/docs",
    dependencies=[Depends(_check_auth)],
)

# Path where the user can drop a grunnlagsdata CSV to override auto-detection
_UPLOADED_GRUNN = ROOT / "Data" / "grunnlagsdata_uploaded.csv"

# Pristine copy of the last generated grunnlagsdata. The upload slot above is
# consumed by a run; this one is not, so it stays available as the clean
# baseline for validating hand edits and as the starting point for a merge.
_GENERATED_GRUNN = ROOT / "Data" / "grunnlagsdata_generert.csv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_grunnlagsdata(run_name: str | None = None) -> str | None:
    """Return path to grunnlagsdata CSV.
    Uploaded file always takes priority over auto-detection.
    run_name is only used as fallback when no uploaded file exists.
    """
    if _UPLOADED_GRUNN.exists():
        return str(_UPLOADED_GRUNN)
    paths = _latest_run_paths(run_name)
    return str(paths[0]) if paths else None


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
        # Prevent path traversal: no slashes, backslashes, or ".." segments
        if re.search(r'[\\/]|\.\.' , run_name) or not run_name.strip():
            return None
        d = results_dir / run_name
        # Ensure resolved path is still inside results_dir
        if not str(d.resolve()).startswith(str(results_dir.resolve())):
            return None
        if not d.is_dir():
            return None
        irir = next((f for pat in ("*grunnlagsdata*.csv", "*grunnlagsdata*.xlsx", "*grunnlagsdata*.xls") for f in d.glob(pat)), None)
        ld   = next(d.glob("Data_Resultater_LD*"), None)
        rd   = next(d.glob("Data_Resultater_RD*"), None)
        return (irir, ld, rd) if (irir and ld and rd) else None

    # Auto-latest: prefer dated Run_ dirs (sorted desc), then any other dir
    def _sort_key(p: Path):
        is_dated = bool(re.match(r'^Run_\d', p.name))
        return (0 if is_dated else 1, p.name)

    run_dirs = sorted(
        [d for d in results_dir.iterdir() if d.is_dir() and not d.name.startswith('.')],
        key=_sort_key,
        reverse=True,
    )
    for d in run_dirs:
        irir = next((f for pat in ("*grunnlagsdata*.csv", "*grunnlagsdata*.xlsx", "*grunnlagsdata*.xls") for f in d.glob(pat)), None)
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


class SonepriserRequest(BaseModel):
    # {"NO1": 624.3, ...} in NOK/MWh — the unit config.yaml uses.
    priser: dict[str, float]


class ScenarioRequest(BaseModel):
    exclude_ids: list[int] = []
    focus_id: int
    run_name: str | None = None


class FusjonGruppeRequest(BaseModel):
    mottaker: int              # orgn of the company that absorbs the others
    maal: list[int] = []       # orgn of the companies being absorbed


class FusjonGrunnlagsdataRequest(BaseModel):
    grupper: list[FusjonGruppeRequest] = []


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
    task_elas_override: dict | None = None  # {"ld": {...}, "rd": {...}}


# ---------------------------------------------------------------------------
# /api/input-files  — BaseData override files (irbase / kraftpris / id)
# ---------------------------------------------------------------------------

# The default filenames must stay in sync with R-script/0_1_Config_Assumptions_Data.R,
# which resolves the same override-then-default pair for each input file.
_INPUT_FILE_DEFS: dict[str, dict[str, str]] = {
    "irbase":    {"override": "irBase_override.xlsx",
                  "default":  "irBase - Stata - 12.11.2025 09_56_56.xlsx",
                  "folder":   "Data/BaseData"},
    "kraftpris": {"override": "kraftpris_override.xlsx",
                  "default":  "kraftpris2026.xlsx",
                  "folder":   "Data/BaseData"},
    "id":        {"override": "id_override.xlsx",
                  "default":  "id_ir_26.xlsx",
                  "folder":   "Data/BaseData"},
}

# In-app editing targets the small lookup files (kraftpris is 82x2, id 97x3).
# irBase is 440x64 - 28k cells is more than the browser table handles well and
# more than anyone edits by hand, so that one stays download / edit / upload.
_SHEET_EDIT_MAX_ROWS = 500
_SHEET_EDIT_MAX_COLS = 12


def _resolve_input_file(key: str) -> tuple[Path, str, bool]:
    """Return (path, filename, is_override) for the file the model would read.

    Same precedence as the R side: the override if one has been uploaded,
    otherwise the shipped default - so a download hands back exactly what the
    next run would use.
    """
    if key not in _INPUT_FILE_DEFS:
        raise HTTPException(404, f"Ukjent fil-nøkkel: {key}")
    d = _INPUT_FILE_DEFS[key]
    folder = ROOT / d["folder"]
    override = folder / d["override"]
    if override.exists():
        return override, d["override"], True
    default = folder / d["default"]
    if not default.exists():
        raise HTTPException(404, f"Finner ikke standardfilen «{d['default']}» i {d['folder']}.")
    return default, d["default"], False


@app.get("/api/input-files")
def get_input_files():
    result: dict = {}
    for key, d in _INPUT_FILE_DEFS.items():
        p = ROOT / d["folder"] / d["override"]
        base = ROOT / d["folder"] / d["default"]
        result[key] = {
            "active": p.exists(),
            "filename": d["override"] if p.exists() else None,
            "size": p.stat().st_size if p.exists() else None,
            # What a download would hand back when no override is uploaded.
            "default_filename": d["default"],
            "default_exists": base.exists(),
        }
    return result


@app.post("/api/input-files/{key}")
async def upload_input_file(key: str, file: UploadFile = File(...)):
    if key not in _INPUT_FILE_DEFS:
        raise HTTPException(404, f"Ukjent fil-nøkkel: {key}")
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Kun Excel-filer (.xlsx/.xls) støttes.")
    d = _INPUT_FILE_DEFS[key]
    dest = ROOT / d["folder"] / d["override"]
    content = await file.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return {"ok": True, "filename": file.filename, "size": len(content)}


@app.delete("/api/input-files/{key}")
def delete_input_file(key: str):
    if key not in _INPUT_FILE_DEFS:
        raise HTTPException(404, f"Ukjent fil-nøkkel: {key}")
    d = _INPUT_FILE_DEFS[key]
    p = ROOT / d["folder"] / d["override"]
    if p.exists():
        p.unlink()
    return {"ok": True}


@app.get("/api/input-files/{key}/download")
def download_input_file(key: str):
    """Hand back the input file as-is, so it can be edited and re-uploaded.

    Without this the upload slot was write-only: you had to already own a
    correctly shaped workbook to use it, which is no help when the question is
    "what does the kraftpris file even look like?".
    """
    path, filename, _ = _resolve_input_file(key)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/input-files/{key}/sheet")
def get_input_file_sheet(key: str):
    """The first sheet of an input file as rows, for editing in the browser.

    too_large is a normal 200, not an error: the caller then points at the
    download route instead of showing a failure.
    """
    path, filename, is_override = _resolve_input_file(key)
    try:
        with pd.ExcelFile(path) as xl:
            sheet = xl.sheet_names[0]
            df = xl.parse(sheet)
    except Exception as e:
        raise HTTPException(500, f"Kunne ikke lese «{filename}»: {e}")

    n_rows, n_cols = int(df.shape[0]), int(df.shape[1])
    too_large = n_rows > _SHEET_EDIT_MAX_ROWS or n_cols > _SHEET_EDIT_MAX_COLS
    return {
        "filename":  filename,
        "sheet":     sheet,
        "source":    "override" if is_override else "standard",
        "n_rows":    n_rows,
        "n_cols":    n_cols,
        "too_large": too_large,
        "max_rows":  _SHEET_EDIT_MAX_ROWS,
        "max_cols":  _SHEET_EDIT_MAX_COLS,
        "columns":   [] if too_large else [str(c) for c in df.columns],
        "rows":      [] if too_large else _df_to_records(df),
    }


class SheetSaveRequest(BaseModel):
    columns: list[str]
    rows: list[dict]
    sheet: str | None = None


def _coerce_sheet_types(df: pd.DataFrame) -> pd.DataFrame:
    """Restore numeric dtypes lost on the round-trip through JSON text inputs.

    This matters because R joins on orgn: written as text - or as 824368082.0 -
    the join matches nothing and the run silently keeps the old prices. A column
    is converted only when *every* non-blank cell parses as a number, so real
    text columns (selskapsnavn) stay text. Norwegian decimal commas are
    accepted, since that is what Excel and the keyboard produce here.
    """
    for col in df.columns:
        raw   = df[col]
        text  = raw.astype(str).str.strip()
        blank = raw.isna() | text.eq("") | text.eq("None") | text.eq("nan")
        text  = text.str.replace(r"^(-?\d+),(\d+)$", r"\1.\2", regex=True)
        num   = pd.to_numeric(text.where(~blank), errors="coerce")
        if (num.isna() & ~blank).any():
            continue  # a real value that is not a number -> leave the column as text
        present = num.dropna()
        if not present.empty and (present % 1 == 0).all():
            df[col] = num.astype("Int64")   # ids and orgn stay integers
        else:
            df[col] = num
    return df


@app.post("/api/input-files/{key}/sheet")
def save_input_file_sheet(key: str, body: SheetSaveRequest):
    """Write edited rows back as the override workbook for this input file."""
    if key not in _INPUT_FILE_DEFS:
        raise HTTPException(404, f"Ukjent fil-nøkkel: {key}")
    if not body.columns:
        raise HTTPException(400, "Ingen kolonner å lagre.")
    if not body.rows:
        # An empty override is worse than no override: the run would read zero
        # rows and quietly drop every company instead of failing.
        raise HTTPException(400, "Kan ikke lagre en tom fil - slett overstyringen i stedet.")

    df = pd.DataFrame(body.rows).reindex(columns=body.columns)
    df = _coerce_sheet_types(df)

    d = _INPUT_FILE_DEFS[key]
    dest = ROOT / d["folder"] / d["override"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Write beside the target and move into place: a crash mid-write would
    # otherwise leave a truncated override that the next run reads as gospel.
    tmp = dest.with_name(dest.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(tmp, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=(body.sheet or "Ark1")[:31])
        tmp.replace(dest)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, f"Kunne ikke skrive «{d['override']}»: {e}")

    return {"ok": True, "filename": d["override"], "rows": len(df), "cols": len(df.columns)}


# ---------------------------------------------------------------------------
# /api/upload-grunnlagsdata
# ---------------------------------------------------------------------------

def _strip_navnerad(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the label row the download adds, if it is there.

    ``/api/grunnlagsdata/download`` writes the full variable names as row 1
    below the column headers, so the file can be read in Excel without a key
    alongside it. That row has to come off again before anything computes on
    the numbers: it makes every column dtype ``object`` and ``orgn`` a string,
    and the R join then matches nothing. The tell is a non-numeric ``orgn``.
    """
    if df.empty or "orgn" not in df.columns:
        return df
    if not pd.isna(pd.to_numeric(pd.Series([df["orgn"].iloc[0]]), errors="coerce").iloc[0]):
        return df
    df = df.iloc[1:].reset_index(drop=True)
    # The text row forced every column to object; put the numbers back, but only
    # where the whole column parses — comp holds company names, not numbers.
    for col in df.columns:
        num = pd.to_numeric(df[col], errors="coerce")
        if not (num.isna() & df[col].notna()).any():
            df[col] = num
    return df


@app.get("/api/grunnlagsdata/download")
def download_grunnlagsdata(run_name: str | None = Query(default=None)):
    """Grunnlagsdata as CSV, with an extra row carrying the full names.

    The column names are R abbreviations. Without the label row, anyone editing
    the file in Excel has to look up what ``ld_OPEXxS`` and ``rd_wv.ol`` mean
    somewhere else. The row is stripped on upload — see ``_strip_navnerad``.
    """
    grunn = _resolve_grunnlagsdata(run_name)
    if not grunn:
        raise HTTPException(404, "Ingen grunnlagsdata funnet. Klikk «Rediger grunnlagsdata» først.")
    df = pd.read_excel(grunn) if str(grunn).lower().endswith((".xlsx", ".xls")) else _read_grunn_csv(grunn)
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed:")]]

    navnerad = pd.DataFrame([{c: variabelnavn.navn(str(c)) for c in df.columns}])
    ut = pd.concat([navnerad, df.astype(object)], ignore_index=True)

    buf = io.StringIO()
    ut.to_csv(buf, index=False)
    today = __import__("datetime").date.today().isoformat()
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{today}_grunnlagsdata.csv"'},
    )


@app.get("/api/variabelnavn")
def get_variabelnavn():
    """Full names for the grunnlagsdata columns, and which ones are key variables."""
    return {
        "navn":      variabelnavn.VARIABELNAVN,
        "grupper":   variabelnavn.NOKKELVARIABLER,
        "gruppenavn": variabelnavn.GRUPPENAVN,
        "id_kolonner": list(variabelnavn.ID_KOLONNER),
    }


@app.post("/api/upload-grunnlagsdata")
async def upload_grunnlagsdata(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Kun CSV-filer støttes.")
    content = await file.read()

    # Decode, stripping any UTF-8 BOM that Excel / the browser download added.
    try:
        text = content.decode("utf-8-sig", errors="replace")
    except Exception as e:
        raise HTTPException(400, f"Kunne ikke lese filen: {e}")

    first_line = text.split("\n", 1)[0]
    if "orgn" not in first_line.lower() and "id" not in first_line.lower():
        raise HTTPException(400, "Filen ser ikke ut som grunnlagsdata (mangler 'orgn'/'id' kolonner).")

    # Sniff the delimiter. The app's own "↓ CSV" buttons and Excel (Norwegian
    # locale) export *semicolon*-separated, but R's read.csv() and every pandas
    # reader downstream assume *comma*. A semicolon file is parsed as a single
    # column → the R override step silently matches 0 rows and changes nothing.
    # Normalise to canonical comma-separated UTF-8 (no BOM, no index) so the file
    # round-trips correctly no matter what the user uploaded.
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep)
    except Exception as e:
        raise HTTPException(400, f"Kunne ikke tolke CSV (skilletegn '{sep}'): {e}")

    df = _strip_navnerad(df)

    # Fail loudly if the key columns didn't parse — prevents a silent no-op run.
    missing = [c for c in ("orgn", "y") if c not in df.columns]
    if missing:
        raise HTTPException(
            400,
            f"Fant ikke kolonnene {missing} etter innlesing "
            f"(tolket skilletegn '{sep}', kolonner: {list(df.columns)[:6]}…). "
            "Sjekk at filen er en grunnlagsdata-CSV.",
        )

    _UPLOADED_GRUNN.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_UPLOADED_GRUNN, index=False, encoding="utf-8")

    # Sanity-check the file rather than letting an impossible value run
    # silently. A hand-merged file typically carries summed områdepriser or
    # summed rammevilkårsvariabler, neither of which the model can detect on
    # its own — nettapskostnaden just comes out billions too high.
    ref = _reference_grunnlagsdata()
    funn = fusjon_grunnlagsdata.validate_grunnlagsdata(
        df, ref=ref, config_path=str(ROOT / "config.yaml")
    )
    delvis = [d for d in fusjon_grunnlagsdata.diff_summary(ref, df) if d["delvis"]] if ref is not None else []

    return _clean({
        "ok": True,
        "filename": file.filename,
        "rows": len(df),
        "validering": funn,
        "delvis_endret": delvis,
    })


@app.delete("/api/upload-grunnlagsdata")
def delete_grunnlagsdata():
    if _UPLOADED_GRUNN.exists():
        _UPLOADED_GRUNN.unlink()
    return {"ok": True}


@app.get("/api/upload-grunnlagsdata/status")
def grunnlagsdata_status():
    if _UPLOADED_GRUNN.exists():
        return {"active": True, "filename": _UPLOADED_GRUNN.name, "size": _UPLOADED_GRUNN.stat().st_size}
    return {"active": False}


# ---------------------------------------------------------------------------
# /api/fusjon-grunnlagsdata  — merge companies before the model runs
# ---------------------------------------------------------------------------

def _read_grunn_csv(path: Path | str) -> pd.DataFrame:
    """Read a grunnlagsdata CSV, sniffing the delimiter as the upload path does."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    sep = ";" if first.count(";") > first.count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep)


def _reference_grunnlagsdata() -> pd.DataFrame | None:
    """A grunnlagsdata frame known to come straight from R, for validation.

    The pristine copy written by /api/generate-grunnlagsdata is preferred. A
    run's own grunnlagsdata.csv is the fallback, but it is written *after* the
    override step, so if that run merged companies it is no longer a clean
    baseline — good enough for a range check, not authoritative.
    """
    if _GENERATED_GRUNN.exists():
        try:
            return _read_grunn_csv(_GENERATED_GRUNN)
        except Exception as exc:
            logger.warning("Kunne ikke lese %s: %s", _GENERATED_GRUNN, exc)
    paths = _latest_run_paths()
    if paths and paths[0] and str(paths[0]).lower().endswith(".csv"):
        try:
            return _read_grunn_csv(paths[0])
        except Exception as exc:
            logger.warning("Kunne ikke lese %s: %s", paths[0], exc)
    return None


def _fusjon_source() -> tuple[pd.DataFrame, str]:
    """The frame a merge is applied to, plus a label for the UI.

    The active upload comes first so a merge can be layered on top of hand
    edits (and so two mergers can be applied one after the other).
    """
    if _UPLOADED_GRUNN.exists():
        return _read_grunn_csv(_UPLOADED_GRUNN), "aktiv grunnlagsdata"
    if _GENERATED_GRUNN.exists():
        return _read_grunn_csv(_GENERATED_GRUNN), "generert grunnlagsdata"
    paths = _latest_run_paths()
    if paths and paths[0] and str(paths[0]).lower().endswith(".csv"):
        return _read_grunn_csv(paths[0]), f"siste kjøring ({Path(paths[0]).name})"
    raise HTTPException(
        404,
        "Ingen grunnlagsdata å fusjonere. Klikk «Rediger grunnlagsdata» først, "
        "eller last opp en fil.",
    )


@app.get("/api/fusjon-grunnlagsdata")
def fusjon_grunnlagsdata_options():
    """Companies available to merge, from whichever grunnlagsdata is active."""
    df, kilde = _fusjon_source()
    if "orgn" not in df.columns:
        raise HTTPException(400, "Grunnlagsdata mangler 'orgn'.")
    work = df.copy()
    work["orgn"] = pd.to_numeric(work["orgn"], errors="coerce")
    if fusjon_grunnlagsdata.SLETT_COL in work.columns:
        keep = pd.to_numeric(work[fusjon_grunnlagsdata.SLETT_COL], errors="coerce").fillna(0) <= 0
        work = work[keep]
    work = work.dropna(subset=["orgn"])

    selskaper = []
    for orgn, grp in work.groupby("orgn"):
        navn = str(grp["comp"].iloc[0]) if "comp" in grp.columns else str(int(orgn))
        selskaper.append({"orgn": int(orgn), "comp": navn})
    selskaper.sort(key=lambda s: s["comp"])
    aar = sorted(int(y) for y in pd.to_numeric(work.get("y"), errors="coerce").dropna().unique()) \
        if "y" in work.columns else []
    return {"kilde": kilde, "selskaper": selskaper, "aar": aar}


@app.post("/api/fusjon-grunnlagsdata")
def fusjon_grunnlagsdata_apply(body: FusjonGrunnlagsdataRequest):
    """Merge companies and stage the result as the active grunnlagsdata.

    Aggregation follows NVE's own merge routine (``functions_nve.R``): costs,
    capital, volumes and task variables are summed, ``ldz_*`` are weighted by
    map grid cells, and the områdepriser are volume-weighted. Absorbed
    companies are flagged ``_slett`` so ``IRiR.R`` removes them from the
    reference set — deleting their rows would not, since the override step only
    changes values in rows it finds.
    """
    if not body.grupper:
        raise HTTPException(400, "Ingen fusjoner oppgitt.")

    df, kilde = _fusjon_source()
    grupper = [
        fusjon_grunnlagsdata.FusjonGruppe(mottaker=g.mottaker, maal=list(g.maal))
        for g in body.grupper
    ]
    try:
        merged, rap = fusjon_grunnlagsdata.merge_companies(df, grupper)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    funn = fusjon_grunnlagsdata.validate_grunnlagsdata(
        merged, ref=_reference_grunnlagsdata(), config_path=str(ROOT / "config.yaml")
    )

    _UPLOADED_GRUNN.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(_UPLOADED_GRUNN, index=False, encoding="utf-8")

    return _clean({
        "ok": True,
        "kilde": kilde,
        "rader": len(merged),
        "aar": rap.aar,
        "grupper": rap.grupper,
        "advarsler": rap.advarsler,
        "behandling": {k: len(v) for k, v in rap.behandling.items()},
        "behandling_kolonner": rap.behandling,
        "selskaper_fjernet": sorted(
            {n for g in rap.grupper for n in g["maal_navn"]}
        ),
        "validering": funn,
    })


# ---------------------------------------------------------------------------
# /api/runs
# ---------------------------------------------------------------------------

@app.get("/api/runs")
def get_runs():
    results_dir = ROOT / "Results"
    if not results_dir.is_dir():
        return {"runs": []}
    runs = []
    def _sort_key(p: Path):
        is_dated = bool(re.match(r'^Run_\d', p.name))
        return (0 if is_dated else 1, p.name if is_dated else p.name.lower())
    for d in sorted([d for d in results_dir.iterdir() if d.is_dir() and not d.name.startswith('.')], key=_sort_key, reverse=False):
        files = [{"name": f.name, "size": f.stat().st_size} for f in sorted(d.iterdir()) if f.is_file()]
        complete = bool(
            next((f for pat in ("*grunnlagsdata*.csv", "*grunnlagsdata*.xlsx", "*grunnlagsdata*.xls") for f in d.glob(pat)), None)
            and next(d.glob("Data_Resultater_LD*"), None)
            and next(d.glob("Data_Resultater_RD*"), None)
        )
        runs.append({"name": d.name, "files": files, "complete": complete})
    # Dated runs are already sorted asc; reverse them so newest first, keep named runs at bottom
    dated = [r for r in runs if re.match(r'^Run_\d', r["name"])]
    named = [r for r in runs if not re.match(r'^Run_\d', r["name"])]
    return {"runs": list(reversed(dated)) + named}


# ---------------------------------------------------------------------------
# /api/run-csv  — read / write editable CSVs inside a run folder
# ---------------------------------------------------------------------------

class CsvSaveRequest(BaseModel):
    rows: list[dict]


def _run_dir_from_name(run_name: str | None) -> Path | None:
    results_dir = ROOT / "Results"
    if run_name:
        # Validate name (same rules as _latest_run_paths)
        if re.search(r'[\\/]|\.\.', run_name) or not run_name.strip():
            return None
        d = results_dir / run_name
        if not str(d.resolve()).startswith(str(results_dir.resolve())):
            return None
        return d if d.is_dir() else None
    # No name: fall back to latest complete run
    paths = _latest_run_paths(None)
    return paths[0].parent if paths else None


def _safe_csv_filename(filename: str) -> bool:
    """Allow only plain .csv filenames with no path components."""
    return (
        filename.endswith(".csv")
        and not re.search(r"[/\\]|\.\.", filename)
        and Path(filename).name == filename
    )


@app.get("/api/run-csv/files")
def list_run_csv_files(run_name: str | None = Query(None)):
    """Return all .csv files present in the run folder."""
    # Special sentinel: expose the uploaded/generated grunnlagsdata
    if run_name == "__uploaded__":
        if _UPLOADED_GRUNN.exists():
            return {"files": [{"filename": _UPLOADED_GRUNN.name, "size": _UPLOADED_GRUNN.stat().st_size}], "run_dir": "__uploaded__"}
        return {"files": [], "run_dir": "__uploaded__"}
    run_dir = _run_dir_from_name(run_name)
    if run_dir is None:
        return {"files": [], "run_dir": ""}
    files = [
        {"filename": f.name, "size": f.stat().st_size}
        for f in sorted(run_dir.glob("*.csv"))
    ]
    return {"files": files, "run_dir": run_dir.name}


@app.get("/api/run-csv")
def get_run_csv(filename: str = Query(...), run_name: str | None = Query(None)):
    if not _safe_csv_filename(filename):
        raise HTTPException(400, "Invalid filename")
    if run_name == "__uploaded__":
        csv_path = _UPLOADED_GRUNN
        if not csv_path.exists():
            raise HTTPException(404, "Ingen generert grunnlagsdata funnet")
        df = pd.read_csv(csv_path)
        rows = [{k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in row.items()} for row in df.to_dict(orient="records")]
        return {"columns": list(df.columns), "rows": rows, "run_dir": "__uploaded__"}
    run_dir = _run_dir_from_name(run_name)
    if run_dir is None:
        raise HTTPException(404, "Run not found")
    csv_path = run_dir / filename
    if not csv_path.exists():
        raise HTTPException(404, f"{filename} not found in this run")
    df = pd.read_csv(csv_path, index_col=0)
    rows = [{k: (None if (isinstance(v, float) and math.isnan(v)) else v)
             for k, v in row.items()}
            for row in df.to_dict(orient="records")]
    return {"columns": list(df.columns), "rows": rows, "run_dir": run_dir.name}


@app.put("/api/run-csv")
def put_run_csv(filename: str = Query(...), run_name: str = Query(...), body: CsvSaveRequest = ...):
    if not _safe_csv_filename(filename):
        raise HTTPException(400, "Invalid filename")
    if run_name == "__uploaded__":
        df = pd.DataFrame(body.rows)
        # R writes row names, so the file reads back with an "Unnamed: 0"
        # column. It is not written out again: every save would otherwise add
        # another one ("Unnamed: 0.1", "Unnamed: 0.2", …) until the file is
        # full of them.
        df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed:")]]
        df.to_csv(_UPLOADED_GRUNN, index=False)
        return {"ok": True, "rows": len(df), "path": str(_UPLOADED_GRUNN)}
    run_dir = _run_dir_from_name(run_name)
    if run_dir is None:
        raise HTTPException(404, "Run not found")
    csv_path = run_dir / filename
    if not csv_path.exists():
        raise HTTPException(404, f"{filename} not found in this run")
    df = pd.DataFrame(body.rows)
    df.to_csv(csv_path)
    return {"ok": True, "rows": len(df), "path": str(csv_path)}


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
# /api/kraftpris-soner  — områdepris per prissone
# ---------------------------------------------------------------------------
#
# The kraftpris file holds one price per company (``pnl.rc``, kr/kWh), not one
# per zone, so "set NO3 to 450" cannot be written directly. Zone membership is
# derived once from the default file — each company gets the zone whose area
# price is nearest its own — and then stored in ``kraftpris_soner_map.csv``.
#
# The map has to be stored rather than re-derived: writing changes both the
# prices in the file and ``omradepriser`` in config.yaml, so a later derivation
# would look for 381.1 in a file that now holds 450 and find nothing. The map is
# rebuilt only when the default file is replaced (a new year).

_SONE_TOLERANSE_KWH = 0.0005   # 0.5 NOK/MWh — enough to absorb rounding in the file
_SONEKART_CSV = ROOT / "Data" / "BaseData" / "kraftpris_soner_map.csv"


def _omradepriser_fra_config() -> dict[str, float]:
    """``forutsetninger.omradepriser`` from config.yaml, in NOK/MWh."""
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        raise HTTPException(404, "config.yaml ble ikke funnet.")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    priser = ((raw.get("forutsetninger") or {}).get("omradepriser")) or {}
    out = {str(k): float(v) for k, v in priser.items() if v is not None}
    if not out:
        raise HTTPException(404, "config.yaml mangler forutsetninger.omradepriser.")
    return out


def _les_kraftprisfil(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_excel(path)
    except Exception as e:
        raise HTTPException(500, f"Kunne ikke lese «{path.name}»: {e}")
    mangler = [c for c in ("orgn", "pnl.rc") if c not in df.columns]
    if mangler:
        raise HTTPException(
            500,
            f"«{path.name}» mangler kolonnene {mangler} (fant {list(df.columns)[:6]}).",
        )
    return df


def _sonekart() -> tuple[pd.DataFrame, dict[str, float]]:
    """(orgn · pnl.rc · sone · basispris, base prices per zone in NOK/MWh).

    ``basispris`` is the price the zone had when the map was built, and is what
    still identifies the zone after the user has changed the price.
    """
    d = _INPUT_FILE_DEFS["kraftpris"]
    standard = ROOT / d["folder"] / d["default"]
    if not standard.exists():
        raise HTTPException(404, f"Finner ikke standardfilen «{d['default']}».")

    if _SONEKART_CSV.exists():
        kart = pd.read_csv(_SONEKART_CSV)
        if set(kart.columns) >= {"orgn", "pnl.rc", "sone", "basispris", "kilde"} \
                and (kart["kilde"] == d["default"]).all():
            basis = (kart.dropna(subset=["sone"])
                         .groupby("sone")["basispris"].first().to_dict())
            return kart, {str(k): float(v) for k, v in basis.items()}

    priser = _omradepriser_fra_config()
    df = _les_kraftprisfil(standard).copy()

    def _sone(verdi) -> str | None:
        v = pd.to_numeric(pd.Series([verdi]), errors="coerce").iloc[0]
        if pd.isna(v):
            return None
        sone, avvik = min(
            ((s, abs(float(v) - p / 1000.0)) for s, p in priser.items()),
            key=lambda t: t[1],
        )
        return sone if avvik <= _SONE_TOLERANSE_KWH else None

    df["sone"] = [_sone(v) for v in df["pnl.rc"]]
    df["basispris"] = [priser.get(s) if isinstance(s, str) else None for s in df["sone"]]
    df["kilde"] = d["default"]
    try:
        _SONEKART_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(_SONEKART_CSV, index=False)
    except OSError as exc:  # read-only mount — the map is then derived each time
        logger.warning("Kunne ikke lagre sonekartet %s: %s", _SONEKART_CSV, exc)
    return df, priser


def _soner_naa() -> tuple[pd.DataFrame, list[dict], str, bool]:
    """(zone map, one row per zone with the price in force, filename, overridden)."""
    kart, standardpriser = _sonekart()
    aktiv_path, aktiv_navn, er_overstyrt = _resolve_input_file("kraftpris")
    aktiv = _les_kraftprisfil(aktiv_path).set_index("orgn")["pnl.rc"]

    soner = []
    for sone, basispris in sorted(standardpriser.items()):
        medlemmer = kart.loc[kart["sone"] == sone, "orgn"]
        naa = pd.to_numeric(aktiv.reindex(medlemmer).dropna(), errors="coerce").dropna()
        # One number per zone assumes every member shares a price. After a
        # hand-edited upload they need not, so say so rather than show an
        # average no company actually has.
        unike = sorted({round(float(v) * 1000.0, 4) for v in naa})
        soner.append({
            "sone":          sone,
            "pris":          unike[0] if len(unike) == 1 else basispris,
            "basispris":     basispris,
            "n_selskaper":   int(len(medlemmer)),
            "blandet":       len(unike) > 1,
        })
    return kart, soner, aktiv_navn, er_overstyrt


@app.get("/api/kraftpris-soner")
def get_kraftpris_soner():
    """Area price per price zone, with company counts and the price in force."""
    kart, soner, aktiv_navn, er_overstyrt = _soner_naa()
    return {
        "soner":       soner,
        "filnavn":     aktiv_navn,
        "overstyrt":   er_overstyrt,
        "uten_sone":   int(kart["sone"].isna().sum()),
        "enhet":       "NOK/MWh",
    }


@app.put("/api/kraftpris-soner")
def put_kraftpris_soner(body: SonepriserRequest):
    """Set the area price for one or more zones.

    Writes both places the price lives: ``kraftpris_override.xlsx``, which the
    model actually computes on, and ``forutsetninger.omradepriser`` in
    config.yaml, which the grunnlagsdata validation and the merge weighting
    read. Without the second step, a new price outside the old band would be
    flagged as impossible.
    """
    kart, soner, _, _ = _soner_naa()
    gjeldende = {s["sone"]: float(s["pris"]) for s in soner}
    ukjente = [s for s in body.priser if s not in gjeldende]
    if ukjente:
        raise HTTPException(400, f"Ukjente prissoner: {ukjente}. Kjente: {sorted(gjeldende)}.")
    for sone, pris in body.priser.items():
        if not math.isfinite(pris) or pris <= 0:
            raise HTTPException(400, f"Prisen for {sone} må være et positivt tall (fikk {pris}).")

    # Start from the prices in force, not the base prices: a change to NO1
    # would otherwise reset NO3 to where it started.
    nye = {**gjeldende, **{s: float(p) for s, p in body.priser.items()}}

    # Companies without a zone keep their price from the active file.
    aktiv_path, _, _ = _resolve_input_file("kraftpris")
    aktiv = _les_kraftprisfil(aktiv_path).set_index("orgn")["pnl.rc"]

    ut = kart[["orgn", "pnl.rc", "sone"]].copy()
    ut["pnl.rc"] = [
        nye[s] / 1000.0 if isinstance(s, str) and s in nye
        else float(aktiv.get(o, v))
        for o, v, s in zip(ut["orgn"], ut["pnl.rc"], ut["sone"])
    ]
    ut = ut.drop(columns=["sone"])

    d = _INPUT_FILE_DEFS["kraftpris"]
    dest = ROOT / d["folder"] / d["override"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(tmp, engine="openpyxl") as writer:
            ut.to_excel(writer, index=False, sheet_name="Ark1")
        tmp.replace(dest)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, f"Kunne ikke skrive «{d['override']}»: {e}")

    # Only the zones the user actually changed are written to config.yaml.
    # Writing all of them would replace the rounded values there with the
    # file's exact ones, producing a diff on zones nobody touched.
    _skriv_omradepriser({s: float(p) for s, p in body.priser.items()})

    endret = int(kart["sone"].isin(body.priser.keys()).sum())
    return {"ok": True, "filnavn": d["override"], "selskaper_endret": endret, "priser": nye}


@app.delete("/api/kraftpris-soner")
def delete_kraftpris_soner():
    """Remove the price override and put the area prices in config.yaml back.

    Both have to go back together. Deleting only the override file would leave
    ``omradepriser`` on the changed price, and the band the grunnlagsdata
    validation measures against would no longer match the prices the run uses.
    """
    _, basispriser = _sonekart()
    d = _INPUT_FILE_DEFS["kraftpris"]
    override = ROOT / d["folder"] / d["override"]
    fantes = override.exists()
    if fantes:
        override.unlink()
    _skriv_omradepriser(basispriser)
    return {"ok": True, "fjernet": fantes, "priser": basispriser}


def _skriv_omradepriser(priser: dict[str, float]) -> None:
    """Update the values under ``omradepriser:`` in config.yaml, line by line.

    Line editing rather than yaml.safe_dump: a full round-trip would rewrite the
    whole file, including keys this function has no business touching.
    """
    cfg_path = ROOT / "config.yaml"
    linjer = cfg_path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, l in enumerate(linjer) if l.strip() == "omradepriser:"), None)
    if start is None:
        raise HTTPException(500, "Fant ikke «omradepriser:» i config.yaml.")
    innrykk = len(linjer[start]) - len(linjer[start].lstrip())
    i = start + 1
    while i < len(linjer):
        l = linjer[i]
        if not l.strip():
            i += 1
            continue
        if (len(l) - len(l.lstrip())) <= innrykk:
            break
        m = re.match(r"^(\s*)([A-Za-z0-9_]+)\s*:\s*.*$", l.rstrip())
        if m and m.group(2) in priser:
            linjer[i] = f"{m.group(1)}{m.group(2)}: {priser[m.group(2)]:g}\n"
        i += 1
    cfg_path.write_text("".join(linjer), encoding="utf-8")


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

# Set to True to stream all R output to the browser (useful for debugging crashes).
# When False, only [STEG] progress markers and errors are forwarded.
_PIPELINE_VERBOSE = False

_SUPPRESS = (
    "── Attaching", "✔ ", "✖ ", "── Conflicts", "ℹ ", "Registered S3",
    "The following object", "The following packages", "tidyverse",
    "Loading required package:", "character(0)",
)

async def _pipeline_generator() -> AsyncGenerator[str, None]:
    # Pre-flight: check IRiR.R for conflict markers and report first lines
    irr_path = ROOT / "IRiR.R"
    try:
        first_lines = irr_path.read_text(encoding="utf-8", errors="replace").splitlines()[:5]
        for ln in first_lines:
            yield f"data: {json.dumps({'line': f'[file] {ln}'})}\n\n"
        conflict_lines = [l for l in first_lines if l.startswith("<<<<<<<") or l.startswith(">>>>>>>")]
        if conflict_lines:
            yield f"data: {json.dumps({'error': 'IRiR.R has unresolved conflict markers — push the resolved file first'})}\n\n"
            return
    except Exception as e:
        yield f"data: {json.dumps({'line': f'[preflight error] {e}'})}\n\n"

    rscript = shutil.which("Rscript")
    if not rscript:
        # Fallback: scan common Windows install paths (works even when conda
        # overwrites PATH and hides the user-added R\bin directory)
        candidates = sorted(
            glob.glob(r"C:\Program Files\R\R-*\bin\Rscript.exe"),
            reverse=True,  # newest version first
        )
        if candidates:
            rscript = candidates[0]
    if not rscript:
        yield f"data: {json.dumps({'error': 'Finner ikke Rscript på PATH'})}\n\n"
        return

    yield f"data: {json.dumps({'line': f'[preflight] Rscript: {rscript}'})}\n\n"

    # On Linux wrap with stdbuf so R flushes stdout line-by-line through the pipe.
    # Without this, R buffers cat() output in a 4–64KB kernel pipe buffer and
    # all SSE events arrive at once at the end (visible on Railway).
    import platform
    if platform.system() != "Windows" and shutil.which("stdbuf"):
        cmd = ["stdbuf", "-oL", rscript, "--quiet", "IRiR.R"]
    else:
        cmd = [rscript, "--quiet", "IRiR.R"]

    # Use subprocess.Popen + thread queue — asyncio.create_subprocess_exec
    # requires ProactorEventLoop on Windows which uvicorn doesn't use.
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _read_proc() -> int:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
            )
            for raw in proc.stdout:  # type: ignore[union-attr]
                line = raw.decode("utf-8", errors="replace").rstrip()
                loop.call_soon_threadsafe(queue.put_nowait, line)
            proc.wait()
            return proc.returncode if proc.returncode is not None else 1
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, f"[ERROR] {exc}")
            return 1
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    fut = loop.run_in_executor(None, _read_proc)

    error_buffer: list[str] = []

    while True:
        line = await queue.get()
        if line is None:
            break
        if not line:
            continue
        is_steg = line.startswith("[STEG]")
        is_debug = line.startswith("[file]") or line.startswith("[preflight") or line.startswith("[diag") or line.startswith("[msg") or line.startswith("[install") or line.startswith("[override")
        is_suppressed = is_debug or any(line.startswith(p) or p in line for p in _SUPPRESS)
        if _PIPELINE_VERBOSE:
            if not is_suppressed:
                yield f"data: {json.dumps({'line': line})}\n\n"
        else:
            if is_steg:
                yield f"data: {json.dumps({'line': line})}\n\n"
            elif not is_suppressed:
                error_buffer.append(line)

    returncode = await fut

    # If R failed and we were in quiet mode, flush the buffered output so the
    # user can see what went wrong (same behaviour as _PIPELINE_VERBOSE = True).
    if returncode != 0 and not _PIPELINE_VERBOSE:
        for buffered in error_buffer:
            yield f"data: {json.dumps({'line': buffered})}\n\n"
    # Consume the uploaded grunnlagsdata — it was applied by R (or skipped on failure).
    # Either way, clear it so future runs are not silently affected.
    if _UPLOADED_GRUNN.exists():
        _UPLOADED_GRUNN.unlink()
    yield f"data: {json.dumps({'done': True, 'code': returncode})}\n\n"


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
        raise HTTPException(404, "Ingen resultater funnet. Kjør Dagens RME modell først.")
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

        grunn_csv = _resolve_grunnlagsdata(body.run_name)

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
            task_elas_override=body.task_elas_override,
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


# The Kostnader tab is gone: the central variables are now edited straight in
# the RME tab (/api/run-csv against grunnlagsdata), and the RME reporting table
# never got further than being displayed. `kostnader.py` is still a standalone
# library with its own CLI for anyone who wants the whole table.


# ---------------------------------------------------------------------------
# /api/forutsetninger  — default assumptions (from kraftpris_soner.csv)
# ---------------------------------------------------------------------------

@app.get("/api/forutsetninger")
def get_forutsetninger():
    from prognose import load_forutsetninger_from_csv, DEFAULT_FORUTSETNINGER  # noqa: PLC0415
    data = load_forutsetninger_from_csv() or DEFAULT_FORUTSETNINGER
    # Serialize int year keys → strings for JSON
    return {k: {str(yr): v for yr, v in series.items()} for k, series in data.items()}


# ---------------------------------------------------------------------------
# /api/task-elasticities  — pooled industry-wide Δtask/MNOK estimates
# ---------------------------------------------------------------------------

@app.get("/api/task-elasticities")
def get_task_elasticities(run_name: str | None = Query(default=None)):
    grunn_csv = _resolve_grunnlagsdata(run_name)
    if not grunn_csv:
        raise HTTPException(404, "Ingen resultater funnet.")
    try:
        from prognose import estimate_task_elasticities  # noqa: PLC0415
        return estimate_task_elasticities(grunn_csv)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/task-elasticities/scatter")
def get_task_elasticities_scatter(run_name: str | None = Query(default=None)):
    grunn_csv = _resolve_grunnlagsdata(run_name)
    if not grunn_csv:
        raise HTTPException(404, "Ingen resultater funnet.")
    try:
        from prognose import get_task_elasticity_observations  # noqa: PLC0415
        return get_task_elasticity_observations(grunn_csv)
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
# /api/download-run  — download a run directory as a zip
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# /api/analyse  — KPI-er og figurer per selskap og år (inntektsrammeanalysen)
# ---------------------------------------------------------------------------

@app.get("/api/analyse")
def get_analyse(
    orgn: int = Query(...),
    aar: int = Query(...),
    run_name: str | None = Query(default=None),
    recalibrate: bool = Query(default=True),
    bfv_rebase: str = Query(default="both"),
):
    """Datagrunnlag for analysepanelet: inntektsramme, avkastning på nettkapital,
    effektivitet per trinn og frontselskap per nettnivå."""
    from analyse import build_analyse  # noqa: PLC0415

    if bfv_rebase not in ("none", "bfv", "both"):
        raise HTTPException(400, "bfv_rebase må være 'none', 'bfv' eller 'both'.")
    try:
        return _clean(build_analyse(
            orgn=orgn, year=aar, run_name=run_name,
            recalibrate=recalibrate, bfv_rebase=bfv_rebase,
        ))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/analyse/tidsserie")
def get_analyse_tidsserie(
    orgn: int = Query(...),
    run_name: str | None = Query(default=None),
    recalibrate: bool = Query(default=True),
    bfv_rebase: str = Query(default="both"),
    aar_fra: int | None = Query(default=None),
    aar_til: int | None = Query(default=None),
):
    """Tidsserieanalyse for ett selskap: effektivitetsutvikling, nøkkeltall med
    CAGR, frontselskap over tid og kostnadsutvikling."""
    from analyse import build_tidsserie  # noqa: PLC0415

    if bfv_rebase not in ("none", "bfv", "both"):
        raise HTTPException(400, "bfv_rebase må være 'none', 'bfv' eller 'both'.")
    try:
        return _clean(build_tidsserie(
            orgn=orgn, run_name=run_name, recalibrate=recalibrate,
            bfv_rebase=bfv_rebase, aar_fra=aar_fra, aar_til=aar_til,
        ))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/analyse/fusjon")
def get_analyse_fusjon(
    orgn_a: int = Query(...),
    orgn_b: int = Query(...),
    fusjonsaar: int = Query(...),
    synergier: str = Query(default="15,33"),
    innfasing_aar: int = Query(default=3),
    en_gangs_kostnad: float = Query(default=0.0),
    synergi_paa_utredning: bool = Query(default=False),
    ny_enhet_i_front: bool = Query(default=True),
    noekkeltall_aar: int | None = Query(default=None),
    run_name: str | None = Query(default=None),
    recalibrate: bool = Query(default=True),
    bfv_rebase: str = Query(default="both"),
):
    """Fusjonsanalyse: effektivitet, inntektsramme, avkastning og frontselskap for
    to selskap slått sammen, under ulike synergiforutsetninger."""
    from fusjon import build_fusjon  # noqa: PLC0415

    if bfv_rebase not in ("none", "bfv", "both"):
        raise HTTPException(400, "bfv_rebase må være 'none', 'bfv' eller 'both'.")
    try:
        syn = tuple(float(x) for x in str(synergier).split(",") if str(x).strip())
    except ValueError:
        raise HTTPException(400, "synergier må være tall separert med komma, f.eks. '15,33'.")
    if not syn:
        raise HTTPException(400, "Oppgi minst ett synerginivå.")
    if len(syn) > 4:
        raise HTTPException(400, "Maks fire synerginivåer.")
    if innfasing_aar < 1:
        raise HTTPException(400, "innfasing_aar må være minst 1.")

    try:
        return _clean(build_fusjon(
            orgn_a=orgn_a, orgn_b=orgn_b, fusjonsaar=fusjonsaar, synergier=syn,
            innfasing_aar=innfasing_aar, en_gangs_kostnad=en_gangs_kostnad,
            synergi_paa_utredning=synergi_paa_utredning,
            ny_enhet_i_front=ny_enhet_i_front, noekkeltall_aar=noekkeltall_aar,
            run_name=run_name, recalibrate=recalibrate, bfv_rebase=bfv_rebase,
        ))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/download-run")
def download_run(run_name: str | None = Query(default=None)):
    """Stream the latest (or named) Results/Run_* directory as a zip file."""
    run_dir = _run_dir_from_name(run_name)
    if run_dir is None:
        raise HTTPException(404, "Ingen kjøring funnet.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(run_dir.rglob("*")):
            if file.is_file():
                zf.write(file, arcname=Path(run_dir.name) / file.relative_to(run_dir))
    buf.seek(0)

    zip_name = f"{run_dir.name}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


# ---------------------------------------------------------------------------
# /api/generate-grunnlagsdata  — run data-load only, return CSV for editing
# ---------------------------------------------------------------------------

@app.get("/api/generate-grunnlagsdata")
async def generate_grunnlagsdata():
    """Run generate_grunnlagsdata.R (data loading only, no DEA) and save the
    result as the active grunnlagsdata override so it appears in the UI slot."""
    rscript = shutil.which("Rscript")
    if not rscript:
        candidates = sorted(glob.glob(r"C:\Program Files\R\R-*\bin\Rscript.exe"), reverse=True)
        if candidates:
            rscript = candidates[0]
    if not rscript:
        raise HTTPException(500, "Finner ikke Rscript på PATH")

    import platform, tempfile
    script = str(ROOT / "generate_grunnlagsdata.R")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if platform.system() != "Windows" and shutil.which("stdbuf"):
            cmd = ["stdbuf", "-oL", rscript, "--quiet", script, tmp_path]
        else:
            cmd = [rscript, "--quiet", script, tmp_path]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(ROOT),
            ),
        )

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            raise HTTPException(500, f"R feilet: {err[:2000]}")

        # Place as the active grunnlagsdata override (same slot as a user upload)
        import shutil as _shutil
        _UPLOADED_GRUNN.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(tmp_path, str(_UPLOADED_GRUNN))
        # Keep a second, pristine copy. A run consumes the slot above, so
        # without this there is no clean baseline left to validate a later
        # hand edit against, or to start a merge from.
        _shutil.copy2(tmp_path, str(_GENERATED_GRUNN))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    size = _UPLOADED_GRUNN.stat().st_size
    today = __import__("datetime").date.today().isoformat()
    return {"ok": True, "filename": f"{today}_grunnlagsdata.csv", "size": size}


# ---------------------------------------------------------------------------
# Static files — must be last
# ---------------------------------------------------------------------------

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(ROOT / "figures" / "favicon.ico")

static_dir = ROOT / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
