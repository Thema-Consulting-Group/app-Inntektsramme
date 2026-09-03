"""Fusjon på grunnlagsdatanivå — slå sammen selskaper før RME-modellen kjøres.

Hvorfor denne modulen finnes
----------------------------
Fram til nå har eneste vei til en fusjon vært å laste ned grunnlagsdata, slå
sammen radene i Excel og laste opp igjen.  Det går galt på to måter som ingen
av dem gir feilmelding:

1. **Priser kan ikke summeres.**  ``pnl.rc`` og ``ap.t_2`` er *områdepriser*
   (kr/kWh), ikke kostnader.  Nettapskostnaden er ``volum * pnl.rc``
   (``inntektsramme.py``, jf. ``R-script/4_0_Revenue_Cap_Calculation.R:17,20``),
   så en summert pris multipliseres med et summert volum.  Slår man sammen tre
   selskaper i NO1/NO3 blir prisen 0,624 + 0,359 + 0,381 = 1,365 kr/kWh — over
   dobbelt så høy som den høyeste områdeprisen som finnes — og nettapskostnaden
   blåses opp med ~1,5 mrd kr.  Riktig pris er et volumvektet snitt (~0,563),
   altså *lavere* enn selskapets egen pris, siden NO3 er billigere enn NO1.

2. **Rammevilkårsvariablene kan ikke summeres.**  ``ldz_*`` er snitt over
   kartruter i konsesjonsområdet.  De skal vektes med antall kartruter
   (``ldz_mgc``), som er nettopp det ``merge_ldz_rdz`` / ``merge_NVE`` i
   ``R-script/functions_nve.R`` gjør.  ``ldz_mgc`` selv summeres.

I tillegg må sammenslåingen gjøres for **alle år** i filen, ikke bare
kostnadsgrunnlagsåret.  ``R-script/0_3_Calculated_Input_Values.R:24-34,63-70``
bygger både pensjonsgrunnlaget og DEAs inn- og utdata som femårssnitt, så en
fusjon som bare treffer siste år gir en enhet som benchmarkes på én femtedel av
sin egen størrelse.

Aggregeringsreglene her følger NVEs egen fusjonsrutine i ``functions_nve.R``,
med ett bevisst avvik: ``ap.t_2`` volumvektes i stedet for å snittes.  Den er en
pris på de samme nettapsvolumene som ``pnl.rc``, så vekting er mer konsistent
enn et rent snitt.  Avviket gjelder bare bransjeaggregatet i
``4_0_Revenue_Cap_Calculation.R:43-45`` og treffer ikke ``ir_tabell``.

Sletting av selskaper
---------------------
Overstyringssteget i ``IRiR.R`` matcher på ``(orgn, y)`` og skriver verdier inn
i ``dat``.  Rader som *mangler* i opplastingen blir derfor stående urørt — å
fjerne et selskap fra CSV-en sletter det ikke fra modellen.  Denne modulen
skriver i stedet kolonnen ``_slett`` (1 = fjern selskapet), som ``IRiR.R``
filtrerer på.  Det er den eneste måten et selskap faktisk forsvinner fra
referansesettet og fra kalibreringen.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import pandas as pd

from utils import Util

logger = logging.getLogger(__name__)

# Kolonnen fusjonsrutinen skriver for å be IRiR.R fjerne et selskap.
SLETT_COL = "_slett"

# Nøkkel-/identitetskolonner som aldri aggregeres.
IDENT_COLS = frozenset({"orgn", "y", "comp", "id", "id.y", "orgn.y", "X", "", "Unnamed: 0"})

# Områdepriser (kr/kWh).  Vektes med samlet nettapsvolum, ld_nl + rd_nl.
PRICE_COLS = frozenset({"pnl.rc", "ap.t_2"})

# Vekten prisene aggregeres med.
PRICE_WEIGHT_COLS = ("ld_nl", "rd_nl")

# Antall kartruter — vekten rammevilkårsvariablene aggregeres med.  Summeres selv.
MGC_COL = "ldz_mgc"

# Prefiks for rammevilkårsvariabler (snitt over kartruter).
GEO_PREFIXES = ("ldz_", "rdz_")

SUM = "sum"
PRICE_WEIGHTED = "volumvektet"
MGC_WEIGHTED = "kartrutevektet"
IDENT = "identitet"


def classify_column(col: str) -> str:
    """Return the aggregation treatment for one grunnlagsdata column.

    Rule-based rather than an explicit list, so a column added to
    ``generate_grunnlagsdata.R`` gets a sane default (sum) instead of being
    silently dropped.
    """
    if col in IDENT_COLS or col == SLETT_COL or str(col).startswith("Unnamed:"):
        return IDENT
    if col in PRICE_COLS:
        return PRICE_WEIGHTED
    if col == MGC_COL:
        return SUM
    if str(col).startswith(GEO_PREFIXES):
        return MGC_WEIGHTED
    return SUM


def classify_columns(cols) -> dict[str, list[str]]:
    """Group column names by treatment."""
    out: dict[str, list[str]] = {SUM: [], PRICE_WEIGHTED: [], MGC_WEIGHTED: [], IDENT: []}
    for c in cols:
        out[classify_column(c)].append(c)
    return out


@dataclass
class FusjonGruppe:
    """One merger: ``mottaker`` absorbs every company in ``maal``."""

    mottaker: int
    maal: list[int]

    @staticmethod
    def from_dict(d: dict) -> "FusjonGruppe":
        maal = d.get("maal") or d.get("targets") or []
        return FusjonGruppe(
            mottaker=int(d.get("mottaker") or d.get("acquirer")),
            maal=[int(x) for x in maal],
        )


@dataclass
class FusjonRapport:
    """What the merge actually did — surfaced in the UI, not just logged."""

    grupper: list[dict] = field(default_factory=list)
    advarsler: list[str] = field(default_factory=list)
    behandling: dict[str, list[str]] = field(default_factory=dict)
    rader_fjernet: int = 0
    aar: list[int] = field(default_factory=list)


def _num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Coerce the given columns to numeric, leaving unparseable values as NaN."""
    out = df.copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _weighted(values: pd.Series, weights: pd.Series) -> tuple[float, bool]:
    """Weighted mean of ``values``, ignoring rows where either side is NaN.

    Returns ``(value, fell_back)``.  ``fell_back`` is True when the weights sum
    to zero (or nothing is usable) and a plain mean was used instead — the
    caller reports that, because a zero-weight fallback is a modelling choice
    the user should see rather than a silent default.
    """
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    ok = v.notna() & w.notna()
    if not ok.any():
        return (float("nan"), True)
    vv, ww = v[ok], w[ok]
    total = float(ww.sum())
    if total == 0 or not math.isfinite(total):
        return (float(vv.mean()), True)
    return (float((vv * ww).sum() / total), False)


def merge_companies(
    df: pd.DataFrame,
    grupper: list[FusjonGruppe],
) -> tuple[pd.DataFrame, FusjonRapport]:
    """Merge companies in a grunnlagsdata frame.

    The receiving company keeps its own ``orgn`` and ``comp``, so every
    id-keyed lookup downstream (``dea_overrides`` in ``config.yaml``,
    ``Data/kundetillegg.csv``) still resolves — and, deliberately, the merged
    entity inherits the receiver's DEA override if it has one.

    Target companies are marked with ``_slett`` rather than dropped from the
    frame, because ``IRiR.R`` applies the upload as a *value* override keyed on
    ``(orgn, y)``: a row that is simply absent leaves the company untouched in
    the model.  Every year present in the file is merged.
    """
    if "orgn" not in df.columns or "y" not in df.columns:
        raise ValueError("Grunnlagsdata mangler 'orgn'/'y'.")

    rap = FusjonRapport()
    out = df.copy()
    out["orgn"] = pd.to_numeric(out["orgn"], errors="coerce").astype("Int64")
    out["y"] = pd.to_numeric(out["y"], errors="coerce").astype("Int64")

    by_treatment = classify_columns(out.columns)
    rap.behandling = {k: sorted(v) for k, v in by_treatment.items()}
    sum_cols = [c for c in by_treatment[SUM] if c in out.columns]
    price_cols = [c for c in by_treatment[PRICE_WEIGHTED] if c in out.columns]
    geo_cols = [c for c in by_treatment[MGC_WEIGHTED] if c in out.columns]

    out = _num(out, sum_cols + price_cols + geo_cols)

    aar = sorted(int(y) for y in out["y"].dropna().unique())
    rap.aar = aar

    # Reject overlapping groups up front — merging A into B and B into C in one
    # pass has no well-defined answer, and silently picking an order would be
    # worse than refusing.
    seen: dict[int, str] = {}
    for g in grupper:
        for orgn, role in [(g.mottaker, "mottaker")] + [(m, "mål") for m in g.maal]:
            if orgn in seen:
                raise ValueError(
                    f"Selskap {orgn} er oppgitt som {seen[orgn]} og {role} i samme "
                    "fusjon. Kjør sammenslåingene etter hverandre i stedet."
                )
            seen[orgn] = role

    name_of = {}
    if "comp" in out.columns:
        for orgn, grp in out.groupby("orgn", dropna=True):
            name_of[int(orgn)] = str(grp["comp"].iloc[0])

    # Companies a previous merge already removed. Their rows are still in the
    # frame (the override step needs to see them to drop them), but they hold
    # pre-merge values and must not be folded into a second merger.
    allerede_slettet: set[int] = set()
    if SLETT_COL in out.columns:
        flagged = pd.to_numeric(out[SLETT_COL], errors="coerce").fillna(0) > 0
        allerede_slettet = {int(o) for o in out.loc[flagged, "orgn"].dropna().unique()}
    for g in grupper:
        for orgn in [g.mottaker] + list(g.maal):
            if orgn in allerede_slettet:
                raise ValueError(
                    f"{name_of.get(orgn, orgn)} er allerede fusjonert inn i et annet "
                    "selskap og kan ikke brukes igjen. Generer grunnlagsdata på nytt "
                    "for å starte fra rene tall."
                )

    slett: set[int] = set()

    for g in grupper:
        if not g.maal:
            rap.advarsler.append(
                f"{name_of.get(g.mottaker, g.mottaker)}: ingen selskaper å fusjonere inn — hoppet over."
            )
            continue

        present = set(int(o) for o in out["orgn"].dropna().unique())
        if g.mottaker not in present:
            raise ValueError(f"Mottakende selskap {g.mottaker} finnes ikke i grunnlagsdata.")
        mangler = [m for m in g.maal if m not in present]
        if mangler:
            raise ValueError(
                f"Selskapene {mangler} finnes ikke i grunnlagsdata og kan ikke fusjoneres inn."
            )

        alle = [g.mottaker] + list(g.maal)
        detalj = {
            "mottaker": g.mottaker,
            "mottaker_navn": name_of.get(g.mottaker, str(g.mottaker)),
            "maal": list(g.maal),
            "maal_navn": [name_of.get(m, str(m)) for m in g.maal],
            "priser": {},
            "aar_uten_alle": [],
        }

        for year in aar:
            rows = out[(out["y"] == year) & (out["orgn"].isin(alle))]
            if rows.empty:
                continue
            dest = out.index[(out["y"] == year) & (out["orgn"] == g.mottaker)]
            if len(dest) == 0:
                rap.advarsler.append(
                    f"{detalj['mottaker_navn']} mangler rad for {year}; de andre selskapenes "
                    f"{year}-verdier ble ikke fusjonert inn."
                )
                continue
            if len(dest) > 1:
                raise ValueError(
                    f"Grunnlagsdata har {len(dest)} rader for orgn {g.mottaker} i {year}. "
                    "Filen må ha én rad per selskap per år."
                )
            i = dest[0]

            if len(rows) < len(alle):
                mangler_aar = [
                    name_of.get(o, str(o)) for o in alle
                    if o not in set(int(x) for x in rows["orgn"])
                ]
                detalj["aar_uten_alle"].append({"aar": year, "mangler": mangler_aar})

            # Weights must be read before any value is overwritten.
            w_price = None
            if price_cols:
                have = [c for c in PRICE_WEIGHT_COLS if c in rows.columns]
                if have:
                    w_price = rows[have].apply(pd.to_numeric, errors="coerce").sum(axis=1)
            w_geo = rows[MGC_COL] if (geo_cols and MGC_COL in rows.columns) else None

            for c in price_cols:
                if w_price is None:
                    rap.advarsler.append(
                        f"Fant ikke {' / '.join(PRICE_WEIGHT_COLS)} — kunne ikke volumvekte {c}."
                    )
                    continue
                before = pd.to_numeric(rows.loc[rows["orgn"] == g.mottaker, c], errors="coerce")
                val, fell_back = _weighted(rows[c], w_price)
                out.loc[i, c] = val
                if fell_back:
                    rap.advarsler.append(
                        f"{detalj['mottaker_navn']} {year}: samlet nettapsvolum er null, "
                        f"så {c} ble satt til et uvektet snitt ({val:.6g})."
                    )
                detalj["priser"].setdefault(c, []).append({
                    "aar": year,
                    "foer": (float(before.iloc[0]) if len(before) and pd.notna(before.iloc[0]) else None),
                    "etter": (None if pd.isna(val) else val),
                })

            for c in geo_cols:
                if w_geo is None:
                    rap.advarsler.append(
                        f"Fant ikke {MGC_COL} — kunne ikke kartrutevekte {c}."
                    )
                    continue
                val, fell_back = _weighted(rows[c], w_geo)
                out.loc[i, c] = val
                if fell_back:
                    rap.advarsler.append(
                        f"{detalj['mottaker_navn']} {year}: {MGC_COL} er null, så {c} "
                        f"ble satt til et uvektet snitt ({val:.6g})."
                    )

            for c in sum_cols:
                out.loc[i, c] = float(
                    pd.to_numeric(rows[c], errors="coerce").sum(skipna=True)
                )

        for m in g.maal:
            slett.add(m)
        rap.grupper.append(detalj)

    if SLETT_COL in out.columns:
        existing = pd.to_numeric(out[SLETT_COL], errors="coerce").fillna(0)
    else:
        existing = pd.Series(0, index=out.index)
    out[SLETT_COL] = ((existing > 0) | out["orgn"].isin(slett)).astype(int)
    rap.rader_fjernet = int(out[SLETT_COL].sum())

    return out, rap


# ---------------------------------------------------------------------------
# Validering av opplastet grunnlagsdata
# ---------------------------------------------------------------------------

def _omradeprisbaand(config_path: str = "config.yaml") -> tuple[float, float] | None:
    """[min, max] områdepris in kr/kWh from ``config.yaml``.

    These are the only prices ``pnl.rc`` and ``ap.t_2`` can be built from, so
    any weighted average of them — a merged entity's included — has to land
    inside this band.  That makes it a *domain* bound rather than a statistical
    one, which is what lets the price check fire without false positives.
    """
    try:
        raw = Util.load_config(config_path)
        priser = raw["forutsetninger"]["omradepriser"]
        vals = [float(v) / 1000.0 for v in priser.values() if v is not None]
        return (min(vals), max(vals)) if vals else None
    except Exception as exc:  # config missing/renamed — skip the check, don't crash a run
        logger.warning("Kunne ikke lese områdepriser fra %s: %s", config_path, exc)
        return None


def validate_grunnlagsdata(
    df: pd.DataFrame,
    ref: pd.DataFrame | None = None,
    config_path: str = "config.yaml",
) -> list[dict]:
    """Flag hand-edited grunnlagsdata that cannot be physically valid.

    Two checks, both with hard bounds — no statistical outlier hunting, because
    a legitimate industry maximum must never be flagged:

    * **Områdepriser** (``pnl.rc``, ``ap.t_2``) must lie inside the band spanned
      by ``forutsetninger.omradepriser`` in ``config.yaml``.  They are weighted
      averages of those prices, so nothing else is reachable.  This is the check
      that catches the error behind the ~1,5 mrd kr nettapssprang:
      0,624 + 0,359 + 0,381 = 1,365 kr/kWh, roughly double the dearest price
      area in the country.

    * **Rammevilkårsvariabler** (``ldz_*``) must lie inside the range the same
      column spans in ``ref``.  They are averages over map grid cells, so any
      weighted combination of companies stays within the industry range — while
      a summed one does not.  Skipped when no reference file is available, since
      the range has to come from data known to be clean.

    Returns ``{level, column, orgn, comp, message}`` dicts; the caller decides
    whether to warn or block.
    """
    funn: list[dict] = []
    if "orgn" not in df.columns:
        return funn

    work = df.copy()
    work["orgn"] = pd.to_numeric(work["orgn"], errors="coerce")
    if SLETT_COL in work.columns:
        keep = pd.to_numeric(work[SLETT_COL], errors="coerce").fillna(0) <= 0
        work = work[keep]

    name_of = {}
    if "comp" in work.columns:
        for orgn, grp in work.groupby("orgn", dropna=True):
            name_of[float(orgn)] = str(grp["comp"].iloc[0])

    def flag(col: str, orgn, v: float, lo: float, hi: float, kind: str) -> None:
        navn = name_of.get(float(orgn), str(orgn))
        span = hi - lo
        # Well outside the range rather than just past the edge: the value
        # cannot be a weighted average of anything in the data, so it is an
        # error rather than something to look at.
        langt_utenfor = span > 0 and v > hi + span * 0.5
        hint = ""
        if langt_utenfor:
            hint = (
                "  Områdeprisen er et volumvektet snitt (ld_nl + rd_nl)."
                if kind == PRICE_WEIGHTED
                else "  Rammevilkårsvariabelen er et kartrutevektet snitt (ldz_mgc)."
            )
            hint += " Bruk «Fusjoner selskaper» for å slå sammen selskaper."
        funn.append({
            "level": "error" if langt_utenfor else "warning",
            "column": col,
            "orgn": int(orgn) if pd.notna(orgn) else None,
            "comp": navn,
            "message": (
                f"{navn}: {col} = {v:.6g} ligger utenfor gyldig intervall "
                f"[{lo:.6g}, {hi:.6g}].{hint}"
            ),
        })

    # --- Områdepriser: hard bound from config ---
    baand = _omradeprisbaand(config_path)
    if baand:
        lo, hi = baand
        # config.yaml carries the områdepriser rounded to 0,1 kr/MWh while the
        # data is full precision, so the band needs a little slack in both
        # directions.  1 % is far tighter than the error being guarded against
        # (a summed price is ~2x the dearest area) and comfortably wider than
        # the rounding.
        lo_t, hi_t = lo * 0.99, hi * 1.01
        for col in [c for c in work.columns if classify_column(c) == PRICE_WEIGHTED]:
            per_company = (
                pd.to_numeric(work[col], errors="coerce")
                .groupby(work["orgn"]).max().dropna()
            )
            for orgn, v in per_company.items():
                # Pure production companies have no network loss and therefore
                # no loss price — a zero here is real data, not a bad edit.
                if v == 0:
                    continue
                if v > hi_t or v < lo_t:
                    flag(col, orgn, float(v), lo, hi, PRICE_WEIGHTED)

    # --- Rammevilkårsvariabler: range taken from the reference file ---
    if ref is not None and "orgn" in ref.columns:
        r = ref.copy()
        r["orgn"] = pd.to_numeric(r["orgn"], errors="coerce")
        for col in [c for c in work.columns if classify_column(c) == MGC_WEIGHTED]:
            if col not in r.columns:
                continue
            rv = pd.to_numeric(r[col], errors="coerce").dropna()
            if rv.empty:
                continue
            lo, hi = float(rv.min()), float(rv.max())
            tol = max((hi - lo) * 1e-6, abs(hi) * 1e-9, 1e-12)
            per_company = (
                pd.to_numeric(work[col], errors="coerce")
                .groupby(work["orgn"]).max().dropna()
            )
            for orgn, v in per_company.items():
                if v > hi + tol or v < lo - tol:
                    flag(col, orgn, float(v), lo, hi, MGC_WEIGHTED)

    return funn


def diff_summary(ref: pd.DataFrame, new: pd.DataFrame) -> list[dict]:
    """Report which company-years changed relative to a reference file.

    This is the check that catches the *other* silent hand-merge error: editing
    only the cost-base year.  ``0_3_Calculated_Input_Values.R`` builds the
    pension base and every DEA input as five-year averages, so a company whose
    values moved in one year but not the rest is benchmarked on a mixture of its
    old and new size.  A partial-year edit is almost always a mistake, so it is
    reported explicitly rather than left for the user to notice in the results.
    """
    out: list[dict] = []
    for f in (ref, new):
        if "orgn" not in f.columns or "y" not in f.columns:
            return out

    def keyed(f: pd.DataFrame) -> pd.DataFrame:
        g = f.copy()
        g["orgn"] = pd.to_numeric(g["orgn"], errors="coerce")
        g["y"] = pd.to_numeric(g["y"], errors="coerce")
        return g.dropna(subset=["orgn", "y"]).set_index(["orgn", "y"])

    a, b = keyed(ref), keyed(new)
    cols = [
        c for c in a.columns.intersection(b.columns)
        if classify_column(c) != IDENT
    ]
    if not cols:
        return out

    shared = a.index.intersection(b.index)
    if len(shared) == 0:
        return out
    av = a.loc[shared, cols].apply(pd.to_numeric, errors="coerce")
    bv = b.loc[shared, cols].apply(pd.to_numeric, errors="coerce")
    # Relative comparison so a large cost column is not flagged on rounding.
    changed = ((bv - av).abs() > (av.abs() * 1e-9 + 1e-9)).any(axis=1)

    name_of = {}
    if "comp" in new.columns:
        n = new.copy()
        n["orgn"] = pd.to_numeric(n["orgn"], errors="coerce")
        for orgn, grp in n.groupby("orgn", dropna=True):
            name_of[float(orgn)] = str(grp["comp"].iloc[0])

    all_years = sorted({int(y) for _, y in shared})
    for orgn in sorted({o for o, _ in shared}):
        years_for = sorted({int(y) for o, y in shared if o == orgn})
        hit = sorted({int(y) for (o, y), c in changed.items() if o == orgn and c})
        if not hit:
            continue
        untouched = [y for y in years_for if y not in hit]
        entry = {
            "orgn": int(orgn),
            "comp": name_of.get(float(orgn), str(int(orgn))),
            "aar_endret": hit,
            "aar_urort": untouched,
            "delvis": bool(untouched),
        }
        if untouched:
            entry["message"] = (
                f"{entry['comp']}: endret i {', '.join(str(y) for y in hit)}, ikke i "
                f"{', '.join(str(y) for y in untouched)}. Femårssnittene i modellen "
                "(pensjonsgrunnlag, DEA-variabler) krever at alle år endres."
            )
        out.append(entry)
    _ = all_years
    return out
