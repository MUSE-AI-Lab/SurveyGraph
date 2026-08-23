Create a **clean, modern comparison/pattern diagram** following the visual style of top-tier survey papers (ACL, NeurIPS, ICML, IEEE Surveys).

## Topic
**{section_title}**

## What to Visualize
{description}

## Key Elements to Include
{key_elements}

---

## DESIGN REQUIREMENTS - SURVEY COMPARISON/PATTERN STYLE

### CRITICAL: PURE WHITE BACKGROUND
- **THE FIGURE MUST HAVE A PURE WHITE BACKGROUND (#FFFFFF)**
- Clean, solid white background for seamless integration into academic documents
- No gradient backgrounds, no dark colors, no patterns

### Visual Style - MODERN SURVEY COMPARISON AESTHETIC
- **Clean, minimalist design** with soft, pastel-like colors
- **Flat design** without heavy shadows or 3D effects
- **Parallel/aligned structure** for easy comparison
- **High readability** with clear distinctions
- **Consistent visual language** across compared items

### Color Palette - SOFT ACADEMIC COLORS

**Category Colors (use different colors for different types/categories):**
- **Type A (Gray/Neutral)**: #F8F9FA, #E9ECEF, #DEE2E6 (light gray for system/base)
- **Type B (Pink/Rose)**: #FADBD8, #F5B7B1, #F1948A (soft pink for user/input)
- **Type C (Green)**: #D5F5E3, #ABEBC6, #82E0AA (soft green for generation/output)
- **Type D (Blue)**: #D6EAF8, #AED6F1, #85C1E9 (soft blue for documents/data)
- **Type E (Orange/Peach)**: #FDEBD0, #FAD7A0, #F8C471 (soft orange for tools)
- **Type F (Purple)**: #E8DAEF, #D2B4DE, #BB8FCE (soft purple for thinking/reasoning)
- **Type G (Yellow)**: #FEF9E7, #FCF3CF, #F9E79F (soft yellow for highlights)

**Border Colors (for outlined boxes):**
- **Pink border**: #E74C3C, #EC7063 (for user-related)
- **Green border**: #27AE60, #58D68D (for generation)
- **Blue border**: #3498DB, #5DADE2 (for data)
- **Orange border**: #E67E22, #F5B041 (for tools)
- **Gray border**: #95A5A6, #BDC3C7 (for neutral)

**Text Colors:**
- **Primary**: #2C3E50 (dark blue-gray)
- **Secondary**: #34495E
- **Labels**: #7F8C8D (medium gray)

### Visual Elements

**Comparison Rows:**
- **Horizontal bars/segments** representing different components
- **Consistent height** for all rows
- **Left-aligned labels** (italicized pattern names)
- **Color-coded segments** for different element types
- **Proportional widths** showing relative sizes (optional)

**Segment Boxes:**
- **Rounded rectangles** with soft fills
- **Thin borders** matching or contrasting fill color
- **Text labels** above or inside segments
- **Consistent spacing** between segments

**Pattern Labels:**
- **Italicized text** for pattern/row names (left side)
- **Regular text** for segment labels (above segments)
- **Small annotations** for additional info

**Layout Types:**

**1. Horizontal Bar Comparison (Timeline-style):**
```
                    label1        label2              label3
Pattern A    ┌────┐ ┌─────────────────────────────┐ ┌────┐
             │gray│ │          pink               │ │org │
             └────┘ └─────────────────────────────┘ └────┘

                    label1  label2  label3  label4  label5
Pattern B    ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
             │gray│ │org │ │grn │ │blue│ │org │ │grn │
             └────┘ └────┘ └────┘ └────┘ └────┘ └────┘
```

**2. Stacked Comparison:**
```
┌─────────────────────────────────────────────────┐
│ Category A                                      │
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐               │
│ │Item1│ │Item2│ │Item3│ │Item4│               │
│ └─────┘ └─────┘ └─────┘ └─────┘               │
├─────────────────────────────────────────────────┤
│ Category B                                      │
│ ┌─────┐ ┌─────┐ ┌─────┐                        │
│ │Item1│ │Item2│ │Item3│                        │
│ └─────┘ └─────┘ └─────┘                        │
└─────────────────────────────────────────────────┘
```

### Layout Principles

**Alignment:**
- **Left-align** pattern/row labels
- **Consistent starting point** for all rows
- **Aligned segment boundaries** where meaningful
- **Uniform row heights**

**Spacing:**
- **Consistent gaps** between rows
- **Small gaps** between segments within a row
- **Generous margins** around the diagram
- **Balanced composition**

**Labels:**
- **Pattern names** on the left (italicized)
- **Segment labels** above or inside segments
- **Legend** if color coding is complex

---

## FIGURE TYPE: COMPARISON/PATTERN DIAGRAM

This style is optimized for **comparison and pattern figures** commonly seen in survey papers:

### Example: Context Pattern Comparison
```
                system        doc                              user
RAG Pattern     ┌────┐ ┌──────────────────────────────────┐ ┌────┐
                │gray│ │            pink                  │ │org │
                └────┘ └──────────────────────────────────┘ └────┘

                system  user    gen     tool    user    gen     tool
Agentic         ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
Pattern         │gray│ │org │ │grn │ │blue│ │org │ │grn │ │blue│
                └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘

                system  user         gen    think   gen   think  gen
Reasoning       ┌────┐ ┌──────────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
Pattern         │gray│ │   org    │ │grn │ │pink│ │grn │ │pink│ │grn │
                └────┘ └──────────┘ └────┘ └────┘ └────┘ └────┘ └────┘
```

### Color Coding Legend:
- **Gray** (#F8F9FA): System prompts, base components
- **Pink/Rose** (#FADBD8): User input, thinking, documents
- **Green** (#D5F5E3): Generation, output
- **Blue** (#D6EAF8): Tools, external data
- **Orange** (#FDEBD0): User queries, highlights

### Segment Styles:
- **Filled boxes**: Main components with soft color fills
- **Outlined boxes**: Optional/variable components (border only, white fill)
- **Wide segments**: Long content (documents, extended generation)
- **Narrow segments**: Short content (system, user queries)

---

## QUALITY STANDARDS

### REQUIREMENTS:
- **Pure white background (#FFFFFF)** (MANDATORY)
- **Soft, pastel-like colors** for segments
- **Clean, flat design** - NO heavy shadows
- **Consistent row heights** and alignment
- **Clear color coding** with legend if needed
- **Rounded corners** on all segments
- **Readable labels** above or inside segments
- **Italicized pattern names** on the left

### AVOID:
- Dark, black, or gradient backgrounds
- Heavily saturated or neon colors
- Heavy drop shadows or 3D effects
- Inconsistent segment sizes or styles
- Overlapping elements
- Complex icons or decorative elements
- Garbled or unreadable text
- Misaligned rows or segments

---

## REFERENCE EXAMPLES

This figure style is commonly seen in:
- **LLM papers** showing context patterns
- **Survey papers** comparing method characteristics
- **System papers** showing message/data flows
- **Analysis papers** showing temporal patterns

Think of figures like:
- "Long Context Patterns" (RAG, Agentic, Reasoning, Multimodal)
- "Comparison of Prompting Strategies"
- "Message Flow Patterns in LLM Applications"
- "Token Distribution Across Different Tasks"

---

## TECHNICAL SPECIFICATIONS

Create a figure that:
1. **Has a pure white background (#FFFFFF)** (MANDATORY)
2. **Uses soft, pastel academic colors** for different segment types
3. **Shows clear parallel/aligned structure** for comparison
4. **Features rounded rectangles** for segments
5. **Uses consistent row heights** and alignment
6. **Includes clear labels** above or inside segments
7. **Has italicized pattern names** on the left
8. **Maintains consistent spacing** throughout

All labels should use objective, technical language appropriate for academic survey papers.