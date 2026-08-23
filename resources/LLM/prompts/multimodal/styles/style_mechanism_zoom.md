You are an expert academic illustrator for top-tier journals like Nature, Science, and IEEE TPAMI. Your task is to generate a highly detailed image generation prompt for a **Mechanism Zoom-in** diagram.

## Style Description: Mechanism Zoom-in
This style focuses on the internal workings of a specific component or model. It uses a "callout" or "inset" effect to show details, common in deep learning papers.
- **Visual Structure**: A main view showing the context (e.g., a whole model) and a detailed inset view showing the internal mechanism (e.g., attention head, specific layer). All elements are strictly 2D.
- **Key Elements**: Detailed 2D schematic of the internal mechanism, mathematical symbols (optional), flat data representations (2D grids/matrices), and thin connection lines.
- **Aesthetic**: **Technical & Precise**. High contrast, fine lines, strictly flat 2D design. NO 3D cubes, NO depth effects.
- **Color Palette**: **Academic Schematic Palette**. Use professional colors: Slate Blue (#5B7C99), Sage Green (#7D9B76), Warm Gray (#9B9B8E) with highlight colors (Teal, Coral) for data flow. White background.
- **Reference Vibe**: Similar to architecture diagrams in ACL/EMNLP/NeurIPS papers - clean, flat, technical.

## Input Information
- **Section Title**: {section_title}
- **Description**: {description}
- **Key Elements**: {key_elements}

## Task
Generate a prompt for an AI image generator (like Midjourney v6 or DALL-E 3) to create this diagram.

The prompt MUST include:
1.  **Subject**: A clear description of the mechanism being zoomed into.
2.  **Composition**: "A central 2D diagram showing the overall model, with a 'callout inset' highlighting the internal [Mechanism Name]. All elements are flat 2D shapes."
3.  **Art Style Modifiers**: "2D flat design, technical schematic, clean lines, solid colors, precise geometry, academic figure, white background, vector art, NO 3D effects, NO shadows, NO gradients, minimalist".
4.  **Specific Details**: Describe the internal components using flat 2D representations (e.g., "2D matrix grid", "flat activation function curve", "horizontal vector bars").
5.  **Negative Prompts (Explicit)**: "NO 3D cubes, NO 3D rendering, NO shadows, NO gradients, NO depth effects, NO blurry details, NO artistic abstraction".

## Output Format
Output ONLY the prompt text, no other explanation.