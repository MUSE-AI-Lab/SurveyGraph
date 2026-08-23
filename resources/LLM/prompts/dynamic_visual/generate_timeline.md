# Timeline Generation Prompt

You are a LaTeX/TikZ expert specializing in academic diagrams. Generate a professional timeline based on the following information.

## Timeline Description
{description}

## Style Preference
{style}

## Data Requirements
{data_requirements}

## Reference Content
{section_content}

## Style Guidelines

### horizontal_timeline
- Time flows left to right
- Events above/below the line
- Good for showing progression

### vertical_timeline
- Time flows top to bottom
- Events on left/right of the line
- Good for detailed descriptions
- **IMPORTANT**: Adjust vertical spacing based on content length to prevent overlap
- Use minimum 3cm spacing between events with multi-line descriptions
- Avoid redundant time periods (e.g., don't use both "2023", "2023-2024", and "2024" consecutively)

### milestone_timeline
- Key events highlighted with larger markers
- Secondary events with smaller markers
- Good for emphasizing important moments

---

## **CRITICAL: Anti-Overlap Rules (MUST FOLLOW)**

### Problem Analysis
When timelines have many events or long descriptions, fixed spacing causes overlap. You MUST dynamically calculate dimensions.

### Dynamic Spacing Calculation Rules

#### 1. Horizontal Timeline - Event Spacing
Calculate based on **number of events** and **text length**:
- 3-5 events: `x spacing = 3cm` between events
- 6-8 events: `x spacing = 2.5cm` between events
- 9+ events: `x spacing = 2cm` AND use smaller font (`\footnotesize`)

#### 2. Horizontal Timeline - Event Box Width
Calculate based on **longest event text**:
- Short text (< 10 chars): `minimum width=1.5cm`
- Medium text (10-20 chars): `minimum width=2cm`
- Long text (> 20 chars): `minimum width=2.5cm` OR use `text width=2cm` with line break

#### 3. Vertical Timeline - Event Spacing
Calculate based on **content lines**:
- Single-line event: `2.5cm` spacing
- 2-line event (with bullets): `3.0cm` spacing
- 3-line event: `3.5cm` spacing
- 4+ line event: `4.0cm` or more spacing

#### 4. Vertical Timeline - Event Box Width
Adjust based on **description length**:
- Short descriptions: `text width=6cm`
- Medium descriptions: `text width=8cm`
- Long descriptions: `text width=10cm`

### Content Abbreviation Strategy

When events are too many or text is too long:

1. **Text Abbreviation**:
   - Use acronyms: "Large Language Model" → "LLM"
   - Use short forms: "Development of X" → "X Development"
   - Combine related events: "2022-2023: Multiple advances"

2. **Event Consolidation**:
   - Group similar events by period: "2020-2022: Foundation Era"
   - Use representative examples: "Key models: GPT-3, BERT, T5"
   - Limit to 6-8 events for readability

3. **Layout Adjustment**:
   - If > 8 events: Consider splitting into multiple timelines
   - If text is long: Use bullet points instead of paragraphs
   - Alternate event positions (above/below for horizontal)

---

## LaTeX Requirements

1. Use `tikz` package with appropriate libraries
2. Include meaningful `\caption` and `\label`
3. Use consistent styling for markers
4. Include year/date labels clearly
5. Keep event descriptions concise
6. **CRITICAL**: Calculate spacing dynamically based on content length
7. **CRITICAL**: Avoid overlapping nodes - ensure sufficient spacing between events
8. **CRITICAL**: Do not create redundant time periods (e.g., avoid "2023", "2023-2024", "2024" in sequence)
9. **CRITICAL**: Use `\resizebox` for wide horizontal timelines

---

## Output Format

Generate ONLY the LaTeX code wrapped in ```latex blocks:

### Horizontal Timeline (basic - few events):
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    % DYNAMIC: Adjust minimum width based on longest text
    event/.style={rectangle, draw, rounded corners, fill=blue!20, minimum width=2cm, minimum height=0.8cm, align=center, font=\small},
    year/.style={font=\footnotesize\bfseries},
]
% Timeline axis - DYNAMIC: length = (num_events - 1) * spacing + 2
\draw[thick, ->, >=stealth] (0,0) -- (14,0);

% Years and events - DYNAMIC: adjust x positions based on event count
\foreach \x/\year/\event in {
    1/2017/Transformers,
    4/2018/BERT,
    7/2020/GPT-3,
    10/2022/ChatGPT,
    13/2023/GPT-4
} {
    \draw (\x,0.1) -- (\x,-0.1);
    \node[year, below] at (\x,-0.2) {\year};
    \node[event, above] at (\x,0.5) {\event};
}

\end{tikzpicture}
\caption{Timeline of major developments in large language models}
\label{fig:timeline}
\end{figure}
```

### Horizontal Timeline (many events - with resizebox):
```latex
\begin{figure}[htbp]
\centering
\resizebox{\textwidth}{!}{%  % Auto-scale to fit page width
\begin{tikzpicture}[
    % DYNAMIC: Smaller boxes for many events
    event/.style={rectangle, draw, rounded corners, fill=blue!20,
        text width=1.8cm, minimum height=0.7cm, align=center, font=\footnotesize},
    year/.style={font=\scriptsize\bfseries},
]
% Timeline axis
\draw[thick, ->, >=stealth] (0,0) -- (20,0);

% Events with tighter spacing
\foreach \x/\year/\event in {
    1/2017/Transformer,
    3.5/2018/BERT,
    6/2019/GPT-2,
    8.5/2020/GPT-3,
    11/2021/Codex,
    13.5/2022/ChatGPT,
    16/2023/GPT-4,
    18.5/2024/Claude 3
} {
    \draw (\x,0.1) -- (\x,-0.1);
    \node[year, below] at (\x,-0.2) {\year};
    % Alternate above/below to prevent overlap
    \pgfmathparse{mod(\x,2)==0 ? 1 : -1}
    \ifnum\pgfmathresult>0
        \node[event, above] at (\x,0.5) {\event};
    \else
        \node[event, below] at (\x,-0.7) {\event};
    \fi
}

\end{tikzpicture}
}%
\caption{Comprehensive timeline of LLM development}
\label{fig:timeline}
\end{figure}
```

### Horizontal Timeline (alternating positions - prevent overlap):
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    event_above/.style={rectangle, draw, rounded corners, fill=blue!20,
        minimum width=2cm, minimum height=0.8cm, align=center, font=\small},
    event_below/.style={rectangle, draw, rounded corners, fill=green!20,
        minimum width=2cm, minimum height=0.8cm, align=center, font=\small},
    year/.style={font=\footnotesize\bfseries},
]
\draw[thick, ->, >=stealth] (0,0) -- (14,0);

% Alternate events above and below the line
\node[year, below] at (1,-0.2) {2017};
\node[event_above, above] at (1,0.5) {Transformer};
\draw (1,0.1) -- (1,-0.1);

\node[year, above] at (4,0.2) {2018};
\node[event_below, below] at (4,-0.5) {BERT};
\draw (4,0.1) -- (4,-0.1);

\node[year, below] at (7,-0.2) {2020};
\node[event_above, above] at (7,0.5) {GPT-3};
\draw (7,0.1) -- (7,-0.1);

\node[year, above] at (10,0.2) {2022};
\node[event_below, below] at (10,-0.5) {ChatGPT};
\draw (10,0.1) -- (10,-0.1);

\node[year, below] at (13,-0.2) {2023};
\node[event_above, above] at (13,0.5) {GPT-4};
\draw (13,0.1) -- (13,-0.1);

\end{tikzpicture}
\caption{Timeline with alternating event positions}
\label{fig:timeline}
\end{figure}
```

### Vertical Timeline (with dynamic spacing):
```latex
\begin{figure}[H]
\centering
\begin{tikzpicture}[
    year/.style={font=\small\bfseries, text=blue!70!black, text width=1.8cm, align=right},
    % DYNAMIC: Adjust text width based on content length
    event/.style={rectangle, rounded corners, draw=gray!50, fill=gray!10, text width=8cm, font=\small, align=left, inner sep=6pt}
]
% Timeline axis - DYNAMIC: extend based on number of events
% Rule: axis length = (number of events - 1) * avg_spacing + 1
\draw[thick, gray!60] (0,0.5) -- (0,-12.5);

% Events - DYNAMIC spacing based on content lines
% Single-line: 2.5cm, 2-line: 3.0cm, 3-line: 3.5cm, 4+: 4.0cm

% Event 1 - single line: next event at -2.5cm
\node[year] at (-1.5, 0.0) {2020-2022};
\node[event, right=0.5cm] at (0, 0.0) {Early frameworks established foundational approaches};
\fill[blue!60] (0, 0.0) circle (4pt);

% Event 2 - 2 lines: spacing 3.0cm from previous
\node[year] at (-1.5, -3.0) {2023};
\node[event, right=0.5cm] at (0, -3.0) {\textbullet\ First major development \\ \textbullet\ Second key advancement};
\fill[blue!60] (0, -3.0) circle (4pt);

% Event 3 - 3 lines: spacing 3.5cm from previous
\node[year] at (-1.5, -6.5) {2024};
\node[event, right=0.5cm] at (0, -6.5) {\textbullet\ Multiple developments \\ \textbullet\ Key innovations \\ \textbullet\ Important breakthroughs};
\fill[blue!60] (0, -6.5) circle (4pt);

% Event 4 - single line: spacing 3.5cm (after 3-line event)
\node[year] at (-1.5, -10.0) {2025};
\node[event, right=0.5cm] at (0, -10.0) {Contemporary developments and future directions};
\fill[blue!60] (0, -10.0) circle (4pt);

\end{tikzpicture}
\caption{Evolution of the research field}
\label{fig:timeline}
\end{figure}
```

### Vertical Timeline (compact - many events):
```latex
\begin{figure}[H]
\centering
\begin{tikzpicture}[
    year/.style={font=\footnotesize\bfseries, text=blue!70!black, text width=1.5cm, align=right},
    % DYNAMIC: Narrower text width for compact layout
    event/.style={rectangle, rounded corners, draw=gray!50, fill=gray!10, text width=6cm, font=\footnotesize, align=left, inner sep=4pt}
]
% Compact spacing for many events
\draw[thick, gray!60] (0,0.5) -- (0,-14);

% Use 2cm spacing for single-line events
\node[year] at (-1.2, 0.0) {2017};
\node[event, right=0.3cm] at (0, 0.0) {Transformer architecture introduced};
\fill[blue!60] (0, 0.0) circle (3pt);

\node[year] at (-1.2, -2.0) {2018};
\node[event, right=0.3cm] at (0, -2.0) {BERT: Bidirectional pre-training};
\fill[blue!60] (0, -2.0) circle (3pt);

\node[year] at (-1.2, -4.0) {2019};
\node[event, right=0.3cm] at (0, -4.0) {GPT-2: Scaling language models};
\fill[blue!60] (0, -4.0) circle (3pt);

\node[year] at (-1.2, -6.0) {2020};
\node[event, right=0.3cm] at (0, -6.0) {GPT-3: Few-shot learning};
\fill[blue!60] (0, -6.0) circle (3pt);

\node[year] at (-1.2, -8.0) {2022};
\node[event, right=0.3cm] at (0, -8.0) {ChatGPT: Conversational AI};
\fill[blue!60] (0, -8.0) circle (3pt);

\node[year] at (-1.2, -10.0) {2023};
\node[event, right=0.3cm] at (0, -10.0) {GPT-4: Multimodal capabilities};
\fill[blue!60] (0, -10.0) circle (3pt);

\node[year] at (-1.2, -12.0) {2024};
\node[event, right=0.3cm] at (0, -12.0) {Open-source LLMs proliferate};
\fill[blue!60] (0, -12.0) circle (3pt);

\end{tikzpicture}
\caption{Comprehensive timeline of LLM evolution}
\label{fig:timeline}
\end{figure}
```

**Spacing Guidelines for Vertical Timeline:**
- Single-line event: 2.0-2.5cm spacing
- 2-line event: 3.0cm spacing
- 3+ line event: 3.5cm or more spacing
- For many events (7+): Use compact style with 2cm spacing and smaller font
- Always extend the timeline axis to accommodate all events
- Use `[H]` placement for better control

### Milestone Timeline:
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    milestone/.style={circle, draw, fill=red!40, minimum size=12pt},
    event/.style={circle, draw, fill=blue!20, minimum size=8pt},
    label/.style={font=\small, align=center, text width=2.5cm},
]
% Timeline axis
\draw[thick, gray] (0,0) -- (12,0);

% Milestones (major events)
\node[milestone] (m1) at (2,0) {};
\node[label, above=0.3cm] at (m1) {2017\\Transformer};

\node[milestone] (m2) at (6,0) {};
\node[label, below=0.3cm] at (m2) {2020\\GPT-3};

\node[milestone] (m3) at (10,0) {};
\node[label, above=0.3cm] at (m3) {2022\\ChatGPT};

% Regular events
\node[event] at (4,0) {};
\node[label, below=0.3cm, font=\footnotesize] at (4,0) {2018\\BERT};

\node[event] at (8,0) {};
\node[label, above=0.3cm, font=\footnotesize] at (8,0) {2021\\Codex};

\end{tikzpicture}
\caption{Key milestones in LLM development}
\label{fig:timeline}
\end{figure}
```

Generate the complete LaTeX code now based on the content provided.