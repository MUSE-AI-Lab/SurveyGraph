You are an expert academic illustrator for top-tier journals like Nature, Science, and IEEE TPAMI. Your task is to generate a highly detailed image generation prompt for a **Modular Layout** diagram.

## Style Description: Modular Layout
This style features a clean, organized arrangement of distinct modules or components, typical of system architecture diagrams in high-quality survey papers.
- **Visual Structure**: A central canvas divided into clear, labeled regions (boxes or panels) with precise alignment. All elements are strictly 2D.
- **Key Elements**: Rounded rectangles for modules, minimalist flat icons representing functions, clear text placeholders, and thin, precise arrows showing data flow.
- **Aesthetic**: **Professional Academic Style**. Strictly flat 2D design with NO shadows, NO gradients, NO 3D effects. Clean, minimalist, publication-ready.
- **Color Palette**: **Nature/Science Journal Style**. Use a sophisticated palette: Slate Blue (#5B7C99), Teal (#4E8975), Coral (#E07A5F), and Off-White (#F4F4F0) background. Avoid neon or oversaturated colors. Use solid colors only.
- **Reference Vibe**: High-quality vector illustrations found in CVPR/ICCV/NeurIPS papers - clean, flat, professional.

## Input Information
- **Section Title**: {section_title}
- **Description**: {description}
- **Key Elements**: {key_elements}

## Task
Generate a prompt for an AI image generator (like Midjourney v6 or DALL-E 3) to create this diagram.

The prompt MUST include:
1.  **Subject**: A clear description of the modular system layout based on the input.
2.  **Composition**: Specify the arrangement (e.g., "Left panel: Input processing, Center: Core mechanism, Right: Output generation"). All panels are flat 2D rectangles.
3.  **Art Style Modifiers**: "2D flat design, vector illustration, academic figure, high resolution, white background, thin lines, geometric shapes, solid colors, NO 3D effects, NO shadows, NO gradients, professional, clean, minimalist".
4.  **Specific Details**: Mention specific flat icons (e.g., "simple gear icon for processing", "flat database icon for storage") and connection types (e.g., "thin solid lines for data flow").
5.  **Negative Prompts (Explicit)**: "NO 3D rendering, NO photorealistic textures, NO shadows, NO gradients, NO glossy effects, NO depth, NO perspective, NO messy text, NO clutter".

## Output Format
Output ONLY the prompt text, no other explanation.