
#### 0_2 Merging Z-variables ####
#### Import data from previous notice ####
load(file = file.path(data_dir, "geo_variables.Rdata"))
load(file = file.path(data_dir, "costs_t_2.Rdata"))

# Setting pnl.rc (price of network loss) from RC-calculation two years prior to ap.t_2 (area price)
ap.t_2 <- cb.y_ex_cap %>% select (c(id, pnl.rc))
names(ap.t_2)[2] <- "ap.t_2"
ap.t_2$ap.t_2 <- ap.t_2$ap.t_2/1000

# Setter ap.t_2 manuelt for selskaper RME har valgt ut (Data/<aar>/aarsoppsett.R)
for (.id in names(ap.t_2_manuelt)) {
  ap.t_2$ap.t_2[ap.t_2$id == as.numeric(.id)] <- ap.t_2_manuelt[[.id]]
}

dat <- merge.data.frame(dat, ap.t_2, by = "id", all.x = TRUE)

# Defining variables that are summed for all merging companies
harm.var_sum = c("ldz_n.mgc_sum")

# Defining variables weighted with number of map grid cells
dat_geo <- dat_geo %>% dplyr::rename(y = y.cb)
dat_geo$id.y <- paste(dat_geo$id, dat_geo$y, sep="")
ldz_harm.var_gc <- startsWith(colnames(dat_geo), prefix = "ldz")
ldz_harm.var_gc <- colnames(dat_geo)[ldz_harm.var_gc]

# Merging companies are defined per year in Data/<aar>/aarsoppsett.R
list <- list() 

for (.navn in names(fusjoner)) {
  .f <- fusjoner[[.navn]]
  list[[.navn]] = merge_ldz_rdz(comps = .f$orgn, new.org = .f$new.org, new.id = .f$new.id, new.name = paste0("fusjonert_", .navn), sum_variables = harm.var_sum, ldz_weighted.var = ldz_harm.var_gc, df = dat_geo)$mds
}

if (length(list) > 0) {
  # Combining all rows in the list into one data frame 
  merged_ldz <- do.call("rbind", list) 
  merged_ldz <- merged_ldz[,c(2,3,1,5,6,7,8,9,10,11,12,13,14,15,16,4)]

  # Deleting companies who have merged (with IDs equal to IDs of merged companies)
  dat_geo = dat_geo[!(dat_geo$id %in% merged_ldz$id),] 

  # Adding newly merged companies 
  dat_geo <- rbind(dat_geo, merged_ldz) 
} else {
  merged_ldz <- NULL
}

# Merging data
dat_geo = dat_geo %>% select(-c(orgn, y, id.y))
dat <- merge.data.frame(dat, dat_geo, by = "id", all.x = T)

# Creating ldz_prod
ldz_prod = dat[dat$y == y.cb, c("orgn","ldz_innmat_midl","ldz_le")]
ldz_prod$ldz_prod = ldz_prod$ldz_innmat_midl /ldz_prod$ldz_le
ldz_prod$ldz_prod[!is.finite(ldz_prod$ldz_prod)] <- 0 # Removing NaN and Inf values
ldz_prod = ldz_prod %>% select(-c(ldz_innmat_midl, ldz_le))
dat <- merge.data.frame(dat, ldz_prod, by = "orgn", all.x = T )

print(unique(dat[is.na(dat$ldz_mgc), "comp" ]))
length(dat[is.na(dat)])

# Deleting NAs
dat[is.na(dat)] <- 0

# Sorting data
idasvector <- as.vector(dat$id)
dat <- dat[order(idasvector),]
rm(idasvector, ldz_prod, merged_ldz, list)

