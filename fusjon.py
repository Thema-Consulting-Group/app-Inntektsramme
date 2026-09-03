"""Fusjonsanalyse — effekten av å slå sammen to nettselskap.

Svarer på: hva skjer med effektivitet, inntektsramme og avkastning dersom selskap
A og B fusjonerer i et gitt år, under ulike forutsetninger om synergi?

Hvorfor dette krever mer enn å summere to prognoser
---------------------------------------------------
Effektiviteten til det sammenslåtte selskapet er *ikke* et vektet snitt av de to
selskapenes effektivitet.  DEA måler kostnad mot oppgavemengde, og en fusjon
endrer begge: kostnadene summeres (minus synergi), oppgavene summeres, og de to
selskapene forsvinner fra referansesettet — som endrer fronten for alle andre.
Vi må derfor kjøre DEA på nytt.

``frontselskap._dea_crs_input`` replikerer RMEs trinn-1 DEA (input-orientert CRS)
som LP, og ``Results/{ld,rd}_InputDEA.csv`` inneholder både referansedata (snitt
over år) og evalueringsdata (kostnadsgrunnlagsåret).  Vi bygger en ny DMU med
summerte inn- og utdata, fjerner de to selskapene fra både referanse- og
evalueringssettet, og løser på nytt.  Det er standard DEA-behandling av en fusjon.

Slik håndteres de tre trinnene
------------------------------
* **Trinn 1** kjøres på nytt via LP for alle selskaper.
* **Trinn 2** (rammevilkår) kan ikke kjøres på nytt uten regresjonen fra R.  For
  *eksisterende* selskaper legger vi derfor endringen i trinn 1 oppå den
  R-beregnede trinn-2-verdien, slik at et scenario uten endring reproduserer
  grunnlinjen eksakt.  For den *nye* enheten finnes ingen R-verdi, så
  rammevilkårspåslaget settes til det kostnadsvektede snittet av de to
  selskapenes påslag.
* **Trinn 3** (oppkalibrering) faller ut av modellen selv: normen fordeles på
  nytt over hele bransjen, og kalibreringskonstanten beregnes om — med den
  fusjonerte enheten i stedet for de to.  Det er nettopp derfor denne analysen
  må kjøre alle selskaper samtidig.

Viktige forutsetninger som må defineres ved en fusjon
-----------------------------------------------------
``fusjonsaar``        når fusjonen får virkning
``synergier``         varig reduksjon i D&V-kostnader (prosent), ett eller flere nivåer
``innfasing_aar``     antall år synergien fases inn over
``en_gangs_kostnad``  omstillingskostnad i fusjonsåret (1000 kr)
``synergi_paa``       hvilke kostnader synergien treffer (D&V, evt. også utredning)
``ny_enhet_i_front``  om den nye enheten kan bli referanseselskap for andre
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from analyse import NIVAA_RAMPER, get_ark, get_rc
from flerarsark import ARK_BASE_YEAR
from frontselskap import _dea_crs_input
from inntektsramme import DEANorm

logger = logging.getLogger(__name__)

# Syntetisk id for den fusjonerte enheten — velges høyt nok å ikke kollidere.
FUSJON_ID = 999_999

DEFAULT_SYNERGIER = (15.0, 33.0)

# Nivåoppsett: filnavn, antall utdatavariabler og resultatkolonner
DEA_NIVAA = {
    "D-nett": {"fil": "ld_InputDEA.csv", "s1": "ld_eff.s1.cb", "s2": "ld_eff.s2.cb",
               "res": "res_ld", "kg": "ld_kg", "dv": "ld_dv", "rab": "ld_rab17b",
               "eff_col": "ld_eff.s2.cb", "overrides": "dea_ld_overrides"},
    "R-nett": {"fil": "rd_InputDEA.csv", "s1": "rd_eff.s1.cb", "s2": "rd_eff.s2.cb",
               "res": "res_rd", "kg": "rd_kg", "dv": "rd_dv", "rab": "rd_rab17b",
               "eff_col": "rd_eff.s2.cb", "overrides": "dea_rd_overrides"},
}

# Linjefarger for sammenligningen — samme familier som resten av analysepanelet.
LINJE_A = ("#184f95", "solid")     # selskap A alene (blå, som D-nett)
LINJE_B = ("#2f6b4a", "dot")       # selskap B alene (grønn, som R-nett)
LINJE_FUSJON = [("#f5c542", "solid"), ("#9cc4a9", "dash"),
                ("#e28a76", "dashdot"), ("#86b6ef", "longdash")]


# ---------------------------------------------------------------------------
# DEA-inndata
# ---------------------------------------------------------------------------

def load_dea_inputs(results_dir: str | Path, fil: str) -> pd.DataFrame:
    """Les {ld,rd}_InputDEA.csv til et generisk format.

    Kolonneoppsettet er: id, X_avg, Y_ref…, X_cb, Y_eval… — like mange
    utdatavariabler i referanse- og evalueringsblokken (3 for LD, 4 for RD).
    """
    df = pd.read_csv(Path(results_dir) / fil, index_col=0)
    n_y = (df.shape[1] - 3) // 2
    kols = (["id", "X_avg"] + [f"Y_ref{i}" for i in range(n_y)]
            + ["X_cb"] + [f"Y_ev{i}" for i in range(n_y)])
    df.columns = kols
    df["id"] = df["id"].astype(int)
    return df.reset_index(drop=True), n_y


def _dea_kjoring(df: pd.DataFrame, n_y: int,
                 id_a: int | None = None, id_b: int | None = None,
                 kostreduksjon: float = 0.0,
                 ny_enhet_i_front: bool = True) -> tuple[dict, list, dict]:
    """Kjør trinn-1 DEA, eventuelt med A og B erstattet av en fusjonert enhet.

    Returnerer ({id: effektivitet}, [(peer_id, vekt)] for den nye enheten,
    {peer_id: vekt} aggregert).  Med id_a/id_b = None kjøres grunnlinjen.
    """
    ycols_ref = [f"Y_ref{i}" for i in range(n_y)]
    ycols_ev = [f"Y_ev{i}" for i in range(n_y)]

    if id_a is None or id_b is None:
        kept = df
        merged = None
    else:
        rader = df[df["id"].isin([id_a, id_b])]
        if len(rader) < 2:
            # Minst ett av selskapene er ikke evaluert på dette nettnivået —
            # da finnes det ingen meningsfull fusjonert DMU her.
            return {}, [], {}
        kept = df[~df["id"].isin([id_a, id_b])].reset_index(drop=True)
        skala = 1.0 - kostreduksjon
        merged = {"id": FUSJON_ID,
                  "X_avg": rader["X_avg"].sum() * skala,
                  "X_cb": rader["X_cb"].sum() * skala}
        for c in ycols_ref + ycols_ev:
            merged[c] = rader[c].sum()
        kept = pd.concat([kept, pd.DataFrame([merged])], ignore_index=True)

    # Referansesettet kan valgfritt utelate den nye enheten (da kan den ikke
    # bli front for andre, men måles fortsatt mot de øvrige).
    ref = kept if (ny_enhet_i_front or merged is None) else kept[kept["id"] != FUSJON_ID]

    eff, lam = _dea_crs_input(ref["X_avg"].values, ref[ycols_ref].values,
                              kept["X_cb"].values, kept[ycols_ev].values)
    eff_map = {int(i): float(e) for i, e in zip(kept["id"].values, eff)}

    peers: dict[int, float] = {}
    if merged is not None:
        rad = int(np.where(kept["id"].values == FUSJON_ID)[0][0])
        for j, pid in enumerate(ref["id"].values):
            v = float(lam[rad, j])
            if v > 1e-6:
                peers[int(pid)] = v
    tot = sum(peers.values()) or 1.0
    peers_pct = {k: v / tot * 100 for k, v in peers.items()}
    return eff_map, sorted(peers_pct.items(), key=lambda t: -t[1]), peers


# ---------------------------------------------------------------------------
# Synergi
# ---------------------------------------------------------------------------

def synergi_faktor(aar: int, fusjonsaar: int, synergi_frac: float,
                   innfasing_aar: int) -> float:
    """Andel av den varige synergien som er realisert i et gitt år.

    Lineær innfasing over `innfasing_aar` fra og med fusjonsåret, slik
    prognosemodellen ellers gjør det.
    """
    if aar < fusjonsaar:
        return 0.0
    if innfasing_aar <= 1:
        return synergi_frac
    trinn = min(aar - fusjonsaar + 1, innfasing_aar)
    return synergi_frac * trinn / innfasing_aar


# ---------------------------------------------------------------------------
# Hovedfunksjon
# ---------------------------------------------------------------------------

def build_fusjon(orgn_a: int, orgn_b: int, fusjonsaar: int,
                 synergier=DEFAULT_SYNERGIER, innfasing_aar: int = 3,
                 en_gangs_kostnad: float = 0.0, synergi_paa_utredning: bool = False,
                 ny_enhet_i_front: bool = True, noekkeltall_aar: int | None = None,
                 run_name: str | None = None, recalibrate: bool = True,
                 bfv_rebase: str = "both") -> dict:
    """Analysér en fusjon mellom to selskap over prognoseperioden."""
    ark = get_ark(run_name=run_name, recalibrate=recalibrate, bfv_rebase=bfv_rebase)
    rc = get_rc(run_name)
    L = ark.long
    rho = float(ark.diagnostics["rho"])
    n93 = rc.cfg.sum_renter_avvik_per_akg

    aar_alle = sorted({int(y) for y in L["aar"] if int(y) >= ARK_BASE_YEAR})
    fusjonsaar = int(fusjonsaar)
    if fusjonsaar not in aar_alle:
        raise ValueError(f"Fusjonsåret må ligge i {aar_alle[0]}–{aar_alle[-1]}.")

    rad_a = L[L["orgn"] == int(orgn_a)]
    rad_b = L[L["orgn"] == int(orgn_b)]
    if rad_a.empty or rad_b.empty:
        raise ValueError("Fant ikke ett av selskapene i flerårsarket.")
    if int(orgn_a) == int(orgn_b):
        raise ValueError("Velg to ulike selskap.")
    id_a, id_b = int(rad_a.iloc[0]["id"]), int(rad_b.iloc[0]["id"])
    navn_a, navn_b = str(rad_a.iloc[0]["selskap"]), str(rad_b.iloc[0]["selskap"])

    # --- DEA-grunnlag og grunnlinje per nettnivå ---------------------------
    results_dir = Path(rc.cfg.base_dir) / "Results"
    dea: dict[str, dict] = {}
    for nivaa, cfg in DEA_NIVAA.items():
        try:
            df, n_y = load_dea_inputs(results_dir, cfg["fil"])
        except FileNotFoundError:
            continue
        base_eff, _, _ = _dea_kjoring(df, n_y)
        res = getattr(rc.data, cfg["res"]).set_index("id")
        # Rammevilkårspåslag per selskap = trinn2 - trinn1 fra R-kjøringen
        paaslag = {int(i): float(res.loc[i, cfg["s2"]]) - float(res.loc[i, cfg["s1"]])
                   for i in res.index if i in base_eff}
        dea[nivaa] = {"df": df, "n_y": n_y, "base_eff": base_eff,
                      "paaslag": paaslag, "res": res, "cfg": cfg}

    begge_nivaa = {n: (id_a in d["base_eff"] and id_b in d["base_eff"])
                   for n, d in dea.items()}

    # Effektiviteten modellen faktisk bruker per selskap og nettnivå: DEA-resultat
    # der det finnes, ellers den manuelle overstyringen fra config.  Denne brukes
    # som nivåanker for den fusjonerte enheten — også på nettnivå der DEA ikke kan
    # kjøres på nytt fordi bare ett av selskapene er DEA-evaluert.
    eff_modell = {
        "D-nett": dict(zip(rc.data.id, rc.dea_ld.efficiency)),
        "R-nett": dict(zip(rc.data.id, rc.dea_rd.efficiency)),
    }

    # --- Hjelper: bygg selskapsrammen for ett år med fusjonert enhet -------
    def _ramme(aar: int, syn: float) -> pd.DataFrame:
        y = L[L["aar"] == aar].copy().reset_index(drop=True)
        a = y[y["orgn"] == int(orgn_a)].iloc[0]
        b = y[y["orgn"] == int(orgn_b)].iloc[0]
        andre = y[~y["orgn"].isin([int(orgn_a), int(orgn_b)])].copy()

        m = {"orgn": -1, "id": FUSJON_ID, "aar": aar,
             "selskap": f"{navn_a} + {navn_b}", "rho": rho}
        en_gangs = en_gangs_kostnad if aar == fusjonsaar else 0.0

        for niv, dv_k, kg_k in (("ld", "ld_dv", "ld_kg"), ("rd", "rd_dv", "rd_kg")):
            dv = (float(a[dv_k]) + float(b[dv_k])) * (1 - syn)
            # Resten av kostnadsgrunnlaget (avskrivning, nettap, KILE, kapital,
            # og for RD utredning) er ikke gjenstand for D&V-synergi.
            rest = ((float(a[kg_k]) - float(a[dv_k]))
                    + (float(b[kg_k]) - float(b[dv_k])))
            if niv == "rd" and synergi_paa_utredning:
                rest -= (float(a["utred"]) + float(b["utred"])) * syn
            m[dv_k] = dv
            m[kg_k] = dv + rest + (en_gangs if niv == "ld" else 0.0)

        for k in ("ld_nettap", "rd_nettap", "avs", "kile", "akg", "bfv",
                  "ld_akg", "rd_akg", "ld_rab17b", "rd_rab17b", "kundetillegg",
                  "ld_nl", "rd_nl", "utred"):
            m[k] = float(a[k]) + float(b[k])
        m["utred"] = m["utred"] * (1 - (syn if synergi_paa_utredning else 0.0))
        m["dv"] = m["ld_dv"] + m["rd_dv"] + en_gangs
        # kg = ld_kg + rd_kg + rd_nettap  (RD-grunnlaget er ekskl. nettap)
        m["kg"] = m["ld_kg"] + m["rd_kg"] + m["rd_nettap"]
        m["kraftpris"] = float(a["kraftpris"])
        m["rd_kg_inkl_nettap"] = m["rd_kg"] + m["rd_nettap"]

        return pd.concat([andre, pd.DataFrame([m])], ignore_index=True)

    # --- Hjelper: kalibrer ett år og hent ut den fusjonerte enhetens tall --
    def _kalibrer(ramme: pd.DataFrame, eff_extra: dict[str, dict]) -> dict:
        ids = ramme["id"]
        norm = {}
        for nivaa, kolonner in (("D-nett", ("ld_kg", "ld_rab17b")),
                                ("R-nett", ("rd_kg", "rd_rab17b"))):
            cfg = DEA_NIVAA[nivaa]
            d = DEANorm(
                ids=ids, eff_col=cfg["eff_col"],
                results_df=getattr(rc.data, cfg["res"]),
                kostnadsgrunn=ramme[kolonner[0]], rab17b=ramme[kolonner[1]],
                overrides=getattr(rc.cfg, cfg["overrides"]),
                eff_extra=eff_extra.get(nivaa),
            )
            norm[nivaa] = d.kalibrert
        k_ld = norm["D-nett"].fillna(0)
        k_rd = (norm["R-nett"] + ramme["rd_nettap"]).fillna(0)
        kg = ramme["kg"].fillna(0)
        akg = ramme["akg"]
        ir_foer = (1 - rho) * kg + rho * (k_ld + k_rd)
        n100 = (float(np.nansum(ir_foer)) - float(np.nansum(kg))) / float(np.nansum(akg))
        k_etter = k_ld + k_rd - akg * (n100 + n93) / rho + ramme["kundetillegg"]
        ir_etter = (1 - rho) * kg + rho * k_etter

        i = int(np.where(ramme["id"].values == FUSJON_ID)[0][0])
        ikke_kap = (float(ramme.loc[i, "dv"]) + float(ramme.loc[i, "avs"])
                    + float(ramme.loc[i, "ld_nettap"]) + float(ramme.loc[i, "rd_nettap"])
                    + float(ramme.loc[i, "kile"]))
        akg_i = float(akg.iloc[i])
        kg_i = float(kg.iloc[i])
        return {
            "ir_mnok": float(ir_etter.iloc[i]) / 1000,
            "avk_pct": ((float(ir_etter.iloc[i]) - ikke_kap) / akg_i * 100) if akg_i else 0.0,
            "vektet_pct": ((float(k_ld.iloc[i]) + float(k_rd.iloc[i])) / kg_i * 100)
                          if kg_i else 0.0,
            "kg_mnok": kg_i / 1000,
            "n100_pct": n100 * 100,
        }

    # --- Grunnlinje: selskapene hver for seg ------------------------------
    def _standalone(rader: pd.DataFrame) -> dict:
        r = rader.set_index("aar")
        ut = {"vektet": [], "ir_mnok": [], "avk_pct": []}
        for y in aar_alle:
            row = r.loc[y]
            ikke_kap = (float(row["dv"]) + float(row["avs"]) + float(row["ld_nettap"])
                        + float(row["rd_nettap"]) + float(row["kile"]))
            akg = float(row["akg"])
            ut["vektet"].append(float(row["eff_w_pct"]))
            ut["ir_mnok"].append(float(row["ir_etter"]) / 1000)
            ut["avk_pct"].append(((float(row["ir_etter"]) - ikke_kap) / akg * 100)
                                 if akg else 0.0)
        return ut

    base_a, base_b = _standalone(rad_a), _standalone(rad_b)

    # --- Scenarier ---------------------------------------------------------
    scenarier = []
    front_per_scenario: dict[str, dict] = {}
    for si, s_pct in enumerate(synergier):
        s_frac = float(s_pct) / 100.0
        farge, strek = LINJE_FUSJON[si % len(LINJE_FUSJON)]
        serie = {"vektet": [], "ir_mnok": [], "avk_pct": []}
        front_aar: dict[str, list] = {n: [] for n in DEA_NIVAA}

        for y in aar_alle:
            if y < fusjonsaar:
                serie["vektet"].append(None)
                serie["ir_mnok"].append(None)
                serie["avk_pct"].append(None)
                for n in DEA_NIVAA:
                    front_aar[n].append(None)
                continue

            syn = synergi_faktor(y, fusjonsaar, s_frac, innfasing_aar)
            ramme = _ramme(y, syn)
            eff_extra: dict[str, dict] = {}

            for nivaa in DEA_NIVAA:
                cfg = DEA_NIVAA[nivaa]
                d = dea.get(nivaa)
                i_m0 = int(np.where(ramme["id"].values == FUSJON_ID)[0][0])

                # Nivåanker: kostnadsvektet snitt av de to selskapenes faktiske
                # effektivitet, vektet med deres kostnadsgrunnlag på nettnivået.
                # Et selskap uten aktivitet på nivået får vekt 0 automatisk.
                a_row = rad_a[rad_a["aar"] == y].iloc[0]
                b_row = rad_b[rad_b["aar"] == y].iloc[0]
                kg_a_n, kg_b_n = float(a_row[cfg["kg"]]), float(b_row[cfg["kg"]])
                e_a, e_b = eff_modell[nivaa].get(id_a), eff_modell[nivaa].get(id_b)
                vekt = 0.0
                anker = 0.0
                for e_x, kg_x in ((e_a, kg_a_n), (e_b, kg_b_n)):
                    if e_x is not None and not pd.isna(e_x) and kg_x > 0:
                        anker += float(e_x) * kg_x
                        vekt += kg_x
                anker = anker / vekt if vekt > 0 else np.nan

                if d is None or not begge_nivaa.get(nivaa):
                    # DEA kan ikke kjøres på nytt her (bare ett av selskapene er
                    # DEA-evaluert).  Enheten beholder ankernivået, så nettnivået
                    # får ingen skala- eller sammensetningseffekt av fusjonen.
                    if not np.isnan(anker):
                        eff_extra[nivaa] = {FUSJON_ID: float(anker)}
                    front_aar[nivaa].append(None)
                    continue
                # D&V-andelen av nivåets kostnadsgrunnlag bestemmer hvor mye av
                # DEA-kostnaden synergien kan treffe.
                i_m = int(np.where(ramme["id"].values == FUSJON_ID)[0][0])
                kg_m = float(ramme.loc[i_m, cfg["kg"]])
                dv_m = float(ramme.loc[i_m, cfg["dv"]])
                dv_andel = (dv_m / kg_m) if kg_m > 0 else 0.0
                kostred = syn * dv_andel

                eff_ny, peers, _ = _dea_kjoring(
                    d["df"], d["n_y"], id_a, id_b, kostred,
                    ny_enhet_i_front=ny_enhet_i_front)
                if not eff_ny:
                    front_aar[nivaa].append(None)
                    continue

                # Eksisterende selskaper: legg endringen i trinn 1 oppå
                # R-verdien for trinn 2, slik at «ingen endring» gir grunnlinjen.
                extra = {}
                for cid, e_ny in eff_ny.items():
                    if cid == FUSJON_ID:
                        continue
                    e_base = d["base_eff"].get(cid)
                    if e_base is None or cid not in d["res"].index:
                        continue
                    extra[cid] = float(d["res"].loc[cid, cfg["s2"]]) + (e_ny - e_base)
                # Ny enhet: LP-skalaen er ikke nødvendigvis den samme som den
                # R-rapporterte (for regionalnett rapporterer R en korrigert verdi
                # som kan overstige 1, og som ikke er en rå CRS-score).  Vi bruker
                # derfor LP-en bare til *endringen* fusjonen gir, og legger den på
                # det kostnadsvektede snittet av de to selskapenes faktiske
                # effektivitet.  For lokalnett, der LP treffer R eksakt, er
                # korreksjonen tilnærmet null.
                x_a = float(d["df"].loc[d["df"]["id"] == id_a, "X_cb"].iloc[0])
                x_b = float(d["df"].loc[d["df"]["id"] == id_b, "X_cb"].iloc[0])
                w = (x_a + x_b) or 1.0
                lp_ref = (d["base_eff"][id_a] * x_a + d["base_eff"][id_b] * x_b) / w
                extra[FUSJON_ID] = float(anker) + (eff_ny[FUSJON_ID] - lp_ref)
                eff_extra[nivaa] = extra

                navn = {int(r["id"]): str(r["comp"])
                        for _, r in getattr(rc.data, cfg["res"]).iterrows()}
                ramp = NIVAA_RAMPER[nivaa]
                front_aar[nivaa].append([
                    {"navn": (f"{navn_a} + {navn_b}" if pid == FUSJON_ID
                              else navn.get(pid, str(pid))),
                     "andel_pct": v, "egen_front": pid == FUSJON_ID,
                     "farge": ramp[-(1 + (j % (len(ramp) - 1)))]}
                    for j, (pid, v) in enumerate(peers)
                ])

            res = _kalibrer(ramme, eff_extra)
            serie["vektet"].append(res["vektet_pct"])
            serie["ir_mnok"].append(res["ir_mnok"])
            serie["avk_pct"].append(res["avk_pct"])

        scenarier.append({
            "synergi_pct": float(s_pct), "navn": f"{navn_a} + {navn_b} ({s_pct:.0f} % synergi)",
            "farge": farge, "strek": strek, **serie,
        })
        front_per_scenario[f"{s_pct:.0f}"] = front_aar

    # --- Nøkkeltall i valgt år --------------------------------------------
    n_aar = int(noekkeltall_aar or fusjonsaar)
    if n_aar not in aar_alle:
        n_aar = fusjonsaar
    idx = aar_alle.index(n_aar)
    noekkeltall = {
        "aar": n_aar,
        "a": {"navn": navn_a, "ir_mnok": base_a["ir_mnok"][idx],
              "avk_pct": base_a["avk_pct"][idx]},
        "b": {"navn": navn_b, "ir_mnok": base_b["ir_mnok"][idx],
              "avk_pct": base_b["avk_pct"][idx]},
        "fusjonert": [{
            "synergi_pct": s["synergi_pct"],
            "ir_mnok": s["ir_mnok"][idx],
            "avk_pct": s["avk_pct"][idx],
        } for s in scenarier],
        "tint": {"ir": "#eef5fd", "avkastning": "#eef6f1"},
    }

    # --- Merknader ---------------------------------------------------------
    merknader = [
        "Effektiviteten til den fusjonerte enheten er beregnet ved å kjøre "
        "trinn-1 DEA på nytt: kostnader og oppgavemengde summeres, de to "
        "selskapene fjernes fra referansesettet, og en ny enhet settes inn.",
        "LP-replikasjonen treffer R-kjøringen eksakt for lokalnett, men ikke for "
        "regionalnett, der R rapporterer en korrigert effektivitet som kan "
        "overstige 1. DEA brukes derfor bare til *endringen* fusjonen gir, lagt "
        "oppå det kostnadsvektede snittet av de to selskapenes faktiske "
        "effektivitet. Nivået er dermed forankret i modellen, og DEA bidrar med "
        "skala- og sammensetningseffekten.",
        f"Synergien fases inn lineært over {innfasing_aar} år fra {fusjonsaar} og "
        "treffer D&V-kostnadene"
        + (" og utredningskostnadene." if synergi_paa_utredning else "."),
        "Oppkalibreringen er beregnet på nytt for hvert år med den fusjonerte "
        "enheten i stedet for de to, så hele bransjens norm er konsistent.",
    ]
    for nivaa, ok in begge_nivaa.items():
        if not ok:
            merknader.append(
                f"Bare ett av selskapene er evaluert på {nivaa} — DEA er ikke "
                f"kjørt på nytt for det nettnivået, og effektiviteten der følger "
                "grunnlinjen."
            )
    if en_gangs_kostnad:
        merknader.append(
            f"Omstillingskostnad på {en_gangs_kostnad:,.0f} tusen kroner er lagt "
            f"til D&V i {fusjonsaar}.".replace(",", " ")
        )
    if not ny_enhet_i_front:
        merknader.append("Den nye enheten er holdt utenfor referansesettet og kan "
                         "dermed ikke bli frontselskap for andre.")

    return {
        "selskap_a": navn_a, "selskap_b": navn_b,
        "orgn_a": int(orgn_a), "orgn_b": int(orgn_b),
        "fusjonsaar": fusjonsaar, "aar": aar_alle,
        "innfasing_aar": innfasing_aar,
        "effektivitet": {
            "linjer": [
                {"navn": navn_a, "farge": LINJE_A[0], "strek": LINJE_A[1],
                 "verdier": base_a["vektet"]},
                {"navn": navn_b, "farge": LINJE_B[0], "strek": LINJE_B[1],
                 "verdier": base_b["vektet"]},
            ] + [{"navn": s["navn"], "farge": s["farge"], "strek": s["strek"],
                  "verdier": s["vektet"]} for s in scenarier],
        },
        "noekkeltall": noekkeltall,
        # Samme tall som ``noekkeltall``, men for hvert år i perioden.  Alt er
        # allerede beregnet per år over, så å sende hele serien lar klienten
        # bytte år uten å kjøre DEA på nytt — ett årsbytte ville ellers kostet
        # en full ny kjøring per synerginivå.
        "noekkeltall_serier": {
            "aar": aar_alle,
            "a": {"navn": navn_a, "ir_mnok": base_a["ir_mnok"],
                  "avk_pct": base_a["avk_pct"]},
            "b": {"navn": navn_b, "ir_mnok": base_b["ir_mnok"],
                  "avk_pct": base_b["avk_pct"]},
            "fusjonert": [{"synergi_pct": s["synergi_pct"],
                           "ir_mnok": s["ir_mnok"], "avk_pct": s["avk_pct"]}
                          for s in scenarier],
        },
        "front": front_per_scenario,
        "merknader": merknader,
    }
