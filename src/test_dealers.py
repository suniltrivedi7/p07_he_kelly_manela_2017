import pandas as pd
from Table02Prep import clean_primary_dealers_data
import config

# Load RAW file directly (before cleaning)
raw_path = config.MANUAL_DATA / "Primary_Dealer_Link_Table3.csv"
raw = pd.read_csv(raw_path)

print("\n=== RAW FILE ===")
print("Unique dealers (raw):", raw["Primary Dealer"].nunique())
print("Total rows (raw):", len(raw))
print("Missing gvkey (raw):", raw["gvkey"].isna().mean())

# Now load cleaned version
cleaned = clean_primary_dealers_data("Primary_Dealer_Link_Table3.csv")

print("\n=== CLEANED VERSION ===")
print("Unique dealers (cleaned):", cleaned["Primary Dealer"].nunique())
print("Total rows (cleaned):", len(cleaned))
print("Missing gvkey (cleaned):", cleaned["gvkey"].isna().mean())

missing = raw[raw["gvkey"].isna()]

print("\n=== DEALERS MISSING GVKEY ===")
print("Count:", missing["Primary Dealer"].nunique())
print(missing["Primary Dealer"].unique())