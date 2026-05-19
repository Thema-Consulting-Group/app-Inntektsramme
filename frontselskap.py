"""
Frontselskapsanalyse — DEA scenario analysis for local distribution (LD).

Supports re-running stage-1 CRS input-oriented DEA with a modified reference
set, e.g. to simulate Rakkestad Energi's exit after its merger with Elvia.

Background
----------
RME uses a two-stage DEA to set efficiency benchmarks:
  Stage 1: Input-oriented CRS DEA (costs vs. outputs).
           Companies whose lambdas are positive for others are "frontselskaper".
  Stage 2: Regression-based geo-correction (frost, coast, forest, leaf).
           Adjusts scores upward for companies in challenging terrain.

This module replicates Stage 1 via LP (scipy HiGHS) and approximates Stage 2
by adding the original (eff_s2 - eff_s1) offset from the R results.

DEA inputs for LD
-----------------
  Input  (X): fha_ld_TOTXDEA  — averaged total costs used in DEA
  Outputs (Y): fha_ld_sub, fha_ld_hv, fha_ld_ss  — averaged subscribers,
               HV lines (km), substations
  Evaluated  : X.cb.ld, ld_sub, ld_hv, ld_ss  — cost-base-year values
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import linprog


# ---------------------------------------------------------------------------
# Core LP-based DEA
# ---------------------------------------------------------------------------

def _dea_crs_input(
    X_ref: np.ndarray,
    Y_ref: np.ndarray,
    X_eval: np.ndarray,
    Y_eval: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Input-oriented CRS DEA via linear programming (HiGHS solver).

    For each evaluated unit i, solve:
        min  theta_i
        s.t. Y_ref' * lambda >= y_i        (output coverage)
             X_ref' * lambda <= theta_i * x_i  (proportional input reduction)
             lambda >= 0

    Parameters
    ----------
    X_ref  : (n_ref,) or (n_ref, n_x)  – reference inputs (averaged data)
    Y_ref  : (n_ref, n_y)               – reference outputs (averaged data)
    X_eval : (n_eval,) or (n_eval, n_x) – evaluated inputs (cost-base-year)
    Y_eval : (n_eval, n_y)              – evaluated outputs (cost-base-year)

    Returns
    -------
    eff     : (n_eval,)       – efficiency scores (1.0 = on frontier)
    lambdas : (n_eval, n_ref) – peer weights (DEA lambdas)
    """
    X_ref  = np.asarray(X_ref,  dtype=float)
    Y_ref  = np.asarray(Y_ref,  dtype=float)
    X_eval = np.asarray(X_eval, dtype=float)
    Y_eval = np.asarray(Y_eval, dtype=float)

    if X_ref.ndim  == 1:
        X_ref  = X_ref.reshape(-1, 1)
    if X_eval.ndim == 1:
        X_eval = X_eval.reshape(-1, 1)

    n_ref, n_x = X_ref.shape
    n_y        = Y_ref.shape[1]
    n_eval     = X_eval.shape[0]

    eff     = np.full(n_eval, np.nan)
    lambdas = np.zeros((n_eval, n_ref))

    # Objective: minimize theta (index 0); lambdas at indices 1..n_ref
    c = np.zeros(1 + n_ref)
    c[0] = 1.0

    # Output coverage block: -Y_ref.T @ lambda <= -y_i
    A_out  = np.hstack([np.zeros((n_y, 1)), -Y_ref.T])   # (n_y, 1+n_ref)
    bounds = [(0.0, None)] * (1 + n_ref)

    for i in range(n_eval):
        x_i = X_eval[i]   # (n_x,)
        y_i = Y_eval[i]   # (n_y,)

        b_out = -y_i

        # Input contraction block: X_ref.T @ lambda - theta * x_i <= 0
        A_inp = np.hstack([-x_i.reshape(-1, 1), X_ref.T])  # (n_x, 1+n_ref)

        A_ub = np.vstack([A_out, A_inp])
        b_ub = np.concatenate([b_out, np.zeros(n_x)])

        res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if res.status == 0:
            eff[i]     = res.x[0]
            lambdas[i] = res.x[1:]

    return eff, lambdas


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ld_dea_inputs(results_dir: str | Path) -> pd.DataFrame:
    """
    Load ld_InputDEA.csv from Results/.

    Columns returned: id, X_avg, fha_sub, fha_hv, fha_ss, X_cb, ld_sub, ld_hv, ld_ss
    """
    path = Path(results_dir) / "ld_InputDEA.csv"
    df = pd.read_csv(path, index_col=0)
    df.columns = [
        "id", "X_avg", "fha_sub", "fha_hv", "fha_ss",
        "X_cb", "ld_sub", "ld_hv", "ld_ss",
    ]
    df["id"] = df["id"].astype(int)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_ld_scenario(
    dea_df: pd.DataFrame,
    res_ld: pd.DataFrame,
    exclude_ids: list[int] | None = None,
) -> pd.DataFrame:
    """
    Run baseline and scenario stage-1 DEA for LD.

    Excluded companies are removed from BOTH the reference set and the
    evaluation set — representing a true merger/exit (e.g. Rakkestad → Elvia).
    They do not appear in the scenario results.

    Stage 2 geo-correction is approximated by adding the original
    (eff_s2 − eff_s1) offset from the R results to the new stage-1 score.

    Parameters
    ----------
    dea_df      : output of load_ld_dea_inputs()
    res_ld      : Data_Resultater_LD sheet — columns: id, comp, ld_eff.s1.cb, ld_eff.s2.cb
    exclude_ids : IDs to remove from BOTH reference and evaluation sets

    Returns
    -------
    DataFrame with one row per evaluated company (excluding excluded_ids), containing:
      id, comp, X_cb,
      eff_s1_baseline, eff_s1_scenario,
      eff_s2_approx_base, eff_s2_approx_scenario,
      gap_mnok_baseline, gap_mnok_scenario,
      peer_{id} columns (lambda weights for scenario reference companies)
    """
    exclude_ids = set(map(int, exclude_ids or []))

    # --- Geo-correction lookup ---
    r_idx      = res_ld.set_index("id")
    geo_offset = {}
    id_to_comp = {}
    for rid in dea_df["id"]:
        if rid in r_idx.index:
            geo_offset[rid] = (
                float(r_idx.loc[rid, "ld_eff.s2.cb"])
                - float(r_idx.loc[rid, "ld_eff.s1.cb"])
            )
            id_to_comp[rid] = str(r_idx.loc[rid, "comp"])
        else:
            geo_offset[rid] = 0.0
            id_to_comp[rid] = str(rid)

    # --- Baseline: full reference + full evaluation ---
    X_eval_full = dea_df["X_cb"].values
    Y_eval_full = dea_df[["ld_sub", "ld_hv", "ld_ss"]].values
    X_ref_full  = dea_df["X_avg"].values
    Y_ref_full  = dea_df[["fha_sub", "fha_hv", "fha_ss"]].values
    eff_base, _lam_base = _dea_crs_input(X_ref_full, Y_ref_full, X_eval_full, Y_eval_full)
    base_ids = dea_df["id"].values

    # --- Scenario: exclude from BOTH reference and evaluation ---
    keep_mask    = ~dea_df["id"].isin(exclude_ids)
    dea_kept     = dea_df[keep_mask].reset_index(drop=True)
    X_eval_scen  = dea_kept["X_cb"].values
    Y_eval_scen  = dea_kept[["ld_sub", "ld_hv", "ld_ss"]].values
    X_ref_scen   = dea_kept["X_avg"].values
    Y_ref_scen   = dea_kept[["fha_sub", "fha_hv", "fha_ss"]].values
    eff_scen, lam_scen = _dea_crs_input(X_ref_scen, Y_ref_scen, X_eval_scen, Y_eval_scen)

    # --- Assemble result table (only kept companies) ---
    # Map baseline efficiency back using original index position
    base_eff_map = {int(rid): float(eff_base[i]) for i, rid in enumerate(base_ids)}

    out = dea_kept[["id", "X_cb", "ld_sub", "ld_hv", "ld_ss"]].copy().reset_index(drop=True)
    out["comp"]                   = out["id"].map(id_to_comp)
    out["eff_s1_baseline"]        = out["id"].map(base_eff_map)
    out["eff_s1_scenario"]        = eff_scen
    out["geo_offset"]             = out["id"].map(geo_offset).fillna(0.0)
    out["eff_s2_approx_base"]     = out["eff_s1_baseline"] + out["geo_offset"]
    out["eff_s2_approx_scenario"] = out["eff_s1_scenario"] + out["geo_offset"]
    out["gap_mnok_baseline"]      = (
        (1 - out["eff_s1_baseline"]) * out["X_cb"] / 1000
    ).clip(lower=0)
    out["gap_mnok_scenario"]      = (
        (1 - out["eff_s1_scenario"]) * out["X_cb"] / 1000
    ).clip(lower=0)

    # Lambda peer-weight columns (reference ID as suffix)
    lam_df = pd.DataFrame(
        lam_scen,
        columns=[f"peer_{int(rid)}" for rid in dea_kept["id"].values],
    )
    out = pd.concat([out, lam_df], axis=1)

    return out


# ---------------------------------------------------------------------------
# Helper: which companies are on the DEA frontier?
# ---------------------------------------------------------------------------

def get_frontier_companies(
    dea_df: pd.DataFrame,
    exclude_ids: list[int] | None = None,
) -> set[int]:
    """
    Return the set of company IDs that define the efficiency frontier
    (positive lambda weight for at least one other evaluated company).

    Excluded companies are removed from BOTH reference and evaluation
    (consistent with run_ld_scenario).

    Parameters
    ----------
    dea_df      : output of load_ld_dea_inputs()
    exclude_ids : IDs removed from both reference and evaluation sets
    """
    exclude_ids = set(map(int, exclude_ids or []))
    keep_mask = ~dea_df["id"].isin(exclude_ids)
    kept      = dea_df[keep_mask].reset_index(drop=True)

    X_eval = kept["X_cb"].values
    Y_eval = kept[["ld_sub", "ld_hv", "ld_ss"]].values
    X_ref  = kept["X_avg"].values
    Y_ref  = kept[["fha_sub", "fha_hv", "fha_ss"]].values

    _eff, lam = _dea_crs_input(X_ref, Y_ref, X_eval, Y_eval)

    peer_ids: set[int] = set()
    for j in range(lam.shape[1]):
        if lam[:, j].sum() > 1e-6:
            peer_ids.add(int(kept.iloc[j]["id"]))
    return peer_ids


# ---------------------------------------------------------------------------
# Helper: extract peer shares for one company
# ---------------------------------------------------------------------------

def get_peer_shares(
    scenario_row: pd.Series,
    id_to_comp: dict[int, str],
) -> pd.DataFrame:
    """
    Extract non-zero peer weights for a single company row.

    Returns DataFrame with columns: comp, lambda, share (fraction of total).
    """
    peer_cols = [c for c in scenario_row.index if c.startswith("peer_")]
    rows = []
    for col in peer_cols:
        weight = float(scenario_row[col])
        if weight > 1e-6:
            rid  = int(col.split("_", 1)[1])
            comp = id_to_comp.get(rid, str(rid))
            rows.append({"comp": comp, "lambda": weight})
    if not rows:
        return pd.DataFrame(columns=["comp", "lambda", "share"])
    df    = pd.DataFrame(rows).sort_values("lambda", ascending=False)
    total = df["lambda"].sum()
    df["share"] = (df["lambda"] / total) if total > 0 else 0.0
    return df.reset_index(drop=True)
