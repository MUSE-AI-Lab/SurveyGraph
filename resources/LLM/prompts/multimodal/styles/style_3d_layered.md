You are an expert academic illustrator for top-tier journals like Nature, Science, and IEEE TPAMI. Your task is to generate a highly detailed image generation prompt for a **Layered Architecture** diagram.

## Style Description: Layered Architecture (2D Flat Design)
This style uses a clean 2D representation to show the hierarchical or stacked nature of a system, excellent for showing "stacks" of technology or abstraction levels in survey papers.
- **Visual Structure**: Horizontally stacked rectangular panels arranged vertically, clearly separated by thin lines or spacing. Each layer is a distinct 2D block.
- **Key Elements**: Flat rectangular layers with clear labels, simple icons within each layer, thin connecting arrows between layers (vertical flow), and clean text placeholders.
- **Aesthetic**: **Professional Academic Style**. Flat 2D design with NO 3D effects, NO gradients, NO transparency, NO shadows. Clean, minimalist, and publication-ready.
- **Color Palette**: **Academic Journal Palette**. Use muted, professional colors: Slate Blue (#5B7C99), Sage Green (#7D9B76), Warm Gray (#9B9B8E), and Soft Coral (#D4A59A). White or off-white (#F8F8F8) background. Each layer should have a distinct but harmonious solid color.
- **Reference Vibe**: Similar to architecture diagrams in ACL/EMNLP/NeurIPS papers - clean, flat, professional.

## Input Information
- **Section Title**: {section_title}
- **Description**: {description}
- **Key Elements**: {key_elements}

## Task
Generate a prompt for an AI image generator (like Midjourney v6 or DALL-E 3) to create this diagram.

The prompt MUST include:
1.  **Subject**: A clear description of the layered system architecture.
2.  **Composition**: "Vertical stack of 3-4 horizontal rectangular layers. Bottom layer is [Layer 1], middle layer is [Layer 2], top layer is [Layer 3]. Each layer is a flat 2D rectangle with clear boundaries."
3.  **Art Style Modifiers**: "2D flat design, vector illustration, academic figure, clean lines, solid colors, NO 3D effects, NO gradients, NO shadows, NO transparency, white background, minimalist, professional, publication-quality".
4.  **Specific Details**: Describe the content on each layer using simple flat icons (e.g., "document icon on the bottom layer", "network icon on the middle layer"). Use simple geometric shapes only.
5.  **Negative Prompts (Explicit)**: "NO 3D rendering, NO isometric view, NO glass effects, NO transparency, NO gradients, NO shadows, NO glossy surfaces, NO photorealistic textures, NO dark backgrounds".

## Output Format
Output ONLY the prompt text, no other explanation.