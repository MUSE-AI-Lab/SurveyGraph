# Professional Comparison Table Generation Prompt

You are a LaTeX expert specializing in creating professional academic comparison tables for survey/review papers. Generate a systematic, well-organized comparison table based on the following information.

## Table Description
{description}

## Style Preference
{style}

## Data Requirements
{data_requirements}

## Reference Content
{section_content}

---

## Professional Comparison Table Guidelines

### Core Principles for Survey-Quality Tables

1. **Systematic Organization**: Group related items together with clear category headers
2. **Multi-dimensional Analysis**: Compare across multiple meaningful dimensions
3. **Visual Clarity**: Use consistent symbols and formatting for easy scanning
4. **Academic Rigor**: Include proper citations for all referenced works
5. **Information Density**: Balance comprehensiveness with readability

### Style Guidelines

#### horizontal_comparison
- **Use when**: Comparing 3-8 methods/models side by side
- **Structure**: Methods as columns, features/attributes as rows
- **Best for**: Highlighting differences across a small set of approaches
- **Example columns**: Method A, Method B, Method C...

#### vertical_comparison (Recommended for surveys)
- **Use when**: Comparing many methods (8+ items)
- **Structure**: Methods as rows, features/attributes as columns
- **Best for**: Comprehensive surveys with many entries
- **Example columns**: Method, Category, Key Feature, Metric 1, Metric 2, Year

#### matrix_comparison
- **Use when**: Showing relationships or scores across two dimensions
- **Structure**: Full matrix with scores, checkmarks, or ratings
- **Best for**: Feature support matrices, compatibility tables
- **Symbols**: Use ✓/✗ or numerical scores (1-5, percentages)

#### feature_checklist
- **Use when**: Comparing binary feature presence/absence
- **Structure**: Items as rows, features as columns with ✓/✗
- **Best for**: Quick feature comparison, capability matrices
- **Keep it**: Clean, scannable, with clear legend

---

## Symbol System

### Binary Features
```latex
\newcommand{\cmark}{\textcolor{green!70!black}{\checkmark}}  % Supported
\newcommand{\xmark}{\textcolor{red}{\ding{55}}}              % Not supported
\newcommand{\pmark}{\textcolor{orange}{$\circ$}}             % Partial support
```

### Stage/Phase Indicators
```latex
% Use circled numbers for stages
\textcircled{1}, \textcircled{2}, \textcircled{3}, \textcircled{4}
% Or use: ①, ②, ③, ④ directly if Unicode is supported
```

### Rating Scales
```latex
% Stars or filled circles for ratings
\newcommand{\fullstar}{\ding{72}}    % ★
\newcommand{\halfstar}{\ding{73}}    % ☆ (half)
\newcommand{\emptystar}{\ding{73}}   % ☆
```

---

## LaTeX Requirements

### Required Packages
```latex
\usepackage{booktabs}      % \toprule, \midrule, \bottomrule
\usepackage{multirow}      % Multi-row cells
\usepackage{xcolor}        % Colors
\usepackage{colortbl}      % \rowcolor, \cellcolor
\usepackage{pifont}        % \ding symbols
\usepackage{amssymb}       % \checkmark
\usepackage{array}         % Enhanced columns
\usepackage{makecell}      % \makecell for line breaks
```

### Category Header Colors
```latex
\definecolor{categorygreen}{RGB}{198, 224, 180}  % Light green
\definecolor{categoryblue}{RGB}{189, 215, 238}   % Light blue
\definecolor{categorygray}{RGB}{217, 217, 217}   % Light gray
```

### Table Structure Rules
1. Use `\toprule` at the top, `\bottomrule` at the bottom
2. Use `\midrule` to separate header from body and between categories
3. Use `\rowcolor{categorygreen}` for category header rows
4. Use `\resizebox{\textwidth}{!}{...}` for wide tables
5. Right-align numeric columns, left-align text columns

---

## Output Format

Generate ONLY the LaTeX table code wrapped in ```latex blocks.

**CRITICAL REQUIREMENTS:**
- **DO NOT** include `\documentclass`, `\usepackage`, `\begin{document}`, `\end{document}`, or any document preamble
- **DO NOT** include `\definecolor` or `\newcommand` definitions (these are already defined in the main document)
- **ONLY** output the `\begin{table}...\end{table}` environment
- The table will be included via `\input{}` in a larger document, so it must be a standalone table fragment

### Template for Vertical Comparison (Survey Style):
```latex
\begin{table}[htbp]
\centering
\caption{Comparison of [topic] methods. We analyze key characteristics including [dimension 1], [dimension 2], and [dimension 3]. \cmark indicates support, \xmark indicates no support.}
\label{tab:comparison}
\resizebox{\textwidth}{!}{%
\begin{tabular}{lp{2.5cm}ccccc}
\toprule
\textbf{Method} & \textbf{Core Approach} & \textbf{Feature A} & \textbf{Feature B} & \textbf{Feature C} & \textbf{Performance} & \textbf{Year} \\
\midrule
\rowcolor{categorygreen} \multicolumn{7}{c}{\textbf{Category 1: [Category Name]}} \\
\midrule
Method A \cite{refA} & Description & \cmark & \xmark & \cmark & 85.2\% & 2022 \\
Method B \cite{refB} & Description & \cmark & \cmark & \xmark & 87.5\% & 2023 \\
Method C \cite{refC} & Description & \xmark & \cmark & \cmark & 82.1\% & 2023 \\
\midrule
\rowcolor{categorygreen} \multicolumn{7}{c}{\textbf{Category 2: [Category Name]}} \\
\midrule
Method D \cite{refD} & Description & \cmark & \cmark & \cmark & 89.3\% & 2023 \\
Method E \cite{refE} & Description & \cmark & \xmark & \cmark & 86.7\% & 2024 \\
\bottomrule
\end{tabular}%
}
\end{table}
```

### Template for Horizontal Comparison:
```latex
\begin{table}[htbp]
\centering
\caption{Detailed comparison of representative methods for [topic].}
\label{tab:horizontal_comparison}
\begin{tabular}{lcccc}
\toprule
\textbf{Aspect} & \textbf{Method A} & \textbf{Method B} & \textbf{Method C} & \textbf{Method D} \\
\midrule
\textbf{Architecture} & Transformer & CNN & RNN & Hybrid \\
\textbf{Parameters} & 175B & 1.5B & 340M & 7B \\
\textbf{Training Data} & 570GB & 40GB & 16GB & 100GB \\
\textbf{Pre-training} & \cmark & \cmark & \xmark & \cmark \\
\textbf{Fine-tuning} & \cmark & \cmark & \cmark & \cmark \\
\textbf{Zero-shot} & \cmark & \xmark & \xmark & \cmark \\
\textbf{Accuracy} & 92.5\% & 88.3\% & 85.1\% & 90.2\% \\
\textbf{Inference Speed} & Slow & Fast & Medium & Medium \\
\bottomrule
\end{tabular}
\end{table}
```

### Template for Feature Matrix:
```latex
\begin{table}[htbp]
\centering
\caption{Feature support matrix for [topic] systems. \cmark = fully supported, \pmark = partially supported, \xmark = not supported.}
\label{tab:feature_matrix}
\begin{tabular}{lccccccc}
\toprule
\textbf{System} & \textbf{F1} & \textbf{F2} & \textbf{F3} & \textbf{F4} & \textbf{F5} & \textbf{F6} & \textbf{F7} \\
\midrule
System A \cite{refA} & \cmark & \cmark & \pmark & \xmark & \cmark & \cmark & \xmark \\
System B \cite{refB} & \cmark & \xmark & \cmark & \cmark & \pmark & \xmark & \cmark \\
System C \cite{refC} & \pmark & \cmark & \cmark & \cmark & \cmark & \cmark & \cmark \\
System D \cite{refD} & \cmark & \cmark & \cmark & \pmark & \cmark & \pmark & \cmark \\
\bottomrule
\end{tabular}
\end{table}
```

---

## Quality Checklist

Before generating, ensure your table:
- [ ] Has a clear, informative caption explaining the comparison
- [ ] Uses consistent formatting throughout
- [ ] Includes proper citations for all methods
- [ ] Groups related items into categories (if applicable)
- [ ] Uses appropriate symbols with a legend in the caption
- [ ] Has balanced column widths for readability
- [ ] Contains accurate, verifiable information from the reference content

---

## Generate the Comparison Table

Based on the provided content and style preference, generate a professional comparison table that:
1. Follows the appropriate template for the chosen style
2. Organizes entries systematically
3. Uses consistent symbols and formatting
4. Includes proper citations
5. Has an informative caption

Generate the complete LaTeX table code now.