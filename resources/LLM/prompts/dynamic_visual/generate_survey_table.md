# Professional Survey Table Generation Prompt

You are a LaTeX expert specializing in creating professional academic survey tables. Your task is to generate a comprehensive, systematic comparison table suitable for survey/review papers.

## Survey Topic
{topic}

## Table Description
{description}

## Table Type
{table_type}

## Data Requirements
{data_requirements}

## Available Citations (MUST USE THESE EXACT BIB KEYS)
{available_citations}

## Reference Content
{section_content}

---

## Professional Survey Table Guidelines

### Key Characteristics of High-Quality Survey Tables

1. **Clean and Minimal Design**: Use booktabs style with \toprule, \midrule, \bottomrule - no vertical lines
2. **Categorical Organization**: Group entries by meaningful categories when appropriate
3. **Citation Integration**: Each entry should include proper citation markers like \cite{reference}
4. **Symbol System**: Use consistent symbols:
   - $\checkmark$ for supported/present/yes
   - $\times$ for not supported/absent/no
   - $\uparrow$ (increasing trend), $\downarrow$ (decreasing trend), $\rightarrow$ (stable/flat)
   - Use asterisk (*) for statistical significance
5. **Temporal Information**: Include actual publication dates (e.g., 2023, 2024) when relevant. NEVER use placeholder text like "YYYY-MM" in the output.
6. **Quantitative Data**: Include specific numbers with percentages where applicable (e.g., "1,463 (17.0%)")

### Table Type Guidelines

#### statistics_table
For presenting data statistics and distributions:
- Columns: Category/Source, Year-wise counts, Totals
- Style: Clean numeric data with clear headers
- Example use: Paper counts by venue and year, dataset statistics

#### annotation_scheme_table
For presenting labeling/annotation schemes:
- Columns: Label/Rating, Description, Count/Percentage
- Style: Clear descriptions with numeric summaries
- Example use: Classification schemes, rating distributions

#### distribution_matrix_table
For showing cross-tabulated distributions:
- Columns: One dimension as rows, another as columns, with counts
- Style: Compact matrix format with totals
- Example use: Year × Venue distributions, Category × Type matrices

#### performance_comparison_table
For comparing model/method performance:
- Columns: Model/Method, Configuration, Metrics (multiple)
- Style: Highlight best results (bold/underline)
- Example use: Model benchmarks, ablation studies

#### evidence_table
For presenting qualitative evidence with citations:
- Columns: Topic/Category, Evidence/Quote, Source
- Style: Wider description columns, proper quotation formatting
- Example use: Literature evidence, case studies

#### trend_analysis_table
For showing trends over time:
- Columns: Topic, Method1 Trend, Method2 Trend, Agreement, Correlation
- Style: Use arrows (↑↓→) for trends, checkmarks for agreement
- Example use: Temporal analysis, method comparison

#### benchmark_comparison
For comparing benchmarks/datasets:
- Columns: Name, Focus/Domain, Size metrics, Source, Key features (binary), Time
- Group by: General vs. Specialized, or by application domain
- Include: Dataset statistics, supported tasks, availability

#### method_comparison
For comparing methods/approaches:
- Columns: Method name, Category, Key technique, Performance metrics, Year
- Group by: Methodology type (e.g., supervised vs. unsupervised)
- Include: Quantitative results where available

#### contribution_summary_table
For summarizing key contributions of papers:
- Columns: Work/Paper, Main Contribution, Innovation Type (tags), Impact Level
- Style: Use colored tags for innovation types, star ratings for impact
- Group by: Research theme or contribution type
- Include: Brief but impactful contribution descriptions
- **CRITICAL for Work/Paper column**:
  - ALWAYS use a descriptive name (method name, system name, or paper title) followed by citation
  - Format: "MethodName \cite{bibkey}" or "Paper Title \cite{bibkey}"
  - NEVER use just citation numbers like "[1]" or "\cite{ref}" alone without a name
  - If no method name exists, use the first author's name + year (e.g., "Smith et al. \cite{bibkey}")

#### research_landscape_table
For presenting multi-dimensional research landscape analysis:
- Columns: Dimension/Aspect, Sub-categories, Representative Works, Maturity Level, Trend
- Style: Use progress bars or filled circles for maturity, arrows for trends
- Include: Coverage indicators showing research density in each area
- Group by: Major research dimensions

---

## LaTeX Requirements

### Required Packages (already in preamble - DO NOT include)
The main document already has: booktabs, multirow, xcolor, colortbl, array, makecell, pifont

### Symbol Usage (already defined - DO NOT redefine)
- \checkmark or $\checkmark$ for check marks
- $\times$ for X marks
- $\uparrow$, $\downarrow$, $\rightarrow$ for trend arrows
- **Maturity/Progress Indicators** (use pifont \ding symbols):
  - \ding{108} for filled circle (Mature)
  - \ding{119} for half-filled circle (Developing)
  - \ding{109} for empty circle (Emerging)
  - **DO NOT USE**: \CIRCLE, \LEFTcircle, \Circle (these require wasysym package which is NOT loaded)

### CRITICAL: \multirow Syntax
When using \multirow with \rowcolor, ensure proper bracket closure:
- **CORRECT**: `\rowcolor{blue!8} \multirow{4}{*}{\textbf{Category Name}}`
- **WRONG**: `\rowcolor{blue!8} \multirow{4}{*}{\textbf{Category Name}` (missing closing `}`)

---

## Output Format

Generate ONLY the LaTeX table code wrapped in ```latex blocks.

**CRITICAL REQUIREMENTS:**
- **DO NOT** include `\documentclass`, `\usepackage`, `\begin{document}`, `\end{document}`, or any document preamble
- **DO NOT** include `\definecolor` or `\newcommand` definitions (these are already defined in the main document)
- **ONLY** output the `\begin{table}...\end{table}` environment
- The table will be included via `\input{}` in a larger document, so it must be a standalone table fragment
- **NEVER** use placeholder text like "YYYY-MM", "[topic]", "TBD" - always use actual values

The table should:

1. Use `\toprule`, `\midrule`, `\bottomrule` from booktabs (NO vertical lines)
2. Use `\rowcolor{categorygreen}` for category header rows (only when categorizing)
3. Use `\resizebox{\textwidth}{!}{...}` only if table is too wide
4. Include meaningful `\caption` with clear description
5. Include `\label{tab:...}` for cross-referencing
6. Use `\cite{...}` for all referenced works
7. Right-align numeric columns, left-align text columns

---

## Example Templates

### Template 1: Statistics Table (Paper Counts by Source and Year)
```latex
\begin{table}[htbp]
\centering
\caption{Crawled vs. LLM-filtered paper counts across sources (2022--2025). Each cell shows Crawled / LLM-filtered counts. ACL venues do not include data for 2025.}
\label{tab:paper_counts}
\begin{tabular}{lrrrr}
\toprule
\textbf{Source / Year} & \textbf{2022} & \textbf{2023} & \textbf{2024} & \textbf{2025} \\
\midrule
\textit{ACL} & 1,032 / 294 & 1,977 / 821 & 1,916 / 1,483 & -- / -- \\
\textit{EMNLP} & 1,372 / 520 & 2,107 / 1,177 & 2,273 / 1,844 & -- / -- \\
\textit{ICLR} & 1,094 / 143 & 1,573 / 251 & 2,260 / 674 & -- / -- \\
\textit{NAACL} & 652 / 217 & -- / -- & 859 / 588 & -- / -- \\
\midrule
\textit{ArXiv} & 52,642 / 5,726 & 66,179 / 13,361 & 85,645 / 27,700 & 22,791 / 8,688 \\
\midrule
\textbf{Yearly Total} & \textbf{57,072 / 6,986} & \textbf{72,546 / 15,883} & \textbf{94,390 / 32,553} & \textbf{22,791 / 8,688} \\
\bottomrule
\end{tabular}
\end{table}
```

### Template 2: Annotation Scheme Table
```latex
\begin{table}[htbp]
\centering
\caption{Annotation scheme for LLM limitation discussion, including label descriptions and distribution of papers in the human annotated dataset.}
\label{tab:annotation_scheme}
\begin{tabular}{clr}
\toprule
\textbf{Label} & \textbf{Description} & \textbf{Count} \\
\midrule
0 & No mention of LLMs. & 62 \\
1 & Mentions LLMs but not their limitations. & 106 \\
2 & Briefly mentions a limitation, e.g., as justification for a new method. & 169 \\
3 & Discusses one or two limitations in moderate detail but not as the primary focus. & 62 \\
4 & Extensively discusses multiple limitations, making them a major focus. & 37 \\
5 & Entirely focused on LLM limitations and challenges. & 9 \\
\bottomrule
\end{tabular}
\end{table}
```

### Template 3: Distribution Matrix Table
```latex
\begin{table}[htbp]
\centering
\caption{Venue-year distribution of papers in the human-annotated dataset.}
\label{tab:venue_year_dist}
\begin{tabular}{lrrrrrrrrr}
\toprule
\textbf{Year} & \textbf{arxiv} & \textbf{acl} & \textbf{aacl} & \textbf{eacl} & \textbf{emnlp} & \textbf{iclr} & \textbf{naacl} & \textbf{tacl} & \textbf{Total} \\
\midrule
2022 & 17 & 15 & 4 & 0 & 21 & 2 & 14 & 0 & 73 \\
2023 & 69 & 22 & 0 & 4 & 39 & 0 & 0 & 82 & 216 \\
2024 & 62 & 19 & 0 & 6 & 25 & 4 & 13 & 27 & 156 \\
\midrule
\textbf{Total} & 148 & 56 & 4 & 10 & 85 & 6 & 27 & 109 & \textbf{445} \\
\bottomrule
\end{tabular}
\end{table}
```

### Template 4: Performance Comparison Table
```latex
\begin{table}[htbp]
\centering
\caption{Weighted Cohen's Kappa for limitation ratings and pairwise F1 scores for evidence extraction across models and prompts. The best weighted Kappa for each model is \underline{underlined}, while the best score overall is in \textbf{bold}.}
\label{tab:model_performance}
\begin{tabular}{llcc}
\toprule
\textbf{Model} & \textbf{Prompt} & \textbf{Weighted Kappa} & \textbf{Evidence F1} \\
\midrule
\multirow{3}{*}{Mistral-7B-Instruct-v0.3} & Prompt 1 & 0.25 & \\
 & Prompt 2 & \underline{0.60} & \\
 & Prompt 3 & \underline{0.60} & 0.36 \\
\midrule
\multirow{3}{*}{Llama-3.1-70b-Instruct} & Prompt 1 & 0.60 & \\
 & Prompt 2 & 0.73 & \\
 & Prompt 3 & \underline{\textbf{0.74}} & \textbf{0.65} \\
\midrule
\multirow{3}{*}{GPT-4o} & Prompt 1 & 0.49 & \\
 & Prompt 2 & 0.68 & \\
 & Prompt 3 & \underline{0.72} & 0.64 \\
\midrule
SBERT + log. regression & -- & 0.43 & -- \\
\bottomrule
\end{tabular}
\end{table}
```

### Template 5: Rating Distribution Table
```latex
\begin{table}[htbp]
\centering
\caption{Distribution of ratings for ACL and arXiv papers. The \textit{ACL Count (\%)} and \textit{arXiv Count (\%)} columns show the number of papers with each rating and their percentage within the respective datasets.}
\label{tab:rating_distribution}
\begin{tabular}{crrr}
\toprule
\textbf{Rating} & \textbf{ACL Count (\%)} & \textbf{arXiv Count (\%)} & \textbf{Total Count (\%)} \\
\midrule
0 & 861 (10.0\%) & 11,416 (20.6\%) & 12,277 (19.2\%) \\
1 & 1,463 (17.0\%) & 10,967 (19.8\%) & 12,430 (19.4\%) \\
2 & 3,911 (45.4\%) & 20,810 (37.5\%) & 24,721 (38.6\%) \\
3 & 1,274 (14.8\%) & 6,057 (10.9\%) & 7,331 (11.4\%) \\
4 & 1,035 (12.0\%) & 5,723 (10.3\%) & 6,758 (10.5\%) \\
5 & 78 (0.9\%) & 481 (0.9\%) & 559 (0.9\%) \\
\midrule
\textbf{Limitation Papers (3--5)} & \textbf{2,387 (27.7\%)} & \textbf{12,261 (22.1\%)} & \textbf{14,648 (22.9\%)} \\
\bottomrule
\end{tabular}
\end{table}
```

### Template 6: Topic Evidence Table
```latex
\begin{table}[htbp]
\centering
\caption{Representative limitation-focused papers, grouped by topic based on clustering. Evidence is extracted from papers with a topic probability of 0.9 or higher.}
\label{tab:topic_evidence}
\begin{tabular}{cp{12cm}}
\toprule
\textbf{Topic} & \textbf{Evidence} \\
\midrule
(1) Reasoning & ``However, applying this [common-sense] reasoning to multimodal domains, where understanding text and images together is essential, remains a substantial challenge.'' (ACL 2024 \cite{ref81}) \\
\midrule
(2) Hallucination & ``Challenges on hallucination and factual inconsistency continue to impede their [LLMs'] wider real-world adoption.'' (EACL 2024 \cite{ref65}) \\
\midrule
(3) Security & ``The prevalence and strong capability of large language models (LLMs) present significant safety and ethical risks if exploited by malicious users.'' (TACL 2024 \cite{ref95}) \\
\midrule
(4) Generalization & ``LLMs are generally trained on publicly available text and code and cannot be expected to directly generalize to domain-specific parsing tasks in a zero-shot setting.'' (EMNLP 2023 \cite{ref73}) \\
\bottomrule
\end{tabular}
\end{table}
```

### Template 7: Trend Analysis Table
```latex
\begin{table}[htbp]
\centering
\caption{Comparison of limitation trends identified by HDBSCAN and LlooM for ACL and arXiv datasets. Trend direction ($\uparrow$ increasing, $\rightarrow$ flat, $\downarrow$ decreasing) is based on Kendall's Tau. Significance is indicated with an asterisk (*).}
\label{tab:trend_comparison}
\begin{tabular}{llcccc}
\toprule
\textbf{HDBSCAN Topic} & \textbf{LlooM Topic} & \textbf{HDBSCAN} & \textbf{LlooM} & \textbf{Match} & \textbf{Spearman $\rho$} \\
\midrule
Security & Security Risks & $\rightarrow$ & $\uparrow$ & $\times$ & 0.661* \\
Generalization & Generalization & $\rightarrow$ & $\rightarrow$ & $\checkmark$ & 0.552 \\
Social Bias & Bias and Fairness & $\rightarrow$ & $\rightarrow$ & $\checkmark$ & 0.539 \\
Hallucination & Hallucination & $\uparrow$ & $\rightarrow$ & $\times$ & 0.539 \\
Reasoning & Reasoning & $\downarrow$ & $\rightarrow$ & $\times$ & 0.430 \\
Long Context & Long Context & $\rightarrow$ & $\uparrow$* & $\times$ & 0.006 \\
\bottomrule
\end{tabular}
\end{table}
```

### Template 8: Benchmark Comparison Table (Categorized)
```latex
\begin{table}[htbp]
\centering
\caption{A comprehensive comparison of evaluation benchmarks for function calling LLMs. Benchmarks are categorized by their primary evaluation objective.}
\label{tab:benchmark_comparison}
\resizebox{\textwidth}{!}{%
\begin{tabular}{llccccc}
\toprule
\textbf{Benchmark} & \textbf{Focus} & \textbf{\# Tools} & \textbf{\# Instances} & \textbf{Multi} & \textbf{Exec} & \textbf{Year} \\
\midrule
\rowcolor{categorygreen} \multicolumn{7}{l}{\textbf{General Benchmarks}} \\
\midrule
API-Bank \cite{li2023apibank} & Task Planning & 73 & 314 & $\checkmark$ & $\checkmark$ & 2023 \\
APIBench \cite{patil2023gorilla} & Tool Selection & 1,645 & 16,450 & $\times$ & $\times$ & 2023 \\
ToolBench \cite{xu2023toolbench} & Tool Calling & 232 & 2,746 & $\times$ & $\checkmark$ & 2023 \\
\midrule
\rowcolor{categorygreen} \multicolumn{7}{l}{\textbf{Domain-Specific Benchmarks}} \\
\midrule
ToolQA \cite{zhuang2023toolqa} & QA & 13 & 1,530 & $\times$ & $\checkmark$ & 2023 \\
SciToolBench \cite{lu2024scitoolbench} & Scientific Reasoning & 2,446 & 856 & $\checkmark$ & $\checkmark$ & 2024 \\
\bottomrule
\end{tabular}%
}
\end{table}
```

### Template 9: Mathematical Formula Comparison Table
```latex
\begin{table}[htbp]
\centering
\caption{A comparative overview of various linear sequence modeling approaches in terms of their memory update rules and optimization objectives. The trajectory reflects a shift from data-independent to data-dependent gating mechanisms.}
\label{tab:formula_comparison}
\resizebox{\textwidth}{!}{%
\begin{tabular}{llcc}
\toprule
\textbf{Type} & \textbf{Model} & \textbf{Memorizing with \textcolor{magenta}{Gate}} & \textbf{Optimization Objective $\mathcal{L}_{\min}$} \\
\midrule
\multirow{2}{*}{Softmax Attn} & SA \cite{ref62} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1}.\text{append}(\boldsymbol{k}_t, \boldsymbol{v}_t)$ & $\sum_{i=1}^{t} \exp(\boldsymbol{q}_t^\top \boldsymbol{k}_i) \|\boldsymbol{v} - \boldsymbol{v}_i\|^2$ \\
 & SWA \cite{ref119} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1}.\text{append}(\boldsymbol{k}_t, \boldsymbol{v}_t).\text{drop}(\boldsymbol{k}_{t-M}, \boldsymbol{v}_{t-M})$ & $\sum_{i=t-M}^{t} \exp(\boldsymbol{q}_t^\top \boldsymbol{k}_i) \|\boldsymbol{v} - \boldsymbol{v}_i\|^2$ \\
\midrule
\multirow{4}{*}{Linear Attn} & LA \cite{ref64} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1} + \boldsymbol{v}_t \boldsymbol{k}_t^\top$ & $\langle \boldsymbol{S}_t \boldsymbol{k}_t, \boldsymbol{v}_t \rangle$ \\
 & Lightning Attn \cite{ref70} & $\boldsymbol{S}_t = \textcolor{magenta}{\alpha} \boldsymbol{S}_{t-1} + \boldsymbol{v}_t \boldsymbol{k}_t^\top$ & $\langle \boldsymbol{S}_t \boldsymbol{k}_t, \boldsymbol{v}_t \rangle + \frac{\alpha}{2} \|\boldsymbol{S}_t\|_2^2$ \\
 & RetNet \cite{ref245} & $\boldsymbol{S}_t = \textcolor{magenta}{\alpha} \boldsymbol{S}_{t-1} + \boldsymbol{v}_t \boldsymbol{k}_t^\top$ & $\langle \boldsymbol{S}_t \boldsymbol{k}_t, \boldsymbol{v}_t \rangle + \frac{\alpha}{2} \|\boldsymbol{S}_t\|_2^2$ \\
 & GLA \cite{ref71} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1} \text{diag}(\boldsymbol{\alpha}_t) + \boldsymbol{v}_t \boldsymbol{k}_t^\top$ & $\langle \boldsymbol{S}_t \boldsymbol{k}_t, \boldsymbol{v}_t \rangle + \frac{\alpha}{2} \|\boldsymbol{S}_t\|_2^2$ \\
\midrule
\multirow{3}{*}{Linear RNN} & HGRN2 \cite{ref80} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1} \text{diag}(\boldsymbol{\alpha}_t) + \boldsymbol{v}_t (\boldsymbol{1} - \boldsymbol{\alpha}_t)^\top$ & $\langle \boldsymbol{S}_t (\boldsymbol{1} - \boldsymbol{\alpha}_t), \boldsymbol{v}_t \rangle + \frac{\alpha_t}{2} \|\boldsymbol{S}_t\|_2^2$ \\
 & RWKV6 \cite{ref82} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1} \text{diag}(\boldsymbol{\alpha}_t) + \boldsymbol{v}_t \boldsymbol{k}_t^\top$ & $\langle \boldsymbol{S}_t \boldsymbol{k}_t, \boldsymbol{v}_t \rangle + \frac{\alpha_t}{2} \|\boldsymbol{S}_t\|_2^2$ \\
 & RWKV7 \cite{ref83} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1} (\text{diag}(\boldsymbol{\alpha}_t) - \beta_t \hat{\boldsymbol{k}}_t \hat{\boldsymbol{k}}_t^\top) + \boldsymbol{v}_t \bar{\boldsymbol{k}}_t^\top$ & $\beta_t \left\| \frac{1}{\beta_t} \boldsymbol{v}_t - \boldsymbol{S}_t \boldsymbol{k}_t \right\|^2 + \frac{\alpha_t}{2} \|\boldsymbol{S}_t\|_2^2$ \\
\midrule
\multirow{3}{*}{SSM} & S4 \cite{ref90} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1} \text{diag}(\boldsymbol{\alpha}) + \boldsymbol{v}_t \boldsymbol{b}^\top \in \mathbb{C}$ & $\langle \boldsymbol{S}_t \boldsymbol{b}, \boldsymbol{v}_t \rangle + \frac{\alpha}{2} \|\boldsymbol{S}_t\|_2^2$ \\
 & Mamba \cite{ref101} & $\boldsymbol{S}_t = \boldsymbol{S}_{t-1} \text{diag}(\boldsymbol{\alpha}) + \beta_t^{\sim 0} \boldsymbol{v}_t \boldsymbol{k}_t^\top$ & $\beta_t \langle \boldsymbol{S}_t \boldsymbol{k}_t, \boldsymbol{v}_t \rangle + \frac{\alpha_t}{2} \|\boldsymbol{S}_t\|_2^2$ \\
 & Mamba2 \cite{ref102} & $\boldsymbol{S}_t = \alpha_t^{\sim 1} \boldsymbol{S}_{t-1} + \beta_t^{\sim 0} \boldsymbol{v}_t \boldsymbol{k}_t^\top$ & $\beta_t \langle \boldsymbol{S}_t \boldsymbol{k}_t, \boldsymbol{v}_t \rangle + \frac{\alpha_t}{2} \|\boldsymbol{S}_t\|_2^2$ \\
\bottomrule
\end{tabular}%
}
\end{table}
```

### Template 10: Application Overview Table (Multi-row with Citations)
```latex
\begin{table}[htbp]
\centering
\caption{Overview of Applications of Efficient Architectures Across Modalities and Categories.}
\label{tab:application_overview}
\resizebox{\textwidth}{!}{%
\begin{tabular}{llp{12cm}}
\toprule
\textbf{Modality} & \textbf{Category} & \textbf{Approach} \\
\midrule
\multirow{7}{*}{Vision} & Classification & InsectMamba \cite{ref208}, V-MoE \cite{ref332}, MoE-CNN \cite{ref368}, pMoE \cite{ref369}, Res-vmamba \cite{ref370}, Mammil \cite{ref371} \\
\cmidrule{2-3}
 & Detection & Vig \cite{ref205}, Vision-rwkv \cite{ref206}, Tutel \cite{ref207}, Mamba yolo \cite{ref374}, Voxel mamba \cite{ref209} \\
\cmidrule{2-3}
 & Segmentation & RWKV-SAM \cite{ref378}, Segman \cite{ref379}, VM-Unet \cite{ref380}, Pyramidmamba \cite{ref381} \\
\cmidrule{2-3}
 & Enhancement \& Restoration & Restore-rwkv \cite{ref382}, Dvmsr \cite{ref383}, Q-mambar \cite{ref384}, RWKV-IR \cite{ref385}, Pixmamba \cite{ref386} \\
\cmidrule{2-3}
 & Generation & DiS \cite{ref396}, Dim \cite{ref397}, DiM \cite{ref210}, Zigma \cite{ref398}, AiM \cite{ref399}, Maskmamba \cite{ref400} \\
\cmidrule{2-3}
 & Medicine & U-mamba \cite{ref211}, Vm-unet \cite{ref212}, Rwkv-unet \cite{ref213}, Segmamba \cite{ref406}, Zig-rir \cite{ref407} \\
\cmidrule{2-3}
 & Autonomous Driving & Mambabev \cite{ref214}, Occrwkv \cite{ref415}, H-mba \cite{ref416}, Trajectory mamba \cite{ref417} \\
\midrule
\multirow{2}{*}{Audio} & Understanding & Audio mamba \cite{ref215}, Mamca \cite{ref216}, Rawbmamba \cite{ref217}, BiMamba \cite{ref220}, Ssamba \cite{ref432} \\
\cmidrule{2-3}
 & Enhancement \& Generation & SEMamba \cite{ref433}, Tramba \cite{ref434}, SaShiMi \cite{ref218}, Music-Diff \cite{ref219} \\
\midrule
\multirow{2}{*}{Multimodality} & Understanding & MaTAV \cite{ref224}, Avs-mamba \cite{ref225}, Av-mamba \cite{ref436}, VisualRWKV-UHD \cite{ref226} \\
\cmidrule{2-3}
 & Unified & Fragkiadaki \cite{ref202}, Mmada \cite{ref204} \\
\bottomrule
\end{tabular}%
}
\end{table}
```

### Template 11: Contribution Summary Table (with colored tags and impact indicators)
```latex
\begin{table}[htbp]
\centering
\caption{Summary of key contributions in the field, categorized by innovation type. Impact levels: \ding{72}\ding{72}\ding{72} (High), \ding{72}\ding{72} (Medium), \ding{72} (Low).}
\label{tab:contribution_summary}
\resizebox{\textwidth}{!}{%
\begin{tabular}{lp{7cm}lc}
\toprule
\textbf{Work} & \textbf{Main Contribution} & \textbf{Innovation Type} & \textbf{Impact} \\
\midrule
\rowcolor{categorygreen} \multicolumn{4}{l}{\textbf{Foundational Methods}} \\
\midrule
GPT-4 \cite{ref1} & Introduced multimodal capabilities with vision understanding & \colorbox{blue!15}{\scriptsize Architecture} \colorbox{green!15}{\scriptsize Scale} & \ding{72}\ding{72}\ding{72} \\
LLaMA \cite{ref2} & Open-source foundation model enabling community research & \colorbox{orange!15}{\scriptsize Open-Source} \colorbox{blue!15}{\scriptsize Architecture} & \ding{72}\ding{72}\ding{72} \\
Claude \cite{ref3} & Constitutional AI for improved safety alignment & \colorbox{purple!15}{\scriptsize Safety} \colorbox{red!15}{\scriptsize Training} & \ding{72}\ding{72} \\
\midrule
\rowcolor{categorygreen} \multicolumn{4}{l}{\textbf{Efficiency Improvements}} \\
\midrule
LoRA \cite{ref4} & Parameter-efficient fine-tuning via low-rank adaptation & \colorbox{cyan!15}{\scriptsize Efficiency} \colorbox{red!15}{\scriptsize Training} & \ding{72}\ding{72}\ding{72} \\
QLoRA \cite{ref5} & Quantized LoRA enabling 65B model fine-tuning on single GPU & \colorbox{cyan!15}{\scriptsize Efficiency} \colorbox{yellow!15}{\scriptsize Memory} & \ding{72}\ding{72} \\
Flash Attention \cite{ref6} & IO-aware attention reducing memory from $O(n^2)$ to $O(n)$ & \colorbox{cyan!15}{\scriptsize Efficiency} \colorbox{blue!15}{\scriptsize Architecture} & \ding{72}\ding{72}\ding{72} \\
\midrule
\rowcolor{categorygreen} \multicolumn{4}{l}{\textbf{Application Innovations}} \\
\midrule
ReAct \cite{ref7} & Synergizing reasoning and acting in language models & \colorbox{green!15}{\scriptsize Reasoning} \colorbox{orange!15}{\scriptsize Agent} & \ding{72}\ding{72} \\
Toolformer \cite{ref8} & Self-supervised tool use learning without human annotation & \colorbox{orange!15}{\scriptsize Tool-Use} \colorbox{red!15}{\scriptsize Training} & \ding{72}\ding{72} \\
\bottomrule
\end{tabular}%
}
\end{table}
```

### Template 12: Research Landscape Table (with maturity indicators and trends)

**CRITICAL LAYOUT FIX**: When using `\multirow` with `\rowcolor`, the row colors from subsequent rows will OVERWRITE the multirow cell content, causing text to disappear. To fix this:
- **Option A (Recommended)**: Do NOT use `\multirow` - show the dimension name only in the FIRST row of each group, leave subsequent rows empty in that column
- **Option B**: Repeat the dimension name in each row (simplest, most reliable)

**The template below uses Option A (dimension name in first row only, empty cells for continuation):**

```latex
\begin{table}[htbp]
\centering
\caption{Research landscape analysis across key dimensions. Maturity: \ding{108}~(Mature), \ding{119}~(Developing), \ding{109}~(Emerging). Trend: $\uparrow\uparrow$ (Rapidly Growing), $\uparrow$ (Growing), $\rightarrow$ (Stable), $\downarrow$ (Declining).}
\label{tab:research_landscape}
\resizebox{\textwidth}{!}{%
\begin{tabular}{p{2.5cm}p{3.5cm}p{5.5cm}ccc}
\toprule
\textbf{Dimension} & \textbf{Sub-area} & \textbf{Representative Works} & \textbf{Maturity} & \textbf{Papers} & \textbf{Trend} \\
\midrule
\rowcolor{blue!8} \textbf{Architecture} & Transformer Variants & GPT \cite{ref1}, BERT \cite{ref2}, T5 \cite{ref3} & \ding{108} & 450+ & $\rightarrow$ \\
\rowcolor{blue!8}  & State Space Models & Mamba \cite{ref4}, S4 \cite{ref5}, RWKV \cite{ref6} & \ding{119} & 120+ & $\uparrow\uparrow$ \\
\rowcolor{blue!8}  & Mixture of Experts & Switch \cite{ref7}, GLaM \cite{ref8}, Mixtral \cite{ref9} & \ding{119} & 85+ & $\uparrow$ \\
\rowcolor{blue!8}  & Hybrid Architectures & Jamba \cite{ref10}, Griffin \cite{ref11} & \ding{109} & 25+ & $\uparrow\uparrow$ \\
\midrule
\rowcolor{green!8} \textbf{Training} & Pre-training & BERT \cite{ref2}, GPT-3 \cite{ref12}, Chinchilla \cite{ref13} & \ding{108} & 380+ & $\rightarrow$ \\
\rowcolor{green!8}  & Alignment & RLHF \cite{ref14}, DPO \cite{ref15}, Constitutional AI \cite{ref16} & \ding{119} & 150+ & $\uparrow$ \\
\rowcolor{green!8}  & Efficient Fine-tuning & LoRA \cite{ref17}, Adapter \cite{ref18}, Prefix-tuning \cite{ref19} & \ding{108} & 200+ & $\rightarrow$ \\
\midrule
\rowcolor{orange!8} \textbf{Inference} & Prompting & CoT \cite{ref20}, Few-shot \cite{ref21}, Self-consistency \cite{ref22} & \ding{108} & 280+ & $\rightarrow$ \\
\rowcolor{orange!8}  & Acceleration & Speculative Decoding \cite{ref23}, KV Cache \cite{ref24} & \ding{119} & 95+ & $\uparrow$ \\
\rowcolor{orange!8}  & Tool Augmentation & Toolformer \cite{ref25}, ReAct \cite{ref26}, Function Calling \cite{ref27} & \ding{119} & 110+ & $\uparrow\uparrow$ \\
\midrule
\rowcolor{purple!8} \textbf{Evaluation} & Benchmarks & MMLU \cite{ref28}, HumanEval \cite{ref29}, BigBench \cite{ref30} & \ding{108} & 160+ & $\rightarrow$ \\
\rowcolor{purple!8}  & Safety Testing & TruthfulQA \cite{ref31}, Red-teaming \cite{ref32} & \ding{119} & 75+ & $\uparrow$ \\
\rowcolor{purple!8}  & Agent Evaluation & AgentBench \cite{ref33}, WebArena \cite{ref34} & \ding{109} & 40+ & $\uparrow\uparrow$ \\
\bottomrule
\end{tabular}%
}
\end{table}
```

---

## Important Notes

1. **Data Accuracy**: Only include information that can be verified from the reference content
2. **Consistent Formatting**: Maintain consistent number formatting (use commas for thousands: 1,000)
3. **Citation Format**: Use `\cite{bibkey}` format for all references
4. **Category Balance**: Aim for balanced category sizes (3-8 entries per category)
5. **Column Selection**: Choose 4-8 columns that best represent the comparison dimensions
6. **Caption Quality**: Write informative captions that explain the table's purpose and any symbols used
7. **NO Placeholder Text**: NEVER use placeholder text like "YYYY-MM", "[topic]", "TBD", or similar in the output. Always replace with actual values from the content.
8. **Mathematical Formulas**: When including formulas, use proper LaTeX math mode and ensure consistency in notation
9. **CRITICAL - Special Character Escaping**: In LaTeX tables, the `&` character is used as a column separator. If you need to include a literal ampersand in text (e.g., "Reasoning & Optimization"), you MUST escape it as `\&`. For example:
   - WRONG: `\textbf{Reasoning & Optimization}` (will cause compilation error)
   - CORRECT: `\textbf{Reasoning \& Optimization}` (properly escaped)
   - Other special characters that need escaping: `%` → `\%`, `$` → `\$`, `#` → `\#`, `_` → `\_`, `{` → `\{`, `}` → `\}`
10. **CRITICAL - Work/Paper Names**: In any table with a "Work", "Paper", "Method", or "Model" column:
    - NEVER use just citation numbers (e.g., "[1]", "[4]") as the only content in the cell
    - ALWAYS include a descriptive name before the citation: "MethodName \cite{bibkey}"
    - If no method/system name is available, use: "AuthorName et al. \cite{bibkey}" or a short paper title
    - Example of WRONG: `[4] & Some contribution...`
    - Example of CORRECT: `ReAct \cite{ref4} & Some contribution...` or `Yao et al. \cite{ref4} & Some contribution...`

## ⚠️ CRITICAL CITATION RULES (MUST FOLLOW)

**YOU MUST ONLY USE CITATIONS FROM THE "Available Citations" LIST PROVIDED ABOVE.**

1. **ONLY use bib keys from the "Available Citations" section** - Do NOT invent or guess citation keys
2. **Use the EXACT bib key format** - If the available citation is `arXiv_2307.16789`, use `\cite{arXiv_2307.16789}`, NOT `\cite{xu2023toolbench}` or any other format
3. **Do NOT fabricate data** - Only include information that is explicitly mentioned in the Reference Content
4. **If you cannot find enough citations** - Generate a smaller table with fewer rows rather than inventing citations
5. **Cross-check every citation** - Before outputting, verify that every `\cite{...}` in your table uses a key from the Available Citations list
6. **No hallucinated entries** - If a benchmark/method/tool is not mentioned in the Reference Content with a valid citation, do NOT include it in the table

**VIOLATION OF THESE RULES WILL CAUSE LATEX COMPILATION ERRORS (showing [?] for missing references)**

---

## Generate the Table

Based on the provided content and requirements, generate a professional survey table that:
1. Matches the appropriate template style for the table type
2. Uses clean booktabs formatting (no vertical lines)
3. Includes proper citations
4. Uses consistent symbols for binary features and trends
5. Has an informative caption without placeholder text

Generate the complete LaTeX table code now.