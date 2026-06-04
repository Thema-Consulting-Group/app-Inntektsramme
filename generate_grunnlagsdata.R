#### Generate grunnlagsdata CSV (data loading only — no DEA/calculations) ####
# Used by the API endpoint /api/generate-grunnlagsdata so users can download,
# edit, and re-upload grunnlagsdata before running the full RME pipeline.

  options(scipen = 2000, warn = 1)
  message <- function(...) cat("[msg]", ..., "\n", sep="")

  options(
    repos = c(CRAN = "https://packagemanager.posit.co/cran/__linux__/noble/latest"),
    HTTPUserAgent = sprintf("R/%s R (%s)", getRversion(),
      paste(getRversion(), R.version[["platform"]], R.version[["arch"]], R.version[["os"]]))
  )

  .ensure <- function(pkg) {
    if (!requireNamespace(pkg, quietly = TRUE)) install.packages(pkg)
  }
  .ensure("tidyverse"); .ensure("dplyr"); .ensure("openxlsx")
  .ensure("writexl");   .ensure("readxl"); .ensure("plyr")

  suppressPackageStartupMessages({
    library(tidyverse); library(dplyr); library(openxlsx)
    library(writexl);   library(readxl); library(plyr)
  })

  setwd(getwd())

  source("./R-script/functions_nve.R")
  source("./R-script/0_1_Config_Assumptions_Data.R")
  source("./R-script/0_2_Merging_Z-variables.R")

  write.dat = dat[,c("orgn", "y", "comp",
    "ld_OPEXxS", "ld_sal", "ld_sal.cap", "ld_pens", "ld_pens.eq", "ld_impl", "ld_391", "ld_elhub", "ld_usla",
    "rd_OPEXxS", "rd_sal", "rd_sal.cap", "rd_pens", "rd_pens.eq", "rd_impl", "rd_391", "rd_elhub",
    "rd_cga", "rd_cga_tidl", "rd_coord", "rd_usla",
    "t_OPEXxS", "t_sal", "t_sal.cap", "t_pens", "t_pens.eq", "t_impl", "t_391", "t_elhub",
    "ld_bv.sf", "ld_dep.sf", "ld_bv.gf", "ld_dep.gf",
    "rd_bv.sf", "rd_dep.sf", "rd_bv.gf", "rd_dep.gf",
    "t_bv.sf", "t_dep.sf",
    "ld_cens", "rd_cens", "t_cens",
    "ld_nl", "rd_nl", "ld_sub",
    "ld_hvoh", "ld_hvug", "ld_hvsc", "ld_hv", "ld_ss",
    "rd_wv.ol", "rd_wv.uc", "rd_wv.sc", "rd_wv.ss",
    "ldz_salt", "ldz_coast_wind", "ldz_water", "ldz_incline", "ldz_prod",
    "ldz_snow_trees", "ldz_forest_broadleaf", "ldz_snowdrift", "ldz_snow_400",
    "ldz_wind_99", "ldz_frosthours", "ldz_forest_mixed_conf",
    "ldz_mgc", "ap.t_2", "pnl.rc")]

  # Write to the output path passed as first argument
  out_path <- commandArgs(trailingOnly = TRUE)[1]
  write.csv(write.dat, file = out_path)
