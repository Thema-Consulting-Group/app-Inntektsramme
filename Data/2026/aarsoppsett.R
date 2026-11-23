#### Aarsoppsett – inntektsrammer 2026 (varsel, datagrunnlag 2024) ####
# Det RME har satt for haand i 0_2 og 0_4 dette aaret. Skriptene i R-script/ er
# felles for alle aar og leser verdiene herfra.

# 0_2: Fusjoner der rammevilkaarsvariablene (ldz_*) slaas sammen.
# orgn = alle selskapene i fusjonen, new.org/new.id = det fusjonerte selskapet.
fusjoner <- list(
  Linja = list(orgn = c(912631532, 925315958),            new.org = 912631532, new.id = 269), # Linja AS + Tindra AS
  Area  = list(orgn = c(923993355, 924934867, 924868759), new.org = 923993355, new.id = 164), # Area + Luostejok Nett + Lega Nett
  Foie  = list(orgn = c(971589752, 923050612, 987626844), new.org = 971589752, new.id = 275)  # Hallingdal Kraftnett + Foie + Hemsil Nett
)

# 0_2: Omraadepris to aar foer (ap.t_2, kr/kWh) satt for haand, per id.
ap.t_2_manuelt <- c("269" = 0.3837, "275" = 0.54424)

# 0_4: Selskaper som legges til de automatiske listene.
ld_av.eff_manuelt <- c(753)  # D-nett satt til gjennomsnittlig effektivitet
rd_no.rc_manuelt  <- c(659)  # R-nett uten inntektsramme
rd_av.eff_manuelt <- c(135)  # R-nett satt til gjennomsnittlig effektivitet
