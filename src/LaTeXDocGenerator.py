r"""
LaTeXDocGenerator.py

Key points:
1) Only the 4th table in each group is shrunk (via adjustbox).
2) "Table 3 Replication" includes an extra paragraph of English text explaining the work done
   for the Table 3 replication.
3) Underscore escaping, skipping repeated lines about "There are significantly fewer..." etc.
4) No large chunk of code omitted; this is the final complete version.
"""

import os
import re
import subprocess
from pathlib import Path

##############################################################################
# Helper functions for underscore escaping and skipping repeated lines
##############################################################################

def escape_underscores_in_text(line: str) -> str:
    """
    Escapes underscores unless the line contains \label{ or \includegraphics,
    using a negative lookbehind '(?<!\\)_'.
    """
    if ("\\label{" in line) or ("\\includegraphics" in line):
        return line
    pattern = r'(?<!\\)_'
    return re.sub(pattern, r'\\_', line)

def load_tex_content_no_env(tex_file: Path) -> list[str]:
    """
    Reads lines from a .tex file, skipping:
      - \begin{table}, \end{table}, \caption{
      - repeated descriptive lines about "There are significantly fewer entries..." etc.
    Escapes underscores for other lines unless skipping them.
    """
    skip_phrases = [
        "There are significantly fewer entries for book equity",
        "There are also some negatives for book equity",
        "than for other measures as shown in the count rows."
    ]

    lines_out = []
    if not tex_file.exists():
        return [f"% WARNING: File not found: {tex_file.name}"]

    with open(tex_file, "r", encoding="utf-8") as f:
        for original_line in f:
            line = original_line.rstrip("\n")

            # skip environment lines and \label (labels with spaces break xelatex)
            if any(token in line for token in ["\\begin{table", "\\end{table}", "\\caption{", "\\label{"]):
                continue


            # skip repeated lines
            if any(phrase in line for phrase in skip_phrases):
                continue

            # underscore escaping if not skipping
            lines_out.append(escape_underscores_in_text(line))
    return lines_out

##############################################################################
# Building table env: first 3 => no shrink, 4th => shrink
##############################################################################

def build_table_env_no_shrink(tex_file: Path, custom_title: str, descriptive_text: str = "") -> list[str]:
    """
    \begin{table}[H], no auto-numbering, no adjustbox => no shrink.
    """
    lines = []
    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(f"\\caption{{{escape_underscores_in_text(custom_title)}}}")

    if descriptive_text.strip():
        lines.append(r"\begin{flushleft}")
        for desc_line in descriptive_text.splitlines():
            lines.append(escape_underscores_in_text(desc_line))
        lines.append(r"\end{flushleft}")

    body = load_tex_content_no_env(tex_file)
    lines.extend(body)

    lines.append(r"\end{table}")
    return lines

def build_table_env_shrink(tex_file: Path, custom_title: str, descriptive_text: str = "") -> list[str]:
    """
    \begin{table}[H], uses scalebox to reduce wide tables, no auto-numbering.
    """
    lines = []
    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(f"\\caption{{{escape_underscores_in_text(custom_title)}}}")

    if descriptive_text.strip():
        lines.append(r"\begin{flushleft}")
        for desc_line in descriptive_text.splitlines():
            lines.append(escape_underscores_in_text(desc_line))
        lines.append(r"\end{flushleft}")

    lines.append(r"\scalebox{0.75}{")
    body = load_tex_content_no_env(tex_file)
    lines.extend(body)
    lines.append(r"}")

    lines.append(r"\end{table}")
    return lines

##############################################################################
# Figures
##############################################################################

def build_figure_env(image_filename: str, custom_title: str = "", descriptive_text: str = "") -> list[str]:
    """
    \begin{figure}[H], optional caption, optional flushleft text.
    """
    lines = []
    lines.append(r"\begin{figure}[H]")
    lines.append(r"\centering")

    if custom_title.strip():
        lines.append(f"\\caption{{{escape_underscores_in_text(custom_title)}}}")

    if descriptive_text.strip():
        lines.append(r"\begin{flushleft}")
        for desc_line in descriptive_text.splitlines():
            lines.append(escape_underscores_in_text(desc_line))
        lines.append(r"\end{flushleft}")

    # skip underscore escaping for the \includegraphics line
    lines.append(f"\\includegraphics[width=\\linewidth]{{{image_filename}}}")
    lines.append(r"\end{figure}")
    return lines

##############################################################################
# Main logic
##############################################################################

def main():
    # Output directory
    output_dir = (Path(__file__).resolve().parent.parent / "_output").resolve()
    output_dir.mkdir(exist_ok=True)

    combined_tex_filename = "combined_document.tex"
    combined_tex_path = output_dir / combined_tex_filename

    latex_lines = []

    # Preamble
    latex_lines.append(r"\documentclass{article}")
    latex_lines.append(r"\usepackage[utf8]{inputenc}")
    latex_lines.append(r"\usepackage{graphicx}")
    latex_lines.append(r"\usepackage{geometry}")
    latex_lines.append(r"\usepackage{xcolor}")
    # adjustbox removed: use resizebox from graphicx instead
    latex_lines.append(r"\usepackage{booktabs}")
    latex_lines.append(r"\usepackage{amsmath}")
    latex_lines.append(r"\usepackage{amssymb}")
    latex_lines.append(r"\usepackage{caption}")
    latex_lines.append(r"\usepackage{float}")
    latex_lines.append(r"\captionsetup{labelformat=empty}")
    latex_lines.append(r"\geometry{left=1in, right=1in, top=1in, bottom=1in}")
    latex_lines.append(r"\begin{document}")

    # Title
    latex_lines.append(r"\title{Intermediary asset pricing: New evidence from many asset classes}")
    latex_lines.append(r"\author{Cole Ginter, Alex Nikolaev, and Sunil Trivedi}")
    latex_lines.append(r"\date{March 10th, 2026}")
    latex_lines.append(r"\maketitle")

    # Introduction
    latex_lines.append(r"\section{Introduction}")

    intro_p1 = r"""He, Kelly, and Manela (2017) --- hereafter HKM --- argue that shocks to the equity capital ratio of NY Federal Reserve primary dealer holding companies serve as a priced risk factor across a broad cross-section of asset classes, including equities, US government and corporate bonds, sovereign bonds, options, credit default swaps, commodities, and foreign exchange. Their central measure, the intermediary capital ratio, is defined as the aggregate market equity of primary dealer holding companies divided by their aggregate market assets (market equity plus book debt). Innovations to this ratio, estimated as the residuals of an AR(1) process and scaled by the lagged capital ratio, constitute the intermediary capital risk factor. HKM find that this factor commands a consistently positive and economically significant price of risk across all seven asset classes, providing broad support for the view that primary dealers are marginal investors in many markets."""

    for line in intro_p1.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    latex_lines.append("")

    intro_p2 = r"""This project replicates Table 2 and Table 3 from HKM, as well as Figure 1 and Figure 4. Table 2 documents that NY Fed primary dealers represent a substantial share of the total broker-dealer sector, banking sector, and Compustat universe by total assets, book debt, book equity, and market equity, justifying their use as a representative intermediary sector. Table 3 reports pairwise time-series correlations between the market capital ratio, book capital ratio, and the AEM leverage measure, alongside several macroeconomic indicators, showing that the market capital ratio is strongly procyclical. Figure 1 plots the intermediary capital ratio and capital risk factor from 1970Q1 through 2012Q4, illustrating sharp declines during each NBER recession and particularly around the 2008 financial crisis and the 1998 LTCM collapse. Figure 4 compares HKM's market-based capital ratio with the book capital ratio and the AEM broker-dealer leverage ratio at both the level and innovation (factor) stage, showing that the three measures have meaningfully different behavior despite moderate positive correlations."""

    for line in intro_p2.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    latex_lines.append("")

    intro_p3 = r"""\subsection{Data Sources}"""
    latex_lines.append(intro_p3)

    intro_p4 = r"""The primary data sources are CRSP and Compustat (via WRDS) for domestic primary dealer holding companies, and Datastream for foreign primary dealer holding companies. The list of NY Fed primary dealers from 1960 onward is obtained from the NY Fed's publicly available historical records. A critical element of this replication is correctly matching each primary dealer to its ultimate publicly traded holding company rather than using the broker-dealer subsidiary directly. HKM measure capital at the holding company level because internal capital markets within large financial conglomerates mean that the holding company's financial health --- not the subsidiary's --- best reflects the intermediary's risk-bearing capacity. The prior group whose work we build upon used the primary dealers themselves, which introduced error into the capital ratio construction. To correct this, we followed the methodology of Giannone and Robotti (the \textit{PrimaryDealers\_GR} reference), matching domestic dealers to their holding companies via CRSP/Compustat GVKEYs and PERMNOs, and foreign dealers to their holding companies via Datastream MNEMs. Domestic dealers are those controlled by US-headquartered companies; foreign dealers are controlled by companies headquartered outside the US, spanning currencies including GBP, JPY, EUR, CHF, AUD, CAD, and HKD."""

    for line in intro_p4.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    latex_lines.append("")

    intro_p5 = r"""\subsection{Overview of Replication Results}"""
    latex_lines.append(intro_p5)

    intro_p6 = r"""Overall, our replication is close to the original paper's results. Our Table 2 numbers track the paper's patterns well, with primary dealers representing the near-totality of total assets and book debt in the broker-dealer sector. The primary challenge we encountered for Table 2 was that Compustat data vintages --- in particular, the availability of book debt data in the early part of the sample --- lead to slightly lower asset and equity ratios than those reported by HKM. This is consistent with known coverage gaps in historical Compustat data and does not reflect an error in methodology. For Table 3, incorporating foreign primary dealer holding companies was essential: the original group's domestic-only specification produced correlations that differed noticeably from HKM's, because foreign dealers constitute a substantial share of the primary dealer population, particularly from 1990 onward. Once foreign holding companies are included, our pairwise correlations align closely with those reported in the paper. For Figure 1, the time-series of the intermediary capital ratio and risk factor match the qualitative features of the paper well, capturing the same cyclical patterns and crisis-period drops, though minor differences in levels arise from our data vintage. For Figure 4, we successfully reproduce both Panel A (capital ratio levels) and Panel B (risk factor innovations), with the market capital ratio exhibiting the expected countercyclical leverage pattern relative to AEM. In addition to the original sample period (1960--2012 for Table 2; 1970--2012 for Table 3 and figures), we extend all results through 2020Q4, showing how the capital ratio and correlations evolved during the post-crisis period and the COVID-19 shock."""

    for line in intro_p6.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    ########################################################
    # Table 2 Replication
    ########################################################
    latex_lines.append(r"\section{Table 2 Replication}")

    t2_intro = r"""Table 2 in HKM establishes that NY Fed primary dealers represent a dominant share of the broker-dealer sector and a meaningful share of the broader financial and Compustat universes. For each of the four balance sheet measures --- total assets, book debt, book equity, and market equity --- the table reports the average ratio of the aggregate primary dealer total to the aggregate total for all broker-dealers (BD), all banks, and all Compustat firms over the full 1960--2012 period and two sub-periods (1960--1990 and 1990--2012). Our replication builds on the prior group's code and corrects a key methodological issue: rather than using the primary dealer entities directly, we match each dealer to its ultimate publicly traded holding company using GVKEYs sourced from the Giannone and Robotti reference dataset. This is essential because HKM measure capital at the holding company level, where the financial health of the entire conglomerate --- not just the broker-dealer subsidiary --- captures the intermediary's true risk-bearing capacity. Our ratios closely track those in the paper, confirming that primary dealers account for the vast majority of broker-dealer sector assets and debt throughout the sample. Residual differences from the published numbers are attributable to Compustat historical coverage limitations and data vintage differences. Following the table, we present a time-series plot of the four ratios and supplementary correlation and descriptive statistics tables."""

    for line in t2_intro.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    # sub-item 1) table02_fixed.tex => no shrink
    latex_lines.extend(build_table_env_no_shrink(
        output_dir / "table02_fixed.tex",
        "Table 2 Replication"
    ))
    # sub-item 2) table02_figure.png => figure
    latex_lines.extend(build_figure_env(
        "table02_figure.png",
        "Table 2 Ratios Over Time (1960--2012)",
        "The figure plots the time series of each of the four primary dealer share ratios (total assets, book debt, book equity, and market equity) relative to the broker-dealer sector over the original 1960--2012 sample period. Primary dealers consistently account for a dominant share of broker-dealer total assets and book debt, while their equity share fluctuates more with market conditions."
    ))
    # sub-item 3) table02_corr.tex => no shrink
    latex_lines.extend(build_table_env_no_shrink(
        output_dir / "table02_corr.tex",
        "Table 2 Correlation Analysis"
    ))
    # sub-item 4) table02_sstable => shrink
    latex_lines.extend(build_table_env_shrink(
        output_dir / "table02_sstable.tex",
        "Table 2 Descriptive Statistics"
    ))

    ########################################################
    # Table 2 (Updated)
    ########################################################
    latex_lines.append(r"\section{Table 2 (Updated)}")

    t2u_intro = r"""We extend the Table 2 analysis through 2020Q4. Notably, the Giannone and Robotti reference dataset provided holding company identifiers through 2020, which defined the upper bound of our update. Over the extended sample, the primary dealer sector has continued to evolve relative to the broker-dealer universe as some large institutions exited the primary dealer list and post-crisis financial regulation reshaped the composition of the sector. The updated ratios capture the impact of the 2008 financial crisis, the post-crisis deleveraging, and the COVID-19 shock of 2020 on intermediary balance sheets."""

    for line in t2u_intro.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    # 1) updated_table02_fixed.tex => no shrink
    latex_lines.extend(build_table_env_no_shrink(
        output_dir / "updated_table02_fixed.tex",
        "Table 2(Updated)"
    ))
    # 2) updated_table02_figure.png => figure
    latex_lines.extend(build_figure_env(
        "updated_table02_figure.png",
        "Table 2 Ratios Over Time (1960--2020)",
        "The figure plots the time series of each of the four primary dealer share ratios over the extended 1960--2020 sample period. The post-2012 period reflects structural changes in the primary dealer sector following the Dodd-Frank Act and Basel III requirements, as well as the effects of the COVID-19 shock in 2020Q1--Q2."
    ))
    # 3) updated_table02_corr.tex => no shrink
    latex_lines.extend(build_table_env_no_shrink(
        output_dir / "updated_table02_corr.tex",
        "Table 2 Correlation Analysis(Updated)"
    ))
    # 4) updated_table02_sstable.tex => shrink
    latex_lines.extend(build_table_env_shrink(
        output_dir / "updated_table02_sstable.tex",
        "Table 2 Descriptive Statistics(Updated)"
    ))

    ########################################################
    # Table 3 Replication (Domestic Only)
    ########################################################
    latex_lines.append(r"\section{Table 3 Replication}")

    table3_intro = r"""Table 3 in HKM reports pairwise time-series correlations between three intermediary capital measures --- the market capital ratio, the book capital ratio, and the AEM broker-dealer leverage ratio --- and a set of macroeconomic indicators: the S\&P 500 earnings-to-price ratio, the unemployment rate, GDP growth, the Chicago Fed National Financial Conditions Index, and realized CRSP market volatility. Both level correlations (Panel A) and factor/innovation correlations (Panel B) are reported. The market capital ratio is strongly negatively correlated with unemployment and market volatility and with the E/P ratio, consistent with the view that primary dealer capital falls during economic downturns. A key challenge in replicating Table 3 is that the full primary dealer sample in HKM includes both domestic and foreign dealers. The prior group's replication used only domestic dealers, which led to substantial discrepancies, particularly for the post-1990 period when foreign dealers became a large share of the active primary dealer population. Below we present results for the domestic-only sample for comparison, followed by the full sample including foreign holding companies identified via Datastream MNEMs."""

    for line in table3_intro.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    # 1) table03.tex => no shrink
    latex_lines.extend(build_table_env_no_shrink(
        output_dir / "table03.tex",
        "Table 3 Replication (Domestic Primary Dealers)"
    ))
    # 2) table03_figure03.png => figure
    latex_lines.extend(build_figure_env(
        "table03_figure03.png",
        "Variable Trend Chart (Domestic)",
        "Time-series plots of the market capital ratio and key macroeconomic variables used in the Table 3 correlation analysis, using the domestic-only primary dealer sample over 1970Q1--2012Q4. The capital ratio tracks economic conditions closely, falling during recessions and rising during expansions."
    ))
    # 3) table03_sstable => shrink
    latex_lines.extend(build_table_env_shrink(
        output_dir / "table03_sstable.tex",
        "Table 3 Descriptive Statistics (Domestic)"
    ))

    ########################################################
    # Table 3 (Updated, Domestic Only)
    ########################################################
    latex_lines.append(r"\newpage")
    latex_lines.append(r"\section{Table 3 (Updated)}")

    t3u_intro = r"""The domestic-only Table 3 is extended through 2020Q4. Over this longer horizon, the relationship between the intermediary capital ratio and macroeconomic conditions strengthens in several respects: the 2008 financial crisis represents the largest peacetime shock to the capital ratio in the sample, and the recovery thereafter demonstrates a sustained rebuilding of dealer balance sheets. The correlations for the updated domestic sample show broadly similar patterns to the original period, though the COVID-19 period introduces new dynamics in the financial conditions and volatility measures."""

    for line in t3u_intro.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    # 1) updated_table03.tex => no shrink
    latex_lines.extend(build_table_env_no_shrink(
        output_dir / "updated_table03.tex",
        "Table 3 Updated (Domestic Primary Dealers)"
    ))
    # 2) updated_table03_figure03.png => figure
    latex_lines.extend(build_figure_env(
        "updated_table03_figure03.png",
        "Variable Trend Chart (Domestic, Updated)",
        "Time-series plots of the market capital ratio and macroeconomic variables for the domestic-only sample, extended through 2020Q4. The figure shows the sharp capital ratio decline during the 2008 crisis and the subsequent recovery, as well as the brief disruption during the COVID-19 shock in early 2020."
    ))
    # 3) updated_table03_sstable => shrink
    latex_lines.extend(build_table_env_shrink(
        output_dir / "updated_table03_sstable.tex",
        "Table 3 Descriptive Statistics (Domestic, Updated)"
    ))

    ########################################################
    # Table 3 Replication (Domestic + Foreign)
    ########################################################
    latex_lines.append(r"\section{Table 3 Replication (Domestic + Foreign Primary Dealers)}")

    t3intl_intro = r"""This section presents the Table 3 replication using the full sample of primary dealers, including both domestic holding companies (matched via CRSP/Compustat GVKEYs) and foreign holding companies (matched via Datastream MNEMs). This is the specification that corresponds most closely to HKM's published results, as the original paper constructs the capital ratio using all publicly traded holding companies of active NY Fed primary dealers regardless of their country of headquarters. Foreign primary dealers include institutions from Great Britain, Japan, continental Europe, Canada, Switzerland, Australia, and Hong Kong. Including the foreign sample increases the number of active intermediaries in the average quarter from approximately 15 domestic to over 22 total, materially affecting the capital ratio and its correlations with macroeconomic variables. Our full-sample correlations are substantially closer to HKM's published Table 3 than the domestic-only results, confirming that the inclusion of foreign dealers is necessary to accurately replicate the paper."""

    for line in t3intl_intro.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    # 1) table03_intl.tex => no shrink
    latex_lines.extend(build_table_env_no_shrink(
        output_dir / "table03_intl.tex",
        "Table 3 Replication (Domestic + Foreign Primary Dealers)"
    ))
    # 2) table03_intl_figure03.png => figure
    latex_lines.extend(build_figure_env(
        "table03_intl_figure03.png",
        "Variable Trend Chart (Domestic + Foreign)",
        "Time-series plots of the market capital ratio and macroeconomic variables for the full domestic-plus-foreign primary dealer sample over 1970Q1--2012Q4. Including foreign primary dealer holding companies increases the representativeness of the capital ratio and brings the series closer to HKM's published results."
    ))
    # 3) table03_intl_sstable => shrink
    latex_lines.extend(build_table_env_shrink(
        output_dir / "table03_intl_sstable.tex",
        "Table 3 Descriptive Statistics (Domestic + Foreign)"
    ))

    ########################################################
    # Table 3 (Updated, Domestic + Foreign)
    ########################################################
    latex_lines.append(r"\section{Table 3 (Updated, Domestic + Foreign Primary Dealers)}")

    t3intlu_intro = r"""Finally, we extend the full domestic-plus-foreign Table 3 through 2020Q4, again reaching the boundary of what the Giannone and Robotti reference dataset supports. The post-2012 period includes a growing share of foreign dealers as the NY Fed continued to update its primary dealer list, and the updated correlations reflect how the intermediary capital ratio's relationship with macroeconomic variables evolved through the post-crisis expansion and the COVID-19 shock. Broadly, the updated full sample continues to display the same procyclical pattern of the capital ratio seen in the original period, with notable drops in the capital ratio coinciding with elevated unemployment, tighter financial conditions, and elevated market volatility."""

    for line in t3intlu_intro.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    # 1) updated_table03_intl.tex => no shrink
    latex_lines.extend(build_table_env_no_shrink(
        output_dir / "updated_table03_intl.tex",
        "Table 3 Updated (Domestic + Foreign Primary Dealers)"
    ))
    # 2) updated_table03_intl_figure03.png => figure
    latex_lines.extend(build_figure_env(
        "updated_table03_intl_figure03.png",
        "Variable Trend Chart (Domestic + Foreign, Updated)",
        "Time-series plots of the market capital ratio and macroeconomic variables for the full sample extended through 2020Q4. This represents the most comprehensive version of our update, incorporating the full primary dealer universe and the most recent data supported by our holding company identifiers."
    ))
    # 3) updated_table03_intl_sstable => shrink
    latex_lines.extend(build_table_env_shrink(
        output_dir / "updated_table03_intl_sstable.tex",
        "Table 3 Descriptive Statistics (Domestic + Foreign, Updated)"
    ))

    ########################################################
    # Paper Figures (Extensions)
    ########################################################
    latex_lines.append(r"\newpage")
    latex_lines.append(r"\section{Paper Figures (Extensions)}")

    figs_intro = r"""This section replicates Figure 1 and Figure 4 from HKM. Figure 1 provides the primary time-series visualization of the intermediary capital ratio and its associated risk factor over the full 1970Q1--2012Q4 sample. Figure 4 is a comparison figure that places HKM's market-based capital ratio alongside two alternative measures of intermediary capital --- the book capital ratio and the AEM broker-dealer leverage ratio --- in order to explain why HKM's results differ from those of Adrian, Etula, and Muir (2014). Both figures were replicated by constructing the capital ratio series from scratch using our matched primary dealer holding company dataset."""

    for line in figs_intro.splitlines():
        latex_lines.append(escape_underscores_in_text(line))

    # Figure 1: Intermediary capital ratio and risk factor
    latex_lines.extend(build_figure_env(
        "figure01.png",
        "Figure 1: Intermediary Capital Ratio and Risk Factor",
        "The solid line plots the aggregate market-based capital ratio of NY Fed primary dealer holding companies, defined as the ratio of total market equity to total market assets (market equity plus book debt), standardized to zero mean and unit variance. The dashed line plots the intermediary capital risk factor, defined as the AR(1) innovation to the capital ratio scaled by the lagged capital ratio, also standardized. Both series are at the quarterly frequency. The capital ratio falls sharply during each NBER recession (shaded regions), with the most pronounced drops occurring around the 1998 LTCM collapse and the 2008 financial crisis. The risk factor captures these unexpected changes in dealer financial health and serves as the main pricing factor in HKM's cross-sectional asset pricing tests. Our replicated series closely matches the published figure, with minor differences attributable to data vintage."
    ))

    # Figure 4: Two-panel comparison of capital measures
    latex_lines.extend(build_figure_env(
        "figure04.png",
        "Figure 4: Intermediary Capital Measures Comparison",
        "Panel A plots the three intermediary capital measures in levels on a log scale: HKM's market-based capital ratio (solid line), the book capital ratio (dotted line), and the AEM implied leverage ratio from the Federal Reserve's Flow of Funds (dashed line). The market and book capital ratios are expressed as percentages. The AEM leverage ratio is substantially more volatile and exhibits procyclical leverage, which is the opposite sign prediction from HKM's countercyclical leverage. Panel B plots the corresponding risk factors (AR(1) innovations) for each measure. The correlation between the market and book capital factors is 0.30, and between the market capital and AEM leverage factors is 0.14, confirming that these measures capture meaningfully different aspects of intermediary financial conditions. Shaded regions indicate NBER recessions. The replication of this figure helps contextualize why HKM's pricing results differ from AEM's: the two papers measure different levels of the financial intermediary hierarchy (holding company versus broker-dealer subsidiary) and use market versus book values of equity."
    ))

    latex_lines.append(r"\end{document}")

    final_tex = "\n".join(latex_lines)
    with open(combined_tex_path, "w", encoding="utf-8") as f:
        f.write(final_tex)

    print(f"Merged LaTeX file generated at: {combined_tex_path}")

    # xelatex
    try:
        subprocess.run(
            ["xelatex", "-interaction=nonstopmode", combined_tex_filename],
            cwd=output_dir,
            check=True,
            timeout=60
        )
        print("XeLaTeX compilation successful!")
    except subprocess.CalledProcessError as e:
        print("XeLaTeX compilation failed (xelatex returned an error):", e)
    except subprocess.TimeoutExpired:
        print("xelatex command timed out.")

if __name__ == "__main__":
    main()
