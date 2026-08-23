"""
Extract Survey Outlines from SOTA Papers
=========================================

This script uses LLM to extract outline structures from high-quality survey papers
to create few-shot examples for improving outline generation prompts.
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# PDF text extraction
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("Warning: PyMuPDF not installed. Install with: pip install pymupdf")

from src.models.LLM.ChatAgent import ChatAgent
from src.configs.config import ADVANCED_CHATAGENT_MODEL

# PDF directory
PDF_DIR = Path(r"C:\Users\admin\Desktop\References")

# Output directory
OUTPUT_DIR = project_root / "mekg" / "scripts" / "tools" / "extracted_outlines"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Extraction prompt
EXTRACTION_PROMPT = """You are an expert at analyzing academic survey papers. 

I will provide you with a PDF survey paper. Your task is to extract its **complete hierarchical outline structure** in a structured JSON format.

## Requirements:

1. **Extract ALL sections and subsections** from the paper, including:
   - Main sections (e.g., "1. Introduction", "2. Background")
   - Subsections (e.g., "2.1 Problem Definition", "2.2 Related Work")
   - Sub-subsections if present (e.g., "2.2.1 Traditional Methods")

2. **For each section, provide:**
   - `number`: The section number (e.g., "1", "2.1", "2.1.1")
   - `title`: The exact section title from the paper
   - `description`: A brief summary of what this section covers (30-80 words)
   - `subsections`: Array of child sections (if any)

3. **Analyze the logical structure:**
   - What is the overall organization pattern?
   - How does the paper transition between sections?
   - What makes this outline effective for a survey?

## Output Format (JSON):

```json
{
  "paper_title": "Full title of the paper",
  "paper_topic": "Main topic/domain of the survey",
  "total_sections": <number of main sections>,
  "outline_pattern": "Description of the organizational pattern used",
  "sections": [
    {
      "number": "1",
      "title": "Introduction",
      "description": "Brief description of section content",
      "subsections": [
        {
          "number": "1.1",
          "title": "Subsection Title",
          "description": "Brief description",
          "subsections": []
        }
      ]
    }
  ],
  "structural_insights": {
    "organization_logic": "How the paper organizes its content",
    "transition_strategy": "How sections connect to each other",
    "depth_analysis": "Analysis of section depth and balance",
    "key_strengths": ["List of what makes this outline effective"]
  }
}
```

Please analyze the provided PDF and extract the complete outline structure.
"""


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 50) -> str:
    """Extract text from PDF using PyMuPDF."""
    if not HAS_PYMUPDF:
        raise ImportError("PyMuPDF is required. Install with: pip install pymupdf")
    
    doc = fitz.open(pdf_path)
    text_parts = []
    
    # Extract text from each page (limit to first max_pages pages)
    for page_num in range(min(len(doc), max_pages)):
        page = doc[page_num]
        text = page.get_text()
        text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
    
    doc.close()
    
    full_text = "\n\n".join(text_parts)
    
    # Truncate if too long (keep first ~80000 chars to leave room for prompt)
    if len(full_text) > 80000:
        full_text = full_text[:80000] + "\n\n[... truncated ...]"
    
    return full_text


def extract_outline_from_pdf(pdf_path: Path, chat_agent: ChatAgent) -> dict:
    """Extract outline from a single PDF using LLM."""
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path.name}")
    print(f"{'='*60}")
    
    try:
        # Extract text from PDF
        print("  Extracting text from PDF...")
        pdf_text = extract_text_from_pdf(pdf_path)
        print(f"  Extracted {len(pdf_text)} characters")
        
        prompt = f"""{EXTRACTION_PROMPT}

## Paper Content (extracted from PDF):

{pdf_text}

Please analyze this paper and extract the complete outline structure as specified above.
Output only the JSON, no additional text.
"""
        
        # Call LLM
        print("  Calling LLM for outline extraction...")
        response = chat_agent.remote_chat(
            text_content=prompt,
            temperature=0.3,
            timeout=300,  # 5 minutes timeout for large content
            model=ADVANCED_CHATAGENT_MODEL
        )
        
        # Parse JSON response
        # Try to extract JSON from response
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{[\s\S]*"sections"[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response
        
        result = json.loads(json_str)
        result["source_file"] = pdf_path.name
        result["extraction_time"] = datetime.now().isoformat()
        
        print(f"✓ Successfully extracted outline: {result.get('paper_title', 'Unknown')[:50]}...")
        print(f"  - Main sections: {result.get('total_sections', 'N/A')}")
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"✗ JSON parsing error: {e}")
        print(f"  Raw response (first 500 chars): {response[:500]}...")
        return {
            "source_file": pdf_path.name,
            "error": f"JSON parsing error: {str(e)}",
            "raw_response": response[:2000]
        }
    except Exception as e:
        print(f"✗ Error processing {pdf_path.name}: {e}")
        return {
            "source_file": pdf_path.name,
            "error": str(e)
        }


def main():
    """Main function to extract outlines from all PDFs."""
    print("="*60)
    print("SOTA Survey Outline Extractor")
    print("="*60)
    
    # Initialize ChatAgent
    print("\nInitializing ChatAgent...")
    chat_agent = ChatAgent()
    
    # Find all PDFs
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    print(f"\nFound {len(pdf_files)} PDF files in {PDF_DIR}")
    
    if not pdf_files:
        print("No PDF files found!")
        return
    
    # Extract outlines from each PDF
    all_outlines = []
    for pdf_path in pdf_files:
        outline = extract_outline_from_pdf(pdf_path, chat_agent)
        all_outlines.append(outline)
        
        # Save individual outline
        output_file = OUTPUT_DIR / f"{pdf_path.stem}_outline.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(outline, f, ensure_ascii=False, indent=2)
        print(f"  Saved to: {output_file}")
    
    # Save combined outlines
    combined_output = OUTPUT_DIR / "all_outlines_combined.json"
    with open(combined_output, 'w', encoding='utf-8') as f:
        json.dump({
            "extraction_time": datetime.now().isoformat(),
            "total_papers": len(all_outlines),
            "outlines": all_outlines
        }, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Combined outlines saved to: {combined_output}")
    
    # Generate few-shot examples summary
    generate_fewshot_summary(all_outlines)
    
    print("\n" + "="*60)
    print("Extraction Complete!")
    print("="*60)


def generate_fewshot_summary(outlines: list):
    """Generate a summary of outlines suitable for few-shot prompting."""
    
    summary = {
        "purpose": "Few-shot examples for survey outline generation",
        "generated_at": datetime.now().isoformat(),
        "examples": []
    }
    
    for outline in outlines:
        if "error" in outline:
            continue
            
        example = {
            "paper_title": outline.get("paper_title", "Unknown"),
            "topic": outline.get("paper_topic", "Unknown"),
            "outline_pattern": outline.get("outline_pattern", ""),
            "section_titles": [],
            "structural_insights": outline.get("structural_insights", {})
        }
        
        # Extract section titles hierarchy
        def extract_titles(sections, prefix=""):
            titles = []
            for sec in sections:
                title = f"{sec.get('number', '')}. {sec.get('title', '')}"
                titles.append(title)
                if sec.get("subsections"):
                    titles.extend(extract_titles(sec["subsections"], "  "))
            return titles
        
        if outline.get("sections"):
            example["section_titles"] = extract_titles(outline["sections"])
        
        summary["examples"].append(example)
    
    # Save summary
    summary_file = OUTPUT_DIR / "fewshot_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Few-shot summary saved to: {summary_file}")


if __name__ == "__main__":
    main()