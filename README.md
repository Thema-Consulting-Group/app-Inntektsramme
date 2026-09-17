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

Appen har fire moduler i menyen til venstre: **Dagens RME modell**, **Prognose**,
**Frontselskapsanalyse** og **Oppgaveelastisiteter**. De to første er de som
brukes til daglig; de to siste er verktøy for enkeltanalyser.

### Dagens RME modell
Klikk **Start** for å kjøre modellen. Resultater lagres automatisk i `Results/`.
Når kjøringen er ferdig kan du laste ned tabellen som CSV.

Resultatsiden viser, i denne rekkefølgen:

1. **Nøkkeltall** for kjøringen – antall selskaper, sum kostnadsgrunnlag, sum
   inntektsramme etter kalibrering.
2. **Analyse for ett selskap og ett år** – inntektsramme, avkastning på
   nettkapital, effektivitet per trinn og frontselskap per nettnivå. Panelet er
   beskrevet under [Analysepanelet](#analysepanelet).
3. **Grunnlagsdata – nøkkelvariabler**, når den er åpnet (se under).
4. **Tabellen over alle selskaper**, sortert med største inntektsramme øverst.

Diagrammene står over tabellen med vilje: KPI-ene svarer på hvordan det gikk for
ett selskap, tabellen på hvordan bransjen ser ut, og det er den rekkefølgen
spørsmålene stilles i.

#### Rediger grunnlagsdata
Knappen **✎ Rediger grunnlagsdata** i venstrepanelet henter grunnlagsdata fra
base-data (kjører `generate_grunnlagsdata.R` hvis det ikke ligger noe inne
allerede) og åpner nøkkelvariablene på siden, over resultattabellen.

Panelet viser tre grupper – **Kostnader**, **Oppgaver** og **Områdepriser** – og
filtrerer på år og selskap. Det starter på siste år, som er kostnadsgrunnlagsåret.
Hver kolonne har det fulle variabelnavnet over R-forkortelsen, slik at
`ld_OPEXxS` også står som «LD OPEX ekskl. lønn (1000 kr)». Navnene ligger i
`variabelnavn.py` og serveres av `/api/variabelnavn`.

`orgn`, `y` og `comp` vises, men redigeres ikke: de er nøkkelen radene skrives
tilbake på.

**Lagre** skriver bare filen – klikk **Start** etterpå for å kjøre modellen med de
nye verdiene. Skal du endre noe som ikke er en nøkkelvariabel (rammevilkår,
totaler, DEA-utdata), bruk **⬇** ved siden av knappen: den laster ned hele filen
som CSV, med en ekstra rad rett under overskriftene som gir det fulle navnet på
hver variabel. Raden leses bort igjen ved opplasting, så filen kan lastes rett
tilbake i grunnlagsdata-feltet.

#### Kraftpris per prissone
Panelet **Kraftpris per prissone** setter områdeprisen for NO1–NO5 i NOK/MWh.
Prisen skrives til `pnl.rc` for alle selskapene i sonen, i
`Data/BaseData/kraftpris_override.xlsx`, og samtidig til
`forutsetninger.omradepriser` i `config.yaml` – valideringen av grunnlagsdata
måler mot det båndet, så en ny pris utenfor det gamle ville ellers blitt flagget
som umulig. **↺** fjerner begge deler igjen.

Sonetilhørigheten utledes én gang fra standard kraftprisfil (hvert selskap får
sonen hvis områdepris ligger nærmest selskapets pris) og lagres i
`kraftpris_soner_map.csv`. Den må lagres, ikke utledes på nytt: skrivingen endrer
jo nettopp prisene kartet ellers ville lett etter.

Selskaper som leverer i flere prisområder har en volumvektet pris som ikke kan
tilbakeføres til én sone. De står urørt når en sonepris endres, og panelet sier
hvor mange det gjelder.

#### Inndata for neste kjøring
Panelet **Inndata for neste kjøring** viser de tre Excel-filene modellen leser:
`irBase` (hoveddatasettet), `Kraftpris` og `Selskaps-ID`. Hver rad har tre knapper:

| Knapp | Gjør |
|---|---|
| **✎** | Åpner filen i appen, der du kan endre tall, legge til eller slette rader, og lagre. |
| **⬇** | Laster ned filen slik den er nå – standardfilen om ingen overstyring ligger inne, ellers din egen. |
| Klikk på raden | Laster opp en fil som erstatter standarden (kan også dras inn). |

Lasting ned og opp er samme fil: du trenger ikke vite hvordan den ser ut på forhånd,
last den ned, rediger i Excel og legg den tilbake i samme rad. En opplastet eller
lagret fil skrives som `*_override.xlsx` i `Data/BaseData/` og leses av
`R-script/0_1_Config_Assumptions_Data.R` foran standardfilen. **✕** fjerner
overstyringen og setter standardfilen tilbake i bruk.

Lagring skriver bare filen – klikk **Start** etterpå for å kjøre modellen med de nye
verdiene.

To ting er verdt å merke seg:

* **irBase kan ikke redigeres i appen** (440 rader × 64 kolonner). Den åpner med en
  forklaring og en nedlastingsknapp i stedet; grensen for redigering er 500 rader ×
  12 kolonner.
* **Å slette rader er ikke ufarlig.** Filene koples på selskapstabellen med en
  venstre-join på `orgn`, så et selskap som ikke står i filen får ingen verdi i
  kjøringen. Editoren varsler om antall rader går ned.

#### Fusjonere selskaper før kjøring
Panelet **Fusjoner selskaper** slår sammen selskaper i grunnlagsdata før modellen
kjører. Velg overtakende selskap, kryss av dem som skal fusjoneres inn, og klikk
**Fusjoner** — deretter **Start**.

Dette erstatter den gamle framgangsmåten (last ned grunnlagsdata, summer rader i
Excel, last opp igjen), som gikk galt på tre måter uten å gi feilmelding:

| Kolonnetype | Riktig behandling | Hva summering gjør |
|---|---|---|
| Kostnader, kapital, volum, oppgaver | Summeres | — |
| `ldz_*` (rammevilkår) | Vektes med kartruter (`ldz_mgc`) | Frosttimer tredobles, skogandeler over 1 |
| `pnl.rc`, `ap.t_2` (områdepriser) | Volumvektes med `ld_nl + rd_nl` | Nettapskostnaden blåses opp |

Prisfeilen er den alvorligste. Nettapskostnaden er `volum × pnl.rc`, så en summert
pris multipliseres med et summert volum. For Tensio TN + Tensio TS + Elvia blir
prisen 0,624 + 0,359 + 0,381 = 1,365 kr/kWh — over dobbelt så høyt som den dyreste
områdeprisen som finnes — og nettapskostnaden i LD og RD kommer ut ~1,5 mrd kr for
høyt. Riktig pris er det volumvektede snittet, 0,563, altså *lavere* enn Elvias
egen pris, siden NO3 er billigere enn NO1.

To ting til er verdt å kjenne:

* **Sammenslåingen gjelder alle år.** Pensjonsgrunnlaget og DEAs inn- og utdata er
  femårssnitt, så en fusjon som bare treffer kostnadsgrunnlagsåret gir en enhet som
  benchmarkes på en femtedel av sin egen størrelse.
* **Overtakende selskap beholder org.nr og navn**, og dermed også en eventuell
  manuell DEA-overstyring i `config.yaml` og kundetillegget sitt.

De innfusjonerte selskapene fjernes helt — fra referansesettet i DEA og fra
kalibreringen. Å slette radene deres i CSV-en gjør *ikke* dette: overstyringssteget
matcher på `(orgn, år)` og endrer bare verdier i rader det finner, så et selskap som
mangler i opplastingen står urørt i modellen. Panelet skriver i stedet kolonnen
`_slett` (1 = fjern selskapet), som `IRiR.R` filtrerer på. Kolonnen kan også settes
for hånd i en redigert CSV.

Laster du opp grunnlagsdata selv, sjekkes filen ved opplasting: områdepriser må ligge
innenfor `forutsetninger.omradepriser`, rammevilkårsvariabler innenfor bransjens
intervall, og selskaper som er endret i bare noen av årene blir flagget.

### Prognose
Velg selskap i venstrepanelet og bytt mellom tre visninger:

| Visning | Innhold |
|---|---|
| **Prognose** | Framskrivningen for det valgte selskapet: nøkkeltall, diagram for inntektsramme / kostnadsgrunnlag / kostnadsnorm, diagram for effektivitet og avkastning, og nederst hele tabellen med variabler på radene og år på kolonnene |
| **Flerår** | Utviklingen over hele prognoseperioden – se [Flerår](#flerår) |
| **Fusjon** | Hva som skjer om selskapet slås sammen med et annet – se [Fusjon](#fusjon) |

Alle tre regner på selskapet som står i velgeren, så et bytte der nullstiller alle
tre. Forutsetningene (KPI, KPI lønn, NVE-rente, systemkraftpris) ligger i en
utslåbar tabell nederst og kan redigeres per år.

De to siste visningene lå tidligere i en egen Analyse-modul. De hører hjemme her:
begge framskriver over prognoseperioden.

Feltet **Enkel fusjonsjustering** i venstrepanelet er noe annet enn Fusjon-visningen
— det er et påslag på kostnadene inne i selve framskrivningen, ikke en ny
DEA-kjøring. Bruk Fusjon-visningen når du vil ha effektivitetseffekten med.

<h3 id="analysepanelet">Analysepanelet</h3>

Panelet ligger på resultatsiden i **Dagens RME modell** og gjenskaper KPI-oppsettet
fra inntektsrammeanalysen (jf. *Inntektsrammeanalyse 2025*, s. 9) for **ett selskap
og ett år**:

| Element | Kilde |
|---|---|
| **Inntektsramme etter bransjeoverheng** | Inntektsramme etter kalibrering, i MNOK, med endring fra året før |
| **Avkastning på nettkapital** | Inntektsramme minus ikke-kapitalkostnader, i prosent av AKG og i MNOK |
| **Effektivitet per trinn** | Trinn 1 = DEA (`eff.s1.cb`), trinn 2 = rammevilkår (`eff.s2.cb`), trinn 3 = oppkalibrering, samt vektet trinn 3 |
| **Frontselskap per nettnivå** | Referansevektene `ld_ncs_*` / `rd_ncs_*` fra DEA-kjøringen |

Velg selskap og år øverst. Årsspennet følger prognosens framskrivning.

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

<h3 id="flerår">Flerår</h3>

Visningen **Flerår** i Prognose-modulen viser utviklingen over hele
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

<h3 id="fusjon">Fusjon</h3>

Visningen **Fusjon** i Prognose-modulen analyserer hva som skjer dersom det valgte
selskapet slås sammen med et annet. Effektiviteten til den sammenslåtte enheten er ikke et snitt
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

### Frontselskapsanalyse og Oppgaveelastisiteter
To frittstående verktøy: DEA-fronten med og uten valgte selskaper, og
oppgaveelastisitetene (Δoppgave per MNOK) som prognosen kan bruke i stedet for
sine egne. Begge står som de er.

---

## Stoppe appen

Lukk terminalvinduet (eller trykk `Ctrl+C`), eller kjør:
```
docker compose down
```

---