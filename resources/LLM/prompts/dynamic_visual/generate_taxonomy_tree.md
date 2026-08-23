# Taxonomy Tree Generation Prompt

You are a LaTeX/TikZ expert specializing in academic diagrams. Generate a professional taxonomy tree based on the following information.

## Tree Description
{description}

## Style Preference
{style}

## Data Requirements
{data_requirements}

## Reference Content
{section_content}

## Style Guidelines

### top_down_tree
- Root node at top, children below
- Good for hierarchical classifications
- Use forest package
- **CRITICAL**: Adjust `l sep` (level separation) based on node content width

### left_right_tree
- Root node at left, children to right
- Good for reading flow
- Compact vertical space
- **CRITICAL**: Adjust `s sep` (sibling separation) based on node content height

### radial_tree
- Root at center, branches radiate outward
- Good for showing equal importance of branches
- Use mindmap style

### mindmap_style
- Organic, flowing branches
- Color-coded categories
- Good for conceptual relationships

---

## **CRITICAL: Anti-Overlap Rules (MUST FOLLOW)**

### Problem Analysis
When taxonomy trees have many nodes or long text content, fixed spacing causes overlap. You MUST dynamically adjust parameters based on content.

### Dynamic Spacing Calculation Rules

#### 1. Count-Based Sibling Separation (`s sep`)
Calculate `s sep` based on the **maximum number of siblings at any level**:
- 2-3 siblings: `s sep=8pt`
- 4-6 siblings: `s sep=12pt`
- 7-10 siblings: `s sep=15pt`
- 10+ siblings: `s sep=18pt` AND consider splitting into sub-categories

#### 2. Content-Based Node Width
**DO NOT use fixed `minimum width`**. Instead:
- Use `text width=Xcm` where X is calculated based on longest text
- Short text (1-2 words): `text width=1.5cm`
- Medium text (3-4 words): `text width=2.5cm`
- Long text (5+ words): `text width=3.5cm` OR abbreviate the text

#### 3. Level Separation (`l sep`)
Calculate based on the **widest node at each level**:
- Narrow nodes (< 2cm): `l sep=1.5cm`
- Medium nodes (2-3cm): `l sep=2.5cm`
- Wide nodes (> 3cm): `l sep=3.5cm`

#### 4. Leaf Node Density
When leaf nodes are dense (many items under one parent):
- Use `tier=leaf` to align all leaf nodes
- Consider using **list format** instead of individual nodes
- Use `fit=tight` to minimize wasted space

### Content Abbreviation Strategy

When content is too long or nodes are too many:

1. **Text Abbreviation**:
   - Use acronyms: "Chain-of-Thought" → "CoT"
   - Use ellipsis for long names: "Very Long Method Name" → "Long Method..."
   - Keep core meaning, remove adjectives

2. **Structure Simplification**:
   - Group similar items: Instead of 10 separate nodes, use "Type A (10 variants)"
   - Use representative examples: "e.g., GPT-4, Claude, Gemini"
   - Limit leaf nodes to 4-6 per parent; if more, create sub-categories

3. **Multi-line Text**:
   - Use `\\` for line breaks in long text
   - Set appropriate `text width` to enable auto-wrapping
   - Example: `text width=2.5cm, align=center`

---

## LaTeX Requirements

1. Use `forest` package for tree structures
2. Use `tikz` with appropriate libraries
3. Include meaningful `\caption` and `\label`
4. Use consistent colors for same-level nodes
5. Keep node text concise (max 3-4 words per line)
6. **CRITICAL**: Calculate spacing dynamically based on content
7. **CRITICAL**: Test mentally if nodes would overlap before finalizing

---

## Output Format

Generate ONLY the LaTeX code wrapped in ```latex blocks:

### For forest-based trees (LEFT-TO-RIGHT, recommended for many nodes):
```latex
\begin{figure}[htbp]
\centering
\resizebox{\textwidth}{!}{%  % Auto-scale to fit page width
\begin{forest}
for tree={
    grow=east,
    reversed=true,
    anchor=base west,
    parent anchor=east,
    child anchor=west,
    base=left,
    font=\small,
    rectangle,
    draw,
    rounded corners,
    align=left,
    % DYNAMIC: Adjust text width based on content length
    text width=2.2cm,
    edge+={darkgray, line width=1pt},
    % DYNAMIC: Adjust s sep based on sibling count
    s sep=10pt,
    % DYNAMIC: Adjust l sep based on node width
    l sep=2cm,
    inner xsep=4pt,
    inner ysep=3pt,
},
% Level-specific adjustments
where level=0{font=\normalsize\bfseries, fill=blue!20, text width=3cm}{},
where level=1{fill=green!15, text width=2.5cm}{},
where level=2{fill=orange!15, text width=2cm}{},
where level=3{fill=gray!10, text width=2cm, font=\footnotesize}{},
[Root Concept
    [Category A
        [Subcategory A1
            [Item 1]
            [Item 2]
        ]
        [Subcategory A2]
    ]
    [Category B
        [Subcategory B1]
        [Subcategory B2]
    ]
]
\end{forest}
}%
\caption{Taxonomy of the research area}
\label{fig:taxonomy}
\end{figure}
```

### For TOP-DOWN trees (good for wide but shallow hierarchies):
```latex
\begin{figure}[htbp]
\centering
\resizebox{\textwidth}{!}{%
\begin{forest}
for tree={
    grow=south,
    anchor=north,
    parent anchor=south,
    child anchor=north,
    font=\small,
    rectangle,
    draw,
    rounded corners,
    align=center,
    % DYNAMIC: Wider text for horizontal layout
    text width=2.5cm,
    edge+={darkgray, line width=1pt},
    % DYNAMIC: Larger l sep for vertical growth
    l sep=1.5cm,
    % DYNAMIC: Adjust s sep based on sibling count
    s sep=15pt,
    inner xsep=6pt,
    inner ysep=4pt,
},
where level=0{font=\normalsize\bfseries, fill=blue!25}{},
where level=1{fill=teal!20}{},
where level=2{fill=orange!15, font=\footnotesize}{},
[Root Concept
    [Category A
        [Sub A1]
        [Sub A2]
    ]
    [Category B
        [Sub B1]
        [Sub B2]
    ]
    [Category C
        [Sub C1]
        [Sub C2]
    ]
]
\end{forest}
}%
\caption{Taxonomy of the research area}
\label{fig:taxonomy}
\end{figure}
```

### For DENSE taxonomies (many leaf nodes):
```latex
\begin{figure}[htbp]
\centering
\resizebox{\textwidth}{!}{%
\begin{forest}
for tree={
    grow=east,
    reversed=true,
    anchor=base west,
    parent anchor=east,
    child anchor=west,
    font=\footnotesize,  % Smaller font for dense trees
    rectangle,
    draw,
    rounded corners,
    align=left,
    text width=2cm,
    edge+={darkgray, line width=0.8pt},
    s sep=6pt,  % Tighter spacing
    l sep=1.8cm,
    inner xsep=3pt,
    inner ysep=2pt,
    % Fit nodes tightly
    fit=tight,
},
where level=0{font=\small\bfseries, fill=blue!20, text width=2.5cm}{},
where level=1{fill=green!15, s sep=8pt}{},
where level=2{fill=orange!10, s sep=5pt}{},
where level=3{fill=gray!8, font=\scriptsize, text width=1.8cm}{},
[Main Topic
    [Category A
        [Type A1, tier=leaf
            [a, b, c, tier=items]
        ]
        [Type A2, tier=leaf]
    ]
    [Category B
        [Type B1, tier=leaf]
        [Type B2, tier=leaf]
    ]
]
\end{forest}
}%
\caption{Detailed taxonomy with multiple levels}
\label{fig:taxonomy}
\end{figure}
```

### For mindmap style (organic layout, auto-spacing):
```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
    mindmap,
    grow cyclic,
    every node/.style={concept},
    concept color=blue!40,
    % DYNAMIC: Adjust level distance based on content
    level 1/.append style={
        level distance=4.5cm,
        sibling angle=360/4,  % Divide evenly: 360/number_of_children
    },
    level 2/.append style={
        level distance=3cm,
        sibling angle=40,  % Adjust based on leaf count
    },
    % Smaller text for deeper levels
    level 1 concept/.append style={font=\small},
    level 2 concept/.append style={font=\footnotesize},
]
\node[font=\normalsize\bfseries]{Central Concept}
    child[concept color=red!40] { node {Branch A}
        child { node {Leaf A1} }
        child { node {Leaf A2} }
    }
    child[concept color=green!40] { node {Branch B}
        child { node {Leaf B1} }
        child { node {Leaf B2} }
    }
    child[concept color=orange!40] { node {Branch C}
        child { node {Leaf C1} }
        child { node {Leaf C2} }
    }
    child[concept color=purple!40] { node {Branch D}
        child { node {Leaf D1} }
        child { node {Leaf D2} }
    };
\end{tikzpicture}
\caption{Conceptual map of the research area}
\label{fig:taxonomy}
\end{figure}
```

---

## Pre-Generation Checklist

Before generating the LaTeX code, mentally verify:

1. [ ] **Node Count**: How many nodes at each level? Adjust `s sep` accordingly.
2. [ ] **Text Length**: What's the longest text? Set appropriate `text width`.
3. [ ] **Tree Depth**: How many levels? Deeper trees need smaller fonts at leaf level.
4. [ ] **Overlap Risk**: Would any nodes overlap? If yes, increase spacing or abbreviate.
5. [ ] **Page Fit**: Will it fit on one page? Use `\resizebox{\textwidth}{!}{}` if needed.

---

Generate the complete LaTeX code now based on the content provided.