# Figure Analysis Prompt

You are an expert academic paper figure analyst. Please carefully analyze this figure from an academic paper.

## Analysis Tasks

Please provide the following information:

### 1. Figure Description (description)
Provide a detailed description of the figure content, including:
- What is being displayed
- Key components and their relationships
- Important labels or annotations
- Overall structure and layout

### 2. Figure Type (image_type)
Select the most appropriate type from the following:
- **architecture**: System/model architecture diagram
- **flowchart**: Process flow, pipeline, or workflow diagram
- **experiment**: Experimental results (line charts, bar charts, scatter plots, etc.)
- **comparison**: Comparison charts or tables
- **illustration**: Conceptual illustration or explanatory diagram
- **screenshot**: Interface screenshot
- **diagram**: Other types of diagrams
- **other**: Other types

### 3. Key Concepts (key_concepts)
List 3-5 key technical concepts or terms shown in the figure.

### 4. Relevance Score (relevance_score)
Rate from 1-10 how important this figure is for understanding the paper's core content:
- **10**: Core architecture diagram or key experimental results
- **7-9**: Important method explanation or comparative analysis
- **4-6**: Supplementary illustration
- **1-3**: Decorative or less relevant figure

### 5. Quality Score (quality_score)
Rate from 1-10 the clarity, professionalism, and readability of the figure:
- **10**: Very clear, professional, and easy to read
- **7-9**: Clear and fairly professional
- **4-6**: Average
- **1-3**: Blurry or difficult to understand

### 6. Academic Value (academic_value)
Rate from 1-10 the value of this figure in an academic survey:
- Consider: Does it help readers understand concepts? Is it representative? Is it suitable for citation?

### 7. Suggested Sections (suggested_sections)
Which type of survey section would this figure be suitable for? (Multiple selections allowed):
- **introduction**: Introduction
- **background**: Background knowledge
- **methodology**: Methodology
- **architecture**: Architecture design
- **experiment**: Experimental analysis
- **analysis**: In-depth analysis
- **discussion**: Discussion
- **application**: Application scenarios

### 8. Suitability (is_suitable)
Is this figure suitable for insertion into an academic survey? (true/false)

### 9. Reasoning (reason)
Briefly explain why this figure is or is not suitable for insertion into a survey.

## Context Information
{context}

## Output Format
Please output in JSON format, ensuring it can be correctly parsed:
```json
{
    "description": "Figure description",
    "image_type": "type",
    "key_concepts": ["concept1", "concept2", "concept3"],
    "relevance_score": 8,
    "quality_score": 7,
    "academic_value": 8,
    "suggested_sections": ["methodology", "architecture"],
    "is_suitable": true,
    "reason": "Reasoning"
}
```

Please output only JSON, without any other content.