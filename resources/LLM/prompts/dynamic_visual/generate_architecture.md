# Architecture Diagram Generation Prompt

You are a LaTeX/TikZ expert specializing in academic diagrams. Generate a professional architecture diagram based on the following information.

## Architecture Description
{description}

## Style Preference
{style}

## Data Requirements
{data_requirements}

## Reference Content
{section_content}

## Style Guidelines

### layered_architecture
- Horizontal layers stacked vertically
- Clear separation between layers
- Good for showing abstraction levels

### component_diagram
- Connected boxes/shapes
- Arrows showing relationships
- Good for showing system components

### pipeline_diagram
- Sequential processing stages
- Data flow from left to right
- Good for showing data pipelines

### grouped_architecture (NEW - for nested categories)
- Category boxes containing multiple sub-items
- Sub-items arranged horizontally within each category
- Good for showing classification with examples
- **CRITICAL**: Must calculate widths dynamically to prevent overlap

---

## **CRITICAL: Anti-Overlap Rules (MUST FOLLOW)**

### Problem Analysis
When architecture diagrams have nested boxes (category containing sub-items), fixed widths cause overlap. You MUST dynamically calculate dimensions.

### Dynamic Width Calculation Rules

#### 1. Sub-item Box Width
Calculate based on **text length**:
- Short text (1-2 words): `minimum width=2cm`
- Medium text (3-5 words): `minimum width=3cm`
- Long text (6+ words): `minimum width=4cm` OR use `text width=3.5cm` with line breaks

#### 2. Horizontal Spacing Between Sub-items
Calculate based on **number of sub-items per row**:
- 2 items: `xshift=3.5cm` between items
- 3 items: `xshift=3cm` between items
- 4+ items: `xshift=2.5cm` AND use smaller font (`\footnotesize`)

#### 3. Category Box Width
**MUST be calculated as**: `(number_of_items × item_width) + (number_of_items - 1) × gap + 2 × padding`
- Example: 3 items × 3cm + 2 × 0.5cm gap + 2 × 0.5cm padding = 11cm

#### 4. Vertical Spacing Between Categories
- Simple categories (1 row of items): `1.8cm` between category centers
- Complex categories (2+ rows): `2.5cm` or more

### Content Abbreviation Strategy

When sub-items are too many or text is too long:

1. **Text Abbreviation**:
   - Use acronyms: "Internal Modularity" → "Int. Mod."
   - Use parenthetical short forms: "MATPO (Internal Modularity)"
   - Truncate with ellipsis: "Very Long Name..."

2. **Layout Adjustment**:
   - If 4+ items: Consider 2 rows instead of 1
   - If text is long: Use `text width` with auto line-break
   - If still crowded: Reduce font size to `\footnotesize` or `\scriptsize`

3. **Grouping Strategy**:
   - Group similar items: "Method A, B, C" → "Methods (A, B, C)"
   - Use representative examples: "e.g., GPT-4, Claude"

---

## LaTeX Requirements

1. Use `tikz` package with appropriate libraries (`positioning`, `fit`, `calc`)
2. Include meaningful `\caption` and `\label`
3. Use consistent styling for components
4. Show clear connections/relationships
5. Keep component labels concise
6. **CRITICAL**: Calculate box widths based on content
7. **CRITICAL**: Use `\resizebox{\textwidth}{!}{}` for wide diagrams

---

## Output Format

Generate ONLY the LaTeX code wrapped in ```latex blocks:

### Layered Architecture:
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    layer/.style={rectangle, draw, minimum width=10cm, minimum height=1.2cm, align=center, font=\small},
    arrow/.style={->, thick, >=stealth}
]

% Layers (bottom to top)
\node[layer, fill=blue!10] (l1) at (0,0) {Data Layer};
\node[layer, fill=blue!20] (l2) at (0,1.5) {Processing Layer};
\node[layer, fill=blue!30] (l3) at (0,3) {Model Layer};
\node[layer, fill=blue!40] (l4) at (0,4.5) {Application Layer};

% Arrows
\draw[arrow] (l1) -- (l2);
\draw[arrow] (l2) -- (l3);
\draw[arrow] (l3) -- (l4);

% Labels on the side
\node[rotate=90, anchor=south] at (-5.5,2.25) {Abstraction Level};

\end{tikzpicture}
\caption{Layered architecture of the proposed system}
\label{fig:architecture}
\end{figure}
```

### Component Diagram:
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    component/.style={rectangle, draw, rounded corners, minimum width=2.5cm, minimum height=1cm, align=center, fill=blue!20, font=\small},
    arrow/.style={->, thick, >=stealth},
    node distance=2cm
]

% Components
\node[component] (input) {Input\\Module};
\node[component, right of=input, xshift=1cm] (encoder) {Encoder};
\node[component, right of=encoder, xshift=1cm] (attention) {Attention\\Mechanism};
\node[component, right of=attention, xshift=1cm] (decoder) {Decoder};
\node[component, right of=decoder, xshift=1cm] (output) {Output\\Module};

% Connections
\draw[arrow] (input) -- (encoder);
\draw[arrow] (encoder) -- (attention);
\draw[arrow] (attention) -- (decoder);
\draw[arrow] (decoder) -- (output);

% Feedback loop
\draw[arrow, dashed] (decoder.south) -- ++(0,-0.8) -| (encoder.south);

\end{tikzpicture}
\caption{Component architecture of the model}
\label{fig:architecture}
\end{figure}
```

### Pipeline Diagram:
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    stage/.style={rectangle, draw, rounded corners, minimum width=2cm, minimum height=1.5cm, align=center, font=\small},
    data/.style={cylinder, draw, shape border rotate=90, minimum width=1cm, minimum height=0.8cm, fill=gray!20},
    arrow/.style={->, thick, >=stealth}
]

% Data sources
\node[data] (d1) at (0,0) {};
\node[below=0.1cm of d1, font=\footnotesize] {Raw Data};

% Pipeline stages
\node[stage, fill=green!20] (s1) at (2.5,0) {Pre-\\processing};
\node[stage, fill=blue!20] (s2) at (5,0) {Feature\\Extraction};
\node[stage, fill=orange!20] (s3) at (7.5,0) {Model\\Training};
\node[stage, fill=red!20] (s4) at (10,0) {Evaluation};

% Output
\node[data] (d2) at (12.5,0) {};
\node[below=0.1cm of d2, font=\footnotesize] {Results};

% Arrows
\draw[arrow] (d1) -- (s1);
\draw[arrow] (s1) -- (s2);
\draw[arrow] (s2) -- (s3);
\draw[arrow] (s3) -- (s4);
\draw[arrow] (s4) -- (d2);

\end{tikzpicture}
\caption{Data processing pipeline}
\label{fig:architecture}
\end{figure}
```

### Grouped Architecture (Categories with Sub-items) - RECOMMENDED for classification diagrams:
```latex
\begin{figure}[htbp]
\centering
\resizebox{\textwidth}{!}{%  % Auto-scale to fit page width
\begin{tikzpicture}[
    % Category box style - width calculated dynamically
    category/.style={
        rectangle, draw, rounded corners=3pt,
        minimum height=1.6cm,
        align=center, font=\small\bfseries,
        inner sep=8pt
    },
    % Sub-item box style - width based on text length
    item/.style={
        rectangle, draw, rounded corners=2pt,
        minimum height=0.9cm,
        align=center, font=\footnotesize,
        inner sep=4pt
    },
]

% ============ Category 1 ============
% Calculate: 3 items × 3.2cm + gaps + padding ≈ 11cm
\node[category, fill=red!15, minimum width=11cm] (cat1) at (0, 0) {};
\node[anchor=north, font=\small\bfseries] at (cat1.north) {Category A Title};

% Sub-items - DYNAMIC spacing based on item count and text length
\node[item, fill=red!8, minimum width=3.2cm] (c1i1) at (-3.5, -0.15) {Item A1\\(Short Desc)};
\node[item, fill=red!8, minimum width=3.2cm] (c1i2) at (0, -0.15) {Item A2\\(Short Desc)};
\node[item, fill=red!8, minimum width=3.2cm] (c1i3) at (3.5, -0.15) {Item A3\\(Short Desc)};

% ============ Category 2 ============
% Calculate: 3 items × 3.2cm + gaps + padding ≈ 11cm
\node[category, fill=blue!15, minimum width=11cm] (cat2) at (0, -2.2) {};
\node[anchor=north, font=\small\bfseries] at (cat2.north) {Category B Title};

% Sub-items
\node[item, fill=blue!8, minimum width=3.2cm] (c2i1) at (-3.5, -2.35) {Item B1\\(Short Desc)};
\node[item, fill=blue!8, minimum width=3.2cm] (c2i2) at (0, -2.35) {Item B2\\(Short Desc)};
\node[item, fill=blue!8, minimum width=3.2cm] (c2i3) at (3.5, -2.35) {Item B3\\(Short Desc)};

% ============ Category 3 ============
% Calculate: 2 items × 4cm + gaps + padding ≈ 9.5cm
\node[category, fill=green!15, minimum width=9.5cm] (cat3) at (0, -4.4) {};
\node[anchor=north, font=\small\bfseries] at (cat3.north) {Category C Title};

% Sub-items - fewer items, can be wider
\node[item, fill=green!8, minimum width=4cm] (c3i1) at (-2.3, -4.55) {Item C1 (Longer Name)};
\node[item, fill=green!8, minimum width=4cm] (c3i2) at (2.3, -4.55) {Item C2 (Longer Name)};

\end{tikzpicture}
}%
\caption{Architecture classification showing categories and their components}
\label{fig:grouped-architecture}
\end{figure}
```

### Grouped Architecture with Long Text (using text width for auto-wrap):
```latex
\begin{figure}[htbp]
\centering
\resizebox{\textwidth}{!}{%
\begin{tikzpicture}[
    category/.style={
        rectangle, draw, rounded corners=3pt,
        minimum height=2cm,
        align=center, font=\small\bfseries,
        inner sep=10pt
    },
    % Use text width for long text - enables auto line-break
    item/.style={
        rectangle, draw, rounded corners=2pt,
        text width=3cm,  % Fixed width, text wraps automatically
        minimum height=1.2cm,
        align=center, font=\scriptsize,
        inner sep=4pt
    },
]

% Category with long item names
\node[category, fill=red!15, minimum width=12cm] (cat1) at (0, 0) {};
\node[anchor=north, font=\small\bfseries] at (cat1.north) {Monolithic Systems with Enhancements};

% Items with long text - use text width for wrapping
\node[item, fill=red!8] (c1i1) at (-4, -0.2) {MATPO\\(Internal Modularity)};
\node[item, fill=red!8] (c1i2) at (0, -0.2) {QUASAR\\(External Verification)};
\node[item, fill=red!8] (c1i3) at (4, -0.2) {DraCor\\(Standardized Protocols)};

% Category 2
\node[category, fill=blue!15, minimum width=12cm] (cat2) at (0, -2.8) {};
\node[anchor=north, font=\small\bfseries] at (cat2.north) {Multi-Agent Systems (MAS)};

\node[item, fill=blue!8] (c2i1) at (-4, -3.0) {GeoJSON Agents\\(Planning)};
\node[item, fill=blue!8] (c2i2) at (0, -3.0) {Tool-MVR\\(Verification Pipeline)};
\node[item, fill=blue!8] (c2i3) at (4, -3.0) {ToolCritic\\(Schema Validation)};

% Category 3 - fewer items
\node[category, fill=green!15, minimum width=9cm] (cat3) at (0, -5.6) {};
\node[anchor=north, font=\small\bfseries] at (cat3.north) {Structural Organization Strategies};

\node[item, fill=green!8] (c3i1) at (-2.2, -5.8) {ChemHAS\\(Rigid Hierarchies)};
\node[item, fill=green!8] (c3i2) at (2.2, -5.8) {ODIA\\(Dynamic Routing)};

\end{tikzpicture}
}%
\caption{Evolution of Agentic Architectures}
\label{fig:agentic-architecture}
\end{figure}
```

---

## Pre-Generation Checklist

Before generating the LaTeX code, mentally verify:

1. [ ] **Item Count per Category**: How many sub-items? Calculate category width accordingly.
2. [ ] **Text Length**: What's the longest item text? Set appropriate `minimum width` or `text width`.
3. [ ] **Horizontal Spacing**: Will items overlap? Calculate: `category_width = n × item_width + (n-1) × gap + padding`
4. [ ] **Vertical Spacing**: Are categories too close? Use at least 2cm between category centers.
5. [ ] **Page Fit**: Will it fit? Use `\resizebox{\textwidth}{!}{}` for wide diagrams.
6. [ ] **Font Size**: Too crowded? Use `\footnotesize` or `\scriptsize` for items.

---

Generate the complete LaTeX code now based on the content provided.