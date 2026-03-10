# Intermediary Asset Pricing Replication Project

This repository contains our final project for replicating tables and figures from the paper "Intermediary Asset Pricing: New Evidence from Many Asset Classes." Our goal is to reproduce key tables (Table 2 and Table 3) and figures (Figure 1 and Figure 4) from the paper using data from CRSP, Compustat, and Datastream and to update these results with the latest available data.

---

## Project Overview

The paper argues that capital shocks to financial intermediaries can explain cross-sectional differences in expected returns across various asset classes (stocks, bonds, options, commodities, currencies, and credit default swaps). Based on this idea, our project focuses on:
- **Building Risk Factors:** We construct risk factors using financial intermediaries' capital ratios.
- **Replicating Table 2:** This table shows the relative size of major market makers by calculating monthly ratios of total assets, book debt, book equity, and market equity relative to different market groups, and then averaging these ratios over time.
- **Replicating Table 3:**
  - *Panel A:* Computes the Market Capital Ratio, Book Capital Ratio, and AEM Leverage Ratio, and explores the correlations among these ratios and key economic variables.
  - *Panel B:* Constructs risk factors from the ratios in Panel A and analyzes their correlations with each other and with the growth rates of various economic indicators.
- **Replicating Figure 1:** The Intermediary Capital Ratio (ICR) and the Intermediary Capital Risk Factor - AR(1) innovations of the ICR scaled by the lagged captial ratio.
- **Replicating Figure 4:**
  - *Panel A*: The levels of the capital and leverage ratios.
  - *Panel B*: Innovations in the state variables of Panel A.

---

## Data & Methodology

- **Data Sources:**  
  We modified the primary dealer list based on real data sources and holding company information. The `ticks.csv` file was updated according to the corresponding gvkey codes.
  
- **Modifications to Calculations:**  
  We adjusted the calculation logic for important ratios and macroeconomic variables (e.g., key ratios and updated macro variable computations) based on the paper’s description, resulting in significant optimization of the replicated results for the tables and figures.
  
- **Output Generation:**  
  The reproduced table results are automatically generated as LaTeX (.tex) files and saved in the output directory. Further data analysis, including descriptive statistics, correlation analysis, and visualization of ratio trends, was also performed.

- **Automation:**  
  We implemented complete automation of the project workflow, storing all results in the `_output` directory.

---

## Project Structure

- **LaTeX Documents:**  
  Auto-generated LaTeX files include the replicated tables and additional figures from the paper.
  
- **Jupyter Notebook:**  
  A comprehensive notebook demonstrates data processing, ratio calculations, table generation, and analysis results.

- **Python Code Files:**  
  Scripts for data download, processing, and metric calculations are included. Each file contains detailed docstrings describing its functionality.

- **Automation (dodo.py):**  
  The `dodo.py` file automates the entire project workflow including data fetching, processing, table generation, and even running the final notebook.

- **Test Files:**  
  Unit tests for both Table 2 and Table 3 have been developed to ensure the replication results closely match the original paper.

- **Additional Files:**  
  The repository also includes supplementary files such as a README, an environment example file (`.env.example`), and other auxiliary scripts to ensure a clear and rigorous project process.(If you want to clone our repository, please ensure you have an .env file (or rename .env.example to .env) and specify the paths for DATA_DIR and OUTPUT_DIR so that the scripts can locate input data and store all generated output files correctly.)

---

## Setup & Usage

1. **Clone the Repository:**
   ```bash
   git clone <link-to-repository>
   cd p07_he_kelly_manela_2017

2. **Create and Activate the Virtual Environment:**
   ```bash
   conda create --name <env-name> python=3.12
   conda activate <env-name>

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt

4. **Run the Project:**
   ```bash
   doit

## Contact

If you have any questions or suggestions, please feel free to reach out via GitHub issues or contact the project members directly.