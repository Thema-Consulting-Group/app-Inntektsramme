"""Analysepanel — KPI-er og figurer per selskap og år.

Bygger datagrunnlaget for de fire elementene i inntektsrammeanalysen
(jf. Inntektsrammeanalyse 2025, s. 9):

  1. Inntektsramme etter bransjeoverheng  — nivå i MNOK + endring fra året før
  2. Avkastning på nettkapital            — prosent og MNOK + endring i pp
  3. Effektivitet per trinn               — DEA (trinn 1), rammevilkår (trinn 2),
                                            oppkalibrering (trinn 3), samt vektet
  4. Frontselskap per nettnivå            — referansevekter fra DEA-analysen

Datakildene finnes allerede i prosjektet:

  * ``ld_eff.s1.cb`` / ``ld_eff.s2.cb`` i ``Data_Resultater_LD.xlsx`` er trinn 1
    og trinn 2 for lokalt distribusjonsnett (tilsvarende for RD).  Regionalnettet
    har ingen rammevilkårskorreksjon — s1 og s2 er identiske — så trinn 2 utgår
    der, akkurat som i analysen.  Dette avgjøres per kjøring, ikke hardkodet.
  * ``ld_ncs_<SELSKAP>`` / ``rd_ncs_<SELSKAP>`` er referansevektene mot
    frontselskapene, og summerer til 1 per selskap.
  * Trinn 3 og de to øverste KPI-ene hentes fra flerårsarket, slik at panelet
    kan vise et vilkårlig prognoseår og endring mot året før.

MERK: trinn 1 og 2 samt frontselskapene er DEA-resultater for *basisåret*.
Prognosen holder effektiviteten fast, så i prognoseår er det bare trinn 3
(oppkalibreringen) som beveger seg.  Panelet merker dette eksplisitt framfor
å vise en endring som alltid er null.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from flerarsark import ARK_BASE_YEAR, build_flerarsark
from inntektsramme import RevenueCapCalculator
from prognose import FORECAST_YEARS

logger = logging.getLogger(__name__)

# Alle år panelet kan vise.  Vi bygger alltid hele spennet slik at ethvert år
# (unntatt det første) har et foregående år å regne endring mot.
ANALYSE_YEARS = list(FORECAST_YEARS)

# ---------------------------------------------------------------------------
# Farger
# ---------------------------------------------------------------------------

# Fargeramper per nettnivå — én fargefamilie hver, lys → mørk.
# D-nett blå, R-nett grønn, Vektet gul, etter mønster fra inntektsrammeanalysen.
# Rampene er ordnet fra lysest til mørkest og brukes to steder:
#   * effektivitetstrinnene: økende trinn = mørkere (trinnene er en progresjon)
#   * frontselskapsringene: større andel = mørkere (andelen er en størrelse)
# I begge tilfeller er det en *sekvensiell* koding av noe ordnet, ikke kategorier
# — derfor er én fargefamilie per nivå riktig her.  Identiteten til frontselskapene
# bæres av navn og prosentetiketter, ikke av fargen, siden fargen koder andelen.
NIVAA_RAMPER = {
    "D-nett": ["#cde2fb", "#86b6ef", "#3987e5", "#184f95"],
    "R-nett": ["#d6e8dc", "#9cc4a9", "#5b9673", "#2f6b4a"],
    "Vektet": ["#fdf0c9", "#fadf8b", "#f5c542", "#d9a017"],
}

# Lys bakgrunn + kantfarge for gruppeboksene i «Effektivitet per trinn».
NIVAA_STIL = {
    "D-nett": {"bakgrunn": "#eef5fd", "kant": "#cfe2f7"},
    "R-nett": {"bakgrunn": "#eef6f1", "kant": "#cfe6d8"},
    "Vektet": {"bakgrunn": "#fffaeb", "kant": "#f6e6b8"},
}

# Bakoverkompatibelt alias — trinnrampene er de samme som nivårampene.
TRINN_RAMPER = NIVAA_RAMPER


def _trinn_farger(n: int, nivaa: str) -> list[str]:
    """Fargesteg for n trinnstolper, lysest → mørkest med økende trinn.

    Det lyseste steget i rampen er reservert til bakgrunner og små ringsegmenter
    — som stolpefyll blir det for blekt — så stolpene bruker de tre mørkeste.
    Én enkelt stolpe (Vektet) får mellomtonen.
    """
    ramp = NIVAA_RAMPER[nivaa][1:]
    if n <= 1:
        return [ramp[1]]
    return [ramp[round(i / (n - 1) * (len(ramp) - 1))] for i in range(n)]


def _andel_farger(n: int, nivaa: str) -> list[str]:
    """Fargesteg for n ringsegmenter, mørkest først (største andel mørkest).

    Segmentene ligger i samme fargefamilie som nettnivået, så vi sprer dem over
    rampen for å holde lysheten godt fra hverandre.  Maks 3 frontselskap opptrer
    samtidig i datagrunnlaget.
    """
    ramp = NIVAA_RAMPER[nivaa]
    if n <= 1:
        return [ramp[-1]]
    if n == 2:
        return [ramp[-1], ramp[1]]
    # n >= 3: mørkest, midt, lysest — og deretter lysest for et evt. haleledd
    valgt = [ramp[-1], ramp[-2], ramp[0]]
    return (valgt + [ramp[0]] * n)[:n]


TRINN_NAVN = {
    1: "DEA-analyse – Trinn 1",
    2: "Rammevilkår – Trinn 2",
    3: "Oppkalibrering – Trinn 3",
}


# ---------------------------------------------------------------------------
# Mellomlagring — flerårsarket tar ~1,5 s å bygge
# ---------------------------------------------------------------------------

_ARK_CACHE: dict = {}
_RC_CACHE: dict = {}
_CACHE_MAX = 4


def _cache_get(store: dict, key, build):
    if key in store:
        return store[key]
    val = build()
    if len(store) >= _CACHE_MAX:
        store.pop(next(iter(store)))
    store[key] = val
    return val


def get_rc(run_name: str | None, config_path: str = "config.yaml") -> RevenueCapCalculator:
    return _cache_get(_RC_CACHE, (run_name, config_path),
                      lambda: RevenueCapCalculator(config_path, run_name=run_name))


def get_ark(run_name: str | None = None, recalibrate: bool = True,
            bfv_rebase: str = "both", align_basis: bool = True,
            base_year_from_ark: bool = True):
    key = (run_name, recalibrate, bfv_rebase, align_basis, base_year_from_ark)
    return _cache_get(_ARK_CACHE, key, lambda: build_flerarsark(
        run_name=run_name, recalibrate=recalibrate, bfv_rebase=bfv_rebase,
        align_basis=align_basis, base_year_from_ark=base_year_from_ark,
        years=ANALYSE_YEARS,
    ))


def clear_cache():
    _ARK_CACHE.clear()
    _RC_CACHE.clear()


# ---------------------------------------------------------------------------
# Frontselskap
# ---------------------------------------------------------------------------

def _front_level(res: pd.DataFrame, prefix: str) -> dict:
    """Returner {orgn: [(navn, vekt)]} for ett nettnivå, sortert på fallende vekt."""
    cols = [c for c in res.columns if c.startswith(f"{prefix}_ncs_")]
    if not cols:
        return {}
    names = [c[len(f"{prefix}_ncs_"):] for c in cols]
    per_orgn: dict[int, list[tuple[str, float]]] = {}
    for _, row in res.iterrows():
        aktive = [(n, float(row[c] or 0)) for n, c in zip(names, cols)
                  if float(row[c] or 0) > 1e-6]
        if aktive:
            per_orgn[int(row["orgn"])] = sorted(aktive, key=lambda t: -t[1])
    return per_orgn


def load_frontselskap(rc: RevenueCapCalculator) -> dict:
    """Referansevekter mot frontselskap, per nettnivå."""
    return {
        "D-nett": _front_level(rc.data.res_ld, "ld"),
        "R-nett": _front_level(rc.data.res_rd, "rd"),
    }


# ---------------------------------------------------------------------------
# Effektivitetstrinn
# ---------------------------------------------------------------------------

def _eff_stages(res: pd.DataFrame, prefix: str, orgn: int) -> dict:
    """Trinn 1 og 2 fra DEA-resultatfilen.  Trinn 2 utgår når den er identisk
    med trinn 1 (regionalnettet har ingen rammevilkårskorreksjon)."""
    rad = res[res["orgn"] == orgn]
    if rad.empty:
        return {}
    r = rad.iloc[0]
    s1 = r.get(f"{prefix}_eff.s1.cb")
    s2 = r.get(f"{prefix}_eff.s2.cb")
    out = {}
    if s1 is not None and not pd.isna(s1):
        out[1] = float(s1) * 100
    if s2 is not None and not pd.isna(s2):
        v2 = float(s2) * 100
        if 1 not in out or abs(v2 - out[1]) > 1e-4:
            out[2] = v2
    return out


def _trinn3(row: pd.Series, nivaa: str) -> float | None:
    """Kalibrert DEA-resultat (trinn 3) for ett nettnivå og år."""
    if nivaa == "D-nett":
        kg, norm = float(row["ld_kg"]), float(row["k_ld"])
    else:
        # RD-normen inneholder nettapskostnaden som gjennomslag; DEA-grunnlaget
        # er ekskl. nettap, så begge må renses for å bli sammenlignbare.
        kg = float(row["rd_kg"])
        norm = float(row["k_rd"]) - float(row["rd_nettap"])
    if kg <= 0:
        return None
    return norm / kg * 100


# ---------------------------------------------------------------------------
# Hovedfunksjon
# ---------------------------------------------------------------------------

def build_analyse(orgn: int, year: int, run_name: str | None = None,
                  recalibrate: bool = True, bfv_rebase: str = "both") -> dict:
    """Datagrunnlag for analysepanelet, for ett selskap og ett år."""
    ark = get_ark(run_name=run_name, recalibrate=recalibrate, bfv_rebase=bfv_rebase)
    rc = get_rc(run_name)

    L = ark.long
    sel = L[L["orgn"] == int(orgn)]
    if sel.empty:
        raise ValueError(f"Selskap med org.nr {orgn} finnes ikke i flerårsarket.")
    sel = sel.set_index("aar")
    if int(year) not in sel.index:
        raise ValueError(
            f"År {year} er utenfor spennet {min(sel.index)}–{max(sel.index)}."
        )

    year = int(year)
    cur = sel.loc[year]
    # Året før basisåret er tilbakeskrevet ved å deflatere basisåret med de samme
    # vekstforutsetningene.  En endring mot det året gjentar bare forutsetningene
    # og sier ingenting om selskapet, så da oppgir vi ingen endringstall.
    prev_year = year - 1 if (year - 1) in sel.index else None
    if prev_year is not None and prev_year < ARK_BASE_YEAR:
        prev_year = None
    prev = sel.loc[prev_year] if prev_year is not None else None
    selskap = str(cur["selskap"])
    merknader: list[str] = []

    # --- 1. Inntektsramme (MNOK) --------------------------------------------
    ir_mnok = float(cur["ir_etter"]) / 1000
    ir_endring = (float(cur["ir_etter"]) - float(prev["ir_etter"])) / 1000 if prev is not None else None

    # --- 2. Avkastning på nettkapital ---------------------------------------
    def _avk(row):
        ikke_kapital = (float(row["dv"]) + float(row["avs"]) + float(row["ld_nettap"])
                        + float(row["rd_nettap"]) + float(row["kile"]))
        kroner = float(row["ir_etter"]) - ikke_kapital
        akg = float(row["akg"])
        return kroner, (kroner / akg * 100 if akg > 0 else 0.0)

    avk_kr, avk_pct = _avk(cur)
    avk_endring = None
    if prev is not None:
        avk_endring = avk_pct - _avk(prev)[1]

    # --- 3. Effektivitet per trinn ------------------------------------------
    ld_stages = _eff_stages(rc.data.res_ld, "ld", int(orgn))
    rd_stages = _eff_stages(rc.data.res_rd, "rd", int(orgn))

    ld_overstyrt = int(cur["id"]) in rc.cfg.dea_ld_overrides
    rd_overstyrt = int(cur["id"]) in rc.cfg.dea_rd_overrides

    trinn: list[dict] = []
    for nivaa, stages in (("D-nett", ld_stages), ("R-nett", rd_stages)):
        rader: list[dict] = []
        for t in sorted(stages):
            rader.append({"trinn": t, "verdi_pct": stages[t], "endring_pp": None,
                          "basisaar": True})
        t3 = _trinn3(cur, nivaa)
        if t3 is not None:
            e3 = None
            if prev is not None:
                p3 = _trinn3(prev, nivaa)
                if p3 is not None:
                    e3 = t3 - p3
            rader.append({"trinn": 3, "verdi_pct": t3, "endring_pp": e3,
                          "basisaar": False})
        if not rader:
            continue
        farger = _trinn_farger(len(rader), nivaa)
        for i, r in enumerate(rader):
            r["farge"] = farger[i]
            r["nivaa"] = nivaa
            r["label"] = TRINN_NAVN[r["trinn"]]
        trinn.extend(rader)

    # Vektet trinn 3 = samlet norm / samlet kostnadsgrunnlag
    vektet = float(cur["eff_w_pct"])
    vektet_endring = (vektet - float(prev["eff_w_pct"])) if prev is not None else None
    trinn.append({
        "nivaa": "Vektet", "trinn": 3, "label": "Vektet – Trinn 3",
        "verdi_pct": vektet, "endring_pp": vektet_endring,
        "basisaar": False, "farge": _trinn_farger(1, "Vektet")[0],
    })

    # --- 4. Frontselskap per nettnivå ---------------------------------------
    front_all = load_frontselskap(rc)
    front: dict[str, list[dict]] = {}
    for nivaa, per_orgn in front_all.items():
        vekter = per_orgn.get(int(orgn))
        if not vekter:
            front[nivaa] = []
            continue
        tot = sum(v for _, v in vekter) or 1.0
        # Vektene er sortert fallende, og fargene går mørkest → lysest, slik at
        # største andel får den mørkeste tonen i nettnivåets fargefamilie.
        farger = _andel_farger(len(vekter), nivaa)
        front[nivaa] = [{
            "navn": navn,
            "andel_pct": v / tot * 100,
            "farge": farger[i],
        } for i, (navn, v) in enumerate(vekter)]

    # --- Merknader -----------------------------------------------------------
    if prev_year is None:
        if year <= ARK_BASE_YEAR:
            merknader.append(
                f"{year} er basisåret. Året før er tilbakeskrevet ved å deflatere "
                f"{ARK_BASE_YEAR}, så en endring mot det ville bare gjentatt "
                "vekstforutsetningene. Endringstall vises derfor fra "
                f"{ARK_BASE_YEAR + 1}."
            )
        else:
            merknader.append(f"{year} er første år i spennet — ingen endringstall.")
    merknader.append(
        f"Trinn 1 og 2 er DEA-resultater for basisåret {ARK_BASE_YEAR}. "
        "Prognosen holder effektiviteten fast, så i prognoseår beveger bare "
        "trinn 3 (oppkalibreringen) seg."
    )
    merknader.append(
        f"Frontselskapene er DEA-resultat for basisåret {ARK_BASE_YEAR} og er "
        "like for alle år."
    )
    if ld_overstyrt or rd_overstyrt:
        hvilke = " og ".join(n for n, f in (("D-nett", ld_overstyrt), ("R-nett", rd_overstyrt)) if f)
        merknader.append(
            f"Selskapet har manuelt overstyrt DEA-resultat for {hvilke} "
            "(alternativ benchmarkingmodell eller «evalueres ikke»), så trinn 1/2 "
            "fra DEA-kjøringen kan mangle eller avvike fra normen som brukes."
        )
    if not front["D-nett"] and not front["R-nett"]:
        merknader.append("Ingen frontselskapsvekter funnet — selskapet er ikke med i DEA-utvalget.")

    return {
        "selskap": selskap,
        "orgn": int(orgn),
        "id": int(cur["id"]),
        "aar": year,
        "forrige_aar": prev_year,
        # 2025 tilbys ikke: det er en tilbakeskriving, ikke et modellresultat.
        "aar_tilgjengelig": [int(y) for y in sel.index if int(y) >= ARK_BASE_YEAR],
        "ir": {"mnok": ir_mnok, "endring_mnok": ir_endring},
        "avkastning": {"pct": avk_pct, "mnok": avk_kr / 1000, "endring_pp": avk_endring},
        "trinn": trinn,
        "nivaastil": NIVAA_STIL,
        "front": front,
        "merknader": merknader,
    }


# ---------------------------------------------------------------------------
# Tidsserieanalyse
# ---------------------------------------------------------------------------

# Linjefarger for effektivitetsutviklingen — samme familier som ellers:
# D-nett blått, R-nett grønt, vektet gult.  Bransjesnittet er en referanselinje,
# ikke et nettnivå, og får derfor en nøytral laksefarge og prikket strek.
TIDSSERIE_LINJER = [
    ("vektet",       "Kalibrert vektet effektivitet", "#f5c542", "solid", 3),
    ("dnett",        "Distribusjonsnett",             "#184f95", "solid", 2),
    ("rnett",        "Regionalnett",                  "#2f6b4a", "dash",  2),
    ("bransjesnitt", "Bransjesnitt (vektet)",         "#e28a76", "dot",   2),
]

# Kostnadskomponentene er *kategorier*, ikke nettnivåer, så de kan ikke ligge i
# blå/grønn/gul-familiene: seks skillbare kategorier får ikke plass i to
# fargefamilier (nærmeste grønnpar havner på ΔE 12,1 i normalt syn, under gulvet
# på 15).  Denne rekkefølgen er validert med dataviz-validatoren på lys flate og
# passerer alle harde krav; kontrastadvarselen er kvittert ut med direkte
# prosentetiketter og endringstabellen ved siden av.
KOSTNAD_KOMPONENTER = [
    ("Kapitalkostnad", "kapitalkostnad", "#2a78d6"),
    ("Avskrivninger",  "avs",            "#eb6834"),
    ("Nettap",         "nettap",         "#1baf7a"),
    ("Kile",           "kile",           "#eda100"),
    ("D&V",            "dv",             "#e87ba4"),
    ("RKSU",           "utred",          "#008300"),
]


def _nansum_local(serie) -> float:
    return float(np.nansum(serie.to_numpy(dtype="float64")))


def _cagr(forste: float, siste: float, aar: int) -> float | None:
    """Årlig gjennomsnittlig vekst over `aar` år."""
    if aar <= 0 or forste <= 0 or siste <= 0:
        return None
    return ((siste / forste) ** (1 / aar) - 1) * 100


def build_tidsserie(orgn: int, run_name: str | None = None,
                    recalibrate: bool = True, bfv_rebase: str = "both",
                    aar_fra: int | None = None, aar_til: int | None = None) -> dict:
    """Tidsserieanalyse for ett selskap over prognoseperioden.

    Fire elementer, etter mønster fra inntektsrammeanalysen:
      1. Effektivitet per nettnivå og vektet, mot bransjesnittet
      2. Inntektsramme, avkastning og investeringsnivå (nivå + CAGR)
      3. Frontselskap per nettnivå over tid
      4. Kostnadsutvikling og -sammensetning
    """
    ark = get_ark(run_name=run_name, recalibrate=recalibrate, bfv_rebase=bfv_rebase)
    rc = get_rc(run_name)
    L = ark.long

    sel = L[L["orgn"] == int(orgn)]
    if sel.empty:
        raise ValueError(f"Selskap med org.nr {orgn} finnes ikke i flerårsarket.")
    sel = sel.set_index("aar").sort_index()

    # Basisåret og framover; 2025 er en tilbakeskriving og holdes utenfor.
    fra = max(int(aar_fra or ARK_BASE_YEAR), ARK_BASE_YEAR)
    til = int(aar_til) if aar_til else int(sel.index.max())
    years = [int(y) for y in sel.index if fra <= int(y) <= til]
    if len(years) < 2:
        raise ValueError(f"Trenger minst to år; fikk {years}.")
    selskap = str(sel.loc[years[0], "selskap"])

    # --- 1. Effektivitet ----------------------------------------------------
    bransje = {}
    for y in years:
        g = L[L["aar"] == y]
        kg = _nansum_local(g["kg"])
        bransje[y] = ((_nansum_local(g["k_ld"]) + _nansum_local(g["k_rd"])) / kg * 100
                      if kg else None)

    serier = {"dnett": [], "rnett": [], "vektet": [], "bransjesnitt": []}
    for y in years:
        row = sel.loc[y]
        serier["dnett"].append(_trinn3(row, "D-nett"))
        serier["rnett"].append(_trinn3(row, "R-nett"))
        serier["vektet"].append(float(row["eff_w_pct"]))
        serier["bransjesnitt"].append(bransje[y])

    effektivitet = {
        "aar": years,
        "serier": serier,
        "linjer": [{"key": k, "navn": n, "farge": f, "strek": d, "bredde": w}
                   for k, n, f, d, w in TIDSSERIE_LINJER],
    }

    # --- 2. Nøkkeltall ------------------------------------------------------
    f_row, s_row = sel.loc[years[0]], sel.loc[years[-1]]
    span = years[-1] - years[0]

    def _avk(row):
        ikke_kap = (float(row["dv"]) + float(row["avs"]) + float(row["ld_nettap"])
                    + float(row["rd_nettap"]) + float(row["kile"]))
        akg = float(row["akg"])
        return ((float(row["ir_etter"]) - ikke_kap) / akg * 100) if akg > 0 else 0.0

    ir_f, ir_s = float(f_row["ir_etter"]) / 1000, float(s_row["ir_etter"]) / 1000
    avk_f, avk_s = _avk(f_row), _avk(s_row)

    # Årlige investeringer utledet av kapitalbasen: I(t) = BFV(t) - BFV(t-1) + AVS(t).
    # Krever et foregående år innenfor prognosen, så vinduet starter ett år senere.
    inv_aar, inv_verdier, bfv_verdier = [], [], []
    for prev, cur in zip(years, years[1:]):
        bfv_c, bfv_p = float(sel.loc[cur, "bfv"]), float(sel.loc[prev, "bfv"])
        inv_aar.append(cur)
        inv_verdier.append(bfv_c - bfv_p + float(sel.loc[cur, "avs"]))
        bfv_verdier.append(bfv_c)
    inv_snitt = (sum(inv_verdier) / len(inv_verdier) / 1000) if inv_verdier else None
    bfv_snitt = (sum(bfv_verdier) / len(bfv_verdier) / 1000) if bfv_verdier else None

    noekkeltall = {
        "forste_aar": years[0],
        "siste_aar": years[-1],
        "ir": {"forste": ir_f, "siste": ir_s, "cagr_pct": _cagr(ir_f, ir_s, span)},
        "avkastning": {"forste": avk_f, "siste": avk_s, "endring_pp": avk_s - avk_f},
        "investering": {
            "aar_fra": inv_aar[0] if inv_aar else None,
            "aar_til": inv_aar[-1] if inv_aar else None,
            "snitt_mnok": inv_snitt,
            "andel_av_nettkapital_pct": (inv_snitt / bfv_snitt * 100)
                                        if (inv_snitt and bfv_snitt) else None,
            "serie": [v / 1000 for v in inv_verdier],
        },
        "tint": {"ir": NIVAA_STIL["D-nett"]["bakgrunn"],
                 "avkastning": NIVAA_STIL["R-nett"]["bakgrunn"],
                 "investering": NIVAA_STIL["Vektet"]["bakgrunn"]},
    }

    # --- 3. Frontselskap over tid -------------------------------------------
    front_all = load_frontselskap(rc)
    front_tid: dict[str, list[dict]] = {}
    for nivaa, per_orgn in front_all.items():
        vekter = per_orgn.get(int(orgn)) or []
        tot = sum(v for _, v in vekter) or 1.0
        farger = _andel_farger(len(vekter), nivaa) if vekter else []
        front_tid[nivaa] = [{
            "navn": navn,
            "farge": farger[i],
            # DEA kjøres bare for basisåret, så andelen er konstant over perioden.
            "andeler": [v / tot * 100] * len(years),
        } for i, (navn, v) in enumerate(vekter)]

    # --- 4. Kostnadsutvikling og -sammensetning -----------------------------
    def _komp(row) -> dict:
        dv = float(row["dv"]); utred = float(row["utred"]); avs = float(row["avs"])
        nettap = float(row["ld_nettap"]) + float(row["rd_nettap"])
        kile = float(row["kile"]); kg = float(row["kg"])
        return {
            "dv": dv, "utred": utred, "avs": avs, "nettap": nettap, "kile": kile,
            # Kapitalkostnaden er residualen AKG * rente.  Renten følger rentebanen,
            # så den leses ut av grunnlaget framfor å regnes på nytt.
            "kapitalkostnad": kg - (dv + utred + avs + nettap + kile),
            "kg": kg,
        }

    k_f, k_s = _komp(f_row), _komp(s_row)
    kg_f = k_f["kg"] or 1.0
    kostnader = {
        "aar_fra": years[0], "aar_til": years[-1],
        "komponenter": [{
            "navn": navn,
            "farge": farge,
            "verdi_forste_mnok": k_f[key] / 1000,
            "andel_pct": k_f[key] / kg_f * 100,
            "endring_pct": ((k_s[key] / k_f[key] - 1) * 100) if k_f[key] else None,
        } for navn, key, farge in KOSTNAD_KOMPONENTER],
        "sum_forste_mnok": kg_f / 1000,
        "sum_siste_mnok": (k_s["kg"] or 0) / 1000,
    }

    merknader = [
        f"Basisåret {ARK_BASE_YEAR} er hentet fra RME-modellen; årene etter er "
        "framskrevet med forutsetningene fra prognosen.",
        "Frontselskapenes andeler er konstante over perioden: DEA kjøres bare for "
        "basisåret, og prognosen holder effektiviteten fast. Utviklingen viser "
        "derfor sammensetningen, ikke en endring i fronten.",
    ]
    if inv_aar:
        merknader.append(
            "Investeringene er utledet av kapitalbasen "
            "(I = BFV(t) − BFV(t−1) + AVS(t)) og dekker "
            f"{inv_aar[0]}–{inv_aar[-1]}; første år mangler et foregående år."
        )
    if not front_tid["D-nett"] and not front_tid["R-nett"]:
        merknader.append("Ingen frontselskapsvekter — selskapet er ikke med i DEA-utvalget.")
    if k_f["kg"] < 1000:  # under 1 MNOK
        merknader.append(
            "Selskapet har praktisk talt ikke kostnadsgrunnlag i perioden, så "
            "kostnadssammensetningen er tom."
        )

    return {
        "selskap": selskap, "orgn": int(orgn), "aar": years,
        "effektivitet": effektivitet,
        "noekkeltall": noekkeltall,
        "front": front_tid,
        "kostnader": kostnader,
        "merknader": merknader,
    }
