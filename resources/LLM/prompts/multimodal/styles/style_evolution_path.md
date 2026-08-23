You are an expert academic illustrator for top-tier journals like Nature, Science, and IEEE TPAMI. Your task is to generate a highly detailed image generation prompt for a **Evolution Path** diagram.

## Style Description: Evolution Path
This style shows the progression or evolution of a concept, method, or technology, emphasizing the "steps" or "generations" of development in a survey paper.
- **Visual Structure**: A linear horizontal path connecting distinct flat nodes (circles or rectangles). All elements are strictly 2D.
- **Key Elements**: Flat nodes representing key stages, thin connecting lines showing the flow, and labels indicating the progression (e.g., "Gen 1", "Gen 2").
- **Aesthetic**: **Clean & Connected**. Use a simple "network" layout. Strictly flat 2D design, NO 3D effects, NO shadows.
- **Color Palette**: **Academic Evolution Palette**. Use distinct solid colors for different stages: Slate Blue (#5B7C99), Sage Green (#7D9B76), Warm Coral (#D4A59A). NO gradients.
- **Reference Vibe**: Similar to evolution figures in ACL/EMNLP/NeurIPS papers - clean, flat, professional.

## Input Information
- **Section Title**: {section_title}
- **Description**: {description}
- **Key Elements**: {key_elements}

## Task
Generate a prompt for an AI image generator (like Midjourney v6 or DALL-E 3) to create this diagram.

The prompt MUST include:
1.  **Subject**: A clear description of the evolutionary path.
2.  **Composition**: "A horizontal sequence of 4 flat connected circles with thin connecting lines. All nodes are the same size, differentiated by color."
3.  **Art Style Modifiers**: "2D flat design, network diagram style, connected nodes, thin clean lines, solid colors, academic figure, white background, NO 3D effects, NO shadows, NO gradients, high contrast, vector art, minimalist".
4.  **Specific Details**: Describe the content of each flat node (e.g., "Node 1: Rule-based with simple icon", "Node 2: Learning-based with brain icon").
5.  **Negative Prompts (Explicit)**: "NO 3D rendering, NO shadows, NO gradients, NO depth effects, NO tangled lines, NO overlapping nodes, NO confusing direction".

## Output Format
Output ONLY the prompt text, no other explanation.