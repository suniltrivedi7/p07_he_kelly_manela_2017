"""
Table02Prep.py

HKM Table 2 replication pipeline. Loads pre-pulled parquet data, builds
month-end sector totals for PD, BD, Banks, and Cmpust. comparison groups,
computes ratios, and exports the final table to LaTeX.
"""

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
import numpy as np
import wrds
import config
import Table02Analysis
from datetime import datetime
from pathlib import Path

# Constants

KEY_COLS = ["total_assets", "book_debt", "book_equity", "market_equity"]

# GE (005047) held Kidder Peabody; Sears (006307) held Dean Witter.
# Their non-financial consolidated assets inflate the PD numerator.
NON_FINANCIAL_PD_GVKEYS = {"005047", "006307"}


# Helpers

def get_ccm_gvkey_universe(db, start_date: str, end_date: str) -> set[str]:
    """Return gvkeys in the CCM link table during the sample window (US-incorporated only)."""
    q = f"""
        SELECT DISTINCT l.gvkey
        FROM crsp.ccmxpf_lnkhist l
        JOIN comp.company c ON l.gvkey = c.gvkey
        WHERE l.gvkey IS NOT NULL
          AND l.linktype LIKE 'L%%'
          AND (l.linkprim = 'C' OR l.linkprim = 'P')
          AND c.fic = 'USA'
          AND (
                (l.linkdt IS NULL OR l.linkdt <= '{end_date}')
            AND (l.linkenddt IS NULL OR l.linkenddt >= '{start_date}')
          )
    """
    ccm = db.raw_sql(q)
    return set(ccm["gvkey"].astype(str).str.zfill(6).tolist())


def get_comparison_group_gvkeys_from_wrds(db, sic_codes: list[int],
                                           start_date: str, end_date: str) -> set[str]:
    """Return gvkeys matching the given SIC codes from comp.funda (both INDL and FS format)."""
    sic_str = ", ".join(f"'{s}'" for s in sic_codes)
    q = f"""
        SELECT DISTINCT f.gvkey
        FROM comp.funda f
        JOIN comp.company c ON f.gvkey = c.gvkey
        WHERE (c.sic IN ({sic_str}) OR f.sich IN ({sic_str}))
          AND c.fic = 'USA'
          AND (f.indfmt = 'INDL' OR f.indfmt = 'FS')
          AND f.datafmt = 'STD'
          AND f.popsrc = 'D'
          AND f.consol = 'C'
          AND f.datadate BETWEEN '{start_date}' AND '{end_date}'
    """
    result = db.raw_sql(q)
    return set(result["gvkey"].astype(str).str.zfill(6).tolist())


def build_pd_active_schedule(merged_main: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """
    Return (gvkey, mdate) pairs where a PD gvkey is active and should be
    excluded from the Banks comparison group during that month.
    """
    months = pd.date_range(pd.to_datetime(start), pd.to_datetime(end), freq="ME")
    sample_end = pd.to_datetime(end)

    mm = merged_main.copy()
    mm["gvkey"] = mm["gvkey"].astype(str).str.zfill(6)
    mm["start_dt"] = pd.to_datetime(mm["Start Date"], errors="coerce")
    end_raw = mm["End Date"].replace("Current", pd.NA)
    mm["end_dt"] = pd.to_datetime(end_raw, errors="coerce").fillna(sample_end)
    mm = mm.dropna(subset=["start_dt", "end_dt"])

    months_s = pd.Series(months, name="mdate")
    excl_parts: list[pd.DataFrame] = []

    for gvkey, grp in mm.groupby("gvkey"):
        for _, row in grp.iterrows():
            active = months_s[
                (months_s >= row["start_dt"]) & (months_s <= row["end_dt"])
            ].to_frame()
            active["gvkey"] = gvkey
            excl_parts.append(active[["gvkey", "mdate"]])

    if not excl_parts:
        return pd.DataFrame(columns=["gvkey", "mdate"])

    return (
        pd.concat(excl_parts, ignore_index=True)
          .drop_duplicates()
          .reset_index(drop=True)
    )


def _eom(dt: pd.Series) -> pd.Series:
    """Convert timestamps to month-end timestamps."""
    dt = pd.to_datetime(dt, errors="coerce")
    return dt.dt.to_period("M").dt.to_timestamp("M")


def _ensure_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# Data Loading

def clean_primary_dealers_data(fname):
    file_path = config.MANUAL_DATA / fname
    prim_dealers = pd.read_csv(file_path)

    prim_dealers["End Date"] = prim_dealers["End Date"].fillna("Current")
    prim_dealers = prim_dealers.dropna(subset=["gvkey"])
    prim_dealers["gvkey"] = prim_dealers["gvkey"].astype(int)

    for col in ["Start Date", "End Date"]:
        prim_dealers[col] = pd.to_datetime(prim_dealers[col], errors="coerce")
        prim_dealers[col] = prim_dealers[col].dt.strftime("%m/%d/%Y")
    prim_dealers["End Date"] = prim_dealers["End Date"].fillna("Current")

    if "Unnamed: 0" in prim_dealers.columns:
        prim_dealers = prim_dealers.drop(columns=["Unnamed: 0"])

    return prim_dealers


def load_link_table(fname):
    return pd.read_csv(config.MANUAL_DATA / fname)


# WRDS Query

def fetch_financial_data(db, linktable, start_date, end_date, ITERATE=False):
    """Pull Compustat fundq for a set of gvkeys; returns firm-level quarterly data."""
    pgvkeys = linktable["gvkey"].tolist()
    results = pd.DataFrame()

    if ITERATE:
        start_dt = pd.to_datetime(linktable["Start Date"], errors="coerce")
        end_raw = linktable["End Date"].copy().replace("Current", pd.NA)
        end_dt = pd.to_datetime(end_raw, errors="coerce")

        start_dt = start_dt.fillna(pd.to_datetime(start_date, errors="coerce"))
        end_dt = end_dt.fillna(pd.to_datetime(end_date, errors="coerce"))

        good = start_dt.notna() & end_dt.notna()
        if not good.all():
            linktable = linktable.loc[good].reset_index(drop=True)
            start_dt = start_dt.loc[good].reset_index(drop=True)
            end_dt = end_dt.loc[good].reset_index(drop=True)
            pgvkeys = linktable["gvkey"].tolist()

        start_str = start_dt.dt.strftime("%Y-%m-%d")
        end_str = end_dt.dt.strftime("%Y-%m-%d")

        for i, gvkey in enumerate(pgvkeys):
            pgvkey_str = f"'{str(int(gvkey)).zfill(6)}'"
            query = f"""
            SELECT datadate,
                   atq AS total_assets,
                   ltq AS book_debt,
                   COALESCE(teqq, ceqq + COALESCE(pstkq, 0) + COALESCE(mibnq, 0)) AS book_equity,
                   (cshoq * prccq) AS market_equity,
                   gvkey, conm, indfmt
            FROM comp.fundq AS cst
            WHERE cst.gvkey = {pgvkey_str}
              AND cst.datadate BETWEEN '{start_str.iloc[i]}' AND '{end_str.iloc[i]}'
              AND (indfmt = 'INDL' OR indfmt = 'FS')
              AND datafmt='STD' AND popsrc='D' AND consol='C'
            """
            data = db.raw_sql(query)
            if not data.empty:
                results = pd.concat([results, data], axis=0)

    else:
        pgvkey_str = ",".join([f"'{str(int(key)).zfill(6)}'" for key in pgvkeys])
        query = f"""
        SELECT datadate,
               atq AS total_assets,
               ltq AS book_debt,
               COALESCE(teqq, ceqq + COALESCE(pstkq, 0) + COALESCE(mibnq, 0)) AS book_equity,
               (cshoq * prccq) AS market_equity,
               gvkey, conm, indfmt
        FROM comp.fundq AS cst
        WHERE cst.gvkey IN ({pgvkey_str})
          AND cst.datadate BETWEEN '{start_date}' AND '{end_date}'
          AND (indfmt = 'INDL' OR indfmt = 'FS')
          AND datafmt='STD' AND popsrc='D' AND consol='C'
        """
        data = db.raw_sql(query)
        if not data.empty:
            results = pd.concat([results, data], axis=0)

    return results


# Group Construction

def create_comparison_group_linktables(link_hist, merged_main,
                                       ccm_gvkeys: set[str] | None = None,
                                       wrds_bd_gvkeys: set[str] | None = None,
                                       wrds_banks_gvkeys: set[str] | None = None):
    """
    Build gvkey lists for PD, BD, Banks, and Cmpust. comparison groups.
    GE and Sears are excluded from PD; Banks uses time-varying PD exclusion downstream.
    """
    link_hist = link_hist.copy()
    link_hist["gvkey"] = pd.to_numeric(link_hist["gvkey"], errors="coerce")
    link_hist = link_hist.dropna(subset=["gvkey"])
    link_hist["gvkey"] = link_hist["gvkey"].astype(int).astype(str).str.zfill(6)
    link_hist["sic"] = pd.to_numeric(link_hist["sic"], errors="coerce")

    merged_main = merged_main.copy()
    merged_main["gvkey"] = pd.to_numeric(merged_main["gvkey"], errors="coerce")
    merged_main = merged_main.dropna(subset=["gvkey"])
    merged_main["gvkey"] = merged_main["gvkey"].astype(int).astype(str).str.zfill(6)

    pd_df = merged_main[~merged_main["gvkey"].isin(NON_FINANCIAL_PD_GVKEYS)].copy()
    pd_gvkeys = set(pd_df["gvkey"].tolist())

    if ccm_gvkeys is not None:
        link_hist = link_hist[link_hist["gvkey"].isin(ccm_gvkeys)].copy()

    if wrds_bd_gvkeys is not None:
        bd_universe = wrds_bd_gvkeys - pd_gvkeys
        if ccm_gvkeys is not None:
            bd_universe = bd_universe & ccm_gvkeys
        linked_bd_less_pd = pd.DataFrame({"gvkey": sorted(bd_universe)})
    else:
        linked_bd_less_pd = link_hist[
            (link_hist["sic"].isin([6211, 6221])) & (~link_hist["gvkey"].isin(pd_gvkeys))
        ]

    if wrds_banks_gvkeys is not None:
        # Time-varying exclusion applied downstream; do NOT statically subtract pd_gvkeys.
        banks_universe = wrds_banks_gvkeys
        if ccm_gvkeys is not None:
            banks_universe = banks_universe & ccm_gvkeys
        linked_banks_less_pd = pd.DataFrame({"gvkey": sorted(banks_universe)})
    else:
        linked_banks_less_pd = link_hist[
            (link_hist["sic"].isin([6011, 6020, 6021, 6022, 6029, 6081, 6082]))
            & (~link_hist["gvkey"].isin(pd_gvkeys))
        ]

    if ccm_gvkeys is not None:
        linked_all_less_pd = pd.DataFrame({"gvkey": sorted(ccm_gvkeys - pd_gvkeys)})
    else:
        linked_all_less_pd = link_hist[~link_hist["gvkey"].isin(pd_gvkeys)]

    return {
        "BD": linked_bd_less_pd,
        "Banks": linked_banks_less_pd,
        "Cmpust.": linked_all_less_pd,
        "PD": pd_df,
    }


def pull_data_for_all_comparison_groups(db, comparison_group_dict, UPDATED=False):
    datasets = {}
    for key, linktable in comparison_group_dict.items():
        ITERATE = (key == "PD")
        if not UPDATED:
            ds = fetch_financial_data(
                db, linktable, config.START_DATE, config.END_DATE, ITERATE=ITERATE
            )
        else:
            if pd.to_datetime(config.UPDATED_END_DATE) > datetime.now():
                UPDATED_END_DATE = datetime.now().strftime("%Y-%m-%d")
            else:
                UPDATED_END_DATE = config.UPDATED_END_DATE
            ds = fetch_financial_data(
                db, linktable, config.START_DATE, UPDATED_END_DATE, ITERATE=ITERATE
            )
        datasets[key] = ds.drop_duplicates()
    return datasets


# Data Processing

def prep_datasets(datasets):
    """Convert raw fundq pulls into quarterly sector totals. Used by the test suite."""
    prepped = {}
    for group_name, df in datasets.items():
        if df is None or df.empty:
            prepped[group_name] = pd.DataFrame(columns=["datadate"] + KEY_COLS)
            continue
        df = df.copy()
        df["datadate"] = pd.to_datetime(df["datadate"], errors="coerce")
        df = df.dropna(subset=["datadate"])
        for c in KEY_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        prepped[group_name] = (
            df.groupby("datadate", as_index=False)[KEY_COLS]
              .sum(min_count=1)
              .sort_values("datadate")
        )
    return prepped


def build_monthly_sector_totals_from_fundq(raw_df: pd.DataFrame,
                                           start: str,
                                           end: str,
                                           key_cols=KEY_COLS,
                                           ffill_limit: int | None = None,
                                           pre_start_quarters: int = 1,
                                           exclude_active_pd: pd.DataFrame | None = None,
                                           ) -> pd.DataFrame:
    """
    Convert firm-level fundq data into month-end sector totals. Resamples each
    firm to monthly frequency (forward-fill), then sums across firms by month.
    Includes one extra quarter before start so the first months have a seed value.
    """
    df = raw_df.copy()
    df["datadate"] = pd.to_datetime(df["datadate"], errors="coerce")
    df = df.dropna(subset=["gvkey", "datadate"])
    df["gvkey"] = df["gvkey"].astype(str).str.zfill(6)
    for c in key_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    pre_start_dt = start_dt - pd.DateOffset(months=pre_start_quarters * 3)
    df = df.loc[(df["datadate"] >= pre_start_dt) & (df["datadate"] <= end_dt)]

    # Prefer FS over INDL when both exist for the same gvkey-date ('FS' < 'INDL').
    if "indfmt" in df.columns:
        df = df.sort_values(["gvkey", "datadate", "indfmt"])
        df = df.drop_duplicates(subset=["gvkey", "datadate"], keep="first")
    else:
        df = df.sort_values(["gvkey", "datadate"])
        df = df.drop_duplicates(subset=["gvkey", "datadate"], keep="last")

    monthly_firm = (
        df.set_index("datadate")
          .groupby("gvkey")[key_cols]
          .resample("ME")
          .ffill(limit=ffill_limit)
          .reset_index()
    )

    # Zero out a PD gvkey's contribution during its active PD months only.
    if exclude_active_pd is not None and not exclude_active_pd.empty:
        excl = exclude_active_pd.rename(columns={"mdate": "datadate"}).copy()
        excl["_exclude"] = True
        monthly_firm = monthly_firm.merge(excl, on=["gvkey", "datadate"], how="left")
        mask = monthly_firm["_exclude"].fillna(False)
        for c in key_cols:
            monthly_firm.loc[mask, c] = np.nan
        monthly_firm = monthly_firm.drop(columns=["_exclude"])

    sector = (
        monthly_firm.groupby("datadate")[key_cols]
                    .sum(min_count=1)
                    .reset_index()
                    .rename(columns={"datadate": "mdate"})
    )

    idx = pd.date_range(start_dt, end_dt, freq="ME")
    sector = sector.set_index("mdate").reindex(idx).rename_axis("mdate").reset_index()
    return sector


def build_all_monthly_totals(ds: dict[str, pd.DataFrame],
                              start: str,
                              end: str,
                              banks_pd_active_schedule: pd.DataFrame | None = None,
                              ) -> dict[str, pd.DataFrame]:
    """Convert firm-level fundq pulls for each group into month-end sector totals."""
    out = {}
    for k, raw in ds.items():
        excl = banks_pd_active_schedule if k == "Banks" else None
        out[k] = build_monthly_sector_totals_from_fundq(raw, start, end,
                                                        exclude_active_pd=excl)
    return out


# Ratio Computation (legacy — used by test suite)

def create_ratios_for_table(prepped_datasets, UPDATED=False):
    """Compute period-average ratios from quarterly totals. Used by the test suite."""
    if not UPDATED:
        sample_periods = [
            ("1960-01-01", "2012-12-31"),
            ("1960-01-01", "1990-12-31"),
            ("1990-01-01", "2012-12-31"),
        ]
        global_end = "2012-12-31"
    else:
        sample_periods = [
            ("1960-01-01", "2025-01-01"),
            ("1960-01-01", "1990-12-31"),
            ("1990-01-01", "2025-01-01"),
        ]
        global_end = "2025-01-01"

    def to_monthly_asof(q_totals, start="1960-01-01", end=global_end):
        q = q_totals.copy()
        q["datadate"] = pd.to_datetime(q["datadate"])
        q = q.sort_values("datadate")
        m = pd.DataFrame({"qdate": pd.date_range(start=start, end=end, freq="ME")})
        out = pd.merge_asof(
            m.sort_values("qdate"), q,
            left_on="qdate", right_on="datadate",
            direction="backward", allow_exact_matches=True,
        )
        return out.dropna(subset=["datadate"]).drop(columns=["datadate"])

    monthly = {}
    for g in ["PD", "BD", "Banks", "Cmpust."]:
        if g not in prepped_datasets:
            raise KeyError(f"Missing group {g} in prepped_datasets.")
        monthly[g] = to_monthly_asof(prepped_datasets[g])

    ratio_df = monthly["PD"][["qdate"]].copy().set_index("qdate")

    for grp in ["BD", "Banks", "Cmpust."]:
        denom = (
            monthly["PD"][KEY_COLS].set_index(monthly["PD"]["qdate"])
            + monthly[grp][KEY_COLS].set_index(monthly[grp]["qdate"])
        )
        num = monthly["PD"][KEY_COLS].set_index(monthly["PD"]["qdate"])
        for c in KEY_COLS:
            ratio_df[f"{c}_{grp}"] = num[c] / denom[c].replace(0, np.nan)

    out = []
    for (s, e) in sample_periods:
        sdt, edt = pd.to_datetime(s), pd.to_datetime(e)
        sub = ratio_df.loc[(ratio_df.index >= sdt) & (ratio_df.index <= edt)].copy()
        means = sub.mean(numeric_only=True)
        means["Period"] = f"{sdt.year}-{edt.year}"
        out.append(means)

    return pd.DataFrame(out).set_index("Period").reset_index()


# Output

def convert_and_export_table_to_latex(formatted_table, UPDATED=False):
    latex = formatted_table.to_latex(
        index=True, column_format="lcccccccccccc", float_format="%.3f"
    )
    latex = latex.replace("_", "\\_")
    caption = "Original" if not UPDATED else "Updated"
    fname = "table02_fixed.tex" if not UPDATED else "updated_table02_fixed.tex"
    wrapper = rf"""
\begin{{table}}[htbp]
\centering
\caption{{{caption}}}
\label{{tab:Table 2}}
\small
{latex}
\end{{table}}
"""
    outpath = config.OUTPUT_DIR / fname
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(wrapper)
    print(f"Table 02 LaTeX saved to: {outpath}")


# Main

def main(UPDATED=False):
    PULLED_DIR = config.DATA_DIR / "pulled"
    merged_main = clean_primary_dealers_data(fname="Primary_Dealer_Link_Table3_DOMESTIC.csv")

    ds = {
        "PD":      pd.read_parquet(PULLED_DIR / "table02_raw_PD.parquet"),
        "BD":      pd.read_parquet(PULLED_DIR / "table02_raw_BD.parquet"),
        "Banks":   pd.read_parquet(PULLED_DIR / "table02_raw_Banks.parquet"),
        "Cmpust.": pd.read_parquet(PULLED_DIR / "table02_raw_Cmpust.parquet"),
    }

    end = config.END_DATE if not UPDATED else config.UPDATED_END_DATE

    pd_active_schedule = build_pd_active_schedule(merged_main, config.START_DATE, end)
    monthly_totals = build_all_monthly_totals(
        ds, config.START_DATE, end, banks_pd_active_schedule=pd_active_schedule
    )
    ratios = Table02Analysis.compute_table2_ratios(monthly_totals, config.START_DATE, end)

    Table02Analysis.create_summary_stat_table_for_data(ds, UPDATED=UPDATED)
    Table02Analysis.create_figure_for_data(ratios, UPDATED=UPDATED)
    Table02Analysis.create_corr_matrix_for_data(ds, UPDATED=UPDATED)
    final = Table02Analysis.summarize_table2(ratios, UPDATED=UPDATED)

    convert_and_export_table_to_latex(final, UPDATED=UPDATED)
    return final


if __name__ == "__main__":
    main(UPDATED=False)
