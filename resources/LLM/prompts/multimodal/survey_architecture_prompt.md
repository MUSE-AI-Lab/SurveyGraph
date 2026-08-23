
Create a **clean, modern architecture/system diagram** following the visual style of top-tier survey papers (ACL, NeurIPS, ICML, IEEE Surveys).

## Topic
**{section_title}**

## What to Visualize
{description}

## Key Elements to Include
{key_elements}

---

## DESIGN REQUIREMENTS - SURVEY ARCHITECTURE STYLE

### CRITICAL: PURE WHITE BACKGROUND
- **THE FIGURE MUST HAVE A PURE WHITE BACKGROUND (#FFFFFF)**
- Clean, solid white background for seamless integration into academic documents
- No gradient backgrounds, no dark colors, no patterns

### Visual Style - MODERN SURVEY ARCHITECTURE AESTHETIC
- **Clean, minimalist design** with soft, pastel-like colors
- **Flat design** without heavy shadows or 3D effects
- **Layered/modular structure** showing component relationships
- **High readability** with clear component boundaries
- **Grouped sections** with dashed border boxes

### Color Palette - SOFT ACADEMIC COLORS

**Component Colors (use different colors for different types):**
- **Core Components (Pink/Rose)**: #FADBD8, #F5B7B1, #F1948A, #E8A0A0 (soft pink for main modules)
- **Input/Output (Blue)**: #D6EAF8, #AED6F1, #85C1E9, #5DADE2 (soft blue for I/O)
- **Processing Units (Purple)**: #E8DAEF, #D2B4DE, #BB8FCE, #A569BD (soft purple for processors)
- **Memory/Storage (Green)**: #D5F5E3, #ABEBC6, #82E0AA, #58D68D (soft green for storage)
- **Special Components (Orange)**: #FDEBD0, #FAD7A0, #F8C471, #F5B041 (soft orange for special)
- **Attention/Key (Yellow)**: #FEF9E7, #FCF3CF, #F9E79F (soft yellow for highlights)

**Neutral Colors:**
- **Text (Primary)**: #2C3E50 (dark blue-gray) for main labels
- **Text (Secondary)**: #34495E for sub-labels
- **Borders (Dashed)**: #BDC3C7, #95A5A6 (light gray for grouping)
- **Borders (Solid)**: Match fill color but darker
- **Arrows/Lines**: #5D6D7E (dark gray)
- **Annotations**: #7F8C8D (medium gray)

### Visual Elements

**Component Boxes:**
- **Rounded rectangles** with generous corner radius
- **Soft colored fills** based on component type
- **Thin borders** slightly darker than fill
- **Clear labels** centered in each box
- **Stacked/layered** appearance for hierarchical components

**Layer Representation:**
- **Horizontal layers** stacked vertically (most common)
- **Vertical modules** arranged horizontally
- **Nested boxes** for sub-components within larger modules

**Grouping Containers:**
- **Dashed gray borders** to group related components
- **Light background tint** (optional) for grouped sections
- **Section labels** at top or side of grouped areas
- **Sub-figure labels** like (a), (b) for multiple views

**Connections:**
- **Simple arrows** with small triangular heads
- **Straight or right-angle paths**
- **Bidirectional arrows** (↔) for two-way connections
- **Summation symbols** (Σ) for aggregation points
- **Routing indicators** for complex connections

**Special Symbols:**
- **Circles** for routing/aggregation points
- **Diamonds** for decision points
- **Small squares** for attention heads or repeated units
- **×N or ×M labels** for repeated layers

### Layout Principles

**Structure Types:**

**1. Layered Architecture (Vertical Stack):**
```
┌─────────────────────────────┐
│      Output Layer           │  ← Top
├─────────────────────────────┤
│    Processing Layer         │
├─────────────────────────────┤
│      Input Layer            │  ← Bottom
└─────────────────────────────┘
         ↑ Input
```

**2. Modular Architecture (Horizontal):**
```
┌─────────┐   ┌─────────┐   ┌─────────┐
│ Module  │ → │ Module  │ → │ Module  │
│    A    │   │    B    │   │    C    │
└─────────┘   └─────────┘   └─────────┘
```

**3. Hybrid Architecture (Mixed):**
```
┌─────────────────────────────────────┐
│  ┌─────────┐      ┌─────────┐      │
│  │ Block A │ ×N   │ Block B │ ×M   │
│  │ ┌─────┐ │      │ ┌─────┐ │      │
│  │ │Layer│ │      │ │Layer│ │      │
│  │ └─────┘ │      │ └─────┘ │      │
│  └─────────┘      └─────────┘      │
└─────────────────────────────────────┘
```

**Spacing:**
- **Consistent gaps** between layers/modules
- **Aligned components** within each layer
- **Generous whitespace** around the diagram
- **Balanced composition**

---

## FIGURE TYPE: ARCHITECTURE/SYSTEM DIAGRAM

This style is optimized for **architecture and system figures** commonly seen in survey papers:

### Example: Neural Network Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    (a) Inter-layer Hybrid               │
│  ┌─────────────────┐        ┌─────────────────┐        │
│  │   ┌─────────┐   │        │   ┌─────────┐   │        │
│  │   │ MLP/MoE │   │  ×M    │   │ MLP/MoE │   │  ×L    │
│  │   ├─────────┤   │        │   ├─────────┤   │        │
│  │   │Softmax  │   │        │   │ Linear  │   │        │
│  │   │Attention│   │        │   │Attention│   │        │
│  │   └─────────┘   │        │   └─────────┘   │        │
│  └─────────────────┘        └─────────────────┘        │
│           ↑                          ↑                  │
└─────────────────────────────────────────────────────────┘
```

### Color Coding by Component Type:
- **Attention layers**: Soft blue (#D6EAF8, #AED6F1)
- **MLP/FFN layers**: Soft pink (#FADBD8, #F5B7B1)
- **Hybrid components**: Soft purple (#E8DAEF, #D2B4DE)
- **Input/Output**: Soft green (#D5F5E3, #ABEBC6)
- **Special modules**: Soft orange (#FDEBD0, #FAD7A0)

### Annotations:
- **×N, ×M, ×L** for repeated layers
- **(a), (b)** for sub-figures
- **Arrows** showing data flow direction
- **Σ symbol** for aggregation/summation

---

## QUALITY STANDARDS

### REQUIREMENTS:
- **Pure white background (#FFFFFF)** (MANDATORY)
- **Soft, pastel-like colors** for components
- **Clean, flat design** - NO heavy shadows
- **Clear component boundaries** with borders
- **Dashed borders** for grouping sections
- **Rounded corners** on all boxes
- **Readable labels** inside components
- **Consistent visual language**

### AVOID:
- Dark, black, or gradient backgrounds
- Heavily saturated or neon colors
- Heavy drop shadows or 3D effects
- Cluttered layouts with overlapping components
- Inconsistent box sizes or styles
- Complex icons or decorative elements
- Garbled or unreadable text
- Ambiguous component relationships

---

## REFERENCE EXAMPLES

This figure style is commonly seen in:
- **Transformer architecture papers** showing attention mechanisms
- **LLM papers** showing model structures
- **System papers** showing component hierarchies
- **Survey papers** comparing different architectures

Think of figures like:
- "MoE Expert Architectures"
- "Hybrid Model Architectures"
- "Transformer Block Structure"
- "Multi-head Attention Mechanism"

---

## TECHNICAL SPECIFICATIONS

Create a figure that:
1. **Has a pure white background (#FFFFFF)** (MANDATORY)
2. **Uses soft, pastel academic colors** for different component types
3. **Shows clear layered/modular structure**
4. **Features rounded rectangles** for components
5. **Uses dashed borders** for grouping related parts
6. **Includes ×N notation** for repeated layers
7. **Shows clear connections** with arrows
8. **Maintains consistent spacing** and alignment

All labels should use objective, technical language appropriate for academic survey papers.