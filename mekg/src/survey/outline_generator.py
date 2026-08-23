"""
MEKG Outline Generator
======================

Generate survey outlines based on MEKG knowledge graph, replacing traditional RAG approaches.

Core Strategy:
1. Use graph community structure to organize sections
2. Use core papers to determine key content
3. Use evolution paths to organize timeline
4. Use relationship types to enrich section descriptions
"""

from __future__ import annotations

import json
import re
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger
from tqdm import tqdm

# Async support
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.models.LLM.ChatAgent import ChatAgent
    HAS_CHAT_AGENT = True
except ImportError:
    HAS_CHAT_AGENT = False

try:
    from src.configs.config import MOUNT_PAPERS_WORKERS, ADVANCED_CHATAGENT_MODEL
except ImportError:
    MOUNT_PAPERS_WORKERS = 50  # Default value


@dataclass
class OutlineSection:
    """Outline section"""
    number: str  # Section number, e.g., "1", "1.1"
    title: str
    description: str
    level: int  # 1=main section, 2=subsection, 3=subsubsection
    paper_ids: List[str] = field(default_factory=list)  # Mounted paper IDs
    key_papers: List[str] = field(default_factory=list)  # Core paper IDs
    subsections: List['OutlineSection'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "number": self.number,
            "title": self.title,
            "description": self.description,
            "level": self.level,
            "paper_ids": self.paper_ids,
            "key_papers": self.key_papers,
            "subsections": [s.to_dict() for s in self.subsections],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'OutlineSection':
        return cls(
            number=data.get("number", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            level=data.get("level", 1),
            paper_ids=data.get("paper_ids", []),
            key_papers=data.get("key_papers", []),
            subsections=[cls.from_dict(s) for s in data.get("subsections", [])],
            metadata=data.get("metadata", {})
        )


@dataclass
class SurveyOutline:
    """Complete survey outline"""
    title: str
    topic: str
    sections: List[OutlineSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "topic": self.topic,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SurveyOutline':
        return cls(
            title=data.get("title", ""),
            topic=data.get("topic", ""),
            sections=[OutlineSection.from_dict(s) for s in data.get("sections", [])],
            metadata=data.get("metadata", {})
        )
    
    def save(self, path: Path):
        """Save outline to file"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> 'SurveyOutline':
        """Load outline from file"""
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_dict(json.load(f))
    
    def to_surveyx_format(self) -> Dict:
        """Convert to SurveyX format outline - supports three-level structure
        
        SurveyX Outlines class expects:
        - Main sections use "section title" and "description" keys
        - Subsections use "subsection title" and "description" keys
        - Subsubsections use "subsubsection title" and "description" keys
        
        Note: SurveyX's Outlines.__str__() method automatically adds numbering (e.g., "1. ", "1.1 ", "1.1.1 "),
        so we need to strip existing number prefixes from MEKG outline to avoid duplication.
        """
        import re
        
        def strip_number_prefix(title: str) -> str:
            """Strip number prefix from title, e.g., '1. ', '1.1. ', '1.1.1 ', '2.3 ' etc."""
            # Match number patterns at the beginning: digit.digit.digit. or digit.digit. or digit.
            return re.sub(r'^[\d]+\.[\d]*\.?[\d]*\.?\s*', '', title).strip()
        
        surveyx_sections = []
        for section in self.sections:
            surveyx_subsections = []
            for sub in section.subsections:
                subsection_dict = {
                    "subsection title": strip_number_prefix(sub.title),
                    "description": sub.description
                }
                # Add three-level structure (subsubsections)
                if sub.subsections:
                    subsection_dict["subsubsections"] = [
                        {
                            "subsubsection title": strip_number_prefix(subsub.title),
                            "description": subsub.description
                        }
                        for subsub in sub.subsections
                    ]
                surveyx_subsections.append(subsection_dict)
            
            surveyx_section = {
                "section title": strip_number_prefix(section.title),
                "description": section.description,
                "subsections": surveyx_subsections
            }
            surveyx_sections.append(surveyx_section)
        
        return {
            "title": self.title,
            "sections": surveyx_sections
        }
    
    def __str__(self) -> str:
        """Generate readable outline string - supports three-level structure"""
        lines = [f"# {self.title}\n"]
        for section in self.sections:
            lines.append(f"\n## {section.number}. {section.title}")
            if section.description:
                lines.append(f"   {section.description}")
            for sub in section.subsections:
                lines.append(f"\n### {sub.number}. {sub.title}")
                if sub.description:
                    lines.append(f"   {sub.description}")
                # Add three-level structure (subsubsections)
                for subsub in sub.subsections:
                    lines.append(f"\n#### {subsub.number}. {subsub.title}")
                    if subsub.description:
                        lines.append(f"   {subsub.description}")
        return "\n".join(lines)


class MEKGOutlineGenerator:
    """
    MEKG Knowledge Graph-based Outline Generator
    
    Core Strategy:
    1. Community-driven: Each community corresponds to a main section
    2. Centrality-driven: High-centrality papers serve as section cores
    3. Relationship-driven: Use paper relationships to organize subsections
    4. Time-driven: Organize content by temporal evolution
    """
    
    # Outline Generation Prompt - MEKG-driven academic survey outline generator
    # Enhanced with universal design principles from 5 SOTA survey papers
    OUTLINE_GENERATION_PROMPT = """You are a senior academic survey expert with extensive experience in writing high-quality review papers. Your task is to generate a well-organized, hierarchical survey outline that **MUST be grounded in the provided MEKG (Methods-Entity Knowledge Graph) structure**.

## Survey Topic
{topic}

## **CRITICAL: MEKG Knowledge Graph Structure (USE THIS AS PRIMARY GUIDE)**

The following structure represents the actual research landscape extracted from {total_papers} papers. **Your outline MUST reflect this structure.**

### Major Research Communities (sorted by paper count - these should guide your main sections)
{communities}

### Core Papers (sorted by impact - reference these in descriptions)
{core_papers}

### Research Evolution Timeline
{evolution_paths}

### Relationship Statistics (indicates research focus areas)
{relation_stats}

---

## **Universal Design Principles (Based on 5 SOTA Survey Analysis)**

We analyzed 5 high-quality survey papers and extracted the following design principles:

| Survey | Key Design Feature | Why It Works |
|--------|-------------------|--------------|
| **Tool Learning Survey** | "Why-How" dual structure + Process-oriented stages | Establishes motivation, then organizes methods by workflow |
| **Multimodal RAG Survey** | Taxonomy Matrix + 4-stage Workflow | Provides panoramic view + clear execution pipeline |
| **RL Meets LLM Survey** | Lifecycle organization (Pre-train → Align → Reason) | Follows natural technology evolution |
| **VLA for AD Survey** | Past-Present-Future + Limitation-driven transitions | Clear progression with explicit motivation for new tech |
| **3D Reconstruction Survey** | Representation-driven taxonomy | Reflects technical essence of different approaches |

---

## **MANDATORY: MEKG-Driven Outline Design**

### Rule 1: Main Sections MUST Derive from MEKG Categories
- Each major MEKG category should correspond to a main section
- The order of sections should roughly follow the paper count (importance) in MEKG
- You may merge small MEKG categories or split large ones, but the content must come from MEKG

### Rule 2: Subsections MUST Derive from MEKG Subcategories
- Use MEKG subcategories as subsection titles
- If a subcategory has many papers, consider further splitting into sub-subsections

### Rule 3: Choose a Logical Flow Pattern

**Pattern A: Why-How-Resources-Future (Widely Applicable)**
```
Background → Why [Topic]? → How [Topic]? → Benchmarks → Challenges → Conclusion
```

**Pattern B: Taxonomy-Workflow-Training (for system/pipeline surveys)**
```
Problem → Taxonomy → Workflow → Training → Evaluation → Applications → Future
```

**Pattern C: Past-Present-Future (for technology evolution surveys)**
```
Preliminaries → Previous Gen → Current Gen → Benchmarks → Challenges
```

**Pattern D: Lifecycle-Based (for technologies with phases)**
```
Preliminaries → Phase 1 → Phase 2 → Phase 3 (deepest) → Resources
```

### Rule 4: Use Process-Oriented Taxonomy for Core Section
When organizing the core technical section, follow a **workflow/process-based** structure:
- Stage 1 → Stage 2 → Stage 3 → Stage 4 (chronological execution flow)
- Each stage should have **paradigm splits** as sub-subsections

**Common Paradigm Splits:**
- Tuning-free vs Tuning-based
- Retriever-based vs LLM-based
- Single-turn vs Multi-turn
- Direct vs Integration
- Parameter-Frozen vs Parameter-Trainable
- End-to-End vs Modular

---

## **FEW-SHOT EXAMPLES: High-Quality Survey Outline Patterns**

**Study ALL 5 examples below, then automatically select the best pattern for your topic.**

### Example 1: "Tool Learning with Large Language Models" (Why-How Pattern)
**Suitable For**: Topics with clear execution workflow/pipeline.
```
1. Introduction
2. Background
3. Why Tool Learning? (Motivation - 6 subsections)
4. How Tool Learning? (Core Technical - Process-Oriented)
   4.1 Overall Paradigm
   4.2 Task Planning (Stage 1)
       4.2.1 Tuning-free Methods
       4.2.2 Tuning-based Methods
   4.3 Tool Selection (Stage 2)
   4.4 Tool Calling (Stage 3)
   4.5 Response Generation (Stage 4)
5. Benchmarks, Toolkits, and Evaluation
6. Challenges and Future Directions (7 specific challenges)
7. Conclusion
```

### Example 2: "Multimodal RAG Survey" (Taxonomy + Workflow Pattern)
**Suitable For**: Topics with multiple modalities/dimensions forming a matrix.
```
1. Introduction
2. Problem Formulation
3. Taxonomy (Input/Output modality matrix)
4. Workflow (4-stage process)
   4.1 Pre-Retrieval
   4.2 Retrieval
   4.3 Augmentation
   4.4 Generation
5. Training Strategies (Frozen / Trainable)
6. Evaluation and Benchmarks
7. Applications
8. Future Directions
9. Conclusion
```

### Example 3: "RL Meets LLM Survey" (Lifecycle-Based Pattern)
**Suitable For**: Topics with distinct development phases.
```
1. Introduction
2. Preliminaries of RL
3. RL in Pre-training and Alignment Phase (Early Phases)
4. RL in Reasoning Phase (Current Frontier - Deepest Section)
   4.1 Experimental Findings
   4.2 Recent Advances
   4.3 Multimodal Reasoning
   4.4 Adaptive Reasoning
5. Datasets and Benchmarks
```

### Example 4: "VLA for Autonomous Driving" (Past-Present-Future Pattern)
**Suitable For**: Topics where new technology replaces/improves old technology.
```
1. Introduction
2. Preliminary Foundations (Component Formalization)
3. Vision-Action Models (PAST)
   3.1 End-to-End Models
   3.2 World Models
   3.3 Limitations of VA Compared to VLA (Transition)
4. Vision-Language-Action Models (PRESENT)
   4.1 End-to-End VLA
   4.2 Dual-System VLA
5. Datasets & Benchmark
6. Challenges and Future Directions
7. Conclusion
```

### Example 5: "3D Reconstruction Survey" (Representation-Driven Pattern)
**Suitable For**: Topics with different underlying technical representations.
```
1. Introduction
2. Methods (Representation-Driven)
   2.1 NeRF (Representation A)
   2.2 Pointmap (Emerging Representation)
   2.3 3DGS (Representation B)
   2.4 Other Representations
3. Tasks & Applications (10 domains)
4. Evaluation
5. Open Challenges
```

---

## **Structural Guidelines**

### Primary Outline (Main Sections):
1. **Introduction** - Always first
2. **Background/Preliminaries** - Definitions, scope, problem formulation
3. **Motivation Section** (Optional but recommended) - "Why [Topic]?" with 3-6 benefits
4. **Core Technical Section(s)** - "How [Topic]?" - This is the LARGEST section
   - MUST use process-oriented taxonomy (Stage 1 → Stage 2 → ...)
   - Each stage MUST have paradigm splits
5. **Evaluation/Benchmarks Section** - Datasets, metrics, toolkits
6. **Challenges and Future Directions** - 5-7 specific challenges
7. **Conclusion** - Always last, no subsections

### Depth Requirements:
- Main sections: 5-7 (excluding Introduction and Conclusion)
- Core technical section: 4-6 subsections, each with 2-3 sub-subsections
- Challenges section: 5-7 specific, actionable challenges

### Description Quality:
- Main section descriptions: 80-150 words
- Subsection descriptions: 40-80 words, mention specific methods/papers
- Sub-subsection descriptions: 30-50 words, include representative work names

### Bad vs Good Examples:

**Bad Challenges (Too Vague):**
- "Improving performance"
- "Better evaluation"
- "More applications"

**Good Challenges (Specific):**
- "High Latency in Tool Learning"
- "Rigorous and Comprehensive Evaluation"
- "Safe and Robust Tool Learning"
- "Unified Tool Learning Framework"

**Bad Descriptions (Generic):**
- "This section discusses various methods"

**Good Descriptions (Concrete):**
- "Reviews tuning-free methods including Chain-of-Thought (CoT), ReAct, and Toolformer"

---

## **Output Format (JSON)**

```json
{{
  "title": "A Survey on {topic}",
  "sections": [
    {{
      "title": "Introduction",
      "desc": "Introduces the limitations of current approaches and presents [topic] as a solution. Outlines the survey's scope and contributions."
    }},
    {{
      "title": "Background",
      "desc": "Defines foundational concepts and terminology. Clarifies the definition of key terms and the scope of this survey."
    }},
    {{
      "title": "Why [Topic]?",
      "desc": "Analyzes the necessity and benefits of [topic] from multiple perspectives.",
      "subsections": [
        {{"title": "Benefit 1", "desc": "Description with specific examples"}},
        {{"title": "Benefit 2", "desc": "Description with specific examples"}},
        {{"title": "Benefit 3", "desc": "Description with specific examples"}}
      ]
    }},
    {{
      "title": "How [Topic]?",
      "desc": "The core technical section reviewing advancements across the [topic] workflow. Structured around distinct stages.",
      "subsections": [
        {{"title": "Overall Paradigm", "desc": "Overview of the workflow and operational paradigms"}},
        {{
          "title": "Stage 1: [Name]",
          "desc": "Reviews methods for [stage description]",
          "subsubsections": [
            {{"title": "Tuning-free Methods", "desc": "Prompt-based approaches like [examples]"}},
            {{"title": "Tuning-based Methods", "desc": "Fine-tuning approaches like [examples]"}}
          ]
        }},
        {{
          "title": "Stage 2: [Name]",
          "desc": "Analyzes how [stage description]",
          "subsubsections": [
            {{"title": "Approach A", "desc": "Description with examples"}},
            {{"title": "Approach B", "desc": "Description with examples"}}
          ]
        }},
        {{
          "title": "Stage 3: [Name]",
          "desc": "Description of this stage",
          "subsubsections": [
            {{"title": "Approach A", "desc": "Description with examples"}},
            {{"title": "Approach B", "desc": "Description with examples"}}
          ]
        }},
        {{
          "title": "Stage 4: [Name]",
          "desc": "Description of this stage",
          "subsubsections": [
            {{"title": "Approach A", "desc": "Description with examples"}},
            {{"title": "Approach B", "desc": "Description with examples"}}
          ]
        }}
      ]
    }},
    {{
      "title": "Benchmarks and Evaluation",
      "desc": "Summarizes the ecosystem for validating [topic].",
      "subsections": [
        {{"title": "Benchmarks", "desc": "Major datasets and their characteristics"}},
        {{"title": "Evaluation Metrics", "desc": "Specific metrics for each stage"}},
        {{"title": "Toolkits", "desc": "Available tools and libraries"}}
      ]
    }},
    {{
      "title": "Challenges and Future Directions",
      "desc": "Identifies critical bottlenecks and proposes research directions.",
      "subsections": [
        {{"title": "Challenge 1: [Specific Name]", "desc": "Concrete problem and potential solutions"}},
        {{"title": "Challenge 2: [Specific Name]", "desc": "Concrete problem and potential solutions"}},
        {{"title": "Challenge 3: [Specific Name]", "desc": "Concrete problem and potential solutions"}},
        {{"title": "Challenge 4: [Specific Name]", "desc": "Concrete problem and potential solutions"}},
        {{"title": "Challenge 5: [Specific Name]", "desc": "Concrete problem and potential solutions"}}
      ]
    }},
    {{
      "title": "Conclusion",
      "desc": "Summarizes the key findings of the survey."
    }}
  ]
}}
```

---

## **Quality Checklist**

Before outputting, verify:
- [ ] Main sections derived from MEKG categories?
- [ ] Subsections derived from MEKG subcategories?
- [ ] Core technical section uses process-oriented taxonomy (stages)?
- [ ] Each stage has paradigm splits (tuning-free vs tuning-based)?
- [ ] Logical flow: Background → Motivation → Methods → Evaluation → Future?
- [ ] 5-7 specific challenges in Future Directions?
- [ ] Descriptions mention specific methods/papers from core papers list?
- [ ] Avoided generic descriptions like "discusses various methods"?

**Output only the JSON, no additional text.**"""
    
    # Section Refinement Prompt - Focus on academic professionalism
    SECTION_REFINEMENT_PROMPT = """Refine the following survey section title and description to make them more academic and professional.

Original Section:
Title: {title}
Description: {description}
Core Papers: {papers}

Requirements:
1. The title should be concise, professional, and accurately summarize the section content
2. The description should explain the research scope, main content, and significance of this section
3. Maintain academic writing style appropriate for the field

Output Format:
```json
{{
  "title": "Refined title",
  "desc": "Refined description (50-100 words)"
}}
```

Output only the JSON."""

    # Critic Prompt - MEKG-aware review focusing on process-oriented structure
    CRITIC_PROMPT = """You are a rigorous academic journal reviewer specializing in evaluating survey paper outlines. Your review should ensure the outline follows SOTA survey patterns.

## Survey Topic
{topic}

## Outline Under Review
{outline}

## Core Review Principles (Based on SOTA Survey Analysis)

### 1. Process-Oriented Structure (Most Important)
High-quality surveys like "Tool Learning with LLMs" use a **process-oriented taxonomy**:
- Core technical section should follow a workflow: Stage 1 → Stage 2 → Stage 3 → Stage 4
- Each stage should have paradigm splits: "Tuning-free Methods" vs "Tuning-based Methods"
- **Check**: Does the core technical section follow a process/workflow structure?

### 2. "Why-How-Resources-Future" Logical Flow
SOTA surveys follow this pattern:
- Background/Preliminaries (definitions)
- "Why [Topic]?" (motivation with 3-6 benefits)
- "How [Topic]?" (core technical, process-oriented)
- Benchmarks/Evaluation (resources)
- Challenges and Future Directions (5-7 specific challenges)
- **Check**: Does the outline follow this logical flow?

### 3. Three-Level Depth in Core Section
- Core technical section MUST have three levels: Section → Subsection → Sub-subsection
- Each workflow stage should have paradigm splits as sub-subsections
- Example: "4.2 Task Planning" → "4.2.1 Tuning-free Methods" + "4.2.2 Tuning-based Methods"
- **Check**: Does the core section have sufficient depth?

### 4. Specific Challenges Section
- "Challenges and Future Directions" should have 5-7 **specific, actionable** challenges
- Each challenge should be a distinct research problem, not vague statements
- **Check**: Are challenges specific enough?

### 5. Description Quality
- Descriptions should mention specific methods, papers, or techniques
- Avoid generic descriptions like "discusses various methods"
- **Check**: Do descriptions include concrete examples?

## Output Format

**Process Structure Issues** (if any):
1. [Workflow] The core section lacks process-oriented structure. Suggest reorganizing into stages:
   - Stage 1: [Name]
   - Stage 2: [Name]
   ...

**Paradigm Split Issues** (if any):
1. [Split] Subsection X.Y should be split into paradigms:
   - X.Y.1: Tuning-free Methods
   - X.Y.2: Tuning-based Methods

**Logical Flow Issues** (if any):
1. [Reorder] Section X should come before/after Section Y because...
2. [Add] Missing "Why [Topic]?" motivation section

**Depth Issues** (if any):
1. [Deepen] Section X needs more subsections
2. [Specify] Description of Y is too vague, add specific methods

**Challenge Issues** (if any):
1. [Expand] Only N challenges listed, need 5-7
2. [Specify] Challenge X is too vague, make it more actionable

Output only the suggestion list. If the structure is already good, provide only minor improvements."""

    # Refine Prompt - SOTA-pattern-aware structural optimization
    REFINE_PROMPT = """You are a senior academic architect skilled in designing well-structured survey outlines following SOTA patterns.

## Survey Topic
{topic}

## Original Outline
{outline}

## Reviewer Comments
{critique}

## Optimization Task

Rewrite the outline based on reviewer comments, following SOTA survey patterns:

### SOTA Pattern: "Why-How-Resources-Future" Structure
```
1. Introduction
2. Background/Preliminaries
3. Why [Topic]? (Motivation - 3-6 benefits)
4. How [Topic]? (Core Technical - Process-Oriented)
   4.1 Overall Paradigm
   4.2 Stage 1: [Name]
       4.2.1 Tuning-free Methods
       4.2.2 Tuning-based Methods
   4.3 Stage 2: [Name]
       4.3.1 Approach A
       4.3.2 Approach B
   ...
5. Benchmarks and Evaluation
6. Challenges and Future Directions (5-7 specific challenges)
7. Conclusion
```

### Process-Oriented Core Section
The "How [Topic]?" section MUST follow a workflow/process structure:
- Identify the stages in the workflow (e.g., Planning → Selection → Execution → Generation)
- Each stage should have paradigm splits as sub-subsections
- Common paradigm splits:
  - Tuning-free vs Tuning-based
  - Retriever-based vs LLM-based
  - Single-turn vs Multi-turn
  - Direct vs Integration

### Specific Challenges
The "Challenges and Future Directions" section should have 5-7 specific challenges:
- Each challenge should be a distinct, actionable research problem
- Examples: "High Latency", "Rigorous Evaluation", "Safe and Robust [Topic]", "Unified Framework"

### Description Quality
- Main section descriptions: 80-150 words
- Subsection descriptions: 40-80 words, mention specific methods/papers
- Sub-subsection descriptions: 30-50 words, include representative work names

### Quality Checklist
After optimization, verify:
- [ ] Follows "Why-How-Resources-Future" pattern?
- [ ] Core section uses process-oriented taxonomy (stages)?
- [ ] Each stage has paradigm splits (tuning-free vs tuning-based)?
- [ ] 5-7 specific challenges in Future Directions?
- [ ] Descriptions mention specific methods/papers?

## Output Format (Strict JSON)
```json
{{
  "title": "A Survey on {topic}",
  "sections": [
    {{
      "title": "Introduction",
      "desc": "Introduces the problem and presents the survey's scope and contributions."
    }},
    {{
      "title": "Background",
      "desc": "Defines foundational concepts and terminology."
    }},
    {{
      "title": "Why [Topic]?",
      "desc": "Analyzes the necessity and benefits.",
      "subsections": [
        {{"title": "Benefit 1", "desc": "Description"}},
        {{"title": "Benefit 2", "desc": "Description"}}
      ]
    }},
    {{
      "title": "How [Topic]?",
      "desc": "Core technical section with process-oriented structure.",
      "subsections": [
        {{"title": "Overall Paradigm", "desc": "Overview of the workflow"}},
        {{
          "title": "Stage 1: [Name]",
          "desc": "Description of this stage",
          "subsubsections": [
            {{"title": "Tuning-free Methods", "desc": "Prompt-based approaches"}},
            {{"title": "Tuning-based Methods", "desc": "Fine-tuning approaches"}}
          ]
        }}
      ]
    }},
    {{
      "title": "Benchmarks and Evaluation",
      "desc": "Evaluation resources and metrics.",
      "subsections": [
        {{"title": "Benchmarks", "desc": "Major datasets"}},
        {{"title": "Evaluation Metrics", "desc": "Metrics for each stage"}}
      ]
    }},
    {{
      "title": "Challenges and Future Directions",
      "desc": "Critical bottlenecks and research directions.",
      "subsections": [
        {{"title": "Challenge 1: [Specific Name]", "desc": "Description"}},
        {{"title": "Challenge 2: [Specific Name]", "desc": "Description"}},
        {{"title": "Challenge 3: [Specific Name]", "desc": "Description"}},
        {{"title": "Challenge 4: [Specific Name]", "desc": "Description"}},
        {{"title": "Challenge 5: [Specific Name]", "desc": "Description"}}
      ]
    }},
    {{
      "title": "Conclusion",
      "desc": "Summarizes the key findings."
    }}
  ]
}}
```

Output only the JSON, no additional text."""

    def __init__(self, chat_agent: Optional[ChatAgent] = None, enable_critic: bool = True, skip_mount: bool = False):
        """
        Initialize outline generator
        
        Args:
            chat_agent: LLM chat agent, if None will attempt to create automatically
            enable_critic: Whether to enable critic-refine loop
            skip_mount: Whether to skip paper mounting (should be True when using SurveyX ContentGenerator)
        """
        self.chat_agent = chat_agent
        self.enable_critic = enable_critic
        self.skip_mount = skip_mount
        if self.chat_agent is None and HAS_CHAT_AGENT:
            try:
                self.chat_agent = ChatAgent()
            except Exception as e:
                print(f"Warning: Failed to create ChatAgent: {e}")

    def _remote_chat_once(self, prompt: str, **kwargs) -> str:
        """Call the chat agent once when the caller has a safe fallback path."""
        chat_once = getattr(self.chat_agent, "remote_chat_no_retry", None)
        if callable(chat_once):
            return chat_once(prompt, **kwargs)
        return self.chat_agent.remote_chat(prompt, **kwargs)
    
    def generate_from_mekg_data(
        self,
        mekg_data: Dict[str, Any],
        topic: str,
        target_sections: int = 5
    ) -> SurveyOutline:
        """
        Generate outline from MEKG data
        
        Args:
            mekg_data: MEKG data (containing papers, relations, categories, etc.)
            topic: Survey topic
            target_sections: Target number of sections (recommended 4-6, default 5)
            
        Returns:
            SurveyOutline object
        """
        # 1. Analyze graph structure
        structure_info = self._analyze_graph_structure(mekg_data)
        
        # 2. Generate outline using LLM
        if self.chat_agent:
            outline = self._generate_with_llm(topic, structure_info, target_sections)
            
            # 2.1 Critic-refine loop
            if self.enable_critic:
                print("   Entering Critic-Refine loop...")
                outline = self._critic_and_refine(outline, topic)
        else:
            # Use rule-based generation when LLM is unavailable
            outline = self._generate_with_rules(topic, structure_info, target_sections)
        
        # 3. Mount papers to sections (if not skipped)
        if not self.skip_mount:
            self._mount_papers_to_sections(outline, mekg_data)
        else:
            logger.info("Skipping MEKG paper mounting (will be handled by SurveyX ContentGenerator)")
        
        return outline

    def _critic_and_refine(self, outline: SurveyOutline, topic: str) -> SurveyOutline:
        """Execute critic-refine loop"""
        try:
            logger.info("Entering Critic-Refine loop...")
            import time
            
            # 1. Critic phase - with shorter timeout
            logger.info("Reviewer is examining the outline...")
            start_time = time.time()
            outline_str = str(outline)
            critic_prompt = self.CRITIC_PROMPT.format(topic=topic, outline=outline_str)
            
            try:
                critique = self._remote_chat_once(critic_prompt, temperature=0.7, timeout=180, model=ADVANCED_CHATAGENT_MODEL)
            except Exception as e:
                logger.warning(f"Reviewer timeout or error: {e}, skipping optimization")
                return outline
            
            elapsed = time.time() - start_time
            logger.info(f"Reviewer comments (elapsed: {elapsed:.2f}s):")
            
            # Print only first 5 suggestions
            lines = [l.strip() for l in critique.split('\n') if l.strip()]
            for line in lines[:5]:
                logger.info(f"  {line}")
            if len(lines) > 5:
                logger.info(f"  ... {len(lines)} suggestions in total")
            
            # 2. Refine phase - with shorter timeout
            logger.info("Architect is optimizing the outline...")
            start_time = time.time()
            
            # Convert original outline to JSON format for LLM understanding
            original_json = json.dumps(outline.to_surveyx_format(), ensure_ascii=False, indent=2)
            
            refine_prompt = self.REFINE_PROMPT.format(
                topic=topic,
                outline=original_json,  # Use JSON format instead of string format
                critique=critique
            )
            
            try:
                refined_response = self._remote_chat_once(refine_prompt, temperature=0.3, timeout=120)
            except Exception as e:
                logger.warning(f"Optimization timeout or error: {e}, keeping original")
                return outline
            
            logger.info(f"Optimization complete (elapsed: {time.time() - start_time:.2f}s)")
            
            refined_dict = self._parse_llm_response(refined_response)
            
            # Validate parsed result
            if refined_dict and refined_dict.get("sections"):
                # Additional validation: ensure each section has required fields
                valid = True
                for sec in refined_dict["sections"]:
                    if not sec.get("title"):
                        valid = False
                        break
                
                if valid:
                    new_outline = self._build_outline_from_dict(refined_dict, topic)
                    # Validate section count: 4-6 is ideal range
                    if 3 <= len(new_outline.sections) <= 8:
                        # Check subsection depth
                        avg_subsections = sum(len(s.subsections) for s in new_outline.sections) / max(len(new_outline.sections), 1)
                        logger.info(f"Outline updated: {len(outline.sections)} -> {len(new_outline.sections)} sections, avg subsections: {avg_subsections:.1f}")
                        
                        if len(new_outline.sections) > 6:
                            logger.warning(f"Section count ({len(new_outline.sections)}) is high, consider merging related sections")
                        if avg_subsections < 3:
                            logger.warning(f"Avg subsection count ({avg_subsections:.1f}) is low, consider adding more depth")
                        
                        return new_outline
                    else:
                        logger.warning(f"Abnormal section count after optimization ({len(new_outline.sections)}), keeping original")
                else:
                    logger.warning("Optimized outline missing required fields, keeping original")
            else:
                logger.warning("Optimized outline has invalid format, keeping original")
            
            return outline
                
        except Exception as e:
            logger.error(f"Critic-Refine process error: {e}, keeping original")
            import traceback
            logger.debug(traceback.format_exc())
            return outline
    
    def generate_from_classified_papers(
        self,
        topic: str,
        categories: Dict[str, Dict[str, List[Dict]]],
        papers: List[Dict],
        relations: List[Dict]
    ) -> SurveyOutline:
        """
        Generate outline from classified papers
        
        Args:
            topic: Survey topic
            categories: Classification structure {category: {subcategory: [papers]}}
            papers: Paper list
            relations: Relation list
            
        Returns:
            SurveyOutline object
        """
        # Build MEKG data format
        mekg_data = {
            "topic": topic,
            "papers": papers,
            "relations": relations,
            "categories": categories
        }
        
        return self.generate_from_mekg_data(mekg_data, topic)
    
    def _analyze_graph_structure(self, mekg_data: Dict) -> Dict[str, Any]:
        """Analyze graph structure and extract key information"""
        papers = mekg_data.get("papers", [])
        relations = mekg_data.get("relations", [])
        categories = mekg_data.get("categories", {})
        
        # 1. Analyze community/classification structure
        communities = []
        for cat_name, subcats in categories.items():
            total_papers = sum(
                len(papers) if isinstance(papers, list) else papers
                for papers in subcats.values()
            )
            communities.append({
                "name": cat_name,
                "paper_count": total_papers,
                "subcategories": list(subcats.keys())
            })
        communities.sort(key=lambda x: x["paper_count"], reverse=True)
        
        # 2. Identify core papers (high citations)
        core_papers = sorted(
            papers,
            key=lambda x: x.get("citations", 0),
            reverse=True
        )[:20]
        
        # 3. Analyze relationship statistics
        relation_stats = defaultdict(int)
        for rel in relations:
            relation_stats[rel.get("type", "unknown")] += 1
        
        # 4. Analyze temporal evolution
        year_distribution = defaultdict(int)
        for paper in papers:
            year = paper.get("year")
            if year:
                year_distribution[year] += 1
        
        return {
            "communities": communities,
            "core_papers": core_papers,
            "relation_stats": dict(relation_stats),
            "year_distribution": dict(sorted(year_distribution.items())),
            "total_papers": len(papers),
            "total_relations": len(relations)
        }
    
    def _generate_with_llm(
        self,
        topic: str,
        structure_info: Dict,
        target_sections: int
    ) -> SurveyOutline:
        """Generate outline using LLM"""
        logger.info(f"Generating outline with LLM (Topic: {topic})...")
        
        # Format community information - more detailed for MEKG-driven generation
        communities_str = "\n".join([
            f"- **{c['name']}** ({c['paper_count']} papers)\n  Subcategories: {', '.join(c['subcategories'])}"
            for c in structure_info["communities"]
        ])
        
        # Format core papers - include more details
        core_papers_str = "\n".join([
            f"- [{p.get('title', 'Unknown')[:80]}] ({p.get('year', '?')}, {p.get('citations', 0)} citations)\n  Category: {p.get('category', 'N/A')} > {p.get('subcategory', 'N/A')}"
            for p in structure_info["core_papers"][:15]
        ])
        
        # Format evolution paths
        years = sorted(structure_info["year_distribution"].keys())
        if years:
            evolution_str = f"Time span: {min(years)} - {max(years)}\n"
            evolution_str += "Annual distribution: " + ", ".join([
                f"{y}({structure_info['year_distribution'][y]})"
                for y in years[-5:]
            ])
        else:
            evolution_str = "No temporal information available"
        
        # Format relationship statistics
        relation_stats_str = "\n".join([
            f"- {rel_type}: {count} relations"
            for rel_type, count in sorted(
                structure_info["relation_stats"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
        ])
        
        # Build prompt with total_papers
        prompt = self.OUTLINE_GENERATION_PROMPT.format(
            topic=topic,
            total_papers=structure_info.get("total_papers", "N/A"),
            communities=communities_str,
            core_papers=core_papers_str,
            evolution_paths=evolution_str,
            relation_stats=relation_stats_str
        )
        
        # Call LLM - use advanced model for outline generation
        logger.info(f"Waiting for LLM response (initial outline, using advanced model: {ADVANCED_CHATAGENT_MODEL})...")
        import time
        start_time = time.time()
        try:
            response = self._remote_chat_once(prompt, temperature=0.3, model=ADVANCED_CHATAGENT_MODEL)
        except Exception as e:
            logger.warning(f"Initial outline generation failed: {e}; falling back to rule-based outline")
            return self._generate_with_rules(topic, structure_info, target_sections)
        logger.info(f"LLM response complete (elapsed: {time.time() - start_time:.2f}s)")
        
        # Parse response
        outline_dict = self._parse_llm_response(response)
        if not outline_dict.get("sections"):
            logger.warning("Initial outline generation returned no sections; falling back to rule-based outline")
            return self._generate_with_rules(topic, structure_info, target_sections)
        
        # Build SurveyOutline
        return self._build_outline_from_dict(outline_dict, topic)
    
    def _generate_with_rules(
        self,
        topic: str,
        structure_info: Dict,
        target_sections: int
    ) -> SurveyOutline:
        """Generate outline using rules (fallback when LLM unavailable)"""
        sections = []
        
        # 1. Introduction
        sections.append(OutlineSection(
            number="1",
            title="Introduction",
            description=f"Introduction to {topic}, including background, motivation, and survey scope.",
            level=1,
            subsections=[
                OutlineSection(
                    number="1.1",
                    title="Background and Motivation",
                    description="Research background and motivation for this survey.",
                    level=2
                ),
                OutlineSection(
                    number="1.2",
                    title="Survey Scope and Contributions",
                    description="Scope of this survey and main contributions.",
                    level=2
                ),
                OutlineSection(
                    number="1.3",
                    title="Organization",
                    description="Organization of this survey paper.",
                    level=2
                )
            ]
        ))
        
        # 2. Generate middle sections based on communities
        communities = structure_info["communities"][:target_sections - 2]
        for i, community in enumerate(communities, start=2):
            section = OutlineSection(
                number=str(i),
                title=community["name"],
                description=f"Overview of {community['name']} approaches and methods.",
                level=1,
                subsections=[]
            )
            
            # Add subsections
            for j, subcat in enumerate(community["subcategories"][:4], start=1):
                section.subsections.append(OutlineSection(
                    number=f"{i}.{j}",
                    title=subcat,
                    description=f"Discussion of {subcat} methods and techniques.",
                    level=2
                ))
            
            sections.append(section)
        
        # Last section: Conclusion
        sections.append(OutlineSection(
            number=str(len(sections) + 1),
            title="Conclusion and Future Directions",
            description="Summary of key findings and future research directions.",
            level=1,
            subsections=[]
        ))
        
        return SurveyOutline(
            title=f"A Survey on {topic}",
            topic=topic,
            sections=sections
        )
    
    def _parse_llm_response(self, response: str) -> Dict:
        """Parse LLM response - robust parsing"""
        try:
            # Method 1: Try to extract ```json``` block
            match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                json_str = match.group(1)
                return json.loads(json_str)
            
            # Method 2: Try to extract ``` block
            match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                json_str = match.group(1)
                try:
                    return json.loads(json_str)
                except:
                    pass
            
            # Method 3: Try to find JSON object
            match = re.search(r'\{[\s\S]*"sections"[\s\S]*\}', response)
            if match:
                json_str = match.group(0)
                # Try to fix common JSON errors
                json_str = self._fix_json_string(json_str)
                return json.loads(json_str)
            
            # Method 4: Parse entire response directly
            return json.loads(response)
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed: {e}")
            logger.debug(f"Original response: {response[:500]}...")
            # Return empty structure on parse failure
            return {
                "title": "Survey",
                "sections": []
            }
    
    def _fix_json_string(self, json_str: str) -> str:
        """Try to fix common JSON format errors"""
        # Remove trailing commas
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # Simple fix, may not be perfect
        return json_str
    
    def _build_outline_from_dict(self, data: Dict, topic: str) -> SurveyOutline:
        """Build SurveyOutline from dictionary - supports three-level structure"""
        sections = []
        
        for i, sec_data in enumerate(data.get("sections", []), start=1):
            subsections = []
            for j, sub_data in enumerate(sec_data.get("subsections", []), start=1):
                # Check for three-level structure (subsubsections)
                subsubsections = []
                for k, subsub_data in enumerate(sub_data.get("subsubsections", []), start=1):
                    subsubsections.append(OutlineSection(
                        number=f"{i}.{j}.{k}",
                        title=subsub_data.get("title", f"Subsubsection {i}.{j}.{k}"),
                        description=subsub_data.get("desc", ""),
                        level=3,
                        subsections=[]  # Three-level structure has no deeper children
                    ))
                
                subsections.append(OutlineSection(
                    number=f"{i}.{j}",
                    title=sub_data.get("title", f"Subsection {i}.{j}"),
                    description=sub_data.get("desc", ""),
                    level=2,
                    subsections=subsubsections  # Second level can contain third level
                ))
            
            sections.append(OutlineSection(
                number=str(i),
                title=sec_data.get("title", f"Section {i}"),
                description=sec_data.get("desc", ""),
                level=1,
                subsections=subsections
            ))
        
        return SurveyOutline(
            title=data.get("title", f"A Survey on {topic}"),
            topic=topic,
            sections=sections
        )
    
    def _mount_papers_to_sections(
        self,
        outline: SurveyOutline,
        mekg_data: Dict
    ):
        """Mount papers to corresponding sections - using LLM intelligent mounting (similar to SurveyX)"""
        papers = mekg_data.get("papers", [])
        
        if not papers:
            logger.warning("No papers to mount")
            return
        
        logger.info(f"Starting to mount {len(papers)} papers to {len(outline.sections)} sections")
        
        # Use LLM mounting if ChatAgent is available
        if self.chat_agent:
            self._mount_papers_with_llm(outline, papers)
        else:
            # Fallback to rule-based mounting
            self._mount_papers_with_rules(outline, papers, mekg_data.get("categories", {}))
    
    def _mount_papers_with_llm(self, outline: SurveyOutline, papers: List[Dict]):
        """Mount papers to sections using LLM - supports async high concurrency"""
        
        # Prepare outline string
        outline_str = str(outline)
        
        # Build mounting prompt
        MOUNT_PROMPT = """You are an academic paper classification expert. Analyze which sections of the survey outline the following paper should be mounted to.

## Survey Outline
{outline}

## Paper Information
Title: {title}
Abstract: {abstract}
Year: {year}
Citations: {citations}

## Task
Determine which sections this paper should be mounted to (can be multiple), and extract key information that can be used when writing that section.

## Output Format (JSON)
```json
[
  {{"section_number": "2.1", "key_info": "This paper proposes XXX method to solve YYY problem"}},
  {{"section_number": "3", "key_info": "The experiments in this paper demonstrate ZZZ"}}
]
```

Notes:
1. section_number must be an existing section number in the outline (e.g., "2", "2.1", "3.2", etc.)
2. Do not mount to Introduction and Conclusion sections
3. key_info should be specific, including the paper's core contributions
4. Output only JSON, no additional text"""

        # Build section number to section mapping - supports three-level structure
        section_map = {}
        for section in outline.sections:
            section_map[section.number] = section
            for sub in section.subsections:
                section_map[sub.number] = sub
                # Add three-level structure (subsubsections)
                for subsub in sub.subsections:
                    section_map[subsub.number] = subsub
        
        # Batch process papers
        mount_results = {}  # paper_id -> [(section_number, key_info), ...]
        
        # Check if async is supported
        if HAS_AIOHTTP and hasattr(self.chat_agent, 'async_remote_chat'):
            # Use async mode
            logger.info(f"Using async mode for paper mounting (concurrency: {MOUNT_PAPERS_WORKERS})")
            mount_results = self._mount_papers_async(papers, outline_str, MOUNT_PROMPT)
        else:
            # Fallback to thread pool mode
            logger.info(f"Using thread pool mode for paper mounting (concurrency: {MOUNT_PAPERS_WORKERS})")
            mount_results = self._mount_papers_threaded(papers, outline_str, MOUNT_PROMPT)
        
        # Apply mounting results to outline
        section_papers = {sec_num: [] for sec_num in section_map.keys()}
        section_key_infos = {sec_num: [] for sec_num in section_map.keys()}
        
        for paper_id, mounts in mount_results.items():
            for mount in mounts:
                sec_num = mount.get("section_number", "")
                key_info = mount.get("key_info", "")
                if sec_num in section_papers:
                    section_papers[sec_num].append(paper_id)
                    if key_info:
                        section_key_infos[sec_num].append(f"[{paper_id}] {key_info}")
        
        # Update outline sections
        total_mounted = 0
        for sec_num, section in section_map.items():
            paper_ids = list(set(section_papers.get(sec_num, [])))
            section.paper_ids = paper_ids
            
            # Select core papers by citation count
            paper_map = {p.get("id", p.get("paper_id", "")): p for p in papers}
            section_paper_objs = [paper_map[pid] for pid in paper_ids if pid in paper_map]
            sorted_papers = sorted(section_paper_objs, key=lambda x: x.get("citations", 0), reverse=True)
            section.key_papers = [p.get("id", p.get("paper_id", "")) for p in sorted_papers[:5]]
            
            # Save key information to metadata
            if section_key_infos.get(sec_num):
                section.metadata["key_infos"] = section_key_infos[sec_num]
            
            if paper_ids:
                total_mounted += len(paper_ids)
                logger.info(f"  Section {sec_num} '{section.title}' - mounted {len(paper_ids)} papers")
        
        logger.info(f"LLM mounting complete, total {total_mounted} paper-section mappings")
    
    def _mount_papers_async(self, papers: List[Dict], outline_str: str, mount_prompt: str) -> Dict[str, List[Dict]]:
        """Async paper mounting - high concurrency mode"""
        mount_results = {}
        
        async def mount_single_paper(paper: Dict, session: "aiohttp.ClientSession") -> Tuple[str, List[Dict]]:
            paper_id = paper.get("id", paper.get("paper_id", ""))
            try:
                prompt = mount_prompt.format(
                    outline=outline_str,
                    title=paper.get("title", ""),
                    abstract=(paper.get("abstract") or "")[:500],
                    year=paper.get("year", "?"),
                    citations=paper.get("citations", 0)
                )
                
                response = await self.chat_agent.async_remote_chat(
                    text_content=prompt,
                    temperature=0.3,
                    timeout=60,
                    session=session
                )
                
                # Parse response
                mounts = self._parse_mount_response(response)
                return paper_id, mounts
            except Exception as e:
                logger.debug(f"Failed to mount paper {paper_id}: {e}")
                return paper_id, []
        
        async def run_all():
            semaphore = asyncio.Semaphore(MOUNT_PAPERS_WORKERS)
            results = {}
            
            async def bounded_mount(paper: Dict, session: "aiohttp.ClientSession"):
                async with semaphore:
                    return await mount_single_paper(paper, session)
            
            connector = aiohttp.TCPConnector(limit=0)  # No connection limit
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [bounded_mount(p, session) for p in papers]
                
                # Use tqdm to show progress
                for coro in tqdm(
                    asyncio.as_completed(tasks),
                    total=len(tasks),
                    desc="Async LLM paper mounting",
                    dynamic_ncols=True,
                ):
                    try:
                        paper_id, mounts = await coro
                        if mounts:
                            results[paper_id] = mounts
                    except Exception as e:
                        logger.debug(f"Mount task failed: {e}")
            
            return results
        
        # Run async tasks
        try:
            # Check if already in event loop
            try:
                loop = asyncio.get_running_loop()
                # If already in event loop, use nest_asyncio or create new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, run_all())
                    mount_results = future.result()
            except RuntimeError:
                # No running event loop, run directly
                mount_results = asyncio.run(run_all())
        except Exception as e:
            logger.error(f"Async mounting failed: {e}, falling back to thread pool mode")
            mount_results = self._mount_papers_threaded(papers, outline_str, mount_prompt)
        
        return mount_results
    
    def _mount_papers_threaded(self, papers: List[Dict], outline_str: str, mount_prompt: str) -> Dict[str, List[Dict]]:
        """Thread pool paper mounting - fallback mode"""
        mount_results = {}
        
        def mount_single_paper(paper: Dict) -> Tuple[str, List[Dict]]:
            paper_id = paper.get("id", paper.get("paper_id", ""))
            try:
                prompt = mount_prompt.format(
                    outline=outline_str,
                    title=paper.get("title", ""),
                    abstract=(paper.get("abstract") or "")[:500],
                    year=paper.get("year", "?"),
                    citations=paper.get("citations", 0)
                )
                
                response = self._remote_chat_once(prompt, temperature=0.3, timeout=60)
                
                # Parse response
                mounts = self._parse_mount_response(response)
                return paper_id, mounts
            except Exception as e:
                logger.debug(f"Failed to mount paper {paper_id}: {e}")
                return paper_id, []
        
        # Concurrent processing
        with ThreadPoolExecutor(max_workers=MOUNT_PAPERS_WORKERS) as executor:
            futures = {executor.submit(mount_single_paper, p): p for p in papers}
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="LLM paper mounting"):
                try:
                    paper_id, mounts = future.result()
                    if mounts:
                        mount_results[paper_id] = mounts
                except Exception as e:
                    logger.debug(f"Mount task failed: {e}")
        
        return mount_results
    
    def _parse_mount_response(self, response: str) -> List[Dict]:
        """Parse mount response"""
        try:
            # Extract JSON
            match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                match = re.search(r'\[.*\]', response, re.DOTALL)
                if match:
                    json_str = match.group(0)
                else:
                    json_str = response
            
            data = json.loads(json_str)
            
            # Validate format
            if isinstance(data, list):
                return [
                    {"section_number": item.get("section_number", ""), "key_info": item.get("key_info", "")}
                    for item in data
                    if item.get("section_number")
                ]
            return []
        except Exception as e:
            logger.debug(f"Failed to parse mount response: {e}")
            return []
    
    def _mount_papers_with_rules(self, outline: SurveyOutline, papers: List[Dict], categories: Dict):
        """Mount papers using rules (fallback when LLM unavailable) - supports three-level structure"""
        # Build category to papers mapping
        cat_to_papers = {}
        for paper in papers:
            cat = paper.get("category", "")
            subcat = paper.get("subcategory", "")
            if cat:
                cat_to_papers.setdefault(cat.lower(), []).append(paper)
            if subcat:
                cat_to_papers.setdefault(subcat.lower(), []).append(paper)
        
        # Build keyword index
        keyword_to_papers = self._build_keyword_index(papers)
        
        total_mounted = 0
        paper_map = {p.get("id", p.get("paper_id", "")): p for p in papers}
        
        for section in outline.sections:
            section_title_lower = section.title.lower()
            
            # Skip special sections
            if section_title_lower in ["introduction", "conclusion", "conclusion and future directions"]:
                continue
            
            mounted = self._match_papers_to_section(section.title, papers, cat_to_papers, keyword_to_papers)
            section.paper_ids = list(mounted)
            
            # Core papers
            section_papers = [paper_map[pid] for pid in mounted if pid in paper_map]
            sorted_papers = sorted(section_papers, key=lambda x: x.get("citations", 0), reverse=True)
            section.key_papers = [p.get("id", p.get("paper_id", "")) for p in sorted_papers[:5]]
            
            total_mounted += len(mounted)
            if mounted:
                logger.info(f"  Section {section.number} '{section.title}' - mounted {len(mounted)} papers")
            
            # Subsections (second level)
            for sub in section.subsections:
                sub_mounted = self._match_papers_to_section(sub.title, papers, cat_to_papers, keyword_to_papers)
                
                # If subsection has no papers, inherit from parent section
                if not sub_mounted and mounted:
                    sub_mounted = self._fuzzy_match_papers(sub.title,
                        [paper_map[pid] for pid in mounted if pid in paper_map])
                
                sub.paper_ids = list(sub_mounted)
                sub_papers = [paper_map[pid] for pid in sub_mounted if pid in paper_map]
                sorted_sub = sorted(sub_papers, key=lambda x: x.get("citations", 0), reverse=True)
                sub.key_papers = [p.get("id", p.get("paper_id", "")) for p in sorted_sub[:3]]
                
                if sub_mounted:
                    logger.info(f"    Subsection {sub.number} '{sub.title}' - mounted {len(sub_mounted)} papers")
                
                # Subsubsections (third level)
                for subsub in sub.subsections:
                    subsub_mounted = self._match_papers_to_section(subsub.title, papers, cat_to_papers, keyword_to_papers)
                    
                    # If subsubsection has no papers, inherit from parent subsection
                    if not subsub_mounted and sub_mounted:
                        subsub_mounted = self._fuzzy_match_papers(subsub.title,
                            [paper_map[pid] for pid in sub_mounted if pid in paper_map])
                    
                    subsub.paper_ids = list(subsub_mounted)
                    subsub_papers = [paper_map[pid] for pid in subsub_mounted if pid in paper_map]
                    sorted_subsub = sorted(subsub_papers, key=lambda x: x.get("citations", 0), reverse=True)
                    subsub.key_papers = [p.get("id", p.get("paper_id", "")) for p in sorted_subsub[:3]]
                    
                    if subsub_mounted:
                        logger.info(f"      Subsubsection {subsub.number} '{subsub.title}' - mounted {len(subsub_mounted)} papers")
        
        logger.info(f"Rule-based mounting complete, total {total_mounted} paper-section mappings")
    
    def _match_papers_to_section(self, title: str, papers: List[Dict],
                                  cat_to_papers: Dict, keyword_to_papers: Dict) -> set:
        """Match papers to section"""
        title_lower = title.lower()
        matched = set()
        
        # Method 1: Category matching
        for cat_name, cat_papers in cat_to_papers.items():
            if cat_name in title_lower or title_lower in cat_name:
                for p in cat_papers:
                    pid = p.get("id", p.get("paper_id", ""))
                    if pid:
                        matched.add(pid)
        
        # Method 2: Keyword matching
        keywords = self._extract_section_keywords(title)
        for kw in keywords:
            if kw in keyword_to_papers:
                for p in keyword_to_papers[kw]:
                    pid = p.get("id", p.get("paper_id", ""))
                    if pid:
                        matched.add(pid)
        
        # Method 3: Fuzzy matching
        if not matched:
            matched = self._fuzzy_match_papers(title, papers)
        
        return matched
    
    def _build_keyword_index(self, papers: List[Dict]) -> Dict[str, List[Dict]]:
        """Build keyword to papers index"""
        keyword_to_papers = {}
        
        important_keywords = [
            "tool", "function", "calling", "api", "agent", "planning", "execution",
            "learning", "training", "fine-tuning", "evaluation", "benchmark",
            "selection", "integration", "reasoning", "chain", "thought",
            "llm", "language model", "gpt", "bert", "transformer",
            "retrieval", "augmented", "generation", "rag",
            "prompt", "in-context", "few-shot", "zero-shot"
        ]
        
        for paper in papers:
            title = (paper.get("title") or "").lower()
            abstract = (paper.get("abstract") or "").lower()
            text = f"{title} {abstract}"
            
            for kw in important_keywords:
                if kw in text:
                    keyword_to_papers.setdefault(kw, []).append(paper)
        
        return keyword_to_papers
    
    def _extract_section_keywords(self, title: str) -> List[str]:
        """Extract keywords from section title"""
        title_lower = title.lower()
        stopwords = {'and', 'or', 'the', 'a', 'an', 'of', 'for', 'in', 'on', 'to', 'with', 'by'}
        words = [w for w in title_lower.split() if w not in stopwords and len(w) > 2]
        
        synonyms = {
            "fine-tuning": ["training", "learning", "adaptation"],
            "planning": ["reasoning", "decision", "strategy"],
            "execution": ["running", "calling", "invocation"],
            "evaluation": ["benchmark", "assessment", "testing"],
            "selection": ["choice", "retrieval", "picking"],
        }
        
        expanded = list(words)
        for word in words:
            if word in synonyms:
                expanded.extend(synonyms[word])
        
        return expanded
    
    def _fuzzy_match_papers(self, title: str, papers: List[Dict]) -> set:
        """Fuzzy match papers"""
        if not papers:
            return set()
        
        title_lower = title.lower()
        keywords = set(title_lower.split())
        stopwords = {'and', 'or', 'the', 'a', 'an', 'of', 'for', 'in', 'on', 'to', 'with', 'by'}
        keywords = keywords - stopwords
        
        if not keywords:
            return set()
        
        matched = set()
        for paper in papers:
            paper_title = (paper.get("title") or "").lower()
            paper_abstract = (paper.get("abstract") or "").lower()
            text = f"{paper_title} {paper_abstract}"
            
            score = sum(1 for kw in keywords if kw in text)
            if score >= max(1, len(keywords) // 3):
                pid = paper.get("id", paper.get("paper_id", ""))
                if pid:
                    matched.add(pid)
        
        return matched


def generate_outline_from_mekg_json(
    mekg_json_path: Path,
    output_path: Optional[Path] = None
) -> SurveyOutline:
    """
    Generate outline from MEKG JSON file
    
    Args:
        mekg_json_path: Path to MEKG data JSON file
        output_path: Output path (optional)
        
    Returns:
        SurveyOutline object
    """
    with open(mekg_json_path, 'r', encoding='utf-8') as f:
        mekg_data = json.load(f)
    
    topic = mekg_data.get("topic", "Research Topic")
    
    generator = MEKGOutlineGenerator()
    outline = generator.generate_from_mekg_data(mekg_data, topic)
    
    if output_path:
        outline.save(output_path)
        print(f"Outline saved to: {output_path}")
    
    return outline


if __name__ == "__main__":
    # Test code
    import sys
    
    if len(sys.argv) > 1:
        mekg_path = Path(sys.argv[1])
        output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        outline = generate_outline_from_mekg_json(mekg_path, output_path)
        print(outline)
    else:
        print("Usage: python outline_generator.py <mekg_json_path> [output_path]")
