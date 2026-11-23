#### Aarsoppsett – inntektsrammer 2027 (varsel, datagrunnlag 2025) ####
# Det RME har satt for haand i 0_2 og 0_4 dette aaret. Skriptene i R-script/ er
# felles for alle aar og leser verdiene herfra.
# Kilde: RMEs IRiR-pakke for varsel 2027 (R-script/0_2 og 0_4, november 2026).

# 0_2: Fusjoner der rammevilkaarsvariablene (ldz_*) slaas sammen.
# orgn = alle selskapene i fusjonen, new.org/new.id = det fusjonerte selskapet.
fusjoner <- list(
  Glitre = list(orgn = c(982974011, 980234088), new.org = 982974011, new.id = 624), # Glitre + Norgesnett
  Elvia  = list(orgn = c(980489698, 968398083), new.org = 980489698, new.id = 675), # Elvia + Rakkestad Energi
  Vevig  = list(orgn = c(916319908, 920295975), new.org = 916319908, new.id = 295)  # Vevig + Skiakernett
)

# 0_2: Omraadepris to aar foer (ap.t_2, kr/kWh) satt for haand, per id —
# selskaper som har fusjonert med selskaper utenfor sitt prisomraade.
ap.t_2_manuelt <- c("624" = 0.748, "295" = 0.686)

# 0_4: Selskaper som legges til de automatiske listene.
ld_av.eff_manuelt <- c(753)  # D-nett satt til gjennomsnittlig effektivitet (Saudefaldene, mangler data)
rd_no.rc_manuelt  <- c()     # R-nett uten inntektsramme
rd_av.eff_manuelt <- c()     # R-nett satt til gjennomsnittlig effektivitet
