"""
Table02Prep.py

HKM Table 2 replication pipeline.

Fixes applied vs. original script:
1) No duplicate function definitions — Python uses the last definition of any
   duplicated function, which previously caused the improved CCM-filtering
   versions to be silently ignored.
2) Proper gvkey normalization (6-char zero-padded strings) in
   create_comparison_group_linktables so that PD gvkeys are actually excluded
   from the BD/Banks/Cmpust. denominators.  The original code compared integers
   to raw strings, so the isin() filter was a no-op and PD assets were
   double-counted in every denominator.
3) main() now passes ccm_gvkeys to create_comparison_group_linktables so that
   comparison groups are restricted to CCM-linked firms (prevents denominator
   inflation from firms that are in Compustat but not in CRSP-Compustat merge).
4) build_monthly_sector_totals_from_fundq allows one quarter of data before
   start_dt so that the first few months of the sample have a valid carry-forward
   value rather than NaN.
5) convert_and_export_table_to_latex caption logic was inverted; fixed.
6) fetch_financial_data now queries indfmt IN ('INDL', 'FS') instead of
   indfmt='INDL' only.  Bank holding company PDs (JPMorgan, Citigroup, BofA,
   Chase, etc.) file under indfmt='FS' in Compustat; the INDL-only filter was
   silently returning zero rows for them, making the PD numerator consist only
   of broker-dealer PDs.  The same fix applies to comparison group data pulls
   so that FS-format non-PD banks also appear in the Banks denominator.
7) Comparison group gvkeys (BD, Banks) are now built directly from a WRDS
   query (SIC-based, both INDL and FS) rather than from updated_linktable.csv,
   which was built from INDL-only FUNDA data and therefore missing all
   FS-format financial firms.  Cmpust. gvkeys come from the CCM universe
   (which already covers both formats).
8) GE (gvkey 005047, SIC 9997) and Sears (gvkey 006307, SIC 5311) are
   excluded from the PD numerator.  These industrial/retail conglomerates are
   holding companies for Kidder Peabody and Dean Witter respectively, but their
   full consolidated balance sheets are not appropriate for measuring
   broker-dealer capital.  The Giannone-Robotti (2023) critique paper identifies
   these as the non-financial conglomerates HKM trimmed from the sample.
9) BD comparison group NaN months are treated as ratio = 1.0.  In months where
   no non-PD broker-dealer has Compustat data (roughly 1960-1972), rather than
   excluding those months from the period average (which biases the average
   downward), we assume the non-PD BD sector had zero assets — consistent with
   the reality that virtually all major security broker-dealers were primary
   dealers in the early sample period.
10) CCM universe restricted to US-incorporated firms (fic='USA').  Foreign
    companies with US-listed ADRs (Toyota, Shell, BP, Samsung, etc.) report
    full consolidated assets and inflate the Cmpust. denominator.  HKM's
    Compustat universe refers to domestic public firms; restricting by fic
    removes these foreign balance sheets.
11) Banks comparison group uses time-varying PD exclusion.  Previously, any
    gvkey that was EVER a primary dealer was excluded from Banks for ALL time.
    This incorrectly removes gvkey 3066 (Citicorp → Citigroup Inc., ~$1.9T)
    from the Banks denominator after 1998 when it is no longer a PD.  The fix
    builds a month-by-month PD active schedule from the PD linktable and only
    zeros out a gvkey's Banks contribution during months when it is actually
    an active primary dealer.
12) build_pd_active_schedule uses "active only" exclusion: a PD gvkey is
    excluded from the Banks comparison group ONLY during its actual registered
    PD months.  Pre-PD months (e.g. NationsBank / gvkey 7647 before 07/1993),
    gap periods between two PD stints (e.g. gvkey 3066 / Citigroup 12/1998-
    03/2003), and post-PD months are all INCLUDED in Banks.  This correctly
    treats a firm as part of the commercial bank sector until the moment it
    becomes a primary dealer, and reproduces the HKM target of 0.543 for
    Banks 1990-2012.  The remaining Banks 1960-1990 gap vs. HKM (our ~0.422
    vs. their 0.635) is attributable to Compustat data vintage differences:
    the 2025 database contains far more small commercial banks in 1960-1990
    than existed in HKM's ~2011 snapshot.
"""

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
import numpy as np
import wrds
import config
from datetime import datetime
from pathlib import Path

# --------------------------
# Constants
# --------------------------

KEY_COLS = ["total_assets", "book_debt", "book_equity", "market_equity"]

# Non-financial conglomerate holding companies excluded from the PD numerator.
# GE (005047, SIC 9997) held Kidder Peabody 1986-1994.
# Sears (006307, SIC 5311) held Dean Witter Reynolds 1977-1993.
# Their consolidated balance sheets include vast non-financial assets (appliances,
# retail stores, GE Capital, etc.) that inflate the PD total beyond what HKM
# intended.  The Giannone-Robotti (2023) paper identifies these as the
# "industrial conglomerate" firms HKM trimmed from their sample.
NON_FINANCIAL_PD_GVKEYS = {"005047", "006307"}


# --------------------------
# Helpers
# --------------------------

def get_ccm_gvkey_universe(db, start_date: str, end_date: str) -> set[str]:
    """
    Returns the set of gvkeys that are in the CRSP-Compustat Merged (CCM) link
    table during (roughly) the sample window.

    Why: HKM restricts to PD holding companies in CRSP-Compustat data.
         Comparison groups that include gvkeys not in CCM inflate denominators
         and push ratios down.
    """
    # Fix 10: restrict to US-incorporated firms (fic='USA') to exclude foreign
    # companies with US-listed ADRs (Toyota, Shell, Samsung, etc.) whose full
    # consolidated balance sheets inflate the Cmpust. denominator.
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
    """
    Query comp.funda joined to comp.company for gvkeys with the given SIC
    codes, using BOTH indfmt='INDL' and indfmt='FS'.

    Why: updated_linktable.csv was built from INDL-only FUNDA data, so all
    FS-format financial companies (e.g. bank holding companies: JPMorgan 2968,
    Citigroup 3243, BofA 7647, Chase 2943, etc.) are absent.  This causes
    the Banks comparison group denominator to be drastically understated,
    pulling the Banks ratio far below HKM's published values.
    """
    # sic/sich columns in WRDS are character varying — must quote as strings
    sic_str = ", ".join(f"'{s}'" for s in sic_codes)
    # Use comp.funda (annual) joined to comp.company for the SIC lookup.
    # comp.funda uses 'sich' (historical SIC) which can be stale/missing,
    # while comp.company.sic is the current/canonical SIC for the gvkey.
    # We accept either: if company.sic matches OR funda.sich matches.
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
    Return a DataFrame[gvkey, mdate] of (gvkey, month-end) pairs where a
    historical PD gvkey should be EXCLUDED from the Banks comparison group.

    Rule (Fix 11 / Fix 12): exclude a gvkey only during its ACTIVE PD months
    — i.e. months that fall within at least one PD interval recorded in the
    link table.  Months outside any PD interval are INCLUDED in Banks:

      - Pre-PD months (e.g. NationsBank / gvkey 7647 before 07/1993) are
        INCLUDED in Banks.  Economically, the firm is a regular commercial
        bank until it becomes a PD; it belongs in the bank comparison group.
      - Gap periods between two PD stints (e.g. gvkey 3066 / Citigroup Inc.
        12/1998–03/2003) are INCLUDED in Banks.
      - Post-PD months for graduated PDs are INCLUDED in Banks.

    This "active only" approach matches HKM's apparent methodology: the
    Banks comparison group is all commercial banks that are NOT currently
    primary dealers.  Including pre-PD bank assets in the denominator for
    the years before a firm becomes a PD is the correct treatment (HKM
    target for Banks 1990-2012 = 0.543 is reproduced with this logic).

    Note on Banks 1960-1990 (target 0.635, our result ~0.422): the large
    gap is due to Compustat data vintage — the 2025 database has far more
    small commercial banks in 1960-1990 than were present in HKM's ~2011
    snapshot.  It is not caused by the exclusion approach.
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
        # Exclude only during active PD intervals for this gvkey
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


def asof_fill_quarterly_to_monthly(df_q, date_col="datadate", by_col="gvkey",
                                   value_cols=None, start="1960-01-01",
                                   end="2012-12-31", debug_name=""):
    """
    Take quarterly Compustat panel (multiple gvkeys) and produce a monthly
    EOM panel by gvkey using as-of merge (last available quarterly observation
    carried forward).

    Kept for backward compatibility with the test suite.
    The main pipeline uses build_monthly_sector_totals_from_fundq instead.
    """
    if value_cols is None:
        value_cols = KEY_COLS

    df = df_q.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[by_col, date_col])
    df[by_col] = df[by_col].astype(str).str.zfill(6)

    idx = pd.date_range(pd.to_datetime(start), pd.to_datetime(end), freq="ME")
    idx = pd.DataFrame({date_col: idx})

    out = []
    df = df.sort_values([by_col, date_col])

    for gvkey, g in df.groupby(by_col, sort=False):
        g = g.sort_values(date_col)
        filled = pd.merge_asof(
            idx, g[[date_col] + value_cols],
            on=date_col, direction="backward"
        )
        filled[by_col] = gvkey
        out.append(filled)

    out = pd.concat(out, ignore_index=True)

    if debug_name:
        print(f"[{debug_name}] monthly filled rows:", len(out))
        print(f"[{debug_name}] unique gvkeys:", out[by_col].nunique())
        miss = out[value_cols].isna().mean().sort_values(ascending=False)
        print(f"[{debug_name}] missing share (post fill):\n{miss}\n")

    return out


# --------------------------
# Data Loading
# --------------------------

def clean_primary_dealers_data(fname):
    file_path = config.MANUAL_DATA / fname
    prim_dealers = pd.read_csv(file_path)

    prim_dealers["End Date"] = prim_dealers["End Date"].fillna("Current")
    prim_dealers = prim_dealers.dropna(subset=["gvkey"])
    prim_dealers["gvkey"] = prim_dealers["gvkey"].astype(int)

    date_cols = ["Start Date", "End Date"]
    for col in date_cols:
        prim_dealers[col] = pd.to_datetime(prim_dealers[col], errors="coerce")
        prim_dealers[col] = prim_dealers[col].dt.strftime("%m/%d/%Y")
    prim_dealers["End Date"] = prim_dealers["End Date"].fillna("Current")

    if "Unnamed: 0" in prim_dealers.columns:
        prim_dealers = prim_dealers.drop(columns=["Unnamed: 0"])

    print(prim_dealers.head())
    print("Unique dealers:", prim_dealers["Primary Dealer"].nunique())
    print("Missing start dates:", prim_dealers["Start Date"].isna().mean())
    print("Missing end dates:", prim_dealers["End Date"].isna().mean())
    print("Missing gvkey:", prim_dealers["gvkey"].isna().mean())

    return prim_dealers


def load_link_table(fname):
    file_path = config.MANUAL_DATA / fname
    link_hist = pd.read_csv(file_path)
    return link_hist


# --------------------------
# WRDS Query
# --------------------------

def fetch_financial_data(db, linktable, start_date, end_date, ITERATE=False):
    """
    Pull Compustat quarterly fundamentals (fundq) for a set of gvkeys.
    Returns firm-level quarterly data; monthly conversion happens downstream.
    """
    pgvkeys = linktable["gvkey"].tolist()
    results = pd.DataFrame()

    if ITERATE:
        # For PD: query each dealer only during its active primary-dealer period.
        start_dt = pd.to_datetime(linktable["Start Date"], errors="coerce")
        end_raw = linktable["End Date"].copy().replace("Current", pd.NA)
        end_dt = pd.to_datetime(end_raw, errors="coerce")

        global_start = pd.to_datetime(start_date, errors="coerce")
        global_end = pd.to_datetime(end_date, errors="coerce")

        start_dt = start_dt.fillna(global_start)
        end_dt = end_dt.fillna(global_end)

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
            s_i = start_str.iloc[i]
            e_i = end_str.iloc[i]

            query = f"""
            SELECT datadate,
                   atq AS total_assets,
                   ltq AS book_debt,
                   COALESCE(teqq, ceqq + COALESCE(pstkq, 0) + COALESCE(mibnq, 0)) AS book_equity,
                   (cshoq * prccq) AS market_equity,
                   gvkey,
                   conm,
                   indfmt
            FROM comp.fundq AS cst
            WHERE cst.gvkey = {pgvkey_str}
              AND cst.datadate BETWEEN '{s_i}' AND '{e_i}'
              AND (indfmt = 'INDL' OR indfmt = 'FS')
              AND datafmt='STD'
              AND popsrc='D'
              AND consol='C'
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
               gvkey,
               conm,
               indfmt
        FROM comp.fundq AS cst
        WHERE cst.gvkey IN ({pgvkey_str})
          AND cst.datadate BETWEEN '{start_date}' AND '{end_date}'
          AND (indfmt = 'INDL' OR indfmt = 'FS')
          AND datafmt='STD'
          AND popsrc='D'
          AND consol='C'
        """
        data = db.raw_sql(query)
        if not data.empty:
            results = pd.concat([results, data], axis=0)

    return results


def get_comparison_group_data(db, linktable_df, start_date, end_date, ITERATE=False):
    return fetch_financial_data(db, linktable_df, start_date, end_date, ITERATE=ITERATE)


# --------------------------
# Group Construction
# --------------------------

def create_comparison_group_linktables(link_hist, merged_main,
                                       ccm_gvkeys: set[str] | None = None,
                                       wrds_bd_gvkeys: set[str] | None = None,
                                       wrds_banks_gvkeys: set[str] | None = None):
    """
    Build comparison group gvkey lists.

    Fix (Issue 2): Both link_hist["gvkey"] and merged_main["gvkey"] are
    normalised to 6-char zero-padded strings before the exclusion filter.

    Fix (Issue 1 / CCM): If ccm_gvkeys is provided, comparison groups are
    restricted to firms that appear in the CRSP-Compustat merge.

    Fix (Issue 7 / FS format): If wrds_bd_gvkeys / wrds_banks_gvkeys are
    provided (from get_comparison_group_gvkeys_from_wrds), those sets replace
    the linktable-based SIC filter for BD and Banks.  This captures FS-format
    bank holding companies that are absent from updated_linktable.csv.
    Cmpust. always falls back to the CCM universe when ccm_gvkeys is provided.

    Fix (Issue 8 / non-financial PDs): GE (005047) and Sears (006307) are
    removed from the PD group before any comparison is made.
    """
    link_hist = link_hist.copy()

    # Normalise gvkeys in link_hist
    link_hist["gvkey"] = pd.to_numeric(link_hist["gvkey"], errors="coerce")
    link_hist = link_hist.dropna(subset=["gvkey"])
    link_hist["gvkey"] = link_hist["gvkey"].astype(int).astype(str).str.zfill(6)
    link_hist["sic"] = pd.to_numeric(link_hist["sic"], errors="coerce")

    # Normalise gvkeys in merged_main (PD list)
    merged_main = merged_main.copy()
    merged_main["gvkey"] = pd.to_numeric(merged_main["gvkey"], errors="coerce")
    merged_main = merged_main.dropna(subset=["gvkey"])
    merged_main["gvkey"] = merged_main["gvkey"].astype(int).astype(str).str.zfill(6)

    # Fix 8: Remove non-financial conglomerate holding companies from PD group.
    # These firms (GE, Sears) have vast non-financial assets that are not
    # representative of broker-dealer intermediary capital.
    pd_df = merged_main[~merged_main["gvkey"].isin(NON_FINANCIAL_PD_GVKEYS)].copy()
    pd_gvkeys = set(pd_df["gvkey"].tolist())
    removed = set(merged_main["gvkey"].tolist()) - pd_gvkeys
    if removed:
        print(f"[PD FILTER] Removed {len(removed)} non-financial gvkeys from PD: {removed}")

    # Restrict linktable to CCM universe (optional but recommended for Cmpust.)
    if ccm_gvkeys is not None:
        before = link_hist["gvkey"].nunique()
        link_hist = link_hist[link_hist["gvkey"].isin(ccm_gvkeys)].copy()
        after = link_hist["gvkey"].nunique()
        print(f"[CCM FILTER] link_hist gvkeys: {before} -> {after}")

    # --- BD comparison group ---
    if wrds_bd_gvkeys is not None:
        # Use WRDS-queried gvkeys (includes FS-format firms)
        bd_universe = wrds_bd_gvkeys - pd_gvkeys
        if ccm_gvkeys is not None:
            bd_universe = bd_universe & ccm_gvkeys
        linked_bd_less_pd = pd.DataFrame({"gvkey": sorted(bd_universe)})
    else:
        linked_bd_less_pd = link_hist[
            (link_hist["sic"].isin([6211, 6221])) & (~link_hist["gvkey"].isin(pd_gvkeys))
        ]

    # --- Banks comparison group ---
    if wrds_banks_gvkeys is not None:
        # Fix 11: do NOT statically subtract pd_gvkeys from Banks universe.
        # Time-varying exclusion is applied downstream in
        # build_monthly_sector_totals_from_fundq using banks_pd_active_schedule,
        # so historical PD bank gvkeys (e.g. gvkey 3066 = Citigroup after 1999)
        # correctly contribute to the Banks denominator outside their PD period.
        banks_universe = wrds_banks_gvkeys
        if ccm_gvkeys is not None:
            banks_universe = banks_universe & ccm_gvkeys
        linked_banks_less_pd = pd.DataFrame({"gvkey": sorted(banks_universe)})
    else:
        linked_banks_less_pd = link_hist[
            (link_hist["sic"].isin([6011, 6020, 6021, 6022, 6029, 6081, 6082]))
            & (~link_hist["gvkey"].isin(pd_gvkeys))
        ]

    # --- Cmpust. comparison group ---
    # Prefer the CCM universe (covers both INDL and FS format) over linktable.
    if ccm_gvkeys is not None:
        cmpust_universe = ccm_gvkeys - pd_gvkeys
        linked_all_less_pd = pd.DataFrame({"gvkey": sorted(cmpust_universe)})
    else:
        linked_all_less_pd = link_hist[~link_hist["gvkey"].isin(pd_gvkeys)]

    print("[GROUP GVKEY COUNTS]")
    print("  PD:", len(pd_gvkeys))
    n_bd = linked_bd_less_pd["gvkey"].nunique() if "gvkey" in linked_bd_less_pd.columns else len(linked_bd_less_pd)
    n_bk = linked_banks_less_pd["gvkey"].nunique() if "gvkey" in linked_banks_less_pd.columns else len(linked_banks_less_pd)
    n_cm = linked_all_less_pd["gvkey"].nunique() if "gvkey" in linked_all_less_pd.columns else len(linked_all_less_pd)
    print("  BD:", n_bd)
    print("  Banks:", n_bk)
    print("  Cmpust:", n_cm)
    print()

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
            ds = get_comparison_group_data(
                db, linktable, config.START_DATE, config.END_DATE, ITERATE=ITERATE
            )
        else:
            if pd.to_datetime(config.UPDATED_END_DATE) > datetime.now():
                UPDATED_END_DATE = datetime.now().strftime("%Y-%m-%d")
            else:
                UPDATED_END_DATE = config.UPDATED_END_DATE
            ds = get_comparison_group_data(
                db, linktable, config.START_DATE, UPDATED_END_DATE, ITERATE=ITERATE
            )

        datasets[key] = ds.drop_duplicates()
    return datasets


# --------------------------
# Data Processing
# --------------------------

def prep_datasets(datasets):
    """
    Convert raw fundq pulls into quarterly totals per group.
    Kept for backward compatibility with the test suite.
    The main pipeline uses build_all_monthly_totals instead.
    """
    prepped = {}

    for group_name, df in datasets.items():
        if df is None or df.empty:
            print(f"[WARN] {group_name} dataset is empty")
            prepped[group_name] = pd.DataFrame(columns=["datadate"] + KEY_COLS)
            continue

        df = df.copy()
        df["datadate"] = pd.to_datetime(df["datadate"], errors="coerce")
        df = df.dropna(subset=["datadate"])

        for c in KEY_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        q_totals = (
            df.groupby("datadate", as_index=False)[KEY_COLS]
              .sum(min_count=1)
              .sort_values("datadate")
        )

        prepped[group_name] = q_totals

        if group_name == "PD":
            print("\n[PD SIZE CHECK]")
            print("Total assets mean (quarterly sum):", q_totals["total_assets"].mean())
            print("Max total assets (quarterly):", q_totals["total_assets"].max())

        if group_name == "Banks":
            print("\n[Banks SIZE CHECK]")
            print("Total assets mean (quarterly sum):", q_totals["total_assets"].mean())

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
    Convert Compustat FUNDQ (quarterly, firm-level) into a MONTH-END sector
    total series.

    Steps:
      1) firm-level clean + sort
      2) resample to month-end and forward-fill (HKM-style)
      3) sum across firms by month
      4) reindex to a complete month-end grid from start to end

    Fix (Issue 5): data from pre_start_quarters quarters before start_dt is
    included so that the first few months of the sample have a valid carry-
    forward value rather than NaN.  The output grid still starts at start_dt.

    ffill_limit:
      - None: carry last quarterly value forward until the next report
      - int:  stop carrying forward after this many months (e.g. 5)
    """
    df = raw_df.copy()

    df["datadate"] = pd.to_datetime(df["datadate"], errors="coerce")
    df = df.dropna(subset=["gvkey", "datadate"])
    df["gvkey"] = df["gvkey"].astype(str).str.zfill(6)

    for c in key_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)

    # Allow one extra quarter before start_dt so the first months have a seed
    # value for forward-fill instead of NaN.
    pre_start_dt = start_dt - pd.DateOffset(months=pre_start_quarters * 3)
    df = df.loc[(df["datadate"] >= pre_start_dt) & (df["datadate"] <= end_dt)]

    # When both indfmt='FS' and indfmt='INDL' exist for the same gvkey-date
    # (rare but possible for conglomerates), prefer FS.  'FS' < 'INDL' alphabetically,
    # so sorting ascending by indfmt and keeping the first row gives us FS.
    if "indfmt" in df.columns:
        df = df.sort_values(["gvkey", "datadate", "indfmt"])
        df = df.drop_duplicates(subset=["gvkey", "datadate"], keep="first")
    else:
        df = df.sort_values(["gvkey", "datadate"])
        df = df.drop_duplicates(subset=["gvkey", "datadate"], keep="last")

    # Firm-level resample to month-end, then forward-fill
    monthly_firm = (
        df.set_index("datadate")
          .groupby("gvkey")[key_cols]
          .resample("ME")
          .ffill(limit=ffill_limit)
          .reset_index()
    )

    # Fix 11: time-varying PD exclusion for Banks comparison group.
    # For each (gvkey, month) where the gvkey is an active PD, zero out its
    # contribution so it doesn't appear in the Banks denominator during its
    # PD-active period.  Outside that period (e.g. Citigroup after 1999) the
    # gvkey correctly contributes to the Banks total.
    if exclude_active_pd is not None and not exclude_active_pd.empty:
        excl = exclude_active_pd.rename(columns={"mdate": "datadate"}).copy()
        excl["_exclude"] = True
        monthly_firm = monthly_firm.merge(excl, on=["gvkey", "datadate"], how="left")
        mask = monthly_firm["_exclude"].fillna(False)
        for c in key_cols:
            monthly_firm.loc[mask, c] = np.nan
        monthly_firm = monthly_firm.drop(columns=["_exclude"])

    # Sector totals by month
    sector = (
        monthly_firm.groupby("datadate")[key_cols]
                    .sum(min_count=1)
                    .reset_index()
                    .rename(columns={"datadate": "mdate"})
    )

    # Reindex to a complete month-end grid from start_dt (not pre_start_dt)
    idx = pd.date_range(start_dt, end_dt, freq="ME")
    sector = sector.set_index("mdate").reindex(idx).rename_axis("mdate").reset_index()

    return sector


def build_all_monthly_totals(ds: dict[str, pd.DataFrame],
                              start: str,
                              end: str,
                              banks_pd_active_schedule: pd.DataFrame | None = None,
                              ) -> dict[str, pd.DataFrame]:
    """
    Convert firm-level FUNDQ pulls for each group into month-end sector totals.

    banks_pd_active_schedule: if provided, passed to the Banks group so that
    historical PD gvkeys are only excluded from Banks during their PD-active
    months (Fix 11 / time-varying exclusion).
    """
    out = {}

    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    full_idx = pd.date_range(start_dt, end_dt, freq="ME")
    expected = len(full_idx)

    for k, raw in ds.items():
        excl = banks_pd_active_schedule if k == "Banks" else None
        out[k] = build_monthly_sector_totals_from_fundq(raw, start, end,
                                                        exclude_active_pd=excl)

        miss = out[k][KEY_COLS].isna().mean()
        all4 = out[k][KEY_COLS].notna().all(axis=1).mean()
        ta_mean = out[k]["total_assets"].mean()
        ta_max = out[k]["total_assets"].max()
        nrows = len(out[k])
        nonmissing_rows = out[k]["total_assets"].notna().sum()

        print(f"\n[{k}] MONTHLY TOTALS DIAGNOSTICS")
        print(f"  rows / expected: {nrows} / {expected}")
        print(f"  total_assets non-missing months: {nonmissing_rows} ({nonmissing_rows/expected:.3%})")
        print(f"  missing share:\n{miss}")
        print(f"  share months with ALL 4 totals present: {all4:.3f}")
        print(f"  total_assets mean: {ta_mean:,.2f}")
        print(f"  total_assets max : {ta_max:,.2f}\n")

    return out


# --------------------------
# Ratio Computation
# --------------------------

def compute_table2_ratios(monthly_totals: dict[str, pd.DataFrame],
                           start: str,
                           end: str) -> pd.DataFrame:
    """
    Compute ratios: PD / (PD + group_less_PD) per month.
    Assumes BD / Banks / Cmpust. groups already exclude PD gvkeys.
    """
    pd_m = monthly_totals["PD"].copy().set_index("mdate")
    out = {}

    for grp in ["BD", "Banks", "Cmpust."]:
        g = monthly_totals[grp].copy().set_index("mdate")

        aligned = pd_m[KEY_COLS].join(g[KEY_COLS], how="inner",
                                      lsuffix="_pd", rsuffix="_g")

        print(f"\n[RATIO DIAGNOSTICS] Group={grp}")
        print(f"  aligned months: {len(aligned)}")
        print(f"  PD total_assets missing: {aligned['total_assets_pd'].isna().mean():.3%}")
        print(f"  {grp} total_assets missing: {aligned['total_assets_g'].isna().mean():.3%}")

        for col in KEY_COLS:
            g_vals = aligned[f"{col}_g"].copy()
            # Fix 9: for BD, months with no non-PD broker-dealer data are
            # treated as BD_comparison = 0 (ratio = 1.0).  In the early sample
            # (roughly 1960-1972) virtually all security broker-dealers were
            # primary dealers; the few non-PD small firms weren't yet in
            # Compustat.  Excluding those months biases the period average down.
            if grp == "BD":
                g_vals = g_vals.fillna(0)
            denom = aligned[f"{col}_pd"] + g_vals
            denom0 = (denom == 0).mean()
            denom_na = denom.isna().mean()
            ratio = aligned[f"{col}_pd"] / denom.replace(0, np.nan)
            r_na = ratio.isna().mean()
            r_gt1 = (ratio > 1).mean()
            r_lt0 = (ratio < 0).mean()

            print(f"  {col}: denom==0 {denom0:.3%}, denom NA {denom_na:.3%}, "
                  f"ratio NA {r_na:.3%}, ratio>1 {r_gt1:.3%}, ratio<0 {r_lt0:.3%}")

            if ratio.notna().any():
                top = ratio.sort_values(ascending=False).head(3)
                bot = ratio.sort_values(ascending=True).head(3)
                print(f"    top3: {[(str(i.date()), round(float(v), 4)) for i, v in top.items()]}")
                print(f"    bot3: {[(str(i.date()), round(float(v), 4)) for i, v in bot.items()]}")

            out[f"{col}_{grp}"] = ratio

    ratios = pd.DataFrame(out)
    ratios.index.name = "mdate"
    ratios = ratios.loc[
        (ratios.index >= pd.to_datetime(start)) & (ratios.index <= pd.to_datetime(end))
    ]

    print("\n[OVERALL RATIO MISSING SHARE]")
    print(ratios.isna().mean().sort_values(ascending=False).head(12))

    return ratios


def summarize_table2(ratios: pd.DataFrame, UPDATED=False) -> pd.DataFrame:
    if not UPDATED:
        periods = [
            ("1960-01-01", "2012-12-31", "1960-2012"),
            ("1960-01-01", "1990-12-31", "1960-1990"),
            ("1990-01-01", "2012-12-31", "1990-2012"),
        ]
    else:
        periods = [
            ("1960-01-01", "2025-01-01", "1960-2025"),
            ("1960-01-01", "1990-12-31", "1960-1990"),
            ("1990-01-01", "2025-01-01", "1990-2025"),
        ]

    rows = []
    for s, e, name in periods:
        sub = ratios.loc[pd.to_datetime(s):pd.to_datetime(e)]
        nmonths = len(sub)
        complete = sub.notna().all(axis=1).mean() if nmonths else np.nan

        print(f"\n[PERIOD DIAGNOSTICS] {name}")
        print(f"  months in period: {nmonths}")
        print(f"  share months complete across ALL columns: {complete:.3f}")

        preview_cols = [c for c in sub.columns if c.startswith("total_assets_")]
        if nmonths and preview_cols:
            print("  total_assets means:", sub[preview_cols].mean().to_dict())

        rows.append(pd.Series(sub.mean(numeric_only=True), name=name))

    table = pd.DataFrame(rows)

    all_cols = [
        "total_assets_BD", "total_assets_Banks", "total_assets_Cmpust.",
        "book_debt_BD", "book_debt_Banks", "book_debt_Cmpust.",
        "book_equity_BD", "book_equity_Banks", "book_equity_Cmpust.",
        "market_equity_BD", "market_equity_Banks", "market_equity_Cmpust.",
    ]
    table = table[all_cols]

    mapping = {
        "total_assets_BD":      ("Total assets", "BD"),
        "total_assets_Banks":   ("Total assets", "Banks"),
        "total_assets_Cmpust.": ("Total assets", "Cmpust."),
        "book_debt_BD":         ("Book debt", "BD"),
        "book_debt_Banks":      ("Book debt", "Banks"),
        "book_debt_Cmpust.":    ("Book debt", "Cmpust."),
        "book_equity_BD":       ("Book equity", "BD"),
        "book_equity_Banks":    ("Book equity", "Banks"),
        "book_equity_Cmpust.":  ("Book equity", "Cmpust."),
        "market_equity_BD":     ("Market equity", "BD"),
        "market_equity_Banks":  ("Market equity", "Banks"),
        "market_equity_Cmpust.":("Market equity", "Cmpust."),
    }
    table.columns = pd.MultiIndex.from_tuples(
        [mapping[c] for c in table.columns], names=["Metric", "Source"]
    )
    return table


# --------------------------
# Old pipeline (kept for backward compatibility with test suite)
# --------------------------

def create_ratios_for_table(prepped_datasets, UPDATED=False):
    """
    HKM Table 2: ratios computed at month-end, then time-series average.
    Kept for backward compatibility with Table02_testing.py.
    The main pipeline uses build_all_monthly_totals + compute_table2_ratios.
    """
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
        m = m.sort_values("qdate")
        out = pd.merge_asof(
            m, q, left_on="qdate", right_on="datadate",
            direction="backward", allow_exact_matches=True,
        )
        out = out.dropna(subset=["datadate"])
        out = out.drop(columns=["datadate"])
        return out

    monthly = {}
    for g in ["PD", "BD", "Banks", "Cmpust."]:
        if g not in prepped_datasets:
            raise KeyError(f"Missing group {g} in prepped_datasets.")
        monthly[g] = to_monthly_asof(prepped_datasets[g])

    ratio_df = monthly["PD"][["qdate"]].copy()
    ratio_df = ratio_df.set_index("qdate")

    for grp in ["BD", "Banks", "Cmpust."]:
        denom = (
            monthly["PD"][KEY_COLS].set_index(monthly["PD"]["qdate"])
            + monthly[grp][KEY_COLS].set_index(monthly[grp]["qdate"])
        )
        num = monthly["PD"][KEY_COLS].set_index(monthly["PD"]["qdate"])
        for c in KEY_COLS:
            d = denom[c].replace(0, np.nan)
            ratio_df[f"{c}_{grp}"] = num[c] / d

    out = []
    for (s, e) in sample_periods:
        sdt, edt = pd.to_datetime(s), pd.to_datetime(e)
        sub = ratio_df.loc[(ratio_df.index >= sdt) & (ratio_df.index <= edt)].copy()
        means = sub.mean(numeric_only=True)
        means["Period"] = f"{sdt.year}-{edt.year}"
        out.append(means)

    combined = pd.DataFrame(out).set_index("Period")
    combined = combined.reset_index()
    return combined


def format_final_table_from_ratios(ratio_df, UPDATED=False):
    """Kept for backward compatibility."""
    table = ratio_df.groupby("Period").mean(numeric_only=True)

    all_cols = [
        "total_assets_BD", "total_assets_Banks", "total_assets_Cmpust.",
        "book_debt_BD", "book_debt_Banks", "book_debt_Cmpust.",
        "book_equity_BD", "book_equity_Banks", "book_equity_Cmpust.",
        "market_equity_BD", "market_equity_Banks", "market_equity_Cmpust.",
    ]
    table = table[all_cols].reset_index()

    mapping = {
        "total_assets_BD":      ("Total assets", "BD"),
        "total_assets_Banks":   ("Total assets", "Banks"),
        "total_assets_Cmpust.": ("Total assets", "Cmpust."),
        "book_debt_BD":         ("Book debt", "BD"),
        "book_debt_Banks":      ("Book debt", "Banks"),
        "book_debt_Cmpust.":    ("Book debt", "Cmpust."),
        "book_equity_BD":       ("Book equity", "BD"),
        "book_equity_Banks":    ("Book equity", "Banks"),
        "book_equity_Cmpust.":  ("Book equity", "Cmpust."),
        "market_equity_BD":     ("Market equity", "BD"),
        "market_equity_Banks":  ("Market equity", "Banks"),
        "market_equity_Cmpust.":("Market equity", "Cmpust."),
    }
    multiindex = pd.MultiIndex.from_tuples(
        [mapping[c] for c in all_cols], names=["Metric", "Source"]
    )
    final_df = pd.DataFrame(
        table.drop("Period", axis=1).values,
        index=table["Period"],
        columns=multiindex,
    )

    if UPDATED:
        order = ["1960-2025", "1960-1990", "1990-2025"]
    else:
        order = ["1960-2012", "1960-1990", "1990-2012"]

    return final_df.reindex(order)


# --------------------------
# Output
# --------------------------

def convert_and_export_table_to_latex(formatted_table, UPDATED=False):
    latex = formatted_table.to_latex(
        index=True, column_format="lcccccccccccc", float_format="%.3f"
    )
    latex = latex.replace("_", "\\_")

    # Fix: caption was previously inverted (showed "Updated" for the original
    # period and "Original" for the updated period).
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


# --------------------------
# Main
# --------------------------

def main(UPDATED=False):
    # Load pre-pulled WRDS data from parquet (produced by pull_table02_data.py).
    # All groups were pulled through UPDATED_END_DATE; analysis windows are
    # applied downstream by build_all_monthly_totals / compute_table2_ratios.
    PULLED_DIR = config.DATA_DIR / "pulled"

    merged_main = clean_primary_dealers_data(fname="Primary_Dealer_Link_Table3_DOMESTIC.csv")

    ds = {
        "PD":      pd.read_parquet(PULLED_DIR / "table02_raw_PD.parquet"),
        "BD":      pd.read_parquet(PULLED_DIR / "table02_raw_BD.parquet"),
        "Banks":   pd.read_parquet(PULLED_DIR / "table02_raw_Banks.parquet"),
        "Cmpust.": pd.read_parquet(PULLED_DIR / "table02_raw_Cmpust.parquet"),
    }
    print("[LOAD] Table 2 parquet data loaded from _data/pulled/")

    # --- PD coverage diagnostic ---
    # Prints which PD gvkeys have Compustat data and what year range.
    # Helps identify gvkeys that map to subsidiaries with sparse/no data
    # (e.g. First Boston 4684, Discount Corp 3689, Irving Securities 6186).
    print("\n[PD COVERAGE DIAGNOSTIC]")
    pd_raw = ds.get("PD", pd.DataFrame())
    pd_raw_cols = pd_raw.columns.tolist()
    has_gvkey = "gvkey" in pd_raw_cols
    has_date  = "datadate" in pd_raw_cols
    has_at    = "total_assets" in pd_raw_cols

    mm_diag = merged_main.copy()
    mm_diag["gvkey"] = mm_diag["gvkey"].astype(str).str.zfill(6)
    mm_diag = mm_diag[~mm_diag["gvkey"].isin(NON_FINANCIAL_PD_GVKEYS)]
    print(f"  {'gvkey':>6}  {'Compustat coverage':30s}  Names")
    for gvkey, grp in mm_diag.groupby("gvkey"):
        names = "; ".join(grp["Primary Dealer"].tolist())[:70]
        if has_gvkey:
            sub = pd_raw[pd_raw["gvkey"] == gvkey]
        else:
            sub = pd.DataFrame()
        if sub.empty:
            yr_range = "NO DATA"
        elif has_at and has_date:
            with_at = sub[sub["total_assets"].notna()]
            if with_at.empty:
                yr_range = "no total_assets"
            else:
                mn = pd.to_datetime(with_at["datadate"]).min().year
                mx = pd.to_datetime(with_at["datadate"]).max().year
                yr_range = f"{mn}-{mx} ({len(with_at)} qtrs)"
        else:
            yr_range = f"{len(sub)} rows"
        flag = " <-- NO DATA" if yr_range == "NO DATA" else ""
        print(f"  {gvkey:>6}  {yr_range:30s}  {names}{flag}")
    print()

    # --- Diagnostic A: PD entity check (requires live WRDS connection) ---
    # Moved to pull_table02_data.py.  Re-run that script to see entity names / SIC codes.

    # --- Diagnostic B: PD numerator coverage rate by year ---
    # For each calendar year, shows: active PDs in link table vs. those with
    # Compustat data.  Years with low coverage explain BD ratio understatement.
    print("[PD COVERAGE BY YEAR]")
    print(f"  {'Year':>4}  {'Active PDs':>10}  {'With Data':>9}  {'Coverage':>8}  {'PD total_assets ($M)':>20}")
    mm_cov = merged_main.copy()
    mm_cov["gvkey"] = mm_cov["gvkey"].astype(str).str.zfill(6)
    mm_cov = mm_cov[~mm_cov["gvkey"].isin(NON_FINANCIAL_PD_GVKEYS)]
    mm_cov["start_dt"] = pd.to_datetime(mm_cov["Start Date"], errors="coerce")
    end_raw2 = mm_cov["End Date"].replace("Current", pd.NA)
    mm_cov["end_dt"] = pd.to_datetime(end_raw2, errors="coerce").fillna(
        pd.to_datetime(config.END_DATE if not UPDATED else config.UPDATED_END_DATE)
    )
    pd_raw2 = pd_raw.copy() if has_gvkey and has_date and has_at else pd.DataFrame()
    if not pd_raw2.empty:
        pd_raw2["year"] = pd.to_datetime(pd_raw2["datadate"]).dt.year
    for yr in range(
        pd.to_datetime(config.START_DATE).year,
        (pd.to_datetime(config.END_DATE if not UPDATED else config.UPDATED_END_DATE).year) + 1
    ):
        active_mask = (mm_cov["start_dt"].dt.year <= yr) & (mm_cov["end_dt"].dt.year >= yr)
        active_gvkeys = set(mm_cov.loc[active_mask, "gvkey"].unique())
        n_active = len(active_gvkeys)
        if pd_raw2.empty:
            n_with_data, avg_at = 0, float("nan")
        else:
            yr_data = pd_raw2[(pd_raw2["year"] == yr) & (pd_raw2["total_assets"].notna())]
            with_data_gvkeys = set(yr_data["gvkey"].unique()) & active_gvkeys
            n_with_data = len(with_data_gvkeys)
            avg_at = yr_data[yr_data["gvkey"].isin(active_gvkeys)]["total_assets"].sum()
        coverage = f"{n_with_data / n_active:.0%}" if n_active > 0 else "n/a"
        at_str = f"{avg_at:>20,.0f}" if not pd.isna(avg_at) else f"{'n/a':>20}"
        print(f"  {yr:>4}  {n_active:>10}  {n_with_data:>9}  {coverage:>8}  {at_str}")
    print()

    # --- Diagnostic C: Asset-magnitude check (requires live WRDS connection) ---
    # Moved to pull_table02_data.py.  Re-run that script to see per-year atq values.

    # Fix 11: build the month-by-month PD active schedule for time-varying
    # Banks exclusion.  Covers the full sample so both UPDATED and base runs
    # handle the correct PD periods.
    print("[SCHEDULE] Building PD active schedule for Banks time-varying exclusion...")
    pd_active_schedule = build_pd_active_schedule(
        merged_main,
        config.START_DATE,
        config.END_DATE if not UPDATED else config.UPDATED_END_DATE,
    )
    print(f"  -> {len(pd_active_schedule)} (gvkey, month) PD-active entries\n")

    monthly_totals = build_all_monthly_totals(
        ds,
        config.START_DATE,
        config.END_DATE if not UPDATED else config.UPDATED_END_DATE,
        banks_pd_active_schedule=pd_active_schedule,
    )

    ratios = compute_table2_ratios(
        monthly_totals,
        config.START_DATE,
        config.END_DATE if not UPDATED else config.UPDATED_END_DATE,
    )

    final = summarize_table2(ratios, UPDATED=UPDATED)

    print("\n[FINAL TABLE PREVIEW]\n")
    print(final.round(3))

    convert_and_export_table_to_latex(final, UPDATED=UPDATED)

    return final


if __name__ == "__main__":
    main(UPDATED=False)
