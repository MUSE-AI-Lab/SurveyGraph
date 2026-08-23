# Callout Box / Info Box Generation Prompt

You are a LaTeX expert specializing in creating professional academic callout boxes and info boxes. Your task is to generate visually appealing text boxes that highlight key information in survey papers.

## Survey Topic
{topic}

## Box Type
{box_type}

## Content to Highlight
{content}

## Section Context
{section_content}

---

## Box Type Definitions

### 1. **key_insights** - Key Insights Box
- **Purpose**: Summarize main findings or takeaways from a section
- **Style**: Gray header bar with "Key Insights" title, blue/purple left border, bullet points inside
- **Use when**: After presenting analysis results, comparisons, or important conclusions

### 2. **example** - Example Box
- **Purpose**: Show concrete examples of concepts, prompts, or outputs
- **Style**: Rounded corners, light background, clear structure with labels
- **Use when**: Demonstrating how something works, showing input/output pairs

### 3. **evidence** - Evidence/Quote Box
- **Purpose**: Highlight important quotes or evidence from papers
- **Style**: Left border accent, italicized quote, citation reference
- **Use when**: Citing key findings from referenced papers

### 4. **definition** - Definition Box
- **Purpose**: Define important terms or concepts
- **Style**: Clean box with term in bold, definition below
- **Use when**: Introducing new terminology

### 5. **warning** - Warning/Limitation Box
- **Purpose**: Highlight limitations, caveats, or important notes
- **Style**: Orange/yellow accent, warning icon style
- **Use when**: Discussing limitations or important caveats

---

## LaTeX Implementation

### Required Package (already in preamble)
```latex
\usepackage[most]{tcolorbox}
```

### Color Definitions (already defined)
```latex
\definecolor{keyinsightbg}{RGB}{245, 245, 250}      % Light gray-blue background
\definecolor{keyinsightborder}{RGB}{100, 100, 180}  % Blue-purple border
\definecolor{keyinsightheader}{RGB}{128, 128, 160}  % Gray header
\definecolor{examplebg}{RGB}{252, 252, 252}         % Very light gray
\definecolor{exampleborder}{RGB}{200, 200, 200}     % Light gray border
\definecolor{evidenceborder}{RGB}{150, 100, 180}    % Purple border
\definecolor{definitionbg}{RGB}{240, 248, 255}      % Alice blue
\definecolor{warningbg}{RGB}{255, 250, 240}         % Light orange
\definecolor{warningborder}{RGB}{255, 180, 100}     % Orange border
```

---

## Output Templates

### Key Insights Box
```latex
\begin{tcolorbox}[
    enhanced,
    colback=keyinsightbg,
    colframe=keyinsightborder,
    coltitle=white,
    fonttitle=\bfseries,
    title=Key Insights,
    attach boxed title to top left={yshift=-2mm, xshift=2mm},
    boxed title style={colback=keyinsightheader, sharp corners},
    sharp corners=south,
    rounded corners=north,
    left=3mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt,
    leftrule=3pt
]
\begin{itemize}[leftmargin=*, itemsep=2pt]
    \item First key insight about the topic with \textit{emphasized terms} highlighted.
    \item Second key insight mentioning specific findings like 36.4\% or other statistics.
    \item Third key insight discussing implications or comparisons.
\end{itemize}
\end{tcolorbox}
```

### Example Box
```latex
\begin{tcolorbox}[
    enhanced,
    colback=examplebg,
    colframe=exampleborder,
    coltitle=black,
    fonttitle=\bfseries,
    title=An Example for [Topic],
    attach boxed title to top left={yshift=-2mm, xshift=2mm},
    boxed title style={colback=white, colframe=exampleborder},
    rounded corners,
    left=3mm,
    right=3mm,
    top=4mm,
    bottom=3mm,
    boxrule=0.5pt
]
\textbf{Instruction Prompt:} You are currently in the response generation stage...

\textbf{User Question:} \textit{I would like to know the value of 5 ounces of gold...}

\textbf{Return from Tool Calling:} \textit{The stock price of AMZN is 130 USD...}

\textbf{Output:} \textcolor{red}{Total value in CNY: Total value = Value of gold in CNY + Value of stocks in CNY...}
\end{tcolorbox}
```

### Evidence/Quote Box
```latex
\begin{tcolorbox}[
    enhanced,
    colback=white,
    colframe=white,
    leftrule=3pt,
    left=4mm,
    right=3mm,
    top=2mm,
    bottom=2mm,
    borderline west={3pt}{0pt}{evidenceborder}
]
\textbf{Evidence:} ``We find that zero-shot CoT reasoning in sensitive domains significantly increases a model's likelihood to produce harmful or undesirable output [...]''\cite{reference92}

\textbf{Generated Keyphrases:} \textcolor{purple}{``zero-shot CoT reasoning limitations''}, \textcolor{purple}{``increased harmful output''}, \textcolor{purple}{``sensitive domains challenges''}, \textcolor{purple}{``prompt format issues''}
\end{tcolorbox}
```

### Definition Box
```latex
\begin{tcolorbox}[
    enhanced,
    colback=definitionbg,
    colframe=keyinsightborder,
    rounded corners,
    left=3mm,
    right=3mm,
    top=3mm,
    bottom=3mm,
    boxrule=0.5pt
]
\textbf{Definition (Term Name):} A clear and concise definition of the term, explaining its meaning in the context of the survey topic.
\end{tcolorbox}
```

### Warning/Limitation Box
```latex
\begin{tcolorbox}[
    enhanced,
    colback=warningbg,
    colframe=warningborder,
    coltitle=black,
    fonttitle=\bfseries,
    title={\faExclamationTriangle\ Important Note},
    rounded corners,
    left=3mm,
    right=3mm,
    top=3mm,
    bottom=3mm,
    boxrule=0.5pt
]
This approach has several limitations that should be considered...
\end{tcolorbox}
```

---

## Content Guidelines

### For Key Insights (CRITICAL - Must be Evidence-Based):
**Every insight MUST be grounded in actual research findings and include citations.**

✅ **Good Example:**
- "Transformer-based models achieve 15-20% accuracy improvement over CNN-based approaches on document understanding tasks [Author2023]"
- "Multi-modal pre-training significantly improves cross-modal alignment, with LayoutLM achieving 94.1% F1 on FUNSD [Xu2020]"

❌ **Bad Example (Too Vague):**
- "LLMs are very powerful for document understanding"
- "Multi-modal models perform better than single-modal models"

**Requirements:**
- Extract 2-4 main takeaways from the section
- **MUST include specific numbers, statistics, or quantitative findings**
- **MUST include citation keys in [brackets] when referencing papers**
- Use bullet points for clarity
- Italicize key terms or method names
- Keep each point concise but informative (1-2 sentences)
- Ensure insights are **synthesized observations**, not just restated facts

### For Examples:
- Structure with clear labels (Input, Output, etc.)
- Use different text styles to distinguish parts
- Include realistic, concrete examples
- Show the relationship between input and output

### For Evidence:
- Quote directly from papers with proper citation
- Highlight key phrases in color
- Keep quotes focused and relevant
- Include page/section reference if available

### For Numbered Lists and Concept Lists:
- Each item should be substantive and informative
- Include citations where the concept is defined or discussed
- Provide clear, professional descriptions

---

## Output Format

Generate ONLY the LaTeX code wrapped in ```latex blocks.

**CRITICAL REQUIREMENTS:**
- **DO NOT** include `\documentclass`, `\usepackage`, `\begin{document}`, `\end{document}`, or any document preamble
- **DO NOT** include `\definecolor` definitions (these are already defined in the main document)
- **ONLY** output the `\begin{tcolorbox}...\end{tcolorbox}` environment
- The box will be included directly in the document

**Content Requirements:**
- Fill in actual content based on the section context provided
- Use proper LaTeX escaping for special characters
- **MUST include proper citations using \cite{} command**
- Make the content informative, specific, and evidence-based
- Avoid vague or generic statements - be precise and quantitative

**Citation Format:**
- Use `\cite{citation_key}` for citations
- Example: "LLMs achieve 95\% accuracy~\cite{Author2024}"