"""
plot_figure01.py

Replicates Figure 1 from He, Kelly, and Manela (2017):
  "Intermediary Asset Pricing: New Evidence from Many Asset Classes"

Figure 1: Intermediary capital ratio (solid) and capital risk factor (dashed),
both standardized to zero mean and unit variance. Quarterly sample 1970Q1-2012Q4.
Shaded regions indicate NBER recessions.

Usage:
    python plot_figure01.py               # original 1970Q1-2012Q4 sample
    python plot_figure01.py --updated     # extended sample through UPDATED_END_DATE
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import argparse
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import wrds

import config
import Table03
import Table02Prep
import Table03Load

# NBER recession dates (start, end) — same list used in Table03Analysis
NBER_RECESSIONS = [
    (datetime(1973, 11, 1), datetime(1975, 3, 1)),
    (datetime(1980, 1, 1),  datetime(1980, 7, 1)),
    (datetime(1981, 7, 1),  datetime(1982, 11, 1)),
    (datetime(1990, 7, 1),  datetime(1991, 3, 1)),
    (datetime(2001, 3, 1),  datetime(2001, 11, 1)),
    (datetime(2007, 12, 1), datetime(2009, 6, 1)),
]


def _standardize(series):
    """Standardize a Series to zero mean and unit variance."""
    return (series - series.mean()) / series.std()


def plot_figure01(ratio_dataset, factors_dataset, UPDATED=False):
    """
    Generates Figure 1 from HKM (2017) and saves it to OUTPUT_DIR.

    Inputs:
        ratio_dataset   : DataFrame with 'market_cap_ratio' column and date index.
        factors_dataset : DataFrame with 'market_capital_factor' column and date index.
        UPDATED         : bool — if True, extends the sample and prefixes output filename
                          with 'updated_'.
    Output:
        Saves figure01.png (or updated_figure01.png) to config.OUTPUT_DIR.
    """
    end = config.UPDATED_END_DATE if UPDATED else config.END_DATE

    ratio  = ratio_dataset['market_cap_ratio'].loc[:end].dropna()
    factor = factors_dataset['market_capital_factor'].loc[:end].dropna()

    ratio_std  = _standardize(ratio)
    factor_std = _standardize(factor)

    fig, ax = plt.subplots(figsize=(12, 6))

    # --- NBER recession shading ---
    for rec_start, rec_end in NBER_RECESSIONS:
        ax.axvspan(rec_start, rec_end, color='lightgray', alpha=0.8, zorder=0)

    # --- Plot the two series ---
    ax.plot(ratio_std.index,  ratio_std.values,
            color='#1f4e79', linewidth=1.8, linestyle='-')
    ax.plot(factor_std.index, factor_std.values,
            color='#e07b00', linewidth=1.0, linestyle='--')

    # --- Axes formatting ---
    ax.set_xlim(ratio_std.index.min(), ratio_std.index.max())
    ax.set_ylim(-4, 4)
    ax.set_yticks([-4, -2, 0, 2, 4])
    ax.xaxis.set_major_locator(mdates.YearLocator(10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.tick_params(axis='both', labelsize=12)
    ax.axhline(0, color='black', linewidth=0.5, linestyle='-', alpha=0.4)

    # --- In-plot annotations (matching paper style) ---
    # "Intermediary Capital Ratio" — annotate near the late-1990s peak
    peak_ratio_idx = ratio_std.loc['1995':'2002'].idxmax()
    ax.annotate(
        'Intermediary Capital Ratio',
        xy=(peak_ratio_idx, ratio_std[peak_ratio_idx]),
        xytext=(40, 20), textcoords='offset points',
        fontsize=10, color='#1f4e79',
        arrowprops=dict(arrowstyle='->', color='#1f4e79', lw=1.0),
    )

    # "Intermediary Capital Risk Factor" — annotate near the 2008 trough
    trough_factor_idx = factor_std.loc['2006':'2010'].idxmin()
    ax.annotate(
        'Intermediary Capital Risk Factor',
        xy=(trough_factor_idx, factor_std[trough_factor_idx]),
        xytext=(30, -30), textcoords='offset points',
        fontsize=10, color='#e07b00',
        arrowprops=dict(arrowstyle='->', color='#e07b00', lw=1.0),
    )

    # --- Caption below the figure ---
    end_quarter = "2012Q4" if not UPDATED else config.UPDATED_END_DATE[:4] + "Q4"
    caption = (
        "Fig. 1.  Intermediary capital ratio and risk factor.  "
        "Intermediary capital risk factor (dashed line) is AR(1) innovations to the "
        "market-based capital ratio of primary dealers (solid line), scaled by the lagged "
        "capital ratio.  Both time-series are standardized to zero mean and unit variance "
        f"for illustration.  The quarterly sample is 1970Q1\u2013{end_quarter}.  "
        "Shaded regions indicate NBER recessions."
    )
    fig.text(0.5, -0.04, caption, ha='center', va='top', fontsize=8,
             wrap=True, transform=ax.transAxes,
             style='italic', color='#333333')

    plt.tight_layout()

    fname = "updated_figure01.png" if UPDATED else "figure01.png"
    outfile = config.OUTPUT_DIR / fname
    plt.savefig(outfile, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Figure 1 saved to: {outfile}")


def _build_datasets(UPDATED=False):
    """
    Runs the Table 3 data pipeline and returns (ratio_dataset, factors_dataset).
    Opens and closes its own WRDS connection.
    """
    db = wrds.Connection(wrds_username=config.WRDS_USERNAME)

    # Domestic primary dealers
    prim_dealers = Table02Prep.clean_primary_dealers_data(
        fname='Primary_Dealer_Link_Table3_DOMESTIC.csv'
    )
    dataset, _ = Table03Load.fetch_data_for_tickers(prim_dealers, db)

    # Foreign primary dealers (if available)
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

    prep_datast    = Table03.prep_dataset(dataset, UPDATED=UPDATED)
    ratio_dataset  = Table03.aggregate_ratios(prep_datast)
    factors_dataset = Table03.convert_ratios_to_factors(ratio_dataset)

    return ratio_dataset, factors_dataset


def main(UPDATED=False):
    ratio_dataset, factors_dataset = _build_datasets(UPDATED=UPDATED)
    plot_figure01(ratio_dataset, factors_dataset, UPDATED=UPDATED)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Figure 1 from HKM (2017).")
    parser.add_argument('--updated', action='store_true',
                        help="Use extended sample beyond 2012Q4.")
    args = parser.parse_args()
    main(UPDATED=args.updated)
