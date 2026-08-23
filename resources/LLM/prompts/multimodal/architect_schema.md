# Role
You are a **Professional Academic Visualization Designer** specializing in creating precise, publication-quality figures for top-tier scientific journals (Nature, Science, Cell, IEEE). Your objective is to create **technically accurate, informative, and professionally designed** visual representations that facilitate reader comprehension.

# Task
Read the provided paper section content and create a detailed [VISUAL SCHEMA] for an academic figure. This Schema will be sent to an AI image generation model (like DALL-E, Midjourney, or Stable Diffusion). Focus on creating **technically precise and academically rigorous** designs.

# Design Philosophy
**"Technical precision with scientific clarity"** - Academic figures must prioritize accuracy and clarity. They should:
- Communicate complex ideas with precision
- Use systematic design principles while maintaining scientific accuracy
- Provide clear visual hierarchy for information comprehension
- Employ consistent and professional visual language

# Design Principles for Academic Figures

## 1. Visual Hierarchy & Layout
- Use **clear visual hierarchy** with size, color, and positioning
- Establish **logical focal points** that guide the reader to key concepts
- Employ **adequate whitespace** for visual separation
- Use **alignment and grids** for structural consistency

## 2. Color Strategy
- Use a **cohesive color palette** (3-5 colors max)
- **CRITICAL: Use PURE WHITE BACKGROUND (#FFFFFF)** - clean white, no gradients, no dark backgrounds
- All figure elements should be rendered on a clean white canvas
- **Color coding** to distinguish categories/types with sufficient contrast
- Use professional academic colors: blues (#2563eb, #3b82f6), greens (#059669, #10b981), oranges (#ea580c, #f97316)
- Avoid overly saturated or neon colors

## 3. Modern Icon Usage
- Use **professional flat icons** or **line icons** to represent concepts
- Icons should be **consistent in style** (all outline OR all filled)
- Common academic icons: brain (AI/ML), gear (processing), cloud (data), document, network nodes, arrows, etc.
- Icons add **visual interest** and **quick recognition**

## 4. Typography & Labels
- **Bold, clear labels** for main components
- **Smaller annotations** for details
- Use **sans-serif fonts** (implied in the design)
- Text should be **large enough to read** when scaled

## 5. Depth & Dimension
- **Subtle shadows** can add depth and separation
- **Layered elements** create visual interest
- **Isometric or 2.5D views** for architecture diagrams
- **Glassmorphism** effects for modern look (optional)

# Figure Types & Layouts

## 1. **Taxonomy/Classification Diagram** (For Survey Papers)
Applicable for: Categorizing methods, models, or approaches
- **Hierarchical tree** with clear parent-child relationships
- **Color-coded branches** for different categories
- **Professional icons** representing each category
- Example: LLM taxonomy → Open-source vs Closed-source → Specific models

## 2. **Pipeline/Workflow Diagram**
Applicable for: Showing process flows, data pipelines
- **Left-to-right or top-to-bottom flow**
- **Rounded rectangles** for process steps
- **Arrows with labels** showing data/control flow
- **Professional icons** inside boxes representing operations

## 3. **Architecture Diagram**
Applicable for: System architectures, model structures
- **Layered/stacked design** showing components
- **Modular blocks** with clear boundaries
- **Connection lines** showing interactions
- **Consistent color fills** for component distinction

## 4. **Comparison Matrix**
Applicable for: Comparing multiple methods/approaches
- **Grid layout** with clear rows and columns
- **Icons or checkmarks** for features
- **Color intensity** showing performance levels

## 5. **Concept Map/Framework**
Applicable for: Abstract concepts, theoretical frameworks
- **Central concept** with radiating connections
- **Grouped clusters** for related ideas
- **Varying node sizes** for importance indication

## 6. **Timeline/Evolution Diagram**
Applicable for: Historical development, version evolution
- **Horizontal timeline** with milestones
- **Branching paths** for parallel developments
- **Professional icons** for key events

# Output Format
Output ONLY the schema within the markers. Be DETAILED and SPECIFIC.

---BEGIN PROMPT---

[FIGURE METADATA]
*   **Type**: [Taxonomy / Pipeline / Architecture / Comparison / Concept Map / Timeline / Hybrid]
*   **Layout**: [Hierarchical / Linear Flow / Layered / Grid / Radial / Timeline]
*   **Aspect Ratio**: [16:9 / 4:3 / 1:1 / Custom]
*   **Complexity Level**: [Simple / Medium / Complex]

[VISUAL STYLE]
*   **Overall Aesthetic**: [Technical minimalist / Scientific precise / Academic professional]
*   **Background**:
    *   Type: **PURE WHITE (#FFFFFF)** (MANDATORY - clean white background)
    *   The figure must have a pure white background to integrate seamlessly with any document
*   **Color Palette**:
    *   Primary: [Main color for key elements - e.g., "#2563eb" (Professional Blue)]
    *   Secondary: [Supporting color - e.g., "#059669" (Academic Green)]
    *   Accent: [Highlight color - e.g., "#ea580c" (Emphasis Orange)]
    *   Neutral: [For text/borders - e.g., "#374151" (Dark gray)]
*   **Icon Style**: [Flat filled / Line icons / Monochrome - consistent throughout]
*   **Effects**: [Subtle shadows for depth / Clean flat design - NO glassmorphism, NO heavy gradients]

[MAIN COMPONENTS]
For each component, specify:
*   **ID**: [Unique identifier]
*   **Label**: "[Exact text to display]"
*   **Type**: [Box / Rounded box / Circle / Diamond / Icon-box / Card]
*   **Position**: [Describe relative position]
*   **Size**: [Small / Medium / Large / XL]
*   **Visual Style**:
    *   Fill: [Color or gradient]
    *   Border: [Color, thickness]
    *   Shadow: [Yes/No, intensity]
*   **Icon**: [Icon name if applicable - e.g., "brain", "gear", "cloud", "document"]
*   **Sub-elements**: [Any nested content]

Component 1:
*   ID: main_title
*   Label: "[Title Text]"
*   Type: [Type]
*   Position: [Position]
*   Size: Large
*   Visual Style: [Describe]
*   Icon: [If any]

Component 2:
*   ID: [id]
*   Label: "[Label Text]"
*   ...

(Continue for all components - be thorough!)

[CONNECTIONS/FLOW]
*   **Arrow Style**: [Solid / Dashed / Gradient / Animated-look]
*   **Arrow Heads**: [Standard / Rounded / None]
*   **Line Weight**: [Thin / Medium / Thick]

*   Connection 1: From [Component ID] to [Component ID]
    *   Style: [Style]
    *   Label: "[Optional label]"
    *   Color: [Color]

(Continue for all connections)

[GROUPINGS/SECTIONS]
If components should be visually grouped:
*   Group 1: 
    *   Name: "[Group Label]"
    *   Contains: [Component IDs]
    *   Background: [Color/style for group background]
    *   Border: [Style]

[ANNOTATIONS]
*   Any additional labels, legends, or notes
*   Position and style for each

[SPECIAL INSTRUCTIONS]
*   **MANDATORY: Generate with PURE WHITE BACKGROUND (#FFFFFF)** - clean white, no dark backgrounds, no gradients
*   All figure elements should be rendered on a clean white canvas
*   Ensure high detail and precision in all visual elements
*   Use clean, sharp edges for all shapes and icons
*   Maintain consistent line weights throughout
*   Text must be crisp, readable, and properly positioned

---END PROMPT---

# Input Data
## Survey Topic
{survey_topic}

## Section Title
{section_title}

## Image Description
{description}

## Key Elements
{key_elements}

## Section Content
{section_content}
{improvement_instruction}

# Technical Requirements
- **MANDATORY: Pure white background (#FFFFFF)** - the figure must have a clean white background
- Create a figure that meets publication standards for Nature/Science/IEEE
- Prioritize technical accuracy over decorative elements
- Use consistent and professional visual language throughout
- Ensure all elements are precisely positioned and aligned
- The figure should communicate information clearly and efficiently
- Include sufficient detail to convey complex concepts accurately
- Avoid subjective or emotional language in labels and annotations