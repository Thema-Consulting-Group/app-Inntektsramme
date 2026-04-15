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

Når du ser teksten `You can now view your Streamlit app in your browser`, åpne:

**http://localhost:8501**

---

## Bruke appen

Appen er delt i tre steg – naviger med knappene øverst.

### Steg 1 – RME Modell
Klikk **Kjør RME Modell** for å kjøre modellen. Resultater lagres automatisk i `Results/`.
Når kjøringen er ferdig kan du laste ned tabellen som CSV eller Excel.

### Steg 2 – Prognosebygger
Velg selskap, juster forutsetninger og se prognosen.
Lagre endringer med **Lagre forutsetninger**.

### Steg 3 – Kostnader
Filtrer og utforsk RME-rapporteringstabellen. Last ned med CSV/Excel-knappene.
---

## Stoppe appen

Lukk terminalvinduet (eller trykk `Ctrl+C`), eller kjør:
```
docker compose down
```

---