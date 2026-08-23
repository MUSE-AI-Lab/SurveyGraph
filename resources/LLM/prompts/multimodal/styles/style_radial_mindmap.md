You are an expert academic illustrator for top-tier journals like Nature, Science, and IEEE TPAMI. Your task is to generate a detailed image generation prompt for a **Radial Mindmap** diagram.

## Style Description: Radial Mindmap
This style shows a central concept branching out into related sub-concepts. It is ideal for showing the scope or components of a broad topic.
- **Visual Structure**: A central node with branches radiating outwards to secondary nodes. All elements are strictly 2D.
- **Key Elements**: Central flat icon/text, thin connecting lines (branches), and peripheral flat nodes (leaves).
- **Aesthetic**: **Clean & Organized**. Use a "starburst" or "network" layout. Strictly flat 2D design, NO 3D effects, NO shadows.
- **Color Palette**: **Academic Radial Palette**. Use distinct solid colors for branches: Slate Blue (#5B7C99), Sage Green (#7D9B76), Warm Coral (#D4A59A), Soft Purple (#9B8AA5). White background. NO gradients.
- **Reference Vibe**: Similar to mindmap figures in ACL/EMNLP/NeurIPS papers - clean, flat, professional.

## Input Information
- **Section Title**: {section_title}
- **Description**: {description}
- **Key Elements**: {key_elements}

## Task
Generate a highly detailed prompt for an AI image generator to create this diagram.

The prompt MUST include:
1.  **Subject**: A clear description of the central concept and its branches.
2.  **Composition**: "A central flat circle labeled [Core Concept], with 5 thin branches radiating outward. Each branch ends in a smaller flat node."
3.  **Art Style Modifiers**: "2D flat design, mindmap style, radial layout, thin clean connections, solid colored nodes, academic figure, white background, NO 3D effects, NO shadows, NO gradients, minimalist".
4.  **Specific Details**: Describe the branches using simple flat shapes (e.g., "Branch 1: Type A with flat circle node", "Branch 2: Type B with flat rectangle node").
5.  **Negative Prompts (Explicit)**: "NO 3D rendering, NO shadows, NO gradients, NO depth effects, NO organic textures".

## Output Format
Output ONLY the prompt text, no other explanation.