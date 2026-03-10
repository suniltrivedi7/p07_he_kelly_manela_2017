from Table02Prep import main, clean_primary_dealers_data, load_link_table, create_comparison_group_linktables
from Table02Prep import pull_data_for_all_comparison_groups, prep_datasets, create_ratios_for_table
import wrds
import config

# Option 1 (simplest): just run the pipeline and print the final table
final_table = main(UPDATED=False)
print(final_table)

# If you specifically want the raw ratios by period:
# db = wrds.Connection(wrds_username=config.WRDS_USERNAME)
# merged_main = clean_primary_dealers_data(fname='Primary_Dealer_Link_Table3.csv')
# link_hist = load_link_table(fname='updated_linktable.csv')
# link_dict = create_comparison_group_linktables(link_hist, merged_main)
# datasets = pull_data_for_all_comparison_groups(db, link_dict)
# prepped = prep_datasets(datasets)
# ratios = create_ratios_for_table(prepped)
# print(ratios.groupby("Period").mean())