# Figure Insertion Decision Prompt

You are an expert academic survey writer. Please decide whether the following figure should be inserted into the survey.

## Survey Topic
{survey_topic}

## Survey Outline
{outline}

## Figure Analysis Results
- **Description**: {description}
- **Figure Type**: {image_type}
- **Key Concepts**: {key_concepts}
- **Relevance Score**: {relevance_score}/10
- **Quality Score**: {quality_score}/10
- **Academic Value**: {academic_value}/10
- **Suggested Section Types**: {suggested_sections}
- **Analysis Reasoning**: {reason}

## Decision Task

Please decide:
1. Should this figure be inserted into the survey?
2. If yes, which specific section should it be inserted into? (Provide section number, e.g., "3.2")
3. Generate an academic-style English caption for this figure (Figure X: ...)
4. Generate a brief English description (1-2 sentences) explaining what this figure shows and its relevance to the survey

## Decision Criteria

### Figures that SHOULD be inserted:
- Core architecture diagrams that explain the main methodology
- Key experimental results that support important conclusions
- Comparison tables/charts that help readers understand differences between methods
- Flowcharts that clarify complex processes
- Figures with high academic value (score >= 7)

### Figures that should NOT be inserted:
- Low quality or blurry images
- Figures not directly related to the survey topic
- Redundant figures (similar to already inserted ones)
- Screenshots or photos without academic value
- Figures with low relevance score (< 5)

### Placement Guidelines:
- Architecture diagrams → Methodology or Architecture sections
- Experimental results → Experiments or Analysis sections
- Comparison charts → Related sections being compared
- Conceptual illustrations → Background or Introduction sections
- Avoid inserting more than 2 figures per section

## Output Format

If the figure SHOULD be inserted:
```json
{
    "should_insert": true,
    "target_section": "3.2",
    "caption": "Figure X: Overview of the proposed transformer architecture showing the encoder-decoder structure with multi-head attention mechanisms.",
    "description": "This figure illustrates the overall architecture of the model, clearly showing the key components including the encoder layers, decoder layers, and attention mechanisms. It provides readers with an intuitive understanding of the model structure.",
    "confidence": 0.85,
    "reason": "This is a high-quality architecture diagram that clearly explains the model structure and is highly relevant to the methodology section of the survey."
}
```

If the figure should NOT be inserted:
```json
{
    "should_insert": false,
    "reason": "The figure quality is too low (blurry) and the content is not directly related to the main topic of the survey."
}
```

Please output only JSON, without any other content.