"""
dodo.py - Automates project tasks using doit.

This file uses the `doit` Python package to define tasks. 
Each task is defined by its actions, file dependencies, and optional targets.
"""

import os
from pathlib import Path
from src import config

# Read directory configuration from config
DATA_DIR = config.DATA_DIR
OUTPUT_DIR = config.OUTPUT_DIR

def task_generate_charts():
    """
    Task: Run generate_chart.py to create three CRSP exploratory Plotly charts.
    """
    return {
        "actions": [
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import generate_chart; generate_chart.main()"'
        ],
        "file_dep": [
            "./src/generate_chart.py"
        ],
        "targets": [
            "_output/crsp_returns_timeseries.html",
            "_output/crsp_returns_histogram.html",
            "_output/crsp_rolling_volatility.html"
        ],
        "clean": []
    }

def task_pull_table02_data():
    """
    Task: Pull all WRDS data for Table 2 and save to _data/pulled/ as parquet files.
    Only re-runs when pull_table02_data.py changes or a target file is missing.
    """
    return {
        "actions": [
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import pull_table02_data; pull_table02_data.main()"'
        ],
        "file_dep": [
            "./src/pull_table02_data.py",
            "./src/Table02Prep.py",
        ],
        "targets": [
            f"{DATA_DIR}/pulled/table02_ccm_gvkeys.parquet",
            f"{DATA_DIR}/pulled/table02_bd_gvkeys.parquet",
            f"{DATA_DIR}/pulled/table02_banks_gvkeys.parquet",
            f"{DATA_DIR}/pulled/table02_raw_PD.parquet",
            f"{DATA_DIR}/pulled/table02_raw_BD.parquet",
            f"{DATA_DIR}/pulled/table02_raw_Banks.parquet",
            f"{DATA_DIR}/pulled/table02_raw_Cmpust.parquet",
        ],
        "clean": [],
    }


def task_table02_main():
    """
    Task: Run Table02Prep.py to generate Table 2's LaTeX tables and figures.
    Execute both the original version (UPDATED=False) and the updated version (UPDATED=True).
    Depends on task_pull_table02_data to ensure parquet files exist.
    """
    return {
        "actions": [
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import Table02Prep; Table02Prep.main()"',
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import Table02Prep; Table02Prep.main(UPDATED=True)"'
        ],
        "file_dep": [
            "./src/Table02Prep.py",
            f"{DATA_DIR}/pulled/table02_raw_PD.parquet",
            f"{DATA_DIR}/pulled/table02_raw_BD.parquet",
            f"{DATA_DIR}/pulled/table02_raw_Banks.parquet",
            f"{DATA_DIR}/pulled/table02_raw_Cmpust.parquet",
        ],
        "task_dep": ["pull_table02_data"],
        "clean": [],
    }

def task_test_table02():
    """
    Task: Run the unit tests in Table02_testing.py.
    We change to the src directory before running the tests.
    """
    return {
        "actions": [
            'cd src && ipython -m unittest Table02_testing.py'
        ],
        "file_dep": [
            "./src/Table02_testing.py"
        ],
        "clean": []
    }

def task_table03_main():
    """
    Task: Run Table03.py to generate Table 3's LaTeX tables, summary statistics, and figures.
    Runs all four combinations of UPDATED x INCLUDE_FOREIGN.
    """
    return {
        "actions": [
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import Table03; Table03.main()"',
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import Table03; Table03.main(UPDATED=True)"',
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import Table03; Table03.main(INCLUDE_FOREIGN=True)"',
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import Table03; Table03.main(UPDATED=True, INCLUDE_FOREIGN=True)"',
        ],
        "file_dep": [
            "./src/Table03.py"
        ],
        "clean": []
    }

def task_plot_figures():
    """
    Task: Run plot_figure01.py and plot_figure04.py to generate Figure 1 and Figure 4
    from He, Kelly, and Manela (2017).
    """
    return {
        "actions": [
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import plot_figure01; plot_figure01.main()"',
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import plot_figure04; plot_figure04.main()"',
        ],
        "file_dep": [
            "./src/plot_figure01.py",
            "./src/plot_figure04.py",
        ],
        "targets": [
            "./_output/figure01.png",
            "./_output/figure04.png",
        ],
        "clean": []
    }

def task_test_table03():
    """
    Task: Run the unit tests in Table03_testing.py.
    We change to the src directory before running the tests.
    """
    return {
        "actions": [
            'cd src && ipython -m unittest Table03_testing.py'
        ],
        "file_dep": [
            "./src/Table03_testing.py"
        ],
        "clean": []
    }

def task_pull_fred_data():
    """
    Task: Update FRED historical data and Shiller PE data by calling Table03Load module.
    """
    return {
        "actions": [
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import Table03Load; Table03Load.load_fred_past()"',
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import Table03Load; Table03Load.load_shiller_pe()"'
        ],
        "file_dep": [
            "./src/Table03Load.py"
        ],
        "clean": []
    }


# def task_run_notebook():
#     """
#     Task: Execute the FinalCombinedWalkthrough.ipynb notebook.
#     First clear the notebook outputs, then execute and save it to OUTPUT_DIR.
#     """
#     executed_notebook = Path(OUTPUT_DIR) / "FinalCombinedWalkthrough_executed.ipynb"
#     return {
#         "actions": [
#             f'jupyter nbconvert --ClearOutputPreprocessor.enabled=True --inplace ./src/FinalCombinedWalkthrough.ipynb',
#             f'jupyter nbconvert --to notebook --execute ./src/FinalCombinedWalkthrough.ipynb --output "{executed_notebook}"'
#         ],
#         "file_dep": [
#             "./src/FinalCombinedWalkthrough.ipynb"
#         ],
#         "targets": [
#             str(executed_notebook)
#         ],
#         "clean": []
#     }

def task_generate_latex_doc():
    """
    Task: Integrate all automatically generated .tex and .png files (Table02, Table03, etc.) 
    into one combined LaTeX document, then run pdflatex to produce a PDF.
    """
    return {
        "actions": [
            # Call LaTeXDocGenerator.main() using ipython
            'ipython -c "import sys; sys.path.insert(0, \'src\'); import LaTeXDocGenerator; LaTeXDocGenerator.main()"'
        ],
        # Declare file dependencies (these files must exist before generating the combined document)
        "file_dep": [
            "./src/LaTeXDocGenerator.py",

            "./_output/table02_fixed.tex",
            "./_output/table02_figure.png",
            "./_output/table02_sstable.tex",
            "./_output/table02_corr.tex",
            "./_output/updated_table02_fixed.tex",
            "./_output/updated_table02_figure.png",
            "./_output/updated_table02_sstable.tex",
            "./_output/updated_table02_corr.tex",

            # Domestic-only tables (INCLUDE_FOREIGN=False)
            "./_output/table03.tex",
            "./_output/table03_figure03.png",
            "./_output/table03_sstable.tex",
            "./_output/updated_table03.tex",
            "./_output/updated_table03_figure03.png",
            "./_output/updated_table03_sstable.tex",
            # Domestic + foreign tables (INCLUDE_FOREIGN=True)
            "./_output/table03_intl.tex",
            "./_output/table03_intl_figure03.png",
            "./_output/table03_intl_sstable.tex",
            "./_output/updated_table03_intl.tex",
            "./_output/updated_table03_intl_figure03.png",
            "./_output/updated_table03_intl_sstable.tex",
            # Paper replication figures
            "./_output/figure01.png",
            "./_output/figure04.png",
        ],
        # Explicit task dependencies to guarantee plot_figures runs before this task
        "task_dep": ["plot_figures"],
        # Targets are the files we expect to be generated by this task
        "targets": [
            "./_output/combined_document.tex",
            "./_output/combined_document.pdf"
        ],
        # Keep an empty "clean" so it is declared but does nothing
        "clean": []
    }
