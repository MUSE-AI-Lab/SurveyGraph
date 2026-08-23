# Professional Summary Table Generation Prompt

You are a LaTeX expert specializing in creating professional academic summary tables for survey/review papers. Generate a comprehensive, well-organized summary table based on the following information.

## Table Description
{description}

## Style Preference
{style}

## Data Requirements
{data_requirements}

## Reference Content
{section_content}

---

## Professional Summary Table Guidelines

### Purpose of Summary Tables in Surveys

Summary tables serve to:
1. **Consolidate Information**: Present key findings from multiple works in one place
2. **Enable Quick Reference**: Allow readers to quickly locate relevant methods/papers
3. **Show Trends**: Reveal patterns, evolution, and gaps in the field
4. **Support Arguments**: Provide evidence for claims made in the survey text

### Style Guidelines

#### categorized_summary (Recommended for comprehensive surveys)
- **Use when**: Organizing diverse methods/papers by type or approach
- **Structure**: Group entries by category with clear visual separation
- **Features**: 
  - Category header rows with background color
  - Consistent columns across all categories
  - 5-15 entries per category for balance
- **Best for**: Method surveys, tool comparisons, dataset overviews

#### chronological_summary
- **Use when**: Showing evolution or historical development
- **Structure**: Entries ordered by publication year
- **Features**:
  - Year column prominently placed (first or second column)
  - Clear progression from early to recent work
  - Milestone markers for significant contributions
- **Best for**: Historical surveys, technology evolution, trend analysis

#### hierarchical_summary
- **Use when**: Presenting taxonomies or nested classifications
- **Structure**: Parent-child relationships with visual indentation
- **Features**:
  - Indentation using `\quad` or nested structure
  - Clear hierarchy levels (2-3 levels max)
  - Representative examples at each level
- **Best for**: Taxonomy presentations, classification schemes

#### statistical_summary
- **Use when**: Presenting quantitative results across studies
- **Structure**: Methods as rows, metrics as columns
- **Features**:
  - Numerical data with consistent formatting
  - Best results highlighted (bold or color)
  - Dataset/benchmark information included
- **Best for**: Performance comparisons, experimental results

---

## Symbol and Formatting System

### Category Headers
```latex
\definecolor{categorygreen}{RGB}{198, 224, 180}  % Light green
\definecolor{categoryblue}{RGB}{189, 215, 238}   % Light blue  
\definecolor{categoryyellow}{RGB}{255, 242, 204} % Light yellow
\definecolor{categorygray}{RGB}{217, 217, 217}   % Light gray

% Usage: \rowcolor{categorygreen} for category header rows
```

### Feature Indicators
```latex
\newcommand{\cmark}{\textcolor{green!70!black}{\checkmark}}  % ✓ Supported
\newcommand{\xmark}{\textcolor{red}{\ding{55}}}              % ✗ Not supported
\newcommand{\pmark}{\textcolor{orange}{$\circ$}}             % ○ Partial
\newcommand{\nmark}{--}                                       % -- Not applicable
```

### Highlighting Best Results
```latex
\newcommand{\best}[1]{\textbf{#1}}           % Bold for best
\newcommand{\second}[1]{\underline{#1}}      % Underline for second best
```

### Number Formatting
- Use commas for thousands: 1,000 / 10,000 / 1,000,000
- Use consistent decimal places: 85.2% / 92.5% / 78.3%
- Use K/M/B for large numbers: 175B parameters, 1.5M samples

---

## LaTeX Requirements

### Required Packages
```latex
\usepackage{booktabs}      % Professional rules
\usepackage{multirow}      % Multi-row cells
\usepackage{xcolor}        % Colors
\usepackage{colortbl}      % Colored cells
\usepackage{pifont}        % Ding symbols
\usepackage{amssymb}       % Math symbols
\usepackage{array}         % Enhanced columns
\usepackage{makecell}      % Cell formatting
\usepackage{longtable}     % For very long tables
```

### Column Type Definitions
```latex
% For text columns with specific width
p{3cm}  % Left-aligned, 3cm width
m{3cm}  % Vertically centered, 3cm width

% For numeric columns
r       % Right-aligned
c       % Centered
S       % siunitx aligned numbers (if using siunitx)
```

### Table Sizing
```latex
% For wide tables
\resizebox{\textwidth}{!}{%
  \begin{tabular}{...}
  ...
  \end{tabular}%
}

% For very long tables (spans multiple pages)
\begin{longtable}{...}
...
\end{longtable}
```

---

## Output Format

Generate ONLY the LaTeX table code wrapped in ```latex blocks.

**CRITICAL REQUIREMENTS:**
- **DO NOT** include `\documentclass`, `\usepackage`, `\begin{document}`, `\end{document}`, or any document preamble
- **DO NOT** include `\definecolor` or `\newcommand` definitions (these are already defined in the main document)
- **ONLY** output the `\begin{table}...\end{table}` or `\begin{longtable}...\end{longtable}` environment
- The table will be included via `\input{}` in a larger document, so it must be a standalone table fragment

### Template: Categorized Summary (Survey Style)
```latex
\begin{table}[htbp]
\centering
\caption{Summary of representative methods for [topic]. We categorize approaches by [categorization criterion] and highlight key characteristics including [key dimensions].}
\label{tab:summary}
\resizebox{\textwidth}{!}{%
\begin{tabular}{lp{3cm}p{4cm}ccc}
\toprule
\textbf{Method} & \textbf{Key Technique} & \textbf{Main Contribution} & \textbf{Dataset} & \textbf{Performance} & \textbf{Year} \\
\midrule
\rowcolor{categorygreen} \multicolumn{6}{c}{\textbf{Category A: [Category Name]}} \\
\midrule
Method A1 \cite{refA1} & Technique description & Contribution summary & Dataset1 & 85.2\% & 2022 \\
Method A2 \cite{refA2} & Technique description & Contribution summary & Dataset2 & \best{89.5\%} & 2023 \\
Method A3 \cite{refA3} & Technique description & Contribution summary & Dataset1 & 87.3\% & 2023 \\
\midrule
\rowcolor{categorygreen} \multicolumn{6}{c}{\textbf{Category B: [Category Name]}} \\
\midrule
Method B1 \cite{refB1} & Technique description & Contribution summary & Dataset3 & 82.1\% & 2021 \\
Method B2 \cite{refB2} & Technique description & Contribution summary & Dataset2 & 84.7\% & 2022 \\
\midrule
\rowcolor{categorygreen} \multicolumn{6}{c}{\textbf{Category C: [Category Name]}} \\
\midrule
Method C1 \cite{refC1} & Technique description & Contribution summary & Dataset1 & 91.2\% & 2023 \\
Method C2 \cite{refC2} & Technique description & Contribution summary & Dataset4 & 88.9\% & 2024 \\
\bottomrule
\end{tabular}%
}
\end{table}
```

### Template: Chronological Summary
```latex
\begin{table}[htbp]
\centering
\caption{Chronological development of [topic] methods. We trace the evolution from early approaches to recent state-of-the-art methods.}
\label{tab:chronological_summary}
\resizebox{\textwidth}{!}{%
\begin{tabular}{clp{4cm}p{5cm}c}
\toprule
\textbf{Year} & \textbf{Method} & \textbf{Key Innovation} & \textbf{Impact \& Significance} & \textbf{Citations} \\
\midrule
\rowcolor{categoryyellow} \multicolumn{5}{c}{\textit{Early Foundations (2017-2019)}} \\
\midrule
2017 & Transformer \cite{vaswani2017attention} & Self-attention mechanism & Foundation for modern NLP & 50,000+ \\
2018 & BERT \cite{devlin2019bert} & Bidirectional pre-training & Revolutionized transfer learning & 45,000+ \\
2019 & GPT-2 \cite{radford2019gpt2} & Large-scale language model & Demonstrated scaling benefits & 8,000+ \\
\midrule
\rowcolor{categoryyellow} \multicolumn{5}{c}{\textit{Scaling Era (2020-2022)}} \\
\midrule
2020 & GPT-3 \cite{brown2020gpt3} & 175B parameters & Few-shot learning capability & 15,000+ \\
2021 & Codex \cite{chen2021codex} & Code generation & Programming assistance & 3,000+ \\
2022 & InstructGPT \cite{ouyang2022instructgpt} & RLHF alignment & Improved instruction following & 5,000+ \\
\midrule
\rowcolor{categoryyellow} \multicolumn{5}{c}{\textit{Recent Advances (2023-Present)}} \\
\midrule
2023 & GPT-4 \cite{openai2023gpt4} & Multimodal capability & State-of-the-art performance & 10,000+ \\
2023 & LLaMA \cite{touvron2023llama} & Open-source LLM & Democratized LLM research & 8,000+ \\
2024 & Claude 3 \cite{anthropic2024claude3} & Constitutional AI & Enhanced safety & -- \\
\bottomrule
\end{tabular}%
}
\end{table}
```

### Template: Hierarchical Summary (Taxonomy)
```latex
\begin{table}[htbp]
\centering
\caption{Hierarchical taxonomy of [topic] approaches. We organize methods into [N] main categories with subcategories.}
\label{tab:taxonomy}
\begin{tabular}{lp{5cm}p{4cm}}
\toprule
\textbf{Category / Subcategory} & \textbf{Description} & \textbf{Representative Works} \\
\midrule
\rowcolor{categoryblue} \multicolumn{3}{l}{\textbf{1. Pre-training Methods}} \\
\midrule
\quad 1.1 Masked Language Modeling & Predict randomly masked tokens in input & BERT, RoBERTa, ALBERT \\
\quad 1.2 Causal Language Modeling & Predict next token autoregressively & GPT series, LLaMA \\
\quad 1.3 Sequence-to-Sequence & Encoder-decoder architecture & T5, BART, mT5 \\
\midrule
\rowcolor{categoryblue} \multicolumn{3}{l}{\textbf{2. Fine-tuning Methods}} \\
\midrule
\quad 2.1 Full Fine-tuning & Update all model parameters & Standard approach \\
\quad 2.2 Parameter-Efficient & Update subset of parameters & LoRA, Adapter, Prefix \\
\quad 2.3 Prompt-based & Learn soft prompts & P-tuning, Prompt Tuning \\
\midrule
\rowcolor{categoryblue} \multicolumn{3}{l}{\textbf{3. Alignment Methods}} \\
\midrule
\quad 3.1 Supervised Fine-tuning & Train on instruction-response pairs & InstructGPT, Alpaca \\
\quad 3.2 RLHF & Reinforcement learning from human feedback & ChatGPT, Claude \\
\quad 3.3 DPO & Direct preference optimization & Zephyr, Mistral \\
\bottomrule
\end{tabular}
\end{table}
```

### Template: Statistical Summary (Performance Comparison)
```latex
\begin{table}[htbp]
\centering
\caption{Performance comparison on [benchmark name]. Best results are in \textbf{bold}, second best are \underline{underlined}. All metrics are reported as percentages.}
\label{tab:performance}
\resizebox{\textwidth}{!}{%
\begin{tabular}{lccccccc}
\toprule
\textbf{Method} & \textbf{Params} & \textbf{Task 1} & \textbf{Task 2} & \textbf{Task 3} & \textbf{Task 4} & \textbf{Avg.} & \textbf{Year} \\
\midrule
\rowcolor{categorygray} \multicolumn{8}{c}{\textit{Baseline Methods}} \\
\midrule
Baseline A \cite{refA} & 110M & 72.5 & 68.3 & 75.2 & 70.1 & 71.5 & 2019 \\
Baseline B \cite{refB} & 340M & 78.2 & 74.5 & 79.8 & 76.3 & 77.2 & 2020 \\
\midrule
\rowcolor{categorygray} \multicolumn{8}{c}{\textit{State-of-the-Art Methods}} \\
\midrule
Method C \cite{refC} & 1.5B & 85.3 & 82.1 & 86.7 & 83.5 & 84.4 & 2022 \\
Method D \cite{refD} & 7B & \underline{89.2} & \underline{87.5} & 90.1 & \underline{88.3} & \underline{88.8} & 2023 \\
Method E \cite{refE} & 13B & \best{92.5} & \best{90.2} & \best{93.4} & \best{91.7} & \best{91.9} & 2024 \\
\bottomrule
\end{tabular}%
}
\end{table}
```

---

## Quality Checklist

Before generating, ensure your table:
- [ ] Has a clear, informative caption explaining the table's purpose
- [ ] Uses consistent formatting and alignment throughout
- [ ] Includes proper citations for all referenced works
- [ ] Groups entries logically (by category, time, or hierarchy)
- [ ] Uses appropriate symbols with explanations in the caption
- [ ] Has balanced content (not too sparse or too dense)
- [ ] Contains accurate information from the reference content
- [ ] Highlights key findings or best results appropriately

---

## Generate the Summary Table

Based on the provided content and style preference, generate a professional summary table that:
1. Follows the appropriate template for the chosen style
2. Organizes entries systematically with clear categories
3. Uses consistent formatting and symbols
4. Includes proper citations for all works
5. Has an informative caption explaining the table

Generate the complete LaTeX table code now.