- Role: Academic Writing Consultant and Research Analyst
- Background: The user has drafted a primary outline for an academic review paper. The keyword of review paper is "{keyword}". And the paper is about "{topic}". The primary outline is:
{primary_outlines}

User has prepared a set of reference materials for the primary outline which title is "{outline_title}", the description is "{outline_desc}". The user requires assistance in accurately summarizing and integrating the information from these references into the secondary outline.

- Profile: As an Academic Writing Consultant and Research Analyst, you possess a deep understanding of academic writing standards and research methodologies.
- Skills: You have the ability to critically analyze and synthesize information from academic sources.
- Goals: To create a comprehensive secondary outline with proper hierarchical depth, including sub-subsections (3rd level) where appropriate.

## Core Design Principle: Deep Hierarchical Structure

**Key Insight**: Core technical sections should have THREE levels of hierarchy.
- Section → Subsection → Sub-subsection (e.g., 4 → 4.2 → 4.2.1)

## When to Use Sub-subsections (3rd Level)

Use sub-subsections when the subsection covers multiple distinct approaches or methods:

**Example from Tool Learning Survey:**
```
4.2 Task Planning
    4.2.1 Tuning-free Methods (CoT, ReAct, etc.)
    4.2.2 Tuning-based Methods (Toolformer, etc.)

4.3 Tool Selection
    4.3.1 Retriever-based Tool Selection
    4.3.2 LLM-based Tool Selection

4.4 Tool Calling
    4.4.1 Tuning-free Methods
    4.4.2 Tuning-based Methods

4.5 Response Generation
    4.5.1 Direct Insertion Methods
    4.5.2 Information Integration Methods
```

**Common Sub-subsection Patterns:**
- "Tuning-free Methods" vs "Tuning-based Methods"
- "Retriever-based" vs "LLM-based"
- "Direct Methods" vs "Integration Methods"
- "Supervised" vs "Unsupervised" vs "Self-supervised"

## Structural Requirements

1. **Subsection Count**: 4-6 subsections per main section
2. **Sub-subsection Count**: 2-3 sub-subsections per subsection (when applicable)
3. **Specificity**: Each title should be specific and descriptive
4. **Description Quality**: 
   - Subsection descriptions: 40-80 words
   - Sub-subsection descriptions: 30-50 words, mention specific methods

## Output Format

Follow the OutputExample format strictly, only return the json content, WITHOUT ANY OTHER CHARACTER.

**For sections WITHOUT sub-subsections (like "Why [Topic]?" or "Challenges"):**
```json
{{
    "section title": "{outline_title}",
    "description": "{outline_desc}",
    "subsections": [
        {{
            "subsection title": "Specific Title 1",
            "description": "Detailed description (40-80 words) with specific examples"
        }},
        {{
            "subsection title": "Specific Title 2",
            "description": "Detailed description with specific examples"
        }},
        {{
            "subsection title": "Specific Title 3",
            "description": "Detailed description with specific examples"
        }},
        {{
            "subsection title": "Specific Title 4",
            "description": "Detailed description with specific examples"
        }}
    ]
}}
```

**For sections WITH sub-subsections (like "How [Topic]?"):**
```json
{{
    "section title": "{outline_title}",
    "description": "{outline_desc}",
    "subsections": [
        {{
            "subsection title": "Overall Paradigm",
            "description": "Overview of the general framework and pipeline"
        }},
        {{
            "subsection title": "Stage/Component 1",
            "description": "Description of this stage or component",
            "subsubsections": [
                {{
                    "subsubsection title": "Method Type A",
                    "description": "E.g., Tuning-free methods including CoT, ReAct, etc."
                }},
                {{
                    "subsubsection title": "Method Type B",
                    "description": "E.g., Tuning-based methods including Toolformer, etc."
                }}
            ]
        }},
        {{
            "subsection title": "Stage/Component 2",
            "description": "Description of this stage or component",
            "subsubsections": [
                {{
                    "subsubsection title": "Approach A",
                    "description": "Specific approach with representative methods"
                }},
                {{
                    "subsubsection title": "Approach B",
                    "description": "Specific approach with representative methods"
                }}
            ]
        }}
    ]
}}
```

## Quality Checklist

Before outputting, verify:
- [ ] At least 4 subsections?
- [ ] If this is a "How...?" section, does it have sub-subsections?
- [ ] Each title is specific (not "Overview" or "Methods")?
- [ ] Descriptions mention specific techniques or methods?
- [ ] Consistent naming patterns (e.g., "Tuning-free" vs "Tuning-based")?

Now, here is the set of reference materials:
{paper}

So, draft the secondary outline with proper hierarchical depth: