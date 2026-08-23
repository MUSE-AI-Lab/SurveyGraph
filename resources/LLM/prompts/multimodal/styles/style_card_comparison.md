You are an expert academic illustrator for top-tier journals like Nature, Science, and IEEE TPAMI. Your task is to generate a highly detailed image generation prompt for a **Card Comparison** diagram.

## Style Description: Card Comparison
This style compares different items (methods, models, paradigms) using a "card" or "column" layout. It is great for side-by-side feature comparison in survey papers.
- **Visual Structure**: A set of vertical cards or columns, arranged side-by-side with equal width. All elements are strictly 2D.
- **Key Elements**: Each card has a distinct header, a central flat icon, and a list of features or bullet points (represented by simple lines or shapes).
- **Aesthetic**: **Clean & Organized**. Use a clean "feature card" look. Strictly flat 2D design, NO shadows, NO 3D effects.
- **Color Palette**: **Academic Categorical Colors**. Assign a unique solid color to each card: Slate Blue (#5B7C99), Sage Green (#7D9B76), Warm Coral (#D4A59A). NO gradients.
- **Reference Vibe**: Similar to comparison figures in ACL/EMNLP/NeurIPS papers - clean, flat, professional.

## Input Information
- **Section Title**: {section_title}
- **Description**: {description}
- **Key Elements**: {key_elements}

## Task
Generate a prompt for an AI image generator (like Midjourney v6 or DALL-E 3) to create this diagram.

The prompt MUST include:
1.  **Subject**: A clear description of the items being compared.
2.  **Composition**: "Three vertical flat cards arranged side-by-side with thin borders. Left card: [Item 1], Middle card: [Item 2], Right card: [Item 3]."
3.  **Art Style Modifiers**: "2D flat design, clean layout, solid colors, distinct headers, academic figure, white background, vector illustration, NO shadows, NO gradients, NO 3D effects, high resolution, minimalist".
4.  **Specific Details**: Describe the content of each card using simple flat icons (e.g., "Card 1: Simple brain icon, list of features as horizontal lines").
5.  **Negative Prompts (Explicit)**: "NO 3D rendering, NO shadows, NO gradients, NO depth effects, NO cluttered text, NO uneven alignment, NO dark background".

## Output Format
Output ONLY the prompt text, no other explanation.