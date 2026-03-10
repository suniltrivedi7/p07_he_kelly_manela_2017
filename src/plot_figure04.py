"""
plot_figure04.py

Replicates Figure 4 from He, Kelly, and Manela (2017):
  "Intermediary Asset Pricing: New Evidence from Many Asset Classes"

Figure 4: Two-panel comparison of intermediary capital measures.
  Panel A — Capital and leverage ratios (levels), log scale, 1970Q1-2012Q4.
  Panel B — Risk factors (AR(1) innovations), linear scale, 1970Q1-2012Q4.
Both panels shade NBER recessions and annotate pairwise correlations.

Usage:
    python plot_figure04.py               # original 1970Q1-2012Q4 sample
    python plot_figure04.py --updated     # extended sample through UPDATED_END_DATE
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import wrds

import config
import Table03
import Table02Prep
import Table03Load
from statsmodels.tsa.seasonal import seasonal_decompose

# NBER recession dates — same list used across the project
NBER_RECESSIONS = [
    (datetime(1973, 11, 1), datetime(1975, 3, 1)),
    (datetime(1980, 1, 1),  datetime(1980, 7, 1)),
    (datetime(1981, 7, 1),  datetime(1982, 11, 1)),
    (datetime(1990, 7, 1),  datetime(1991, 3, 1)),
    (datetime(2001, 3, 1),  datetime(2001, 11, 1)),
    (datetime(2007, 12, 1), datetime(2009, 6, 1)),
]

# Consistent colors / styles matching the paper
STYLE_MARKET = dict(color='steelblue',    linestyle='-',      linewidth=1.6)
STYLE_BOOK   = dict(color='forestgreen',  linestyle='dotted', linewidth=1.4)
STYLE_AEM    = dict(color='darkorange',   linestyle='--',     linewidth=1.4)


def _shade_recessions(ax):
    for rec_start, rec_end in NBER_RECESSIONS:
        ax.axvspan(rec_start, rec_end, color='lightgray', alpha=0.8, zorder=0)


def _corr(a, b):
    """Pearson correlation between two aligned Series, ignoring NaNs."""
    combined = pd.concat([a, b], axis=1).dropna()
    return combined.iloc[:, 0].corr(combined.iloc[:, 1])


def plot_figure04(ratio_dataset, factors_dataset, UPDATED=False):
    """
    Generates Figure 4 from HKM (2017) and saves it to OUTPUT_DIR.

    Inputs:
        ratio_dataset   : DataFrame with columns 'market_cap_ratio', 'book_cap_ratio',
                          'aem_leverage' and a date index.
        factors_dataset : DataFrame with columns 'market_capital_factor',
                          'book_capital_factor', 'aem_leverage_factor' and a date index.
        UPDATED         : bool — if True, extends the sample and prefixes output with
                          'updated_'.
    Output:
        Saves figure04.png (or updated_figure04.png) to config.OUTPUT_DIR.
    """
    end = config.UPDATED_END_DATE if UPDATED else config.END_DATE

    # --- Trim to sample period ---
    ratios  = ratio_dataset.loc[:end].copy()
    factors = factors_dataset.loc[:end].copy()

    # --- Pairwise correlations for Panel A (levels) ---
    corrA_mkt_aem  = _corr(ratios['market_cap_ratio'], ratios['aem_leverage'])
    corrA_mkt_book = _corr(ratios['market_cap_ratio'], ratios['book_cap_ratio'])
    corrA_aem_book = _corr(ratios['aem_leverage'],     ratios['book_cap_ratio'])

    # --- Pairwise correlations for Panel B (factors) ---
    corrB_mkt_aem  = _corr(factors['market_capital_factor'], factors['aem_leverage_factor'])
    corrB_mkt_book = _corr(factors['market_capital_factor'], factors['book_capital_factor'])
    corrB_aem_book = _corr(factors['aem_leverage_factor'],   factors['book_capital_factor'])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 10), sharex=True)
    fig.subplots_adjust(hspace=0.08)

    # =========================================================
    # Panel A — Levels (log scale, values in percent)
    # =========================================================
    _shade_recessions(ax1)

    mkt_pct  = ratios['market_cap_ratio'] * 100  # fraction → percentage points
    book_pct = ratios['book_cap_ratio']   * 100  # fraction → percentage points
    aem_pct  = ratios['aem_leverage']            # already a ratio (e.g. 20x), not a fraction

    ax1.plot(ratios.index, mkt_pct,  label='Market Capital Ratio, %', **STYLE_MARKET)
    ax1.plot(ratios.index, book_pct, label='Book Capital Ratio, %',   **STYLE_BOOK)
    ax1.plot(ratios.index, aem_pct,  label='AEM Leverage Ratio',      **STYLE_AEM)

    ax1.set_yscale('log')
    ax1.set_ylim(3, 150)
    ax1.set_yticks([5, 10, 50, 100])
    ax1.get_yaxis().set_major_formatter(ticker.ScalarFormatter())
    ax1.tick_params(axis='both', labelsize=11)
    ax1.set_title('Panel A: Capital and leverage ratios (levels)', fontsize=12, loc='left')

    # Correlation text box — upper left, matching paper
    corr_text_A = (
        f"Corr[Market,AEM]={corrA_mkt_aem:.2f}\n"
        f"Corr[Market,Book]={corrA_mkt_book:.2f}\n"
        f"Corr[AEM,Book]={corrA_aem_book:.2f}"
    )
    ax1.text(0.02, 0.97, corr_text_A, transform=ax1.transAxes,
             fontsize=9, verticalalignment='top',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.6, edgecolor='none'))

    # Annotations with arrows pointing to each series
    arrow_kw = dict(arrowstyle='->', color='black', lw=0.8)

    peak_aem_idx    = aem_pct.idxmax()
    peak_market_idx = mkt_pct.loc['1995':'2002'].idxmax()
    last_book_idx   = book_pct.dropna().index[-1]

    ax1.annotate('AEM Leverage Ratio',
                 xy=(peak_aem_idx, aem_pct[peak_aem_idx]),
                 xytext=(-60, 15), textcoords='offset points',
                 fontsize=9, arrowprops=arrow_kw)
    ax1.annotate('Market Capital Ratio, %',
                 xy=(peak_market_idx, mkt_pct[peak_market_idx]),
                 xytext=(-80, -25), textcoords='offset points',
                 fontsize=9, arrowprops=arrow_kw)
    ax1.annotate('Book Capital Ratio, %',
                 xy=(last_book_idx, book_pct[last_book_idx]),
                 xytext=(-80, -20), textcoords='offset points',
                 fontsize=9, arrowprops=arrow_kw)

    # =========================================================
    # Panel B — Risk factors (innovations), linear scale
    # =========================================================
    _shade_recessions(ax2)

    ax2.plot(factors.index, factors['market_capital_factor'], label='Market Capital Factor', **STYLE_MARKET)
    ax2.plot(factors.index, factors['book_capital_factor'],   label='Book Capital Factor',   **STYLE_BOOK)
    ax2.plot(factors.index, factors['aem_leverage_factor'],   label='AEM Levfac',            **STYLE_AEM)

    ax2.axhline(0, color='black', linewidth=0.5, alpha=0.4)
    ax2.set_ylim(-1.0, 0.6)
    ax2.tick_params(axis='both', labelsize=11)
    ax2.set_title('Panel B: Risk factors (innovations)', fontsize=12, loc='left')

    # Correlation text box — lower left
    corr_text_B = (
        f"Corr[Market,AEM]={corrB_mkt_aem:.2f}\n"
        f"Corr[Market,Book]={corrB_mkt_book:.2f}\n"
        f"Corr[AEM,Book]={corrB_aem_book:.2f}"
    )
    ax2.text(0.02, 0.06, corr_text_B, transform=ax2.transAxes,
             fontsize=9, verticalalignment='bottom',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.6, edgecolor='none'))

    # Annotations for Panel B
    mkt_f  = factors['market_capital_factor']
    book_f = factors['book_capital_factor']
    aem_f  = factors['aem_leverage_factor']

    peak_mkt_f  = mkt_f.loc['1995':'2002'].idxmax()
    trough_book = book_f.loc['1985':'1995'].idxmin()
    trough_aem  = aem_f.loc['2005':'2010'].idxmin()

    ax2.annotate('Market Capital Factor',
                 xy=(peak_mkt_f, mkt_f[peak_mkt_f]),
                 xytext=(15, 20), textcoords='offset points',
                 fontsize=9, arrowprops=arrow_kw)
    ax2.annotate('Book Capital Factor',
                 xy=(trough_book, book_f[trough_book]),
                 xytext=(-20, -25), textcoords='offset points',
                 fontsize=9, arrowprops=arrow_kw)
    ax2.annotate('AEM Levfac',
                 xy=(trough_aem, aem_f[trough_aem]),
                 xytext=(15, -20), textcoords='offset points',
                 fontsize=9, arrowprops=arrow_kw)

    # =========================================================
    # Shared x-axis formatting
    # =========================================================
    ax2.xaxis.set_major_locator(mdates.YearLocator(10))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax2.set_xlim(ratios.index.min(), ratios.index.max())

    # =========================================================
    # Caption
    # =========================================================
    end_quarter = "2012Q4" if not UPDATED else config.UPDATED_END_DATE[:4] + "Q4"
    caption = (
        "Fig. 4.  Intermediary capital measures comparison.  "
        "Panel A compares our main state variable of interest, the aggregate market-based capital ratio of NY Fed "
        "primary dealers with other measures of intermediary capital.  Market capital ratio at t is defined as "
        "\u03a3 marketequity / \u03a3 (marketequity + bookdebt), where market equity is outstanding shares multiplying "
        "stock price, and book debt is total assets minus common equity AT \u2212 CEQ.  "
        "Book capital ratio simply replaces marketequity with bookequity in this calculation.  "
        "AEM leverage ratio is constructed from Federal Reserve Z.1 security brokers and dealers series.  "
        "In Panel A, the capital ratios are in the scale of percentage points (i.e., 5 means 5%).  "
        "Panel B draws a similar comparison for the risk factors (innovations in the state variables).  "
        f"The quarterly sample is 1970Q1\u2013{end_quarter}.  "
        "Shaded regions indicate NBER recessions."
    )
    fig.text(0.5, -0.02, caption, ha='center', va='top', fontsize=8,
             wrap=True, style='italic', color='#333333')

    fname = "updated_figure04.png" if UPDATED else "figure04.png"
    outfile = config.OUTPUT_DIR / fname
    plt.savefig(outfile, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Figure 4 saved to: {outfile}")


def _build_datasets(UPDATED=False, INCLUDE_FOREIGN=False):
    """
    Runs the Table 3 data pipeline and returns (ratio_dataset, factors_dataset).
    Opens and closes its own WRDS connection.

    Args:
        UPDATED        : bool — if True, extends the sample to UPDATED_END_DATE.
        INCLUDE_FOREIGN: bool — if True, appends foreign primary dealer data.
    """
    db = wrds.Connection(wrds_username=config.WRDS_USERNAME)

    # Domestic primary dealers
    prim_dealers = Table02Prep.clean_primary_dealers_data(
        fname='Primary_Dealer_Link_Table3_DOMESTIC.csv'
    )
    dataset, _ = Table03Load.fetch_data_for_tickers(prim_dealers, db)

    # Foreign primary dealers (only if requested)
    if INCLUDE_FOREIGN:
        foreign_dealers = Table03Load.load_foreign_dealers()
        if not foreign_dealers.empty:
            foreign_dataset, foreign_empty = Table03Load.fetch_data_for_international_tickers(
                foreign_dealers, db
            )
            if foreign_empty:
                print(f"No Worldscope data found for MNEMs: {foreign_empty}")
            if not foreign_dataset.empty:
                dataset = pd.concat([dataset, foreign_dataset], axis=0, ignore_index=True)

    db.close()

    prep_datast     = Table03.prep_dataset(dataset, UPDATED=UPDATED)
    ratio_dataset   = Table03.aggregate_ratios(prep_datast)
    factors_dataset = Table03.convert_ratios_to_factors(ratio_dataset)

    # Override AEM leverage and factor using the historical 2013 ZIP archive data
    # (same source as the original paper's UPDATED=False pipeline).  The live FRED
    # API has revised historical values that shift the AEM series; the ZIP archive
    # preserves the original vintage covering 1968Q4-2012Q4.
    Path(config.DATA_DIR, 'pulled').mkdir(parents=True, exist_ok=True)
    aem_raw = Table03Load.load_fred_past()
    aem_raw = aem_raw.loc['1968-12-31':'2012-12-31']
    aem_leverage_full = aem_raw['bd_fin_assets'] / (aem_raw['bd_fin_assets'] - aem_raw['bd_liabilities'])
    leverage_growth = aem_leverage_full.pct_change().fillna(0)
    decomp = seasonal_decompose(leverage_growth, model='additive', period=4)
    aem_factor_full = leverage_growth - decomp.seasonal
    ratio_dataset['aem_leverage']             = aem_leverage_full.reindex(ratio_dataset.index)
    factors_dataset['aem_leverage_factor']    = aem_factor_full.reindex(factors_dataset.index)

    return ratio_dataset, factors_dataset


def main(UPDATED=False, INCLUDE_FOREIGN=False):
    ratio_dataset, factors_dataset = _build_datasets(UPDATED=UPDATED, INCLUDE_FOREIGN=INCLUDE_FOREIGN)
    plot_figure04(ratio_dataset, factors_dataset, UPDATED=UPDATED)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Figure 4 from HKM (2017).")
    parser.add_argument('--updated', action='store_true',
                        help="Use extended sample beyond 2012Q4.")
    args = parser.parse_args()
    main(UPDATED=args.updated)
