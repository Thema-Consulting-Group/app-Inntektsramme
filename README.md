# Inntektsramme – Brukerveiledning

## Docker Desktop

Last ned og installer **Docker Desktop**:

https://www.docker.com/products/docker-desktop/

Godta standardinnstillingene under installasjon. Start Docker Desktop og vent til ikonet i systemstatusfeltet viser «Docker Desktop is running».

---

## Starte appen

### Windows
Dobbeltklikk på **`start.bat`** i prosjektmappen.

### Mac / Linux
Åpne Terminal, naviger til prosjektmappen og kjør:
```
./start.sh
```

Første gang tar det 10–20 minutter å laste ned og bygge tilhørende pakker.

Når containeren er klar, åpne:

**http://localhost:8000**

---

## Bruke appen

Appen er delt i tre steg – naviger med knappene øverst.

### Steg 1 – RME Modell
Klikk **Kjør RME Modell** for å kjøre modellen. Resultater lagres automatisk i `Results/`.
Når kjøringen er ferdig kan du laste ned tabellen som CSV eller Excel.

#### Flerårsark
Under resultattabellen ligger panelet **Flerårsark**, som framskriver inntektsrammearket
for alle selskaper og gir **ett ark per år**. Klikk **Bygg flerårsark**, og last ned med
**⬇ Excel** (ett regneark med `Sammendrag` + ett ark per år).

Basisåret (2026) er hentet direkte fra RME-modellen og er identisk med tabellen over.
Årene etter framskrives med samme forutsetninger som Steg 2 (KPI, KPI lønn, NVE-rente,
kraftpris, investeringer).

Tre forutsetninger kan styres:

| Valg | Betydning |
|---|---|
| **Til år** | Siste prognoseår (2026–2035). |
| **BFV-nivå** | Bokførte verdier i grunnlagsdata ligger over arkets avkastningsgrunnlag (~27 % på lokalt nett, ~8 % på regionalt). Uten justering får kapitalbasen et sprang på ett år mellom basisåret og året etter. Standard *Skaler BFV + investeringer* beholder observert investeringstakt; *Skaler bare BFV* gir høyere vekst på en mindre base; *Ingen justering* er prognosens uendrede oppførsel. |
| **Rekalibrer hvert år** | Fordeler tillegg i norm på nytt og beregner kalibreringskonstanten N100 av det framskrevne bransjeaggregatet for hvert år, slik at hvert årsark er internt konsistent. Slås av for å beholde basisårets konstanter fra `config.yaml`. |

Renteavviket N93 kan ikke utledes av prognosen (det er avviket mellom referanserente og
faktiske rentekostnader) og holdes derfor konstant på verdien i `config.yaml`.

### Steg 2 – Prognosebygger
Velg selskap, juster forutsetninger og se prognosen.
Lagre endringer med **Lagre forutsetninger**.

### Analyse
Panelet gjenskaper KPI-oppsettet fra inntektsrammeanalysen (jf. *Inntektsrammeanalyse
2025*, s. 9) for **ett selskap og ett år**:

| Element | Kilde |
|---|---|
| **Inntektsramme etter bransjeoverheng** | Inntektsramme etter kalibrering, i MNOK, med endring fra året før |
| **Avkastning på nettkapital** | Inntektsramme minus ikke-kapitalkostnader, i prosent av AKG og i MNOK |
| **Effektivitet per trinn** | Trinn 1 = DEA (`eff.s1.cb`), trinn 2 = rammevilkår (`eff.s2.cb`), trinn 3 = oppkalibrering, samt vektet trinn 3 |
| **Frontselskap per nettnivå** | Referansevektene `ld_ncs_*` / `rd_ncs_*` fra DEA-kjøringen |

Velg selskap og år øverst. Årsspennet er det samme som i flerårsarket.

Tre forhold er verdt å merke seg, og panelet viser dem som merknader:

* **Trinn 2 utgår for R-nett.** Regionalnettet har ingen rammevilkårskorreksjon –
  `rd_eff.s1.cb` og `rd_eff.s2.cb` er identiske for alle selskaper – så raden vises
  ikke. Dette avgjøres per kjøring, ikke hardkodet.
* **Trinn 1 og 2 og frontselskapene er basisårsresultater.** Prognosen holder
  DEA-effektiviteten fast, så i prognoseår er det bare trinn 3 (oppkalibreringen)
  som beveger seg.
* **Basisåret har ingen endringstall.** Året før basisåret er tilbakeskrevet ved å
  deflatere basisåret, så en endring mot det ville bare gjentatt
  vekstforutsetningene. Endringstall vises derfor fra 2027.

Selskaper med manuelt overstyrt DEA-resultat (alternativ benchmarkingmodell eller
«evalueres ikke») og selskaper utenfor DEA-utvalget merkes eksplisitt.

#### Tidsserie
Knappen **Tidsserie** øverst i panelet bytter fra ett år til utviklingen over hele
prognoseperioden, med fire elementer:

| Element | Innhold |
|---|---|
| **Effektivitet per nettnivå og vektet** | Kalibrert vektet effektivitet, distribusjonsnett og regionalnett, mot bransjesnittet (vektet) |
| **Inntektsramme, avkastning og investeringsnivå** | Nivå i første og siste år, CAGR for inntektsrammen, og gjennomsnittlige årlige investeringer i MNOK og i prosent av nettkapitalen |
| **Frontselskap per nettnivå** | Andel av front per år, stablet per nettnivå |
| **Kostnadsutvikling og -sammensetning** | Sammensetningen i første år (kapitalkostnad, avskrivninger, nettap, KILE, D&V, RKSU) og endringen i perioden per komponent |

Investeringene er ikke rapportert direkte av prognosen, men utledet av kapitalbasen:
`I(t) = BFV(t) − BFV(t−1) + AVS(t)`. Vinduet starter derfor ett år etter basisåret.

Frontselskapenes andeler er **konstante** over perioden. DEA kjøres bare for
basisåret, og prognosen holder effektiviteten fast, så søylene viser
sammensetningen av fronten – ikke en utvikling i den. Panelet sier dette eksplisitt.

Fargebruken følger resten av panelet: blått for D-nett, grønt for R-nett, gult for
vektet, og en nøytral laksefarget referanselinje for bransjesnittet.
Kostnadskomponentene er derimot *kategorier*, ikke nettnivåer, og bruker en egen
validert kategorisk palett – seks skillbare kategorier får ikke plass innenfor
blå/grønn/gul.

#### Fusjon
Knappen **Fusjon** analyserer hva som skjer dersom det valgte selskapet slås
sammen med et annet. Effektiviteten til den sammenslåtte enheten er ikke et snitt
av de to – DEA måler kostnad mot oppgavemengde, og en fusjon endrer begge – så
**trinn-1 DEA kjøres på nytt**: kostnader og oppgaver summeres, de to selskapene
fjernes fra referansesettet, og en ny enhet settes inn. Oppkalibreringen beregnes
også om for hele bransjen med den nye enheten i stedet for de to.

Forutsetninger som kan settes:

| Parameter | Betydning |
|---|---|
| **Fusjonerer med** | Motparten i fusjonen |
| **Fusjonsår** | Året fusjonen får virkning |
| **Synergi (%)** | Varig reduksjon i D&V-kostnader. Flere nivåer skilles med komma (`15,33`) og vises som egne linjer |
| **Innfasing (år)** | Antall år synergien fases inn lineært over |
| **Engangskostnad** | Omstillingskostnad i fusjonsåret (1000 kr) |
| **Synergi også på utredningskostnader** | Om synergien treffer RKSU i tillegg til D&V |
| **Ny enhet kan bli frontselskap** | Om den sammenslåtte enheten er med i referansesettet |

Presisjonsnivå, verdt å kjenne:

* LP-replikasjonen av DEA treffer R-kjøringen **eksakt for lokalnett** (avvik
  0,0000 over 71 selskaper). For **regionalnett treffer den ikke** – R rapporterer
  der en korrigert effektivitet som kan overstige 1 og ikke er en rå CRS-score.
  DEA brukes derfor bare til *endringen* fusjonen gir, lagt oppå det
  kostnadsvektede snittet av de to selskapenes faktiske effektivitet.
* Er bare ett av selskapene DEA-evaluert på et nettnivå (typisk fordi det andre
  har manuelt overstyrt resultat), kjøres ikke DEA på nytt der. Enheten beholder
  ankernivået, og nettnivået får ingen skala- eller sammensetningseffekt. Panelet
  sier det eksplisitt.
* Beregningen kjører DEA per år og per synerginivå, og tar noen sekunder.

### Steg 3 – Kostnader
Filtrer og utforsk RME-rapporteringstabellen. Last ned med CSV/Excel-knappene.
---

## Stoppe appen

Lukk terminalvinduet (eller trykk `Ctrl+C`), eller kjør:
```
docker compose down
```

---