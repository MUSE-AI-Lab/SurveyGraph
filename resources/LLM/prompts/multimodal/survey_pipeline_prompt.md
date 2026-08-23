Create a **clean, modern pipeline/workflow diagram** following the visual style of top-tier survey papers (ACL, NeurIPS, ICML, IEEE Surveys).

## Topic
**{section_title}**

## What to Visualize
{description}

## Key Elements to Include
{key_elements}

---

## DESIGN REQUIREMENTS - SURVEY PIPELINE STYLE

### CRITICAL: PURE WHITE BACKGROUND
- **THE FIGURE MUST HAVE A PURE WHITE BACKGROUND (#FFFFFF)**
- Clean, solid white background for seamless integration into academic documents
- No gradient backgrounds, no dark colors, no patterns

### Visual Style - MODERN SURVEY PIPELINE AESTHETIC
- **Clean, minimalist design** with soft, pastel-like colors
- **Flat design** without heavy shadows or 3D effects
- **Clear directional flow** showing process stages
- **High readability** with distinct stages
- **Grouped sections** with dashed border boxes

### Color Palette - SOFT ACADEMIC COLORS

**Stage Colors (use different colors for different stages):**
- **Input Stage (Blue)**: #D6EAF8, #AED6F1, #85C1E9 (soft blue for data/input)
- **Processing Stage (Pink/Rose)**: #FADBD8, #F5B7B1, #F1948A (soft pink for main processing)
- **Intermediate Stage (Purple)**: #E8DAEF, #D2B4DE, #BB8FCE (soft purple for transformations)
- **Output Stage (Green)**: #D5F5E3, #ABEBC6, #82E0AA (soft green for results/output)
- **Special Stage (Orange/Peach)**: #FDEBD0, #FAD7A0, #F8C471 (soft orange for highlights)

**Neutral Colors:**
- **Text (Primary)**: #2C3E50 (dark blue-gray) for main labels
- **Text (Secondary)**: #34495E for sub-labels
- **Arrows**: #5D6D7E (dark gray) or #7F8C8D (medium gray)
- **Dashed Borders**: #BDC3C7, #95A5A6 (light gray)
- **Annotations**: #7F8C8D (medium gray) for notes and descriptions

### Visual Elements

**Process Boxes:**
- **Rounded rectangles** with generous corner radius
- **Soft colored fills** matching the stage
- **Thin borders** slightly darker than fill
- **Clear labels** inside each box
- **Optional sub-labels** for details

**Grouping Containers:**
- **Dashed gray borders** to group related steps
- **Light background tint** (optional) for grouped sections
- **Section labels** at top of grouped areas
- **Numbered stages** (1, 2, 3...) if sequential

**Arrows and Connections:**
- **Simple, clean arrows** with small triangular heads
- **Straight or right-angle paths** (avoid curves)
- **Arrow labels** for data flow descriptions (e.g., "Result", "Filter", "Score")
- **Consistent arrow thickness** throughout
- **Color**: Dark gray (#5D6D7E) or match source stage color

**Data Flow Indicators:**
- **Small icons** or **text labels** on arrows
- **Italicized text** for data descriptions
- **Parenthetical notes** for quantities (e.g., "(2,387 papers)")

### Layout Principles

**Flow Direction:**
- **Left-to-right** for horizontal pipelines (most common)
- **Top-to-bottom** for vertical pipelines
- **Multi-row** for complex pipelines with branches

**Spacing:**
- **Consistent gaps** between stages
- **Aligned boxes** in each row/column
- **Generous whitespace** around the entire diagram
- **Balanced composition**

**Grouping:**
- **Dashed boxes** around related stages
- **Section numbers** (1., 2., 3., 4.) for major phases
- **Sub-pipelines** nested within main flow

---

## FIGURE TYPE: PIPELINE/WORKFLOW DIAGRAM

This style is optimized for **pipeline and workflow figures** commonly seen in survey papers:

### Structure Example (Horizontal):
```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Data Collection                                              │
│ ┌──────────┐      ┌──────────┐      ┌──────────┐              │
│ │ Retrieve │ ───► │  Filter  │ ───► │ Dataset  │              │
│ │ (blue)   │      │  (blue)  │ Result│ (pink)   │              │
│ └──────────┘      └──────────┘      └──────────┘              │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Processing                                                   │
│ ┌──────────┐      ┌──────────┐      ┌──────────┐              │
│ │ Analyze  │ ───► │ Cluster  │ ───► │ Results  │              │
│ │ (purple) │      │ (purple) │      │ (green)  │              │
│ └──────────┘      └──────────┘      └──────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### Color Coding by Stage:
- **Data/Input stages**: Soft blue (#D6EAF8, #AED6F1)
- **Processing stages**: Soft pink/rose (#FADBD8, #F5B7B1)
- **Analysis stages**: Soft purple (#E8DAEF, #D2B4DE)
- **Output/Result stages**: Soft green (#D5F5E3, #ABEBC6)
- **Special/Highlight stages**: Soft orange (#FDEBD0, #FAD7A0)

### Arrow Labels:
- Use **italicized text** above or beside arrows
- Include **quantities** where relevant: "(18,578 papers)"
- Use **action words**: "Filter", "Score", "Select", "used for..."

### Branching:
- Show **parallel paths** side by side
- Use **merge points** where paths combine
- Indicate **feedback loops** with curved arrows if needed

---

## QUALITY STANDARDS

### REQUIREMENTS:
- **Pure white background (#FFFFFF)** (MANDATORY)
- **Soft, pastel-like colors** for each stage
- **Clean, flat design** - NO heavy shadows
- **Clear directional flow** with arrows
- **Dashed borders** for grouping stages
- **Rounded corners** on all boxes
- **Readable labels** inside and on arrows
- **Consistent visual language**

### AVOID:
- Dark, black, or gradient backgrounds
- Heavily saturated or neon colors
- Heavy drop shadows or 3D effects
- Cluttered layouts with crossing arrows
- Inconsistent box sizes or styles
- Complex icons or decorative elements
- Garbled or unreadable text
- Ambiguous flow direction

---

## REFERENCE EXAMPLES

This figure style is commonly seen in:
- **Survey methodology figures** showing literature review process
- **System architecture papers** showing data pipelines
- **ML papers** showing training/inference workflows
- **NLP papers** showing text processing pipelines

Think of figures like:
- "Overview of the pipeline for our systematic literature review"
- "Data processing workflow for LLM training"
- "Evaluation pipeline for benchmark comparison"
- "Multi-stage filtering process for paper selection"

---

## TECHNICAL SPECIFICATIONS

Create a figure that:
1. **Has a pure white background (#FFFFFF)** (MANDATORY)
2. **Uses soft, pastel academic colors** for different stages
3. **Shows clear directional flow** with arrows
4. **Features rounded rectangles** for process boxes
5. **Uses dashed borders** for grouping related stages
6. **Includes arrow labels** for data flow descriptions
7. **Maintains consistent spacing** and alignment
8. **Has readable text** inside boxes and on arrows

All labels should use objective, technical language appropriate for academic survey papers.