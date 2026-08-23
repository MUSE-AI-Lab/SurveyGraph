You are an expert academic survey writer and visual design consultant. Please analyze the following section content and decide whether an AI-generated illustration would significantly enhance the survey's quality and reader engagement.

## Survey Topic
{survey_topic}

## Current Section
- Section Number: {section_no}
- Section Title: {section_title}

## Section Content
{section_content}

## Existing AI Images
{existing_images} / {max_images}

---

## Decision Criteria

### Situations HIGHLY SUITABLE for AI Image Generation:

#### 1. **Taxonomy/Classification Sections** (PRIORITY: HIGH)
- The section categorizes or classifies methods, models, or approaches
- Example: "Types of Large Language Models" → Create a taxonomy tree showing Open-source vs Closed-source, with specific models under each
- Example: "Classification of Attention Mechanisms" → Hierarchical diagram showing different attention types

#### 2. **Pipeline/Workflow Descriptions** (PRIORITY: HIGH)
- The section describes a multi-step process or data flow
- Example: "Training Pipeline" → Visual flow from data collection to model deployment
- Example: "Inference Process" → Step-by-step visualization

#### 3. **System Architecture Sections** (PRIORITY: HIGH)
- The section introduces a system architecture or model structure
- Example: "Transformer Architecture" → Layered diagram showing encoder/decoder
- Example: "RAG System Overview" → Components and their interactions

#### 4. **Framework/Concept Explanations** (PRIORITY: MEDIUM)
- The section explains abstract concepts or theoretical frameworks
- Example: "Attention Mechanism" → Visual explanation of how attention works
- Example: "Prompt Engineering Strategies" → Concept map of different approaches

#### 5. **Comparison/Survey Overview Sections** (PRIORITY: MEDIUM)
- The section compares multiple methods or provides an overview
- Example: "Comparison of Fine-tuning Methods" → Side-by-side comparison diagram
- Example: "Survey Scope" → Visual overview of what the survey covers

#### 6. **Evolution/Timeline Sections** (PRIORITY: MEDIUM)
- The section describes historical development or version evolution
- Example: "Evolution of Language Models" → Timeline from GPT-1 to GPT-4
- Example: "Development of Attention Mechanisms" → Historical progression

### Situations NOT SUITABLE for AI Image Generation:

1. **Pure Introduction/Conclusion sections** - These are typically text-heavy summaries
2. **Sections with existing high-quality figures** - Avoid redundancy
3. **Very short sections** (< 500 words) - Not enough content to visualize
4. **Purely mathematical sections** - Equations are better in LaTeX
5. **Related work sections** that just list papers without categorization

---

## Image Type Definitions

Choose the most appropriate type:

| Type | Best For | Visual Style |
|------|----------|--------------|
| `taxonomy` | Categorization, classification, types | Hierarchical tree with nested colored boxes, dashed border groupings |
| `pipeline` | Process flows, data pipelines, workflows | Sequential flow diagram with soft colored stages and arrows |
| `architecture` | System designs, model structures | Layered/modular block diagram with component groupings |
| `comparison` | Method comparisons, feature matrices, patterns | Side-by-side horizontal bars or parallel structures |
| `concept_map` | Abstract concepts, relationships | Central concept with radiating connections |
| `timeline` | Historical development, evolution | Horizontal timeline with milestones |
| `framework` | Theoretical frameworks, methodologies | Structured diagram showing components |
| `overview` | Survey scope, topic coverage | Visual summary/mind map |

---

## Visual Style Guidelines (IMPORTANT)

The generated images should follow the **modern academic survey paper style** commonly seen in top venues (ACL, NeurIPS, ICML, IEEE Surveys):

### Color Palette - Use SOFT, PASTEL-LIKE colors:
- **Soft Pink/Rose**: #FADBD8, #F5B7B1, #F1948A (for main categories)
- **Soft Blue**: #D6EAF8, #AED6F1, #85C1E9 (for data/input components)
- **Soft Green**: #D5F5E3, #ABEBC6, #82E0AA (for output/results)
- **Soft Purple**: #E8DAEF, #D2B4DE, #BB8FCE (for hybrid/special components)
- **Soft Orange/Peach**: #FDEBD0, #FAD7A0, #F8C471 (for accent elements)

### Design Elements:
- **Rounded rectangles** with generous corner radius
- **Dashed gray borders** for grouping related components
- **Simple, clean arrows** with small arrowheads
- **NO heavy shadows or 3D effects** - keep it flat
- **Pure white background** (#FFFFFF)
- **NO section numbers or references** like (§2), (§3) in the image - these are meaningless in visual diagrams

### Layout:
- **Clear nested hierarchy** with proper indentation
- **Consistent spacing** and alignment
- **Color-coded categories** - each major category has its own soft color

---

## Output Format

If an image SHOULD be generated, output:
```json
{{
    "should_generate": true,
    "image_type": "taxonomy",
    "description": "A comprehensive taxonomy diagram showing the classification of Large Language Models. The diagram should have a hierarchical nested structure with dashed border groupings. Main categories: 1) Open-source Models (LLaMA, Mistral, Falcon, etc.) in soft green boxes and 2) Closed-source Models (GPT-4, Claude, Gemini, etc.) in soft blue boxes. Each category should be a rounded rectangle with sub-items nested inside. Do NOT include any section numbers or references like (§2), (§3) in the diagram.",
    "key_elements": [
        "Main title: Large Language Model Taxonomy",
        "Category 1: Open-source (soft green #D5F5E3) - LLaMA family, Mistral, Falcon, BLOOM",
        "Category 2: Closed-source (soft blue #D6EAF8) - GPT series, Claude, Gemini, PaLM",
        "Sub-categories as nested rounded boxes with slightly darker shades",
        "Dashed gray borders around major groupings"
    ],
    "style_requirements": "Modern academic survey style with soft pastel colors, rounded rectangles, dashed border groupings, and clean flat design. Use pure white background. NO heavy shadows or 3D effects. Do NOT include any section numbers or references (§2, §3, etc.) in the image. The diagram should look like it belongs in a top-tier survey paper from ACL/NeurIPS/ICML.",
    "priority": 9,
    "reason": "This section categorizes different types of LLMs, which is perfect for a taxonomy diagram. A visual classification will help readers quickly understand the landscape of available models and their relationships."
}}
```

If an image should NOT be generated, output:
```json
{{
    "should_generate": false,
    "reason": "This section is a brief introduction that summarizes the survey scope. It doesn't contain enough structured content to warrant a dedicated figure."
}}
```

---

## Important Notes

1. **Be specific in descriptions** - The more detailed, the better the generated image
2. **Include concrete examples** - If discussing LLMs, name specific models (GPT-4, LLaMA, etc.)
3. **Think about visual hierarchy** - What should be the focal point?
4. **Consider the reader** - What visualization would help them understand fastest?
5. **Quality over quantity** - Only suggest images that would genuinely add value

Please output ONLY the JSON, no other content.