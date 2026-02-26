# Pipeline Documentation: Table 2 & Table 3

Replication of He, Kelly, and Manela (2017), "Intermediary Asset Pricing: New Evidence from
Many Asset Classes," *Journal of Financial Economics*.

---

## Table of Contents

1. [Repository Layout](#1-repository-layout)
2. [Configuration & Environment](#2-configuration--environment)
3. [Task Automation (dodo.py)](#3-task-automation-dodospy)
4. [External Data Sources](#4-external-data-sources)
5. [Manual Data Files](#5-manual-data-files)
6. [Table 2 Pipeline](#6-table-2-pipeline)
7. [Table 3 Pipeline](#7-table-3-pipeline)
8. [Shared Utilities](#8-shared-utilities)
9. [Output Files](#9-output-files)
10. [Known Issues & Notes](#10-known-issues--notes)

---

## 1. Repository Layout

```
github_repo/
├── dodo.py                        # doit task definitions (entry point)
├── .env                           # local secrets (WRDS credentials, paths)
├── .env.example                   # template for .env
├── src/
│   ├── config.py                  # path/date config for all Table scripts
│   ├── settings.py                # path/date config for CRSP scripts (decouple)
│   ├── load_fred.py               # pull & cache FRED macro + BD data
│   ├── pull_CRSP_stock.py         # pull CRSP monthly stock file + index files
│   ├── pull_CRSP_Compustat.py     # CCM merge utilities (unused by Table2/3 directly)
│   ├── generate_chart.py          # CRSP exploratory charts (Plotly)
│   ├── Table02Prep.py             # Table 2 data prep + ratio calc + LaTeX export
│   ├── Table02Analysis.py         # Table 2 summary stats, figure, correlation matrix
│   ├── Table02_testing.py         # unittest suite for Table 2
│   ├── Table03Load.py             # Table 3 data loaders (WRDS, FRED, Shiller, FF)
│   ├── Table03.py                 # Table 3 ratio/factor calc + correlation + LaTeX export
│   ├── Table03Analysis.py         # Table 3 figures (Figure 1, 2, 3)
│   ├── Table03_testing.py         # unittest suite for Table 3
│   └── LaTeXDocGenerator.py       # combine all .tex + .png → combined_document.pdf
├── data_manual/
│   ├── Primary_Dealer_Link_Table3.csv         # full primary dealer ↔ gvkey table
│   ├── Primary_Dealer_Link_Table3_DOMESTIC.csv # domestic dealers only (Table 3)
│   ├── Primary_Dealer_Link_Table3_FOREIGN.csv  # foreign dealers (Datastream MNEMs)
│   ├── International_Dealer_Link_Table3.csv    # legacy template (superseded)
│   ├── ticks.csv                               # ticker ↔ gvkey ↔ permco mapping
│   └── updated_linktable.csv                   # CRSP/Compustat link history for Table 2
├── _data/pulled/                  # auto-generated data cache (gitignored)
└── _output/                       # auto-generated tables, figures, and PDFs
```

---

## 2. Configuration & Environment

### `src/config.py`

Used by all Table 2 and Table 3 scripts. Reads from `.env` via `python-decouple`.

| Variable | Default | Purpose |
|---|---|---|
| `WRDS_USERNAME` | `""` | WRDS login for Compustat/CRSP queries |
| `MANUAL_DATA` | `data_manual/` | Path to hand-curated CSV files |
| `DATA_DIR` | `_data/` | Root for all downloaded/cached data |
| `OUTPUT_DIR` | `_output/` | Destination for all generated files |
| `START_DATE` | `1960-01-01` | Beginning of the sample |
| `END_DATE` | `2012-12-31` | End of the original HKM sample |
| `UPDATED_END_DATE` | `2025-01-01` | End of the extended sample (UPDATED=True) |

### `src/settings.py`

Used only by `pull_CRSP_stock.py` and `generate_chart.py`. Wraps the same `.env` file but
exposes values through a `config()` function rather than module-level attributes.

### `.env` File

Minimum required entries:
```
WRDS_USERNAME=your_wrds_id
START_DATE=1960-01-01
END_DATE=2012-12-31
```

---

## 3. Task Automation (dodo.py)

Run from the `github_repo/` directory with `doit` or `doit <task_name>`.

| Task name | Command | What it does | Outputs |
|---|---|---|---|
| `generate_charts` | `doit generate_charts` | Loads CRSP monthly return data (auto-pulls from WRDS if missing) and produces three Plotly HTML charts | `_output/crsp_returns_timeseries.html`<br>`_output/crsp_returns_histogram.html`<br>`_output/crsp_rolling_volatility.html` |
| `table02_main` | `doit table02_main` | Runs `Table02Prep.main()` twice (original + updated sample) | `_output/table02.tex`<br>`_output/updated_table02.tex`<br>`_output/table02_figure.png`<br>`_output/table02_sstable.tex`<br>`_output/table02_corr.tex` |
| `test_table02` | `doit test_table02` | Unit tests for Table 2 | console output |
| `table03_main` | `doit table03_main` | Runs `Table03.main()` twice (original + updated sample) | `_output/table03.tex`<br>`_output/updated_table03.tex`<br>`_output/table03_figure.png`<br>`_output/table03_figure03.png`<br>`_output/table03_sstable.tex` |
| `test_table03` | `doit test_table03` | Unit tests for Table 3 | console output |
| `pull_fred_data` | `doit pull_fred_data` | Downloads AEM broker-dealer FRED data and Shiller PE spreadsheet to `_data/pulled/` | `_data/pulled/ltab127d.prn`<br>`_data/pulled/fred_bd_aem.csv`<br>`_data/pulled/shiller_pe.xlsx` |
| `run_notebook` | `doit run_notebook` | Executes `FinalCombinedWalkthrough.ipynb` | `_output/FinalCombinedWalkthrough_executed.ipynb` |
| `generate_latex_doc` | `doit generate_latex_doc` | Assembles all `.tex` and `.png` files into one combined document and runs `pdflatex` | `_output/combined_document.tex`<br>`_output/combined_document.pdf` |

`doit` (no argument) runs all tasks in dependency order.

---

## 4. External Data Sources

### WRDS — accessed live via `wrds.Connection`

| Database | Table | Used by | Contents |
|---|---|---|---|
| `comp.fundq` | Compustat Fundamentals Quarterly | Table02Prep, Table03Load | `atq` (total assets), `ltq` (total liabilities), `ceqq` (common equity), `teqq` (total equity), `cshoq` × `prccq` (market cap), `gvkey`, `conm` |
| `crsp.dsi` | CRSP Daily Stock Index | Table03Load | `date`, `vwretd` (value-weighted return) |
| `crsp_a_indexes.msix` | CRSP Monthly Stock Index | pull_CRSP_stock, generate_chart | `caldt`, `vwretd`, and all decile index columns |
| `crsp.msf` | CRSP Monthly Stock File | pull_CRSP_stock | Individual stock returns, prices, shares outstanding |
| `ccmlinktable` | CRSP/Compustat Merged | Table02Prep | `gvkey` ↔ `permco` link with `linktype`, `linkprim`, date range |
| `worldscope.wrds_ws_funda` | Worldscope Fundamentals | Table03Load | `item6100` (MNEM), `item6001` (fiscal year), `item2999` (total assets), `item3501` (common equity), `item8001` (market cap) — for foreign dealers |

### FRED — accessed via `pandas_datareader`

| Series ID | Description | Used by | Cache file |
|---|---|---|---|
| `UNRATE` | Unemployment Rate (seasonally adjusted, monthly) | Table03 | `_data/pulled/fred_macro.parquet` |
| `NFCI` | Chicago Fed National Financial Conditions Index (weekly) | Table03 | `_data/pulled/fred_macro.parquet` |
| `GDPC1` | Real GDP (quarterly, chained 2017 dollars) | Table03 | `_data/pulled/fred_macro.parquet` |
| `BOGZ1FL664090005Q` | Security Brokers & Dealers: Total Financial Assets (quarterly) | Table03 (AEM leverage) | `_data/pulled/fred_bd.parquet` |
| `BOGZ1FL664190005Q` | Security Brokers & Dealers: Total Liabilities (quarterly) | Table03 (AEM leverage) | `_data/pulled/fred_bd.parquet` |

### Federal Reserve Flow of Funds (historical 2013 release)

Downloaded as a ZIP from `federalreserve.gov/releases/z1/20130307/Disk/ltabs.zip`.
Extracted file `ltab127d.prn` contains `FL664090005.Q` (assets) and `FL664190005.Q`
(liabilities) for broker-dealers from 1968Q4 to 2012Q4. Used as the **primary AEM leverage
source** for the original sample.

Cache: `_data/pulled/ltab127d.prn` and `_data/pulled/fred_bd_aem.csv`.
Loaded by: `Table03Load.load_fred_past()`.

### Shiller IE Data

Downloaded from Robert Shiller's website (`img1.wsimg.com`) as `ie_data.xls`.
Sheet `Data`, rows 1–7 skipped (title/notes), row 8 = column headers.
Column used: **CAPE** (Cyclically Adjusted Price/Earnings, P/E10).
E/P ratio = 1 / CAPE.

Cache: `_data/pulled/shiller_pe.xlsx`.
Loaded by: `Table03Load.load_shiller_pe()` → `_extract_cape_columns()`.

### Fama-French Factors

Pulled from Ken French's data library via `pandas_datareader`:
dataset `F-F_Research_Data_5_Factors_2x3` (monthly, divided by 100).
Column used: `Mkt-RF` (renamed to `mkt_ret`), representing monthly market excess return.
Converted to quarterly compounded returns by `(1+r).prod()-1`.

Used by: `Table03.macro_variables()`.

---

## 5. Manual Data Files

All files live in `data_manual/` and are version-controlled.

### `Primary_Dealer_Link_Table3.csv`

Used by **Table 2** (`Table02Prep.clean_primary_dealers_data()`).

| Column | Type | Notes |
|---|---|---|
| `Primary Dealer` | string | NY Fed primary dealer name |
| `Start Date` | MM/DD/YY or MM/DD/YYYY | First day as primary dealer |
| `End Date` | MM/DD/YY or blank | Last day; blank → "Current" |
| `gvkey` | integer | Compustat global company key |

Dealers with no `gvkey` (NaN) are dropped by `clean_primary_dealers_data()`.

### `Primary_Dealer_Link_Table3_DOMESTIC.csv`

Used by **Table 3** (`Table02Prep.clean_primary_dealers_data(fname='...DOMESTIC.csv')`).
Same schema as above. Contains ~80 domestic US primary dealer holding company entries.
International rows (blank gvkey) have been removed.

### `Primary_Dealer_Link_Table3_FOREIGN.csv`

Used by **Table 3** (`Table03Load.load_foreign_dealers()`).

| Column | Type | Notes |
|---|---|---|
| `Primary Dealer` | string | Dealer name |
| `From` | DD/MM/YYYY | European date format |
| `To` | DD/MM/YYYY or "Current Dealer" | Blank treated as active |
| `Parent Company` | string | Parent holding company name |
| `Country` | string | ISO 3-letter country code |
| `MNEM` | string | Datastream MNEM code (e.g. `H:AAB`) |

One dealer may appear on multiple rows if it had multiple parent companies (e.g.,
Greenwich Capital Markets had three parents). These multi-parent rows are averaged
per quarter by `fetch_data_for_international_tickers()`.
Rows with blank `MNEM` are skipped.

### `updated_linktable.csv`

Used by **Table 2** (`Table02Prep.load_link_table()`).
Provides a broad CRSP/Compustat merged link history used to define comparison groups
(broker-dealers, banks, all Compustat firms) by SIC code.

Key columns: `gvkey`, `sic`.
SIC codes used:
- Broker-dealers (BD): 6211, 6221
- Banks: 6011, 6021, 6022, 6029, 6081, 6082, 6020
- Primary dealers (PD): from `Primary_Dealer_Link_Table3.csv`

### `ticks.csv`

Used by **Table 2** (`Table02Prep.read_in_manual_datasets()`).
Maps ticker symbols to `gvkey` and `permco` for the primary dealer set.
Delimiter: `|` (pipe).

### `International_Dealer_Link_Table3.csv`

Legacy template file created during development. Superseded by
`Primary_Dealer_Link_Table3_FOREIGN.csv`. Not actively used by any script.

---

## 6. Table 2 Pipeline

**Entry point:** `Table02Prep.main(UPDATED=False)`
**doit task:** `table02_main`

### What Table 2 shows

Primary dealers' share of total assets, book debt, book equity, and market equity
relative to three comparison groups (broker-dealers, banks, all Compustat firms),
averaged over three sample periods (full, pre-1990, post-1990).

### Step-by-step pipeline

```
Manual files
  Primary_Dealer_Link_Table3.csv  ──► clean_primary_dealers_data()
  updated_linktable.csv           ──► load_link_table()
                                          │
                                          ▼
                              create_comparison_group_linktables()
                              → dict: {PD, BD, Banks, Cmpust.}
                                          │
                              WRDS comp.fundq (live query)
                                          │
                                          ▼
                              pull_data_for_all_comparison_groups()
                              → raw quarterly DataFrames per group
                                          │
                                          ▼
                                  prep_datasets()
                              → sum per quarter: total_assets,
                                book_debt, book_equity, market_equity
                                          │
                               ┌──────────┴──────────┐
                               │                     │
                    create_ratios_for_table()   Table02Analysis.*
                    → PD share = PD_value /     summary stats,
                      (PD_value + group_value)  figure, corr matrix
                               │
                               ▼
                    format_final_table()
                    → MultiIndex pivot: Period × (Metric, Source)
                               │
                               ▼
                    convert_and_export_table_to_latex()
                    → _output/table02.tex
```

### Key functions

| Function | File | Description |
|---|---|---|
| `clean_primary_dealers_data(fname)` | Table02Prep | Reads CSV, parses dates, drops rows with no `gvkey` |
| `load_link_table(fname)` | Table02Prep | Reads `updated_linktable.csv` as-is |
| `fetch_financial_data(db, linktable, ...)` | Table02Prep | SQL query to `comp.fundq`; two modes: single bulk query (comparison groups) or per-dealer iteration (PD, respects date ranges). Uses `COALESCE(teqq, ceqq + pstkq + mibnq)` for book equity and `CASE WHEN atq=0 THEN actq` fallback for assets. |
| `create_comparison_group_linktables(...)` | Table02Prep | Filters `updated_linktable.csv` by SIC to create BD, Banks, Cmpust. groups; excludes firms already in PD |
| `pull_data_for_all_comparison_groups(...)` | Table02Prep | Loops over the four groups; PD uses `ITERATE=True` (date-range filtering per dealer) |
| `prep_datasets(datasets)` | Table02Prep | Converts `datadate` to quarter start, fills NaN with column mean, sums to quarterly aggregates |
| `create_ratios_for_table(prepped, ...)` | Table02Prep | For each combination of group and sample period: ratio = PD_value / (PD_value + group_value). Stacks all periods into one DataFrame. |
| `format_final_table(table, ...)` | Table02Prep | Pivots to MultiIndex columns; reindexes to three named periods |
| `convert_and_export_table_to_latex(...)` | Table02Prep | Writes `_output/table02.tex` with escaped underscores |
| `create_summary_stat_table_for_data(...)` | Table02Analysis | count/mean/std/min/max per group → `_output/table02_sstable.tex` |
| `create_figure_for_data(ratio_df, ...)` | Table02Analysis | 2×2 subplot of ratio time series → `_output/table02_figure.png` |
| `create_corr_matrix_for_data(datasets, ...)` | Table02Analysis | Correlation of each metric across PD/BD/Banks/Cmpust. → `_output/table02_corr.tex` |

### Compustat query details (Table 2)

```sql
SELECT datadate,
       CASE WHEN atq IS NULL OR atq = 0 THEN actq ELSE atq END AS total_assets,
       CASE WHEN ltq IS NULL OR ltq = 0 THEN lctq ELSE ltq END AS book_debt,
       COALESCE(teqq, ceqq + COALESCE(pstkq, 0) + COALESCE(mibnq, 0)) AS book_equity,
       cshoq * prccq AS market_equity,
       gvkey, conm
FROM comp.fundq
WHERE gvkey IN (...)
  AND datadate BETWEEN '{start}' AND '{end}'
  AND indfmt='INDL' AND datafmt='STD' AND popsrc='D' AND consol='C'
```

---

## 7. Table 3 Pipeline

**Entry point:** `Table03.main(UPDATED=False)`
**doit task:** `table03_main`

### What Table 3 shows

**Panel A:** Pairwise correlations of the *levels* of three capital measures
(market capital ratio, book capital ratio, AEM leverage) with macroeconomic variables
(E/P, unemployment, GDP, financial conditions, market volatility), 1970–2012.

**Panel B:** Pairwise correlations of the *AR(1) innovations* (factors) of the three
capital measures with macroeconomic growth rates and market excess return.

### Step-by-step pipeline

```
Manual files
  Primary_Dealer_Link_Table3_DOMESTIC.csv ──► clean_primary_dealers_data()
  Primary_Dealer_Link_Table3_FOREIGN.csv  ──► load_foreign_dealers()
        │                                          │
        │ WRDS comp.fundq                          │ WRDS worldscope.wrds_ws_funda
        ▼                                          ▼
  fetch_data_for_tickers()           fetch_data_for_international_tickers()
  (domestic quarterly data)          (annual data → forward-filled quarterly)
        │                                          │
        └─────────────── pd.concat() ──────────────┘
                               │
                               ▼
                         prep_dataset()
                    drop dupes, convert datafqtr → date,
                    filter market_equity > 0,
                    sum per quarter
                               │
                    FRED AEM data ◄── load_fred_past()
                    (ltab127d.prn)
                               │
                               ▼
                     aggregate_ratios()
                       → calls calculate_ratios():
                         market_cap_ratio = market_equity / (book_debt + market_equity)
                         book_cap_ratio   = book_equity   / (book_debt + book_equity)
                         aem_leverage     = bd_fin_assets / (bd_fin_assets - bd_liabilities)
                               │
                ┌──────────────┴──────────────────┐
                │                                 │
   convert_ratios_to_factors()          macro_variables()
   AR(1) residual / lagged level          FRED: UNRATE, NFCI, GDPC1
     → market_capital_factor              Shiller: E/P = 1/CAPE
     → book_capital_factor                FF: mkt_ret (compounded quarterly)
     → aem_leverage_factor                CRSP: daily vwretd → quarterly vol
                │                                 │
                └──────────┬──────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
        create_panelA()           create_panelB()
        (levels of ratios         (factors × log-growth of
         × macro levels)           macro variables)
              │                         │
              ▼                         ▼
   calculate_correlation_panelA()  calculate_correlation_panelB()
              │                         │
              └────────────┬────────────┘
                           │
              convert_and_export_tables_to_latex()
                    → _output/table03.tex
```

### Key functions

#### Data loading — `Table03Load.py`

| Function | Description |
|---|---|
| `fetch_financial_data_quarterly(gvkey, start, end, db)` | Queries `comp.fundq` for one gvkey. Returns `datafqtr`, `total_assets`, `book_debt = atq - ceqq`, `book_equity = ceqq`, `market_equity = cshoq*prccq`. |
| `fetch_data_for_tickers(ticks, db)` | Loops over domestic dealer rows, calls `fetch_financial_data_quarterly` for each. Returns concatenated DataFrame + list of gvkeys with no data. |
| `load_foreign_dealers(fname)` | Reads FOREIGN CSV (DD/MM/YYYY dates), drops rows with blank MNEM, converts "Current Dealer" → None. |
| `_fetch_intl_financial_data(mnem, start, end, db)` | Queries `worldscope.wrds_ws_funda` for one MNEM; computes `book_debt = total_assets - book_equity`. Calls `_annual_to_quarterly()`. |
| `_annual_to_quarterly(annual_df, mnem)` | Assigns year-end values to Q4; resamples to quarter-end and forward-fills Q1–Q3. |
| `fetch_data_for_international_tickers(ticks, db)` | Groups by `Primary Dealer`; single parent → direct; multiple parents → average balance-sheet values per quarter. |
| `load_fred_past(url, ...)` | Downloads Federal Reserve Z.1 (2013 vintage) ZIP; extracts `ltab127d.prn`; parses `FL664090005.Q` and `FL664190005.Q`. Covers 1968Q4–2012Q4. |
| `load_shiller_pe(url, ...)` | Loads `_data/pulled/shiller_pe.xlsx` (or downloads from Shiller's site). Delegates to `_extract_cape_columns()`. |
| `_extract_cape_columns(file_path)` | Loads the full Data sheet; searches for a column named "CAPE" / "P/E10" by header; falls back to column 12 (Excel column M). Validates that median > 1 (i.e., it is P/E, not E/P). Returns `[date, cape]` or `[date, ep_direct]` if the column is already an E/P yield. |
| `load_fred_macro_data(from_cache)` | Loads `_data/pulled/fred_macro.parquet` (UNRATE, NFCI, GDPC1). Auto-pulls from FRED via `pandas_datareader` if cache is missing. |
| `fetch_ff_factors(start_date, end_date)` | Fetches Fama-French 5-factor data from Ken French's library via `pandas_datareader`; divides by 100; renames `Mkt-RF` → `mkt_ret`. |
| `pull_CRSP_Value_Weighted_Index(db, ...)` | Queries `crsp.dsi` for `date, vwretd`; caches to `_data/pulled/crsp_return.xlsx`. |

#### Ratio and factor calculation — `Table03.py`

| Function | Description |
|---|---|
| `prep_dataset(dataset, UPDATED)` | Converts `datafqtr` strings to dates, drops rows with NULL or zero `market_equity`, sums to quarterly aggregates, merges with AEM broker-dealer data. Filters to 1970–END_DATE. |
| `calculate_ratios(data)` | `market_cap_ratio = ME / (BD + ME)`, `book_cap_ratio = BE / (BD + BE)`, `aem_leverage = fin_assets / (fin_assets - liabilities)`. |
| `aggregate_ratios(data)` | Calls `calculate_ratios()`, selects the three ratio columns, sets date index. |
| `convert_ratios_to_factors(data)` | For market and book ratios: fits AR(1) with constant via `statsmodels.AutoReg(lags=1)`; factor = residual / lagged ratio. For AEM leverage: computes `pct_change()`, then removes seasonal component via `seasonal_decompose(period=4)`. |
| `calculate_ep(shiller_cape)` | Parses Shiller date column (`%Y.%m`); computes `e/p = 1/cape` (or uses `ep_direct` directly if the spreadsheet column was already an E/P yield). |
| `macro_variables(db, ...)` | Assembles the full macro DataFrame: FRED data (quarterly mean), Shiller E/P (quarterly mean), FF `mkt_ret` (compounded quarterly), CRSP daily `vwretd` std dev per quarter. |
| `create_panelA(ratios, macro)` | Selects macro *levels*: `e/p`, `unemp_rate`, `nfci`, `real_gdp`, `mkt_vol`. Merges with capital ratio levels. |
| `create_panelB(factors, macro)` | Computes log-growth of macro levels (`np.log(x_t / x_{t-1})`); uses first-difference for NFCI (which can be negative); overwrites `mkt_ret` with the raw FF market excess return. |
| `calculate_correlation_panelA(panelA)` | Upper-triangular correlation of the three capital ratios; plus `corrwith` of each ratio against each macro variable. |
| `calculate_correlation_panelB(panelB)` | Same structure for factors and macro growth rates. |
| `convert_and_export_tables_to_latex(...)` | Rounds to 2 decimals, fills NaN with empty string, writes `_output/table03.tex`. |

#### Figures — `Table03Analysis.py`

| Function | Output file | Description |
|---|---|---|
| `plot_figure02(ratios, corr_panelA)` | `table03_figure.png` | Log-scale time series of market capital ratio, book capital ratio, and AEM leverage with NBER recession shading |
| `plot_figure03(ratios, macro)` | `table03_figure03.png` | Two-panel standardized time series: financial ratios (top) and macro variables (bottom) |

### Compustat query details (Table 3 domestic)

```sql
SELECT datafqtr,
       atq AS total_assets,
       (atq - ceqq) AS book_debt,
       ceqq AS book_equity,
       cshoq * prccq AS market_equity,
       gvkey, conm
FROM comp.fundq
WHERE gvkey = '{gvkey_padded_to_6}'
  AND datafqtr BETWEEN '{start_qtr}' AND '{end_qtr}'
  AND indfmt='INDL' AND datafmt='STD' AND popsrc='D' AND consol='C'
```

Note: uses `datafqtr` (fiscal quarter) rather than `datadate`. `book_debt` = total assets
minus common equity (includes all non-equity liabilities). Compare with Table 2 which uses
`ltq` (total liabilities) as `book_debt`.

### Worldscope query details (Table 3 foreign)

```sql
SELECT item6001 AS fiscal_year,
       item2999 AS total_assets,
       item3501 AS book_equity,
       item8001 AS market_equity
FROM worldscope.wrds_ws_funda
WHERE item6100 = '{mnem}'
  AND item6001 BETWEEN {start_year} AND {end_year}
ORDER BY item6001
```

Annual data is forward-filled to quarterly via `_annual_to_quarterly()`.

---

## 8. Shared Utilities

### `src/load_fred.py`

| Function | Cache file | Description |
|---|---|---|
| `load_fred_macro_data(from_cache)` | `_data/pulled/fred_macro.parquet` | UNRATE, NFCI, GDPC1 from FRED |
| `load_fred_bd_data(from_cache)` | `_data/pulled/fred_bd.parquet` | Broker-dealer assets and liabilities (UPDATED path) |
| `pull_fred_macro_data(...)` | same | Forces re-download from FRED |
| `pull_fred_bd_data(...)` | same | Forces re-download from FRED |

`Table03Load.py` imports from `load_fred` via `from load_fred import *`.

### `src/pull_CRSP_stock.py`

| Function | Description |
|---|---|
| `pull_CRSP_index_files(start, end)` | Queries `crsp_a_indexes.msix`; used by `generate_chart.py` to build CRSP return cache |
| `pull_CRSP_monthly_file(start, end)` | Full monthly stock file with delisting return corrections |
| `apply_delisting_returns(df)` | Imputes delisting returns per Bali/Engle/Murray (2016) Chapter 7 |

### `src/generate_chart.py`

| Function | Output | Description |
|---|---|---|
| `load_crsp()` | — | Loads `_data/pulled/crsp_return.xlsx`; auto-pulls from WRDS via `pull_CRSP_index_files()` if missing |
| `chart_returns_time_series(df, col)` | `crsp_returns_timeseries.html` | Plotly line chart |
| `chart_returns_histogram(df, col)` | `crsp_returns_histogram.html` | Plotly histogram |
| `chart_rolling_volatility(df, col)` | `crsp_rolling_volatility.html` | 30-period rolling std dev |

---

## 9. Output Files

| File | Produced by | Contents |
|---|---|---|
| `_output/table02.tex` | `Table02Prep` | PD share of balance sheet metrics vs. BD, Banks, Cmpust. (original sample) |
| `_output/updated_table02.tex` | `Table02Prep` | Same, extended sample |
| `_output/table02_sstable.tex` | `Table02Analysis` | Summary statistics per comparison group |
| `_output/table02_corr.tex` | `Table02Analysis` | Correlation of each balance-sheet metric across groups |
| `_output/table02_figure.png` | `Table02Analysis` | Ratio time series (2×2 subplots) |
| `_output/table03.tex` | `Table03` | Panel A + B correlation table (original sample) |
| `_output/updated_table03.tex` | `Table03` | Same, extended sample |
| `_output/table03_sstable.tex` | `Table03Analysis` | Summary stats for capital factors and macro variables |
| `_output/table03_figure.png` | `Table03Analysis` | Figure 2: log-scale capital ratio levels with recession bands |
| `_output/table03_figure03.png` | `Table03Analysis` | Figure 3: standardized capital ratios and macro variables |
| `_output/crsp_returns_timeseries.html` | `generate_chart` | Plotly: CRSP vwretd over time |
| `_output/crsp_returns_histogram.html` | `generate_chart` | Plotly: return distribution |
| `_output/crsp_rolling_volatility.html` | `generate_chart` | Plotly: 30-period rolling vol |
| `_output/combined_document.tex` / `.pdf` | `LaTeXDocGenerator` | All tables and figures assembled in one document |

All `.tex` and `.png` files are **overwritten** on every run (opened with `'w'` mode).

---

## 10. Known Issues & Notes

### Table 3 replication accuracy

The following discrepancies from the published HKM (2017) Table 3 are known as of the
current codebase state:

| Item | Our output | Paper | Root cause |
|---|---|---|---|
| Market capital vs E/P (Panel A) | +0.71 | −0.83 | Likely missing/zero `prccq` for many historical dealers makes aggregate `market_equity` track `book_equity` closely; capital ratio becomes counter-cyclical |
| Market capital vs Book capital (Panel A) | 0.94 | 0.50 | Same root cause; the two ratios collapse toward each other when market equity ≈ book equity |
| Market capital factor vs Book capital factor (Panel B) | 0.98 | 0.30 | Downstream of Panel A correlation — identical AR(1) innovations when ratios are 0.94 correlated |
| Market excess return vs capital factors (Panel B) | ~0.05 | 0.78 | Factors are too noisy when capital ratio data is poorly measured |

### Market equity data quality

The domestic Compustat query uses `cshoq * prccq` for market equity. For many broker-dealer
holding companies in the 1970s–1980s, quarterly price (`prccq`) is not recorded in Compustat.
The `market_equity > 0` filter in `prep_dataset()` excludes rows where `prccq = 0`, but rows
where `prccq` is NULL are already excluded by the `dropna()` call before it. The net effect is
that the aggregate market equity for early periods is based on fewer firms, making it behave
similarly to book equity. A higher-fidelity fix would join to CRSP via the
CRSP/Compustat Merged (CCM) link table to obtain CRSP-based market capitalizations.

### Shiller E/P column position

`_extract_cape_columns()` now loads columns by header name ("CAPE", "P/E10") rather than by
Excel column position. If the downloaded file has no matching header, it falls back to column 12
(Excel column M). The function validates that the selected column has median > 1 (i.e., it is
a P/E ratio, not already an E/P yield).

### GDP in Panel A vs. Panel B

Panel A uses `real_gdp` (level of real GDP). Panel B uses `np.log(real_gdp_t / real_gdp_{t-1})`
(log quarterly growth rate). The variable `real_gdp_growth_calc` (pct_change) computed inside
`macro_variables()` is retained but **not used** by either panel.

### NFCI first-difference

NFCI is centred at zero and takes negative values. In Panel B, it is computed as
`nfci.diff()` (first-difference) rather than a log-ratio, avoiding NaN from sign changes.

### AEM data vintage

The primary AEM leverage source is the Federal Reserve Z.1 table from the **2013 data
release** (frozen at 2012Q4). For `UPDATED=True`, `load_bd_financials()` supplements this
with live FRED series `BOGZ1FL664090005Q` and `BOGZ1FL664190005Q`.

### Foreign dealers (Worldscope)

Foreign dealer data is pulled via Worldscope (`worldscope.wrds_ws_funda`). If your WRDS
subscription does not include Worldscope, all international dealers will be silently absent
from the aggregate and a list of failed MNEMs will be printed. Verify access by running:
```python
db.list_schemas()
db.list_tables(library='worldscope')
```

### Date arithmetic — `quarter_to_date()`

Converts `"YYYYQ#"` to the last calendar day of that quarter (March 31, June 30,
September 30, December 31). This matches pandas `resample('QE')` quarter-end timestamps
so all merges align correctly.
