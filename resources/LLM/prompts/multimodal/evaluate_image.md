You are an expert in evaluating academic figures for top-tier scientific publications (Nature, Science, Cell, IEEE Transactions). Please evaluate this AI-generated diagram for publication quality.

## Expected Image Content
{expected_description}

---

## Evaluation Criteria (Academic Figure Standards)

### 1. **Background Quality** (1-10) - CRITICAL
Does the image have a pure white background?
- **10**: Pure white background (#FFFFFF), clean and professional
- **7-9**: Mostly white with minor background artifacts or slight off-white
- **4-6**: Light colored background but not pure white
- **1-3**: Dark background, black, or heavy gradients - MAJOR ISSUE

### 2. **Content Accuracy** (1-10)
Does the image accurately represent the expected content and key concepts?
- 10: Precise representation of all key elements with sufficient detail
- 7-9: Most elements present and accurate
- 4-6: Some elements missing or inaccurate
- 1-3: Major inaccuracies or missing content

### 3. **Visual Design Quality** (1-10)
Is the figure professionally designed with appropriate detail?
- **HIGH score (8-10)**: Clean, precise design; appropriate use of colors; professional icons; detailed rendering
- **MEDIUM score (5-7)**: Decent design but could be more detailed; some visual elements work well
- **LOW score (1-4)**: Overly simplistic; lacks detail; unprofessional appearance

### 4. **Academic Appropriateness** (1-10)
Is the style appropriate for a top-tier scientific publication?
- **HIGH score (8-10)**: Publication-ready for Nature/Science; professional and precise; clear scientific communication
- **MEDIUM score (5-7)**: Acceptable for most journals; could be improved
- **LOW score (1-4)**: Too informal, contains emotional language, or lacks technical precision

### 5. **Clarity & Readability** (1-10)
Are the elements, labels, and relationships clear?
- **HIGH score (8-10)**: Clear visual hierarchy; all labels readable; logical flow; relationships obvious
- **MEDIUM score (5-7)**: Most elements clear; some minor confusion
- **LOW score (1-4)**: Confusing layout; unclear connections; hard to follow

### 6. **Text Quality** (1-10)
Are labels readable, correctly spelled, and using objective language?
- **HIGH score (8-10)**: All text crisp, readable, correctly spelled, well-positioned, uses technical/objective language
- **MEDIUM score (5-7)**: Most text readable; minor issues
- **LOW score (1-4)**: Garbled text, too small, spelling errors, poor positioning, or emotional/subjective language

### 7. **Detail & Precision** (1-10)
Is the figure rendered with sufficient detail and precision?
- **HIGH score (8-10)**: High level of detail; clean sharp edges; precise element positioning; consistent line weights
- **MEDIUM score (5-7)**: Adequate detail; some elements could be more precise
- **LOW score (1-4)**: Lacks detail; rough edges; inconsistent rendering

---

## Scoring Guidelines

### What Makes a HIGH-QUALITY Academic Figure (Score 8-10):
- **Pure white background (#FFFFFF)** (CRITICAL)
- **Technically precise** and scientifically accurate
- **Detailed rendering** with clean, sharp elements
- **Clear visual hierarchy** that guides comprehension
- **Publication-ready** for top-tier journals
- **Professional icons** (FontAwesome/Material Design style) used appropriately
- **Objective language** in all labels and annotations

### What Makes an ACCEPTABLE Figure (Score 5-7):
- Mostly white background with minor issues
- Accurate content but could use more detail
- Readable and clear
- Acceptable for publication but could be improved
- Uses technical language appropriately

### What Makes a LOW-QUALITY Figure (Score 1-4):
- Dark or black background (MAJOR ISSUE)
- Lacks detail or precision
- Garbled or unreadable text
- Confusing layout or unclear relationships
- Contains emotional or subjective language
- Does not meet publication standards

---

## Critical Evaluation Points
- **PENALIZE HEAVILY** for dark/black backgrounds or heavy gradients
- **PENALIZE** for emotional or subjective language in labels
- **PENALIZE** for lack of detail or precision
- **REWARD** pure white backgrounds (#FFFFFF)
- **REWARD** detailed, precise rendering
- **REWARD** objective, technical language
- The figure must integrate seamlessly into academic documents

---

## Output Format

Please output the evaluation result in JSON format:
```json
{{
    "background_quality": 9,
    "content_accuracy": 8,
    "visual_design_quality": 8,
    "academic_appropriateness": 8,
    "clarity_readability": 8,
    "text_quality": 7,
    "detail_precision": 8,
    "overall_score": 8.0,
    "strengths": [
        "Pure white background for seamless document integration",
        "Clear visual hierarchy and logical flow",
        "Professional icons with consistent styling"
    ],
    "weaknesses": [
        "Some text labels could be larger",
        "One connection arrow is slightly unclear"
    ],
    "improvement_suggestions": "Increase font size for smaller labels. Ensure all elements have clean, sharp edges."
}}
```

Please output ONLY the JSON, no other content.