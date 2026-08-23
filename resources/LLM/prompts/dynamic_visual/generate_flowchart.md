# Flowchart Generation Prompt

You are a LaTeX/TikZ expert specializing in academic diagrams. Generate a professional flowchart based on the following information.

## Flowchart Description
{description}

## Style Preference
{style}

## Data Requirements
{data_requirements}

## Reference Content
{section_content}

## Style Guidelines

### linear_flow
- Sequential steps from start to end
- Single path, no branches
- Good for simple processes
- **CRITICAL**: Adjust `node distance` based on text length

### branching_flow
- Decision points with multiple paths
- Diamond shapes for decisions
- Good for conditional logic
- **CRITICAL**: Adjust horizontal spacing (`xshift`) based on branch count

### circular_flow
- Cyclic process that repeats
- Arrows connecting back to earlier steps
- Good for iterative processes
- **CRITICAL**: Adjust spacing to prevent arrow overlap

---

## **CRITICAL: Anti-Overlap Rules (MUST FOLLOW)**

### Problem Analysis
When flowcharts have many nodes or long text, fixed spacing causes overlap. You MUST dynamically calculate dimensions.

### Dynamic Spacing Calculation Rules

#### 1. Node Distance (Vertical)
Calculate based on **text content height**:
- Short text (1 line, < 15 chars): `node distance=1.5cm`
- Medium text (1 line, 15-30 chars): `node distance=1.8cm`
- Long text (2 lines or > 30 chars): `node distance=2.2cm`
- Very long text (3+ lines): `node distance=2.8cm`

#### 2. Node Width
Calculate based on **longest text**:
- Short text (< 10 chars): `minimum width=2.5cm`
- Medium text (10-20 chars): `minimum width=3.5cm`
- Long text (20-35 chars): `minimum width=4.5cm`
- Very long text (> 35 chars): Use `text width=4cm` with auto line-break

#### 3. Horizontal Spacing (for branching)
Calculate based on **number of branches**:
- 2 branches: `xshift=2.5cm` for each side
- 3 branches: `xshift=3.5cm` for outer branches
- 4+ branches: Consider vertical layout instead

#### 4. Decision Diamond Size
Adjust based on **question text length**:
- Short question (< 10 chars): `minimum width=2cm, minimum height=1cm`
- Medium question (10-20 chars): `minimum width=2.5cm, minimum height=1.2cm`
- Long question (> 20 chars): `minimum width=3cm, minimum height=1.5cm, text width=2.5cm`

### Content Abbreviation Strategy

When text is too long:

1. **Text Abbreviation**:
   - Use acronyms: "Data Preprocessing" → "Preprocess"
   - Use short forms: "Validation Check" → "Validate"
   - Use line breaks: "Long Step Name" → "Long Step\\Name"

2. **Layout Adjustment**:
   - If > 8 nodes: Consider splitting into sub-flowcharts
   - If text is long: Use `text width` for auto line-break
   - If branches overlap: Increase `xshift` or use vertical branching

---

## LaTeX Requirements

1. Use `tikz` package with shapes and arrows libraries
2. Include meaningful `\caption` and `\label`
3. Use consistent node shapes:
   - Rectangles for processes
   - Diamonds for decisions
   - Rounded rectangles for start/end
   - Parallelograms for input/output
4. Use clear arrow connections
5. Keep text concise in nodes
6. **CRITICAL**: Calculate spacing dynamically based on content
7. **CRITICAL**: Use `\resizebox` for wide flowcharts

---

## Output Format

Generate ONLY the LaTeX code wrapped in ```latex blocks:

### Linear Flow (with dynamic spacing):
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    % DYNAMIC: Adjust node distance based on text length
    node distance=1.8cm,
    startstop/.style={
        rectangle, rounded corners,
        minimum width=3.5cm,  % DYNAMIC: based on longest text
        minimum height=1cm,
        text centered, draw=black, fill=red!30,
        font=\small
    },
    process/.style={
        rectangle,
        minimum width=3.5cm,  % DYNAMIC: based on longest text
        minimum height=1cm,
        text centered, draw=black, fill=blue!20,
        font=\small
    },
    arrow/.style={thick,->,>=stealth}
]

\node (start) [startstop] {Start};
\node (step1) [process, below of=start] {Step 1: Data Collection};
\node (step2) [process, below of=step1] {Step 2: Preprocessing};
\node (step3) [process, below of=step2] {Step 3: Model Training};
\node (step4) [process, below of=step3] {Step 4: Evaluation};
\node (end) [startstop, below of=step4] {End};

\draw [arrow] (start) -- (step1);
\draw [arrow] (step1) -- (step2);
\draw [arrow] (step2) -- (step3);
\draw [arrow] (step3) -- (step4);
\draw [arrow] (step4) -- (end);

\end{tikzpicture}
\caption{Overview of the methodology pipeline}
\label{fig:flowchart}
\end{figure}
```

### Linear Flow (with long text - using text width):
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    % DYNAMIC: Larger node distance for multi-line text
    node distance=2.5cm,
    startstop/.style={
        rectangle, rounded corners,
        text width=4cm,  % Enable auto line-break
        minimum height=1cm,
        text centered, draw=black, fill=red!30,
        font=\small, inner sep=5pt
    },
    process/.style={
        rectangle,
        text width=4cm,  % Enable auto line-break
        minimum height=1.2cm,
        text centered, draw=black, fill=blue!20,
        font=\small, inner sep=5pt
    },
    arrow/.style={thick,->,>=stealth}
]

\node (start) [startstop] {Input Data from Multiple Sources};
\node (step1) [process, below of=start] {Data Collection and Initial Filtering};
\node (step2) [process, below of=step1] {Preprocessing with Normalization};
\node (step3) [process, below of=step2] {Model Training with Cross-Validation};
\node (step4) [process, below of=step3] {Evaluation and Performance Analysis};
\node (end) [startstop, below of=step4] {Final Output Results};

\draw [arrow] (start) -- (step1);
\draw [arrow] (step1) -- (step2);
\draw [arrow] (step2) -- (step3);
\draw [arrow] (step3) -- (step4);
\draw [arrow] (step4) -- (end);

\end{tikzpicture}
\caption{Detailed methodology pipeline with comprehensive steps}
\label{fig:flowchart}
\end{figure}
```

### Branching Flow (with dynamic spacing):
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    % DYNAMIC: Adjust based on branch width needs
    node distance=1.8cm and 3cm,
    startstop/.style={
        rectangle, rounded corners,
        minimum width=2.5cm, minimum height=0.8cm,
        text centered, draw=black, fill=red!30,
        font=\small
    },
    process/.style={
        rectangle,
        minimum width=2.5cm, minimum height=0.8cm,
        text centered, draw=black, fill=blue!20,
        font=\small
    },
    decision/.style={
        diamond,
        minimum width=2.5cm, minimum height=1.2cm,
        text centered, draw=black, fill=green!20,
        aspect=2, font=\small
    },
    arrow/.style={thick,->,>=stealth}
]

\node (start) [startstop] {Input};
\node (proc1) [process, below of=start] {Process Data};
\node (dec1) [decision, below of=proc1, yshift=-0.8cm] {Valid?};
% DYNAMIC: Adjust xshift based on node width
\node (proc2a) [process, below left of=dec1, xshift=-2cm, yshift=-1cm] {Handle Error};
\node (proc2b) [process, below right of=dec1, xshift=2cm, yshift=-1cm] {Continue};
\node (end) [startstop, below of=dec1, yshift=-3cm] {Output};

\draw [arrow] (start) -- (proc1);
\draw [arrow] (proc1) -- (dec1);
\draw [arrow] (dec1) -| node[anchor=south, pos=0.25] {No} (proc2a);
\draw [arrow] (dec1) -| node[anchor=south, pos=0.25] {Yes} (proc2b);
\draw [arrow] (proc2a) |- (end);
\draw [arrow] (proc2b) |- (end);

\end{tikzpicture}
\caption{Decision flow in the processing pipeline}
\label{fig:flowchart}
\end{figure}
```

### Branching Flow (with multiple branches):
```latex
\begin{figure}[htbp]
\centering
\resizebox{\textwidth}{!}{%  % Auto-scale for wide flowcharts
\begin{tikzpicture}[
    node distance=2cm and 2.5cm,
    startstop/.style={
        rectangle, rounded corners,
        minimum width=2cm, minimum height=0.8cm,
        text centered, draw=black, fill=red!30,
        font=\small
    },
    process/.style={
        rectangle,
        minimum width=2.5cm, minimum height=0.8cm,
        text centered, draw=black, fill=blue!20,
        font=\small
    },
    decision/.style={
        diamond,
        minimum width=2cm, minimum height=1cm,
        text centered, draw=black, fill=green!20,
        aspect=2, font=\footnotesize
    },
    arrow/.style={thick,->,>=stealth}
]

\node (start) [startstop] {Start};
\node (dec1) [decision, below of=start, yshift=-0.5cm] {Type?};

% Multiple branches - DYNAMIC spacing
\node (proc1) [process, below left of=dec1, xshift=-3.5cm, yshift=-1cm] {Type A\\Processing};
\node (proc2) [process, below of=dec1, yshift=-1.5cm] {Type B\\Processing};
\node (proc3) [process, below right of=dec1, xshift=3.5cm, yshift=-1cm] {Type C\\Processing};

\node (merge) [process, below of=proc2, yshift=-1cm] {Merge Results};
\node (end) [startstop, below of=merge] {End};

\draw [arrow] (start) -- (dec1);
\draw [arrow] (dec1) -| node[anchor=south, pos=0.2] {A} (proc1);
\draw [arrow] (dec1) -- node[anchor=east] {B} (proc2);
\draw [arrow] (dec1) -| node[anchor=south, pos=0.2] {C} (proc3);
\draw [arrow] (proc1) |- (merge);
\draw [arrow] (proc2) -- (merge);
\draw [arrow] (proc3) |- (merge);
\draw [arrow] (merge) -- (end);

\end{tikzpicture}
}%
\caption{Multi-branch decision flow}
\label{fig:flowchart}
\end{figure}
```

### Circular Flow (with dynamic spacing):
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    % DYNAMIC: Adjust based on node width
    node distance=2.5cm,
    process/.style={
        rectangle,
        minimum width=3cm, minimum height=1cm,
        text centered, draw=black, fill=blue!20,
        font=\small
    },
    arrow/.style={thick,->,>=stealth, bend left=30}
]

% DYNAMIC: Adjust xshift based on node width
\node (step1) [process] {Data Collection};
\node (step2) [process, right of=step1, xshift=2.5cm] {Analysis};
\node (step3) [process, below of=step2] {Model Update};
\node (step4) [process, left of=step3, xshift=-2.5cm] {Evaluation};

\draw [arrow] (step1) to (step2);
\draw [arrow] (step2) to (step3);
\draw [arrow] (step3) to (step4);
\draw [arrow] (step4) to (step1);

\end{tikzpicture}
\caption{Iterative refinement cycle}
\label{fig:flowchart}
\end{figure}
```

---

## Pre-Generation Checklist

Before generating the LaTeX code, mentally verify:

1. [ ] **Node Count**: How many nodes? If > 8, consider splitting or using smaller font.
2. [ ] **Text Length**: What's the longest text? Set appropriate `minimum width` or `text width`.
3. [ ] **Branch Count**: How many branches? Adjust `xshift` accordingly.
4. [ ] **Overlap Risk**: Would any nodes or arrows overlap? Increase spacing if needed.
5. [ ] **Page Fit**: Will it fit? Use `\resizebox{\textwidth}{!}{}` for wide flowcharts.

---

Generate the complete LaTeX code now based on the content provided.