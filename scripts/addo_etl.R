#!/usr/bin/env Rscript
# ADDO ETL: raw Pharmacy Council inventory xls -> standardized outlet CSV.
#
# Input : data-raw/ADDO_Inventory_Form_results-Edited.xls
# Output: data/tanzania/addo_standardized.csv
#
# Run from the project root:
#   Rscript scripts/addo_etl.R
#
# After this script, run scripts/build_boundaries.py to (a) simplify the
# GADM Tanzania admin boundaries into web-friendly GeoJSON and (b) enrich
# this CSV with gid_region / gid_district / gid_ward columns so the ADDO
# Registry choropleth can aggregate counts client-side.

suppressPackageStartupMessages({
  library(readxl)
  library(dplyr)
  library(stringr)
  library(readr)
  library(tidyr)
})

raw_path <- "data-raw/ADDO_Inventory_Form_results-Edited.xls"
out_path <- "data/tanzania/addo_standardized.csv"

# Header spans rows 4-5; data starts at row 6. Read raw, then rename by position.
raw <- read_excel(raw_path, sheet = 1, skip = 5, col_names = FALSE)

cols <- c(
  "sn", "addo_name_raw", "business_type_raw", "accreditation_source_raw",
  "po_box", "region_raw", "district_raw", "ward_raw", "village_street_raw",
  "phone_raw", "training_center_raw",
  "lat_tablet", "lon_tablet", "alt_tablet", "acc_tablet",
  "lat_hand", "lon_hand", "acc_hand"
)
names(raw) <- cols[seq_len(ncol(raw))]

# Business-type / accreditation-source expansions (see data-raw dataset legend).
biz_map <- c(RA = "Retail A", RW = "Retail Wholesale")
acc_map <- c(PC = "Pharmacy Council", TFDA = "TFDA")

# Tanzania rough bounding box (used to reject clearly-invalid coordinates).
tz_lat <- c(-12.0, -0.9)
tz_lon <- c(29.3, 40.5)

tz_regions <- c(
  "Arusha","Dar es Salaam","Dodoma","Geita","Iringa","Kagera","Katavi",
  "Kigoma","Kilimanjaro","Lindi","Manyara","Mara","Mbeya","Morogoro",
  "Mtwara","Mwanza","Njombe","Pwani","Rukwa","Ruvuma","Shinyanga",
  "Simiyu","Singida","Songwe","Tabora","Tanga",
  "Kaskazini Unguja","Kusini Unguja","Mjini Magharibi",
  "Kaskazini Pemba","Kusini Pemba"
)

to_num <- function(x) suppressWarnings(as.numeric(x))
title_case <- function(x) str_to_title(str_squish(as.character(x)))

# Coerce misspelled/case-varied region strings to the closest canonical
# Tanzanian region (adist ratio threshold ~0.25 == difflib cutoff 0.75).
canonical_region <- function(x) {
  vapply(x, function(v) {
    if (is.na(v) || !nzchar(v)) return(NA_character_)
    s <- str_squish(gsub("[^[:alnum:] ]", " ", v))
    s <- str_to_title(s)
    if (!nzchar(s)) return(NA_character_)
    s2 <- str_squish(sub("\\s+(City|Cc|Mc|Dc|Tc|Mun|Cicty|Municipal|Municipality)\\b.*$", "", s, ignore.case = TRUE))
    for (cand in unique(c(s2, s))) {
      if (cand %in% tz_regions) return(cand)
      d <- adist(cand, tz_regions, ignore.case = TRUE)[1, ]
      score <- 1 - d / pmax(nchar(cand), nchar(tz_regions))
      best <- which.max(score)
      if (length(best) && score[best] >= 0.75) return(tz_regions[best])
    }
    NA_character_
  }, character(1), USE.NAMES = FALSE)
}

std <- raw %>%
  filter(!is.na(addo_name_raw)) %>%
  mutate(
    addo_uid              = sprintf("TZ-ADDO-%05d", row_number()),
    addo_name             = str_squish(as.character(addo_name_raw)),
    business_type         = unname(biz_map[str_to_upper(str_squish(business_type_raw))]),
    accreditation_source  = unname(acc_map[str_to_upper(str_squish(accreditation_source_raw))]),
    po_box                = str_squish(as.character(po_box)),
    region_raw_clean      = str_squish(as.character(region_raw)),
    region                = canonical_region(region_raw),
    district              = title_case(district_raw),
    ward                  = title_case(ward_raw),
    village_street        = title_case(village_street_raw),
    phone                 = str_squish(as.character(phone_raw)),
    training_center       = str_squish(as.character(training_center_raw)),
    across(c(lat_tablet, lon_tablet, alt_tablet, lat_hand, lon_hand), to_num),
    tablet_ok = !is.na(lat_tablet) & !is.na(lon_tablet) &
                between(lat_tablet, tz_lat[1], tz_lat[2]) &
                between(lon_tablet, tz_lon[1], tz_lon[2]),
    hand_ok   = !is.na(lat_hand) & !is.na(lon_hand) &
                between(lat_hand, tz_lat[1], tz_lat[2]) &
                between(lon_hand, tz_lon[1], tz_lon[2]),
    latitude   = if_else(tablet_ok, lat_tablet, if_else(hand_ok, lat_hand, NA_real_)),
    longitude  = if_else(tablet_ok, lon_tablet, if_else(hand_ok, lon_hand, NA_real_)),
    altitude   = if_else(tablet_ok, alt_tablet, NA_real_),
    gps_source = case_when(tablet_ok ~ "tablet", hand_ok ~ "hand", TRUE ~ NA_character_),
    gps_accuracy = case_when(
      tablet_ok ~ as.character(acc_tablet),
      hand_ok   ~ as.character(acc_hand),
      TRUE      ~ NA_character_
    ),
    has_coords = !is.na(latitude) & !is.na(longitude)
  ) %>%
  select(
    addo_uid, addo_name, business_type, accreditation_source,
    po_box, region, region_raw_clean, district, ward, village_street, phone, training_center,
    latitude, longitude, altitude, gps_source, gps_accuracy, has_coords
  )

dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)
write_csv(std, out_path, na = "")

message(sprintf(
  "wrote %d outlets to %s | geocoded: %d (%.1f%%) | regions: %d",
  nrow(std), out_path,
  sum(std$has_coords), 100 * mean(std$has_coords),
  dplyr::n_distinct(std$region[!is.na(std$region)])
))
