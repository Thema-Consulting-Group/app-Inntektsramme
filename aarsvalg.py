"""Hvilket inntektsrammeår modellen regner på, og hvor årets filer ligger.

Alt som skifter fra ett år til det neste ligger i én mappe per år:

    Data/<år>/config.yaml        forutsetninger, kalibrering, DEA-overstyringer
    Data/<år>/aarsoppsett.R      fusjoner og selskapslister RME har satt for året
    Data/<år>/*.Rdata            RMEs forutsetninger, geo-variabler, kostnader t-2
    Data/<år>/kundetillegg.csv   tillegg i kostnadsnorm for kundevekst
    Data/<år>/BaseData/          irBase, kraftpris og id-liste fra RME
    Results/<år>/                kjøringer og DEA-referansesettet for året

Året er inntektsrammeåret (y.rc), ikke datagrunnlagsåret (y.cb = år − 2).

Aktivt år velges i appen og lagres i ``Data/aktivt_aar.txt``.  ``IR_AAR`` i
miljøet overstyrer filen — det er slik API-et låser R-kjøringen til året den
ble startet for, selv om noen bytter år i appen mens den går.  R-siden
(``IRiR.R``) leser året på samme måte, så skriptet kan også kjøres for seg.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "Data"
RESULTS = ROOT / "Results"
_AKTIVT_AAR_FIL = DATA / "aktivt_aar.txt"


def tilgjengelige_aar() -> list[int]:
    """År som har en datamappe med config.yaml, eldste først."""
    if not DATA.is_dir():
        return []
    return sorted(
        int(p.name) for p in DATA.iterdir()
        if p.is_dir() and p.name.isdigit() and (p / "config.yaml").exists()
    )


def aktivt_aar() -> int:
    aar = tilgjengelige_aar()
    if not aar:
        raise FileNotFoundError(
            "Fant ingen årsmapper (Data/<år>/config.yaml). Se aarsvalg.py."
        )
    for kilde in (os.environ.get("IR_AAR", ""), _les_aktivt_aar_fil()):
        kilde = kilde.strip()
        if kilde.isdigit() and int(kilde) in aar:
            return int(kilde)
    return aar[-1]


def sett_aktivt_aar(aar: int) -> int:
    if aar not in tilgjengelige_aar():
        raise ValueError(f"{aar} er ikke et tilgjengelig år ({tilgjengelige_aar()}).")
    _AKTIVT_AAR_FIL.write_text(f"{aar}\n", encoding="utf-8")
    return aar


def _les_aktivt_aar_fil() -> str:
    try:
        return _AKTIVT_AAR_FIL.read_text(encoding="utf-8")
    except OSError:
        return ""


def data_dir(aar: int | None = None) -> Path:
    return DATA / str(aar or aktivt_aar())


def basedata_dir(aar: int | None = None) -> Path:
    return data_dir(aar) / "BaseData"


def config_path(aar: int | None = None) -> Path:
    return data_dir(aar) / "config.yaml"


def results_dir(aar: int | None = None) -> Path:
    return RESULTS / str(aar or aktivt_aar())


# Standardfilene i BaseData finnes ved navnemønster i stedet for å stå oppført
# her og i R: RME setter uttaksdatoen inn i navnet på irBase, så et nytt uttrekk
# kan legges inn uten å endre kode.  R-siden (0_1_Config_Assumptions_Data.R)
# bruker de samme mønstrene.
INNDATA_MONSTER: dict[str, tuple[str, str]] = {
    # nøkkel: (glob for standardfilen, navn på overstyringsfilen)
    "irbase":    ("irBase*.xlsx",    "irBase_override.xlsx"),
    "kraftpris": ("kraftpris*.xlsx", "kraftpris_override.xlsx"),
    "id":        ("id_ir_*.xlsx",    "id_override.xlsx"),
}


def standardfil(nokkel: str, aar: int | None = None) -> Path:
    """Den ene filen RME leverte for nøkkelen, uten overstyringer."""
    monster, overstyring = INNDATA_MONSTER[nokkel]
    mappe = basedata_dir(aar)
    treff = sorted(
        p for p in mappe.glob(monster)
        if p.name != overstyring and not p.name.endswith(".tmp.xlsx")
    )
    if len(treff) != 1:
        hva = "ingen" if not treff else ", ".join(p.name for p in treff)
        raise FileNotFoundError(
            f"Ventet nøyaktig én fil som passer «{monster}» i {mappe.relative_to(ROOT)}, fant {hva}."
        )
    return treff[0]


def overstyringsfil(nokkel: str, aar: int | None = None) -> Path:
    return basedata_dir(aar) / INNDATA_MONSTER[nokkel][1]


# ---------------------------------------------------------------------------
# Flytting av oppsettet fra før årsmappene fantes
# ---------------------------------------------------------------------------

# Før årsvalget lå 2026-filene rett under Data/ og Results/.  Det som er sporet
# i git ble flyttet med git mv; dette tar resten — lokale kjøringer og
# opplastinger som bare finnes på maskinen (eller i Docker-volumet).
_ELDSTE_AAR = 2026
_ELDRE_DATAFILER = (
    "grunnlagsdata_uploaded.csv",
    "grunnlagsdata_generert.csv",
    "BaseData/irBase_override.xlsx",
    "BaseData/kraftpris_override.xlsx",
    "BaseData/id_override.xlsx",
    "BaseData/kraftpris_soner_map.csv",
    "Bootstrap/ld_bs.csv",
)


def flytt_eldre_oppsett() -> list[str]:
    """Flytt filer fra før årsmappene inn under 2026.  Trygt å kalle flere ganger."""
    flyttet: list[str] = []
    maal_data = DATA / str(_ELDSTE_AAR)
    if not maal_data.is_dir():
        return flyttet

    for rel in _ELDRE_DATAFILER:
        kilde, maal = DATA / rel, maal_data / rel
        if kilde.is_file() and not maal.exists():
            maal.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(kilde), str(maal))
            flyttet.append(f"Data/{rel}")

    if RESULTS.is_dir():
        maal_res = RESULTS / str(_ELDSTE_AAR)
        for p in list(RESULTS.iterdir()):
            if p.name.isdigit() or p.name.startswith("."):
                continue
            maal = maal_res / p.name
            if maal.exists():
                continue
            maal_res.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(maal))
            flyttet.append(f"Results/{p.name}")
    return flyttet
