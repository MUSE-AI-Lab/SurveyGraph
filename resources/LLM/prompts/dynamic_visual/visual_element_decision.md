# Visual Element Decision Prompt

You are an expert academic survey writer specializing in visual design. Your task is to analyze survey content and decide what visual elements would enhance the academic value and readability.

## Survey Information
- **Topic**: {survey_topic}
- **Section Number**: {section_no}
- **Section Title**: {section_title}

## Section Content
{section_content}

## Already Used Visual Elements
{existing_visuals}

## Available Reference Images from Papers
{reference_images_info}

## Visual Element Types Available

### 1. Reference Figure (reference_figure)
Use when: High-quality figures exist in reference papers that directly illustrate key concepts.
- Architecture diagrams from seminal papers
- Experimental results that are widely cited
- Framework illustrations that are authoritative

### 2. Comparison Table (comparison_table)
Use when: Multiple methods/models/approaches need to be compared.
Styles:
- **horizontal_comparison**: Methods as columns, features as rows
- **vertical_comparison**: Methods as rows, features as columns
- **matrix_comparison**: Full matrix with checkmarks/scores
- **feature_checklist**: Binary feature presence/absence

### 3. Summary Table (summary_table)
Use when: Need to summarize key information about a category of methods.
Styles:
- **categorized_summary**: Grouped by category
- **chronological_summary**: Ordered by time/year
- **hierarchical_summary**: Nested structure

### 4. Timeline (timeline)
Use when: Showing evolution, development history, or milestones.
Styles:
- **horizontal_timeline**: Left-to-right progression
- **vertical_timeline**: Top-to-bottom progression
- **milestone_timeline**: Key events highlighted

### 5. Taxonomy Tree (taxonomy_tree)
Use when: Showing classification, categorization, or hierarchical relationships.
Styles:
- **top_down_tree**: Root at top
- **left_right_tree**: Root at left
- **radial_tree**: Root at center
- **mindmap_style**: Organic branching

### 6. Flowchart (flowchart)
Use when: Showing process, workflow, or decision logic.
Styles:
- **linear_flow**: Sequential steps
- **branching_flow**: Decision points with branches
- **circular_flow**: Cyclic process

### 7. Architecture Diagram (architecture)
Use when: Showing system structure, model components, or pipeline.
Styles:
- **layered_architecture**: Stacked layers
- **component_diagram**: Connected components
- **pipeline_diagram**: Data/process flow

### 8. None (none)
Use when: Section is primarily textual and doesn't benefit from visuals.

## Decision Criteria

1. **Diversity**: Prefer element types not yet used in the survey
2. **Relevance**: Element must directly support the section content
3. **Academic Value**: Prioritize elements that enhance scholarly communication
4. **Moderation**: Maximum 1-2 elements per section
5. **Reference Priority**: If suitable reference images exist, prefer citing them

## Output Format

Return a JSON array with your decisions:
```json
[
    {
        "element_type": "comparison_table",
        "description": "Comparison of transformer-based models",
        "style_preference": "matrix_comparison",
        "data_requirements": {
            "columns": ["Model", "Parameters", "Training Data", "Key Innovation"],
            "rows": ["BERT", "GPT-3", "T5", "LLaMA"]
        },
        "reference_images": [],
        "priority": 8,
        "reason": "Section compares multiple models; table provides clear overview"
    }
]
```

Output ONLY the JSON array, no additional text.