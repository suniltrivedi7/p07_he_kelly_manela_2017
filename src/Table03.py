"""
Table03.py

This module reads manually curated datasets for primary dealers and holding companies,
matches them with link history data, calculates key financial ratios (market cap ratio, 
book cap ratio, and AEM leverage defined as broker-dealer book leverage), and converts 
these ratios into analytical factors. It then merges these results with macroeconomic 
variables to produce outputs (tables and figures) for Table 03 in the intermediary asset 
pricing replication.
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
import wrds
import config
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

from statsmodels.tsa.ar_model import AutoReg
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.filters.hp_filter import hpfilter

import Table03Load
import importlib
importlib.reload(Table03Load)

from Table03Load import quarter_to_date, date_to_quarter
import Table03Analysis
import Table02Prep

def combine_bd_financials(UPDATED=False):
    """
    Load broker-dealer financial data (bd_fin_assets, bd_liabilities) from FRED.

    Uses load_bd_financials() for the full date range so the end date is driven
    by config.py rather than a hardcoded 2012Q4 ZIP archive.

    UPDATED=False  → pull through config.END_DATE        (original 1960-2012 sample)
    UPDATED=True   → pull through config.UPDATED_END_DATE (extended sample)
    """
    end_date = config.UPDATED_END_DATE if UPDATED else config.END_DATE
    return Table03Load.load_bd_financials(end=end_date)

def prep_dataset(dataset, UPDATED=False):
    """
    Prepare the raw financial dataset by removing duplicates, converting quarter strings to dates,
    and aggregating key financial columns by quarter.
    Input: dataset (DataFrame) with raw financial data and UPDATED flag.
    Output: Aggregated DataFrame with summed total_assets, book_debt, book_equity, and market_equity,
    merged with broker-dealer data.
    """
    dataset = dataset.drop_duplicates()
    dataset['datafqtr'] = dataset['datafqtr'].apply(quarter_to_date)
    # Use subset so international rows (which lack gvkey/conm) are not dropped
    dataset = dataset.dropna(subset=['datafqtr', 'total_assets', 'book_debt', 'book_equity', 'market_equity'])
    # Exclude rows where market_equity is zero — these indicate a missing/zero stock price
    # in Compustat (prccq = 0) rather than a genuine zero market cap, and would pull the
    # aggregate market capital ratio toward the book capital ratio.
    dataset = dataset[dataset['market_equity'] > 0]
    aggregated_dataset = dataset.groupby('datafqtr').agg({
        'total_assets': 'sum',
        'book_debt': 'sum',
        'book_equity': 'sum',
        'market_equity': 'sum'
    }).reset_index()
    
    print(f"\n[PREP] PD firm-quarters after dropna/market_equity>0: {len(dataset)}")
    print(f"[PREP] Unique gvkeys in raw data: {dataset['gvkey'].nunique() if 'gvkey' in dataset.columns else 'N/A'}")
    print(f"[PREP] Quarterly sector totals before BD merge: {len(aggregated_dataset)} quarters")
    bd_financials_combined = combine_bd_financials(UPDATED=UPDATED)
    print(f"[PREP] BD financials: {bd_financials_combined.index.min().date()} to {bd_financials_combined.index.max().date()} ({len(bd_financials_combined)} quarters)")
    aggregated_dataset = aggregated_dataset.merge(bd_financials_combined, left_on='datafqtr', right_index=True)
    if not UPDATED:
        aggregated_dataset = aggregated_dataset[
            (aggregated_dataset['datafqtr'] >= "1970-01-01") &
            (aggregated_dataset['datafqtr'] <= config.END_DATE)
        ]
    else:
        aggregated_dataset = aggregated_dataset[
            (aggregated_dataset['datafqtr'] >= "1970-01-01") &
            (aggregated_dataset['datafqtr'] <= config.UPDATED_END_DATE)
        ]
    print(f"[PREP] After date filter and BD merge: {len(aggregated_dataset)} quarters")
    if len(aggregated_dataset):
        print(f"[PREP] Sample: {aggregated_dataset['datafqtr'].min().date()} to {aggregated_dataset['datafqtr'].max().date()}")
    return aggregated_dataset

def calculate_ratios(data):
    """
    Calculate key financial ratios from aggregated data.
    Input: data (DataFrame) with aggregated columns for assets, debt, equity, etc.
    Output: DataFrame with added columns: market_cap_ratio, book_cap_ratio, and aem_leverage.
    market_cap_ratio = market_equity / (book_debt + market_equity), 
    book_cap_ratio = book_equity / (book_debt + book_equity), 
    aem_leverage = bd_fin_assets / (bd_fin_assets - bd_liabilities).
    """
    data['market_cap_ratio'] = data['market_equity'] / (data['book_debt'] + data['market_equity'])
    data['book_cap_ratio'] = data['book_equity'] / (data['book_debt'] + data['book_equity'])
    data['aem_leverage'] = data['bd_fin_assets'] / (data['bd_fin_assets'] - data['bd_liabilities'])
    return data


def aggregate_ratios(data):
    """
    Aggregates the calculated financial ratios and sets the date as the index.
    Input: data (DataFrame) after ratio calculation.
    Output: DataFrame with columns market_cap_ratio, book_cap_ratio, and aem_leverage, with index set to date.
    The function renames 'datafqtr' to 'date' and sets it as the index.
    """
    data = calculate_ratios(data)
    # Directly use aem_leverage without inversion
    data = data[['datafqtr', 'market_cap_ratio', 'book_cap_ratio', 'aem_leverage']]
    data.rename(columns={'datafqtr': 'date'}, inplace=True)
    data = data.set_index('date')
    print(f"\n[RATIOS] Quarters in ratio series: {len(data)}")
    print(f"[RATIOS] Date range: {data.index.min().date()} to {data.index.max().date()}")
    print(data[['market_cap_ratio', 'book_cap_ratio', 'aem_leverage']].describe().round(4).to_string())
    return data

def convert_ratios_to_factors(data):
    """
    Converts financial ratios into analytical factors.
    Input: data (DataFrame) with financial ratios.
    Output: DataFrame with factors: market_capital_factor, book_capital_factor, and aem_leverage_factor.
    For each ratio, an AR(1) model is fit and the residuals are used to compute the factor.
    The AEM leverage factor is based on the percentage change of raw leverage minus its seasonal component.
    """
    factors_df = pd.DataFrame(index=data.index)

    # AR(1) for market cap ratio
    cleaned_data = data['market_cap_ratio'].fillna(0)
    model = AutoReg(cleaned_data, lags=1, trend='c')
    model_fitted = model.fit()
    factors_df['innovations_mkt_cap'] = model_fitted.resid
    factors_df['market_capital_factor'] = factors_df['innovations_mkt_cap'] / data['market_cap_ratio'].shift(1)
    factors_df.drop(columns=['innovations_mkt_cap'], inplace=True)

    # AR(1) for book cap ratio
    cleaned_data = data['book_cap_ratio'].fillna(0)
    model = AutoReg(cleaned_data, lags=1, trend='c')
    model_fitted = model.fit()
    factors_df['innovations_book_cap'] = model_fitted.resid
    factors_df['book_capital_factor'] = factors_df['innovations_book_cap'] / data['book_cap_ratio'].shift(1)
    factors_df.drop(columns=['innovations_book_cap'], inplace=True)

    # Calculate AEM leverage factor based on raw leverage growth (percentage change) and remove seasonal component.
    factors_df['leverage_growth'] = data['aem_leverage'].pct_change().fillna(0)
    decomposition = seasonal_decompose(factors_df['leverage_growth'], model='additive', period=4)
    factors_df['aem_leverage_factor'] = factors_df['leverage_growth'] - decomposition.seasonal

    result = factors_df[['market_capital_factor', 'book_capital_factor', 'aem_leverage_factor']]
    print(f"\n[FACTORS] Date range: {result.index.min().date()} to {result.index.max().date()}")
    print(f"[FACTORS] Non-null counts: market_capital_factor={result['market_capital_factor'].notna().sum()}, "
          f"book_capital_factor={result['book_capital_factor'].notna().sum()}, "
          f"aem_leverage_factor={result['aem_leverage_factor'].notna().sum()}")
    print(result.describe().round(4).to_string())
    return result

def calculate_ep(shiller_cape):
    """
    Process Shiller CAPE data to calculate the earnings-to-price (E/P) ratio.

    Input: shiller_cape (DataFrame) returned by load_shiller_pe().
      - If it contains a 'cape' column (P/E10), E/P = 1 / CAPE.
      - If it contains an 'ep_direct' column (already E/P), use it as-is.
    Output: DataFrame with an 'e/p' column, date as index.
    The date is parsed using the format '%Y.%m' and adjusted to month end.
    """
    df = shiller_cape.copy()
    df['date'] = df['date'].astype(str)
    df['date'] = pd.to_datetime(df['date'], format='%Y.%m', errors='coerce') + pd.offsets.MonthEnd(0)
    df = df.dropna(subset=['date'])
    df = df.set_index('date')
    if 'ep_direct' in df.columns:
        df['e/p'] = pd.to_numeric(df['ep_direct'], errors='coerce')
    else:
        df['e/p'] = 1 / pd.to_numeric(df['cape'], errors='coerce')
    return df[['e/p']]

def macro_variables(db, from_cache=True, UPDATED=False):
    """
    Creates a merged DataFrame of quarterly macroeconomic variables.
    Input: WRDS connection object and UPDATED flag.
    Output: A DataFrame containing macro data from FRED, Shiller, Fama-French factors, and CRSP volatility.
    It renames FRED series, resamples to quarterly, and merges all data on the date index.
    """
    
    # Load FRED macroeconomic data and rename columns
    macro_data = Table03Load.load_fred_macro_data(from_cache = from_cache)
    macro_data = macro_data.rename(columns={'UNRATE': 'unemp_rate',
                                              'NFCI': 'nfci',
                                              'GDPC1': 'real_gdp'})
    macro_data.index = pd.to_datetime(macro_data.index)
    macro_data.rename(columns={'DATE': 'date'}, inplace=True)
    macro_quarterly = macro_data.resample('QE').mean()
    macro_quarterly['real_gdp_growth_calc'] = macro_quarterly['real_gdp'].pct_change(periods=1)

    # Load Shiller market data, calculate E/P, and resample quarterly
    shiller_cape = Table03Load.load_shiller_pe(from_cache = from_cache)
    shiller_ep = calculate_ep(shiller_cape)
    shiller_quarterly = shiller_ep.resample('QE').mean()

    # Determine the end date for FF factors based on the UPDATED flag and load the data
    if UPDATED:
        end_date_ff = config.UPDATED_END_DATE
    else:
        end_date_ff = config.END_DATE
    ff_facs = Table03Load.fetch_ff_factors(start_date=config.START_DATE.replace("-", ""),
                                           end_date=end_date_ff.replace("-", ""))
    ff_facs_quarterly = ff_facs.to_timestamp(freq='M').resample('QE').apply(
        lambda x: (1 + x).prod() - 1
    )

    # Load the CRSP value-weighted index data and convert the date column to datetime
    value_wtd_indx = Table03Load.pull_CRSP_Value_Weighted_Index(db)
    value_wtd_indx['date'] = pd.to_datetime(value_wtd_indx['date'])
    
    # Compute market volatility using logarithmic returns:
    # Assume vwretd is a return (in decimal form), then the log return is ln(1 + vwretd)
    log_returns = value_wtd_indx.set_index('date')['vwretd']
    annual_vol_quarterly = log_returns.groupby(pd.Grouper(freq='QE')).std().rename('mkt_vol')

    print(f"\n[MACRO] Shiller E/P: {shiller_quarterly.index.min().date()} to {shiller_quarterly.index.max().date()} ({len(shiller_quarterly)} quarters)")
    print(f"[MACRO] FRED (UNRATE/NFCI/GDPC1): {macro_quarterly.index.min().date()} to {macro_quarterly.index.max().date()} ({len(macro_quarterly)} quarters)")
    print(f"[MACRO]   NFCI non-null: {macro_quarterly['nfci'].notna().sum()} quarters (starts {macro_quarterly['nfci'].first_valid_index().date() if macro_quarterly['nfci'].notna().any() else 'N/A'})")
    print(f"[MACRO] FF factors (mkt_ret): {ff_facs_quarterly.index.min().date()} to {ff_facs_quarterly.index.max().date()} ({len(ff_facs_quarterly)} quarters)")
    print(f"[MACRO] CRSP vol: {annual_vol_quarterly.index.min().date()} to {annual_vol_quarterly.index.max().date()} ({len(annual_vol_quarterly)} quarters)")

    # Merge all macroeconomic data
    macro_merged = shiller_quarterly.merge(macro_quarterly, left_index=True, right_index=True, how='left')
    macro_merged = macro_merged.merge(ff_facs_quarterly[['mkt_ret']], left_index=True, right_index=True)
    macro_merged = macro_merged.merge(annual_vol_quarterly, left_index=True, right_index=True)

    print(f"[MACRO] After merge: {len(macro_merged)} quarters, {macro_merged.index.min().date()} to {macro_merged.index.max().date()}")
    print(f"[MACRO] Non-null counts per column:\n{macro_merged.notna().sum().to_string()}")
    return macro_merged

def create_panelA(ratios, macro, UPDATED=False):
    """
    Creates Panel A for Table 03 by merging financial ratios with macroeconomic variables.
    Input: ratios (DataFrame with financial ratios), macro (DataFrame with macro data),
           and UPDATED flag (False → 1970Q1-2012Q4; True → 1970Q1-UPDATED_END_DATE).
    Output: A DataFrame for Panel A with columns for Market capital, Book capital, AEM leverage, and selected macro variables.
    """
    ratios_renamed = ratios.rename(columns={
        'market_cap_ratio': 'Market capital',
        'book_cap_ratio': 'Book capital',
        'aem_leverage': 'AEM leverage'
    })
    macro = macro[['e/p', 'unemp_rate', 'nfci', 'real_gdp', 'mkt_ret', 'mkt_vol']].copy()
    # HP-filter log real GDP (lambda=1600, standard for quarterly data).
    # Raw log-level GDPC1 still trends from ~8.3 to ~9.7 over 1970-2012; any two
    # trended series produce spuriously high positive correlations regardless of
    # log-transformation.  The HP cyclical component removes the secular trend,
    # leaving a stationary, zero-centered series that captures the business cycle.
    # This is the representation consistent with the paper's GDP correlation of
    # +0.18/+0.32/-0.23 rather than our pre-fix +0.54/+0.74/+0.67.
    log_gdp = np.log(macro['real_gdp']).dropna()
    hp_cycle, _ = hpfilter(log_gdp, lamb=1600)
    macro['real_gdp'] = hp_cycle.reindex(macro.index)
    print(f"[PANEL A] GDP: using HP-cycle of log(real_gdp), lambda=1600. "
          f"Range: {macro['real_gdp'].dropna().min():.4f} to {macro['real_gdp'].dropna().max():.4f}")
    macro_renamed = macro.rename(columns={
        'e/p': 'E/P',
        'unemp_rate': 'Unemployment',
        'nfci': 'Financial conditions',
        'real_gdp': 'GDP',
        'mkt_ret': 'Market excess return',
        'mkt_vol': 'Market volatility'
    })
    panelA = ratios_renamed.merge(macro_renamed, left_index=True, right_index=True)
    ordered_columns = ['Market capital', 'Book capital', 'AEM leverage',
                       'E/P', 'Unemployment', 'Financial conditions', 'GDP', 'Market excess return', 'Market volatility']
    panelA = panelA[ordered_columns]
    # Apply sample bounds: 1970Q1 lower bound; 2012Q4 (config.END_DATE) upper bound unless UPDATED.
    end_bound = config.UPDATED_END_DATE if UPDATED else config.END_DATE
    panelA = panelA.loc['1970-01-01':end_bound]
    print(f"\n[PANEL A] Shape: {panelA.shape}  ({panelA.index.min().date()} to {panelA.index.max().date()})")
    print(f"[PANEL A] Non-null counts:\n{panelA.notna().sum().to_string()}")
    return panelA

def create_panelB(factors, macro, UPDATED=False):
    """
    Creates Panel B for Table 03 by merging analytical factors with macroeconomic variable growth rates.
    Input: factors (DataFrame with analytical factors), macro (DataFrame with macro data),
           and UPDATED flag (False → 1970Q1-2012Q4; True → 1970Q1-UPDATED_END_DATE).
    Output: A DataFrame for Panel B with growth rate columns for the factors and macro variables.
    """
    factors_renamed = factors.rename(columns={
        'market_capital_factor': 'Market capital factor',
        'book_capital_factor': 'Book capital factor',
        'aem_leverage_factor': 'AEM leverage factor'
    })
    macro_growth = macro.copy()
    # Log growth for positive, non-zero series
    for col in ['e/p', 'unemp_rate', 'real_gdp']:
        macro_growth[col] = np.log(macro[col] / macro[col].shift(1))
    # NFCI is centred at zero and can be negative; log-ratio produces NaN on sign changes.
    # Use first-difference (absolute change) instead.
    macro_growth['nfci'] = macro['nfci'].diff()
    # Market volatility: use pct_change rather than log ratio.
    # During the 2008 crisis, daily-return vol jumped ~5-10x in a single quarter;
    # log(vol_t / vol_{t-1}) produces values >2, swamping all other observations
    # and pulling the correlation coefficient toward zero.  pct_change is on the
    # same scale and is less sensitive to that single outlier.
    macro_growth['mkt_vol'] = macro['mkt_vol'].pct_change()
    # Market excess return: already a return, use directly (not growth-of-return)
    macro_growth['mkt_ret'] = macro['mkt_ret']
    # Drop any remaining columns not needed (real_gdp_growth_calc etc.)
    macro_growth = macro_growth.loc['1970-01-01':]
    macro_growth_renamed = macro_growth.rename(columns={
        'e/p': 'E/P growth',
        'unemp_rate': 'Unemployment growth',
        'nfci': 'Financial conditions growth',
        'real_gdp': 'GDP growth',
        'mkt_ret': 'Market excess return',
        'mkt_vol': 'Market volatility growth'
    })
    panelB = factors_renamed.merge(macro_growth_renamed, left_index=True, right_index=True)
    ordered_columns = ['Market capital factor', 'Book capital factor', 'AEM leverage factor',
                       'E/P growth', 'Unemployment growth', 'Financial conditions growth', 'GDP growth', 'Market excess return', 'Market volatility growth']
    panelB = panelB[ordered_columns]
    # Apply sample bounds: 1970Q1 lower bound; 2012Q4 (config.END_DATE) upper bound unless UPDATED.
    end_bound = config.UPDATED_END_DATE if UPDATED else config.END_DATE
    panelB = panelB.loc['1970-01-01':end_bound]
    print(f"\n[PANEL B] Shape: {panelB.shape}  ({panelB.index.min().date()} to {panelB.index.max().date()})")
    print(f"[PANEL B] Non-null counts:\n{panelB.notna().sum().to_string()}")
    return panelB

def format_correlation_matrix(corr_matrix):
    """
    Formats the given correlation matrix by masking its lower triangle.
    Input: corr_matrix (DataFrame) containing correlation coefficients.
    Output: The same DataFrame with the lower triangle masked (set to NaN) for better readability.
    """
    corr_matrix = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=0).astype(bool))
    return corr_matrix

def calculate_correlation_panelA(panelA,UPDATED=False):
    """
    Calculates pairwise correlations for Panel A (levels) data.
    Input: panelA (DataFrame) containing levels of financial ratios and macro variables.
    Output: A correlation DataFrame showing correlations between the main ratios and each macro variable.
    It computes the correlations among the first three columns and then with each macro variable.
    """
    if not UPDATED:
        panelA = panelA[:config.END_DATE]
    print(f"\n[CORR A] Using {len(panelA)} quarters: {panelA.index.min().date()} to {panelA.index.max().date()}")
    correlation_panelA = format_correlation_matrix(panelA.iloc[:, :3].corr())
    main_cols = panelA[['Market capital', 'Book capital', 'AEM leverage']]
    other_cols = panelA[['E/P', 'Unemployment', 'GDP', 'Financial conditions', 'Market volatility']]
    correlation_results_panelA = pd.DataFrame(index=main_cols.columns)
    for column in other_cols.columns:
        correlation_results_panelA[column] = main_cols.corrwith(other_cols[column])
    result = pd.concat([correlation_panelA, correlation_results_panelA.T], axis=0)
    print("[CORR A] Correlation matrix:\n" + result.round(2).fillna('').to_string())
    return result

def calculate_correlation_panelB(panelB,UPDATED=False):
    """
    Calculates pairwise correlations for Panel B (factor growth rates) data.
    Input: panelB (DataFrame) containing analytical factor growth rates and macro variable growth rates.
    Output: A correlation DataFrame showing correlations between factor growth rates and macro growth rates.
    It computes the upper triangle and then correlations between the first three columns and the remaining columns.
    """
    if not UPDATED:
        panelB = panelB[:config.END_DATE]
    print(f"\n[CORR B] Using {len(panelB)} quarters: {panelB.index.min().date()} to {panelB.index.max().date()}")
    correlation_panelB = format_correlation_matrix(panelB.iloc[:, :3].corr())
    main_cols = panelB[['Market capital factor', 'Book capital factor', 'AEM leverage factor']]
    other_cols = panelB[['Market excess return', 'E/P growth', 'Unemployment growth', 'GDP growth', 'Financial conditions growth', 'Market volatility growth']]
    correlation_results_panelB = pd.DataFrame(index=main_cols.columns)
    for column in other_cols.columns:
        correlation_results_panelB[column] = main_cols.corrwith(other_cols[column])
    result = pd.concat([correlation_panelB, correlation_results_panelB.T], axis=0)
    print("[CORR B] Correlation matrix:\n" + result.round(2).fillna('').to_string())
    return result

def format_final_table(corrA, corrB):
    """
    Formats the final correlation table by merging Panel A and Panel B correlation data.
    Input: corrA and corrB (DataFrames) for Panel A and Panel B respectively.
    Output: A combined DataFrame with a MultiIndex for columns for clearer presentation.
    The function reorders and labels columns and rows.
    """
    panelB_renamed = corrB.copy()
    panelB_renamed.columns = corrA.columns
    panelB_column_names = pd.DataFrame([corrB.columns], columns=corrA.columns)
    panelB_column_names.reset_index(drop=True, inplace=True)
    panelB_combined = pd.concat([panelB_column_names, panelB_renamed])
    panelA_title = pd.DataFrame({col: ["Panel A: Correlations of Levels"] for col in corrA.columns})
    panelB_title = pd.DataFrame({col: ["Panel B: Correlations of Factors"] for col in corrA.columns})
    full_table = pd.concat([panelA_title, corrA, panelB_title, panelB_combined])
    return full_table

def convert_and_export_tables_to_latex(corrA, corrB, UPDATED=False, INCLUDE_FOREIGN=False):
    """
    Converts correlation tables to LaTeX format and exports the result as a .tex file.
    Input: corrA and corrB (DataFrames), UPDATED flag, and INCLUDE_FOREIGN flag.
    Output: A LaTeX file saved in the directory specified by config.OUTPUT_DIR.
    Filename: [updated_]table03[_intl].tex
    """
    corrA = corrA.round(2).fillna('')
    corrB = corrB.round(2).fillna('')
    caption = ("Updated International" if INCLUDE_FOREIGN else "Updated") if UPDATED else ("International" if INCLUDE_FOREIGN else "Original")
    column_format = 'l' + 'c' * (len(corrA.columns))
    header_row = " & " + " & ".join(corrA.columns) + " \\\\"
    panelA_rows = "\n".join([f"{index} & " + " & ".join(corrA.loc[index].astype(str)) + " \\\\" for index in corrA.index])
    panelB_rows = "\n".join([f"{index} & " + " & ".join(corrB.loc[index].astype(str)) + " \\\\" for index in corrB.index])
    full_latex = rf"""
    \begin{{table}}[htbp]
    \centering
    \caption{{\label{{tab:correlation}}{caption}}}
    \scalebox{{0.75}}{{
    \small
    \begin{{tabular}}{{{column_format}}}
        \toprule
        Panel A: Correlation of Levels \\
        \midrule
        {header_row}
        \midrule
        {panelA_rows}
        \midrule
        Panel B: Correlations of Factors \\
        \midrule
        {header_row}
        \midrule
        {panelB_rows}
        \bottomrule
    \end{{tabular}}
    }}
    \end{{table}}
    """
    prefix = "updated_" if UPDATED else ""
    intl = "_intl" if INCLUDE_FOREIGN else ""
    outfile = config.OUTPUT_DIR / f"{prefix}table03{intl}.tex"
    with open(outfile, 'w', encoding='utf-8') as f:
        f.write(full_latex)

def main(UPDATED=False, INCLUDE_FOREIGN=False):
    """
    Main function to execute the entire data processing pipeline for Table 03.

    Parameters
    ----------
    UPDATED        : bool  Use extended sample through config.UPDATED_END_DATE (default False).
    INCLUDE_FOREIGN: bool  Include international primary dealers via Worldscope (default False).
                           When False, only domestic (Compustat) PDs are used — output files
                           are named table03.tex / updated_table03.tex.
                           When True, foreign PDs are appended — output files are named
                           table03_intl.tex / updated_table03_intl.tex.
    """
    db = wrds.Connection(wrds_username=config.WRDS_USERNAME)
    print(f"\n{'='*60}")
    print(f"TABLE 03 PIPELINE  (UPDATED={UPDATED}, INCLUDE_FOREIGN={INCLUDE_FOREIGN})")
    print(f"Sample target: 1970Q1 – {'2012Q4' if not UPDATED else config.UPDATED_END_DATE}")
    print(f"{'='*60}")

    # --- Domestic primary dealers (gvkey-identified, queried via Compustat) ---
    print("\n[STEP 1] Loading domestic primary dealers from DOMESTIC CSV...")
    prim_dealers = Table02Prep.clean_primary_dealers_data(fname='Primary_Dealer_Link_Table3_DOMESTIC.csv')

    # Exclude non-financial conglomerate parents — mirrors Table02Prep.NON_FINANCIAL_PD_GVKEYS.
    # GE (gvkey 5047, parent of Kidder Peabody 1979-1994) and Sears (gvkey 6307,
    # parent of Dean Witter 1977-1998) have massive industrial balance sheets that
    # distort the PD-sector aggregate capital ratios.
    NON_FINANCIAL_PD_GVKEYS = {5047, 6307}
    n_before = len(prim_dealers)
    prim_dealers = prim_dealers[~prim_dealers['gvkey'].isin(NON_FINANCIAL_PD_GVKEYS)]
    print(f"[STEP 1] Excluded {n_before - len(prim_dealers)} non-financial PD row(s) "
          f"(gvkeys {NON_FINANCIAL_PD_GVKEYS}); {len(prim_dealers)} rows remain.")

    print(f"[STEP 1] Querying Compustat for {len(prim_dealers)} domestic PD records...")
    dataset, empty_domestic = Table03Load.fetch_data_for_tickers(prim_dealers, db)
    print(f"[STEP 1] Domestic firm-quarters fetched: {len(dataset)}")
    if empty_domestic:
        print(f"[STEP 1] WARNING — no Compustat data for: {empty_domestic}")

    # --- Foreign primary dealers (MNEM-identified, queried via Worldscope) ---
    if INCLUDE_FOREIGN:
        print("\n[STEP 2] Loading foreign primary dealers from FOREIGN CSV...")
        foreign_dealers = Table03Load.load_foreign_dealers()
        if not foreign_dealers.empty:
            print(f"[STEP 2] Querying Worldscope for {len(foreign_dealers)} foreign PD records...")
            foreign_dataset, foreign_empty = Table03Load.fetch_data_for_international_tickers(foreign_dealers, db)
            if foreign_empty:
                print(f"[STEP 2] No Worldscope data found for MNEMs: {foreign_empty}")
            if not foreign_dataset.empty:
                print(f"[STEP 2] Foreign firm-quarters fetched: {len(foreign_dataset)}")
                dataset = pd.concat([dataset, foreign_dataset], axis=0, ignore_index=True)
            else:
                print("[STEP 2] No foreign data fetched; proceeding with domestic only.")
        else:
            print("[STEP 2] No foreign dealer file found; skipping.")
    else:
        print("\n[STEP 2] INCLUDE_FOREIGN=False — skipping foreign dealer fetch.")

    print(f"\n[STEP 3] Preparing and aggregating PD data to quarterly sector totals...")
    prep_datast = prep_dataset(dataset, UPDATED=UPDATED)

    print(f"\n[STEP 4] Computing capital ratios (market, book, AEM leverage)...")
    ratio_dataset = aggregate_ratios(prep_datast)

    print(f"\n[STEP 5] Converting ratios to AR(1) factors...")
    factors_dataset = convert_ratios_to_factors(ratio_dataset)

    print(f"\n[STEP 6] Loading macroeconomic variables...")
    macro_dataset = macro_variables(db, UPDATED=UPDATED)

    print(f"\n[STEP 7] Building Panel A (levels) and Panel B (factors/growth)...")
    panelA = create_panelA(ratio_dataset, macro_dataset, UPDATED=UPDATED)
    panelB = create_panelB(factors_dataset, macro_dataset, UPDATED=UPDATED)
    
    print(f"\n[STEP 8] Computing summary statistics and figures...")
    Table03Analysis.create_summary_stat_table_for_data(panelB, UPDATED=UPDATED, INCLUDE_FOREIGN=INCLUDE_FOREIGN)
    Table03Analysis.plot_figure03(ratio_dataset, macro_dataset, UPDATED=UPDATED, INCLUDE_FOREIGN=INCLUDE_FOREIGN)
    Table03Analysis.plot_figure02(ratio_dataset, calculate_correlation_panelA(panelA, UPDATED=UPDATED), UPDATED=UPDATED, INCLUDE_FOREIGN=INCLUDE_FOREIGN)

    print(f"\n[STEP 9] Computing correlation matrices...")
    correlation_panelA = calculate_correlation_panelA(panelA, UPDATED=UPDATED)
    correlation_panelB = calculate_correlation_panelB(panelB, UPDATED=UPDATED)
    formatted_table = format_final_table(correlation_panelA, correlation_panelB)
    convert_and_export_tables_to_latex(correlation_panelA, correlation_panelB, UPDATED=UPDATED, INCLUDE_FOREIGN=INCLUDE_FOREIGN)
    print(f"\n{'='*60}")
    print("FINAL TABLE (as formatted for LaTeX):")
    print(f"{'='*60}")
    print(formatted_table.style.format(na_rep=''))


if __name__ == "__main__":
    main(UPDATED=False)
    print("Table 03 has been created and exported to LaTeX format.")
