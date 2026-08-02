# Archived: multi-country data & pages

This folder holds content from PharmaScope's earlier "HealthScope" phase, when
the portal covered health facility data across nine countries. The live site
(`_quarto.yml`'s `render:` list) now publishes **Tanzania ADDO registry data
only** (`data/tanzania/addo_standardized.csv` + boundary GeoJSONs) — none of
what's archived here is built into `docs/` or linked from the current nav.

Moved here on 2026-07-29 during a data/repo audit, unchanged in content.

## Contents

- `Benin/`, `Botswana/`, `Ethiopia/`, `Kenya/`, `Malawi/`, `Nigeria/`, `Uganda/`,
  `Zambia/` — per-country facility/service datasets (was `data/<Country>/`).
- `countries/` — the per-country Quarto pages that read this data (was
  top-level `countries/`). Several (e.g. `Botswana.qmd`, `Malawi.qmd`) depend
  on the `etl` git submodule (`etl/data/processed/country_standardized/...`),
  which isn't initialized in this checkout, so they won't render as-is.
  `Benin.qmd` additionally references two files that no longer exist anywhere
  in this repo (`benin_adm2_monthly_allages_with_rainfall.rds`,
  `data/Benin/hf_demographics.csv`) — it was already broken before the move.
- `kenya.qmd`, `country-data.qmd` — orphaned top-level pages, not in the
  render list and not linked from any published page.
- `data converter.R` — a standalone script with pre-existing copy-paste bugs
  (saves the wrong country's data frame to several output paths); not called
  by anything else in the repo.
- `tanzania-legacy-mfl/` — a general Tanzania master-facility-list dataset
  (`tanzania_master.csv`, `hf_services.csv`, `hf_demographics.csv`, and four
  near-duplicate `*_standardized*`/`tz_*` variants of the same file) that
  predates the ADDO-only pivot and is unrelated to the current ADDO registry
  (`data/tanzania/addo_standardized.csv`).

## Reviving a country

To bring a country back onto the live site: move its data back under `data/`
(or finish wiring it to the `etl` submodule), move its page back under
`countries/`, add the page to `_quarto.yml`'s `render:` list and navbar, then
re-render.
