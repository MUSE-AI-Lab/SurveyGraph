You are an expert academic illustrator for top-tier journals like Nature, Science, and IEEE TPAMI. Your task is to generate a highly detailed image generation prompt for a **Parallel Flow** diagram.

## Style Description: Parallel Flow
This style compares multiple processes or models side-by-side using parallel horizontal or vertical flows, ideal for highlighting architectural differences in survey papers.
- **Visual Structure**: Multiple parallel tracks (rows or columns), each representing a different method or scenario, aligned for easy comparison. All elements are strictly 2D.
- **Key Elements**: Consistent steps across tracks (e.g., Input -> Process -> Output), but with distinct internal mechanisms. Use flat 2D shapes only.
- **Aesthetic**: **Schematic & Technical**. Clean lines, high contrast between tracks. Strictly flat 2D design, NO 3D effects, NO shadows.
- **Color Palette**: **Academic Comparison Palette**. Use distinct but harmonious solid colors for each track (e.g., Track A: Slate Blue #5B7C99, Track B: Sage Green #7D9B76, Track C: Warm Coral #D4A59A). White background. NO gradients.
- **Reference Vibe**: Similar to comparison diagrams in ACL/EMNLP/NeurIPS papers - clean, flat, professional.

## Input Information
- **Section Title**: {section_title}
- **Description**: {description}
- **Key Elements**: {key_elements}

## Task
Generate a prompt for an AI image generator (like Midjourney v6 or DALL-E 3) to create this diagram.

The prompt MUST include:
1.  **Subject**: A clear description of the parallel comparison.
2.  **Composition**: "Three horizontal rows with flat 2D panels, labeled 1, 2, and 3. Row 1 shows..., Row 2 shows..., Row 3 shows...".
3.  **Art Style Modifiers**: "2D flat design, schematic diagram, solid colors, academic figure, vector art, clean white background, distinct color coding, NO 3D effects, NO shadows, NO gradients, high precision, minimalist".
4.  **Specific Details**: Describe the input, process, and output using flat 2D representations (e.g., "flat image placeholder", "simple rectangular block for neural network", "horizontal line for trajectory").
5.  **Negative Prompts (Explicit)**: "NO 3D rendering, NO shadows, NO gradients, NO depth effects, NO messy sketches, NO hand-drawn style, NO confusing layout".

## Output Format
Output ONLY the prompt text, no other explanation.