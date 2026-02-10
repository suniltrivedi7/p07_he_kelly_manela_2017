# src/generate_chart.py

from pathlib import Path
import pandas as pd
import plotly.express as px

DATA_DIR = Path("_data/pulled")
OUTPUT_DIR = Path("_output")

OUTPUT_DIR.mkdir(exist_ok=True)


def load_crsp():
    """Load CRSP returns from Excel file."""
    xlsx = DATA_DIR / "crsp_return.xlsx"
    xls = DATA_DIR / "crsp_return.xls"

    if xlsx.exists():
        df = pd.read_excel(xlsx)
    elif xls.exists():
        df = pd.read_excel(xls)
    else:
        raise FileNotFoundError("CRSP return file not found in _data/pulled")

    # Attempt to standardize columns
    df = df.dropna(how="all")

    # identify numeric return column automatically
    num_cols = df.select_dtypes(include="number").columns
    if len(num_cols) == 0:
        raise ValueError("No numeric return column found in CRSP dataset")

    return df, num_cols[0]


def chart_returns_time_series(df, return_col):
    """Time series plot of CRSP returns."""
    x_col = df.columns[0]

    fig = px.line(
        df,
        x=x_col,
        y=return_col,
        title="CRSP Returns Time Series"
    )

    fig.write_html(OUTPUT_DIR / "crsp_returns_timeseries.html")


def chart_returns_histogram(df, return_col):
    """Histogram of CRSP returns."""
    fig = px.histogram(
        df,
        x=return_col,
        nbins=50,
        title="Distribution of CRSP Returns"
    )

    fig.write_html(OUTPUT_DIR / "crsp_returns_histogram.html")


def chart_rolling_volatility(df, return_col):
    """Rolling volatility (30-period std dev)."""
    x_col = df.columns[0]

    df["rolling_vol"] = df[return_col].rolling(window=30).std()

    fig = px.line(
        df,
        x=x_col,
        y="rolling_vol",
        title="CRSP Rolling Volatility (30-period)"
    )

    fig.write_html(OUTPUT_DIR / "crsp_rolling_volatility.html")


def main():
    """Generate three exploratory CRSP charts."""
    df, return_col = load_crsp()

    chart_returns_time_series(df, return_col)
    chart_returns_histogram(df, return_col)
    chart_rolling_volatility(df, return_col)


if __name__ == "__main__":
    main()
