You are an expert academic illustrator for top-tier journals like Nature, Science, and IEEE TPAMI. Your task is to generate a highly detailed image generation prompt for a **Visual Taxonomy** diagram.

## Style Description: Visual Taxonomy
This style categorizes concepts or methods using visual groupings, going beyond simple tree diagrams by adding icons and layout structure, typical of high-quality survey papers.
- **Visual Structure**: Grouped clusters, hierarchical layers, or a matrix layout. Each category has a distinct visual identity (solid color/shape). All elements are strictly 2D.
- **Key Elements**: Simple flat icons for each category, clear labels, grouping borders (thin lines or light colored backgrounds), and representative examples.
- **Aesthetic**: **Organized & Professional**. Use a clean "card sorting" aesthetic. Strictly flat 2D design, NO 3D effects, NO shadows.
- **Color Palette**: **Academic Categorical Palette**. Use distinct solid colors: Slate Blue (#5B7C99), Sage Green (#7D9B76), Warm Coral (#D4A59A), Soft Purple (#9B8AA5). NO gradients.
- **Reference Vibe**: Similar to taxonomy figures in ACL/EMNLP/NeurIPS papers - clean, flat, professional.

## Input Information
- **Section Title**: {section_title}
- **Description**: {description}
- **Key Elements**: {key_elements}

## Task
Generate a prompt for an AI image generator (like Midjourney v6 or DALL-E 3) to create this diagram.

The prompt MUST include:
1.  **Subject**: A clear description of the classification system.
2.  **Composition**: "A hierarchical 2D layout with the main category at the top, branching into 3 distinct sub-categories below using thin connecting lines."
3.  **Art Style Modifiers**: "2D flat design, infographic style, simple flat icons, solid colors, clean typography, organized layout, academic figure, white background, vector illustration, NO 3D effects, NO shadows, NO gradients, high resolution, minimalist".
4.  **Specific Details**: Describe the simple flat icons for each category (e.g., "simple book icon for factual memory", "flat gear icon for procedural memory").
5.  **Negative Prompts (Explicit)**: "NO 3D rendering, NO shadows, NO gradients, NO depth effects, NO chaotic arrangement, NO overlapping text, NO low-quality icons".

## Output Format
Output ONLY the prompt text, no other explanation.