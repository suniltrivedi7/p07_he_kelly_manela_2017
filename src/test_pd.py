from Table02Prep import clean_primary_dealers_data

# Replace filename with whatever you actually pass in main()
fname = "Primary_Dealer_Link_Table3.csv"

df = clean_primary_dealers_data(fname)

print("\n=== HEAD ===")
print(df.head())

print("\n=== COLUMNS ===")
print(df.columns)

print("\nUnique dealers:", df["Primary Dealer"].nunique())

print("Missing Start Date:", df["Start Date"].isna().mean())
print("Missing End Date:", df["End Date"].isna().mean())
print("Missing gvkey:", df["gvkey"].isna().mean())