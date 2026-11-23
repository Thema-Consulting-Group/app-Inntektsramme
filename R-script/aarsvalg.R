#### Aarsvalg – hvilket inntektsrammeaar som beregnes ####
# Samme regler som aarsvalg.py:
#   1. IR_AAR i miljoeet (API-et setter den naar det starter en kjoering)
#   2. Data/aktivt_aar.txt (aaret som er valgt i appen)
#   3. nyeste aarsmappe under Data/
# Aaret er inntektsrammeaaret (y.rc). Alt som skifter fra aar til aar ligger i
# Data/<aar>/, og resultatene skrives til Results/<aar>/.

.aar_mapper <- suppressWarnings(as.integer(grep("^[0-9]{4}$", list.files("./Data"), value = TRUE)))
.aar_mapper <- sort(.aar_mapper[file.exists(file.path("./Data", .aar_mapper, "config.yaml"))])
if (length(.aar_mapper) == 0) stop("Fant ingen aarsmapper (Data/<aar>/config.yaml).")

.aar_kilder <- c(
  Sys.getenv("IR_AAR"),
  if (file.exists("./Data/aktivt_aar.txt")) trimws(readLines("./Data/aktivt_aar.txt", n = 1, warn = FALSE)) else ""
)
ir_aar <- NA_integer_
for (.k in .aar_kilder) {
  if (is.na(ir_aar) && length(.k) == 1 && grepl("^[0-9]{4}$", .k) && as.integer(.k) %in% .aar_mapper) {
    ir_aar <- as.integer(.k)
  }
}
if (is.na(ir_aar)) ir_aar <- max(.aar_mapper)
rm(.aar_mapper, .aar_kilder, .k)

data_dir        <- file.path("./Data", ir_aar)
basedata_dir    <- file.path(data_dir, "BaseData")
aar_results_dir <- file.path("./Results", ir_aar)
dir.create(aar_results_dir, recursive = TRUE, showWarnings = FALSE)
cat("[diag] Inntektsrammeaar:", ir_aar, "\n")

# Inndatafil fra RME: overstyringen hvis en er lastet opp i appen, ellers den
# ene filen i BaseData som passer moensteret. Moensteret, og ikke filnavnet,
# staar her fordi RME setter uttaksdatoen inn i navnet paa irBase.
finn_inndata <- function(monster, overstyring) {
  ov <- file.path(basedata_dir, overstyring)
  if (file.exists(ov)) return(ov)
  treff <- setdiff(list.files(basedata_dir, pattern = monster), overstyring)
  treff <- treff[!grepl("\\.tmp\\.xlsx$", treff)]
  if (length(treff) != 1) {
    stop("Ventet noeyaktig en fil som passer '", monster, "' i ", basedata_dir,
         ", fant ", if (length(treff) == 0) "ingen" else paste(treff, collapse = ", "))
  }
  file.path(basedata_dir, treff)
}

# Fusjoner, selskapslister og andre valg RME har gjort for haand dette aaret.
source(file.path(data_dir, "aarsoppsett.R"))
