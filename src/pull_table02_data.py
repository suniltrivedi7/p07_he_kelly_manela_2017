"""
pull_table02_data.py

Pulls all WRDS data required for Table 2 replication and saves to
_data/pulled/ as parquet files.  Run this once (via doit) before
Table02Prep.main().

Targets
-------
  _data/pulled/table02_ccm_gvkeys.parquet
  _data/pulled/table02_bd_gvkeys.parquet
  _data/pulled/table02_banks_gvkeys.parquet
  _data/pulled/table02_raw_PD.parquet
  _data/pulled/table02_raw_BD.parquet
  _data/pulled/table02_raw_Banks.parquet
  _data/pulled/table02_raw_Cmpust.parquet

All data is pulled through UPDATED_END_DATE (max coverage).
Both Table02Prep.main(UPDATED=False) and main(UPDATED=True) load from
these files and filter to their respective analysis windows downstream.
"""

from datetime import datetime

import pandas as pd
import wrds

import config
from Table02Prep import (
    clean_primary_dealers_data,
    create_comparison_group_linktables,
    get_ccm_gvkey_universe,
    get_comparison_group_gvkeys_from_wrds,
    load_link_table,
    pull_data_for_all_comparison_groups,
)

PULLED_DIR = config.DATA_DIR / "pulled"

# SIC codes — must match Table02Prep.main()
BD_SICS = [6211]
BANK_SICS = [6020, 6021, 6022]

# Maps ds dict keys to parquet file names (avoids dot in "Cmpust." filenames)
GROUP_FILES = {
    "PD":      "table02_raw_PD.parquet",
    "BD":      "table02_raw_BD.parquet",
    "Banks":   "table02_raw_Banks.parquet",
    "Cmpust.": "table02_raw_Cmpust.parquet",
}


def main():
    """Pull all Table 2 WRDS data and save to _data/pulled/."""
    PULLED_DIR.mkdir(parents=True, exist_ok=True)

    # Cap end date at today if UPDATED_END_DATE is in the future
    end_date = config.UPDATED_END_DATE
    if pd.to_datetime(end_date) > pd.Timestamp(datetime.now()):
        end_date = datetime.now().strftime("%Y-%m-%d")

    db = wrds.Connection(wrds_username=config.WRDS_USERNAME)

    # ------------------------------------------------------------------
    # 1. CCM gvkey universe
    # ------------------------------------------------------------------
    print("[PULL] CCM gvkey universe...")
    ccm_gvkeys = get_ccm_gvkey_universe(db, config.START_DATE, end_date)
    pd.DataFrame({"gvkey": sorted(ccm_gvkeys)}).to_parquet(
        PULLED_DIR / "table02_ccm_gvkeys.parquet", index=False
    )
    print(f"  -> {len(ccm_gvkeys)} gvkeys saved\n")

    # ------------------------------------------------------------------
    # 2. BD comparison group gvkeys (INDL + FS, SIC 6211)
    # ------------------------------------------------------------------
    print("[PULL] BD comparison group gvkeys (INDL + FS)...")
    wrds_bd_gvkeys = get_comparison_group_gvkeys_from_wrds(
        db, BD_SICS, config.START_DATE, end_date
    )
    pd.DataFrame({"gvkey": sorted(wrds_bd_gvkeys)}).to_parquet(
        PULLED_DIR / "table02_bd_gvkeys.parquet", index=False
    )
    print(f"  -> {len(wrds_bd_gvkeys)} BD gvkeys saved\n")

    # ------------------------------------------------------------------
    # 3. Banks comparison group gvkeys (INDL + FS, SIC 6020/6021/6022)
    # ------------------------------------------------------------------
    print("[PULL] Banks comparison group gvkeys (INDL + FS)...")
    wrds_banks_gvkeys = get_comparison_group_gvkeys_from_wrds(
        db, BANK_SICS, config.START_DATE, end_date
    )
    pd.DataFrame({"gvkey": sorted(wrds_banks_gvkeys)}).to_parquet(
        PULLED_DIR / "table02_banks_gvkeys.parquet", index=False
    )
    print(f"  -> {len(wrds_banks_gvkeys)} Banks gvkeys saved\n")

    # ------------------------------------------------------------------
    # 4. Build group linktables (needed to define which gvkeys to pull)
    # ------------------------------------------------------------------
    print("[PULL] Building comparison group linktables...")
    merged_main = clean_primary_dealers_data(
        "Primary_Dealer_Link_Table3_DOMESTIC.csv"
    )
    link_hist = load_link_table("updated_linktable.csv")

    group_links = create_comparison_group_linktables(
        link_hist,
        merged_main,
        ccm_gvkeys=ccm_gvkeys,
        wrds_bd_gvkeys=wrds_bd_gvkeys,
        wrds_banks_gvkeys=wrds_banks_gvkeys,
    )

    # ------------------------------------------------------------------
    # 5. Pull raw fundq data for all groups (use UPDATED=True for max range)
    # ------------------------------------------------------------------
    print("[PULL] Pulling raw fundq data for all groups...")
    ds = pull_data_for_all_comparison_groups(db, group_links, UPDATED=True)

    for key, df in ds.items():
        fname = GROUP_FILES[key]
        df.to_parquet(PULLED_DIR / fname, index=False)
        print(f"  [{key}] {len(df)} rows -> {fname}")

    db.close()
    print("\n[PULL] All Table 2 data saved to _data/pulled/")


if __name__ == "__main__":
    main()
