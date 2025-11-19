# Simple script to view all data from .Rdata files

# Load forutsetninger (assumptions)
load('./Data/forutsetninger.Rdata')
cat("=== FORUTSETNINGER DATA ===\n")
cat("Available variables:\n")
print(ls())

cat("\n=== KEY VARIABLES ===\n")
cat("Cost base year (y.cb):", y.cb, "\n")
cat("Revenue cap year (y.rc):", y.rc, "\n")
cat("System price (sysp.t_2):", sysp.t_2, "\n")
cat("Working capital premium (wcp):", wcp, "\n")

cat("\n=== CPI VALUES ===\n")
print(cpi)

cat("\n=== CPI-L VALUES ===\n") 
print(cpi.l)

cat("\n=== INTEREST RATES (NVE.ir) ===\n")
print(NVE.ir)

# Load geographic variables
cat("\n\n=== GEOGRAPHIC VARIABLES ===\n")
load('./Data/geo_variables.Rdata')
cat("Geographic data structure:\n")
str(dat_geo)
cat("\nFirst few rows:\n")
print(head(dat_geo))

# Load cost data
cat("\n\n=== COST DATA (t-2) ===\n")
load('./Data/costs_t_2.Rdata')
cat("Cost data structure:\n")
str(cb.y_ex_cap)
cat("\nFirst few rows:\n")
print(head(cb.y_ex_cap))

cat("\n=== SUMMARY COMPLETE ===\n")