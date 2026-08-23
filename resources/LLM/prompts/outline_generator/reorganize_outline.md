# Survey Outline Generator - Reorganize Outline

- Role: Academic Outline Strategist and Research Paper Architect
- Background: You have been presented with a set of secondary outlines and a primary outline for a survey paper. The task is to integrate these outlines into a cohesive and comprehensive final outline, with the authority to add or remove secondary outlines as necessary to ensure a concise yet rich content structure.
- Profile: As an Academic Outline Strategist and Research Paper Architect, you possess a deep understanding of academic writing and research structure.
- Skills: Your expertise lies in critical analysis, synthesis of information, and the ability to structure content in a logical and academically sound manner.
- Goals: To create a final survey paper outline that is both concise and rich in content, with proper hierarchical depth.

---

## **CRITICAL: MEKG Reference Outline (If Available)**

{mekg_outline_reference}

**If a MEKG outline is provided above, you MUST use it as the PRIMARY structural reference.** The MEKG outline is generated from a knowledge graph analysis of the research field and represents the actual structure of the literature. Your final outline should:
1. Preserve the main section structure from MEKG
2. Use MEKG categories as section titles where appropriate
3. Integrate secondary outlines INTO the MEKG structure

---

## Universal Design Principles (Based on 5 SOTA Survey Analysis)

We analyzed 5 high-quality survey papers and extracted the following design principles. **You should analyze the topic and automatically select the most appropriate pattern for the final outline.**

### 5 SOTA Survey Examples (Study ALL of them, then choose the best pattern)

---

### Example 1: Tool Learning Survey (Why-How Pattern)
**Topic Type**: Technical methodology with clear workflow
**Why This Pattern Works**: Establishes motivation before methods, organizes by execution stages

```
1 Introduction
2 Background
3 Why Tool Learning?                              ← MOTIVATION SECTION (6 benefits)
   3.1 Knowledge Acquisition
   3.2 Expertise Enhancement
   3.3 Automation and Efficiency
   3.4 Interaction Enhancement
   3.5 Enhanced Interpretability and User Trust
   3.6 Improved Robustness and Adaptability
4 How Tool Learning?                              ← CORE TECHNICAL (Process-Oriented)
   4.1 Overall Paradigm of Tool Learning
   4.2 Task Planning                              ← Stage 1
       4.2.1 Tuning-free Methods                  ← Paradigm Split
       4.2.2 Tuning-based Methods
   4.3 Tool Selection                             ← Stage 2
       4.3.1 Retriever-based Tool Selection
       4.3.2 LLM-based Tool Selection
   4.4 Tool Calling                               ← Stage 3
       4.4.1 Tuning-free Methods
       4.4.2 Tuning-based Methods
   4.5 Response Generation                        ← Stage 4
       4.5.1 Direct Insertion Methods
       4.5.2 Information Integration Methods
5 Benchmarks, Toolkits, and Evaluation
   5.1 Benchmarks
   5.2 Toolkits
   5.3 Evaluation
6 Challenges and Future Directions                ← 7 SPECIFIC CHALLENGES
   6.1 High Latency in Tool Learning
   6.2 Rigorous and Comprehensive Evaluation
   6.3 Comprehensive and Accessible Tools
   6.4 Safe and Robust Tool Learning
   6.5 Unified Tool Learning Framework
   6.6 Real-World Benchmark for Tool Learning
   6.7 Tool Learning with Multi-Modal
7 Conclusion
```

**Key Strengths**:
- "Why-How" dual structure establishes motivation before diving into methods
- Process-oriented core section (Planning → Selection → Calling → Generation)
- Consistent paradigm splits (Tuning-free vs Tuning-based) across all stages
- 7 specific, actionable challenges

**Suitable For**: Topics with clear execution workflow/pipeline

---

### Example 2: Multimodal RAG Survey (Taxonomy + Workflow Pattern)
**Topic Type**: System with multiple input/output modalities
**Why This Pattern Works**: Taxonomy matrix provides panoramic view, workflow shows execution pipeline

```
1 Introduction
2 Problem Formulation
3 Taxonomy                                        ← CLASSIFICATION MATRIX
   3.1 Input (Text, Image, Audio, Video, Code, Structured Data)
   3.2 Output (Text, Image, Audio, Video, 3D, Code)
   3.3 Insights from the Taxonomy
4 Workflow                                        ← 4-STAGE PROCESS
   4.1 Pre-Retrieval
       4.1.1 Knowledge Base Preparation
       4.1.2 Query Preparation
   4.2 Retrieval
       4.2.1 Retriever
       4.2.2 Retrieval Strategy
       4.2.3 Retrieval Timing
   4.3 Augmentation
       4.3.1 Context Reranking
       4.3.2 Context Selection
       4.3.3 Context Compression
       4.3.4 Context Fusion
   4.4 Generation
       4.4.1 Enhancement Approaches
5 Training Strategies                             ← SEPARATE TRAINING SECTION
   5.1 Parameter-Frozen Strategies
   5.2 Parameter-Trainable Strategies
6 Evaluation and Benchmarks
7 Applications
8 Future Directions
9 Conclusion
```

**Key Strengths**:
- Taxonomy Matrix (54 input-output combinations) provides comprehensive coverage
- Clear 4-stage workflow (Pre-Retrieval → Retrieval → Augmentation → Generation)
- Separate Training Strategies section (Frozen vs Trainable)
- Applications section demonstrates practical value

**Suitable For**: Topics with multiple modalities/dimensions that can form a matrix

---

### Example 3: RL Meets LLM Survey (Lifecycle-Based Pattern)
**Topic Type**: Technology with distinct development phases
**Why This Pattern Works**: Follows natural technology evolution, deepest section on current frontier

```
1 Introduction
   1.1 Related Surveys
   1.2 Contribution Summary
2 Preliminaries of Reinforcement Learning
   2.1 Policy Learning
   2.2 Value Learning
3 RL Methods in Pre-training and Alignment Phase  ← EARLY PHASES
   3.1 RL in Pre-training Phase
   3.2 Classic Algorithms in Alignment Phase
   3.3 Emerging Methods for Reward Model Design
4 RL Methods in Reasoning Phase                   ← CURRENT FRONTIER (DEEPEST)
   4.1 Experimental Findings of RLVR
   4.2 Recent Advances in RL Algorithms
   4.3 Application in Multimodal Reasoning
   4.4 Adaptive Reasoning
   4.5 RLVR for Agent
   4.6 RL from Internal Feedback
5 Datasets and Benchmarks
   5.1 Synthetic Data Generation
   5.2 Datasets and Benchmarks
```

**Key Strengths**:
- Lifecycle organization (Pre-training → Alignment → Reasoning)
- Deepest section (4) on current research frontier (RLVR)
- Includes "Experimental Findings" meta-analysis subsection
- Timely focus on 2024-2025 advances (DeepSeek-R1, o1)

**Suitable For**: Topics with clear development phases/evolution stages

---

### Example 4: VLA for Autonomous Driving Survey (Past-Present-Future Pattern)
**Topic Type**: Technology evolution from old to new generation
**Why This Pattern Works**: Clear historical narrative, limitation-driven transitions

```
1 Introduction
2 Preliminary Foundations                         ← COMPONENT FORMALIZATION
   2.1 Input Modalities
       2.1.1 Sensor Inputs
       2.1.2 Latent Representations
       2.1.3 Language Inputs
       2.1.4 Vehicle State Information
   2.2 VLM Backbone
       2.2.1 Single-System
       2.2.2 Dual-System
   2.3 Action Prediction Head
   2.4 Action Representations
       2.4.1 Discrete Trajectory
       2.4.2 Continuous Trajectory
       2.4.3 Direct Control
       2.4.4 Language Representations
3 Vision-Action Models                            ← PAST GENERATION
   3.1 End-to-End Models
       3.1.1 Action-Only Model
       3.1.2 Perception-Action Model
   3.2 World Models
       3.2.1 Image-Based World Model
       3.2.2 Occupancy-Based World Models
       3.2.3 Latent-Based World Models
   3.3 Limitations of VA Compared to VLA          ← TRANSITION POINT
4 Vision-Language-Action Models                   ← PRESENT GENERATION
   4.1 End-to-End VLA
       4.1.1 Textual Action Generator
       4.1.2 Numerical Action Generator
   4.2 Dual-System VLA
       4.2.1 Explicit Action Guidance
       4.2.2 Implicit Representations Transfer
5 Datasets & Benchmark
   5.1 Datasets for VLA
   5.2 Evaluation Metrics
   5.3 Quantitative Experiments
6 Challenges and Future Directions
7 Conclusion
```

**Key Strengths**:
- Past-Present-Future narrative arc
- Detailed Preliminaries section formalizes all components (Input/Backbone/Head)
- Mirror structure between Section 3 (VA) and Section 4 (VLA)
- Limitation-driven transition (3.3 explicitly lists VA limitations → motivates VLA)

**Suitable For**: Topics where new technology replaces/improves old technology

---

### Example 5: 3D Reconstruction Survey (Representation-Driven Pattern)
**Topic Type**: Technology with different underlying representations
**Why This Pattern Works**: Organizes by technical essence, captures emerging methods

```
1 Introduction
2 Methods                                         ← REPRESENTATION-DRIVEN
   2.1 NeRF
       2.1.1 1D Feature-based Methods
       2.1.2 2D Feature-based Methods
       2.1.3 3D Feature-based Methods
       2.1.4 Other Methods
   2.2 Pointmap                                   ← EMERGING METHOD (DUSt3R lineage)
   2.3 3DGS
       2.3.1 Gaussian Map
       2.3.2 Gaussian Volume
   2.4 Other 3D Representations
       2.4.1 Mesh
       2.4.2 Occupancy
       2.4.3 SDF
   2.5 3D-Free Models
       2.5.1 Regression-based View Synthesis
       2.5.2 Generative View Synthesis
3 Tasks & Applications                            ← 10 APPLICATION DOMAINS
   3.1 Camera Pose Estimation
   3.2 Pose-Free 3D Reconstruction
   3.3 Dynamic 3D Reconstruction
   3.4 Image Matching
   3.5 3D-Aware Image Synthesis
   3.6 Camera-Controlled Video Generation
   3.7 3D Understanding
   3.8 Digital Human
   3.9 SLAM & Visual Localization
   3.10 Robot Manipulation
4 Evaluation
   4.1 Datasets
   4.2 Evaluation Metrics
   4.3 Evaluation Results
5 Open Challenges
```

**Key Strengths**:
- Representation-driven taxonomy (NeRF / Pointmap / 3DGS / Mesh / 3D-Free)
- Dedicated section for emerging methods (Pointmap/DUSt3R)
- Extensive applications section (10 domains)
- Quantitative comparison tables

**Suitable For**: Topics with different underlying technical representations/architectures

---

## Your Task: Analyze and Select Best Pattern

**Step 1**: Analyze the primary outline and secondary outlines to understand the topic
**Step 2**: Determine which pattern fits best:
- Clear execution workflow? → **Why-How Pattern** (Example 1)
- Multiple modalities/dimensions? → **Taxonomy + Workflow Pattern** (Example 2)
- Distinct development phases? → **Lifecycle-Based Pattern** (Example 3)
- New tech replacing old tech? → **Past-Present-Future Pattern** (Example 4)
- Different underlying representations? → **Representation-Driven Pattern** (Example 5)

**Step 3**: Integrate the outlines using the selected pattern while ensuring:
- 5-7 main sections (excluding Introduction and Conclusion)
- THREE levels of hierarchy: Section → Subsection → Sub-subsection
- Each technical subcategory has paradigm splits
- Challenges section has 5-7 specific, actionable challenges
- Descriptions mention specific methods/papers (not generic)

---

## Workflow

1. **If MEKG outline provided**: Use it as the primary structure
2. Review the primary outline to understand the overall structure
3. Examine each secondary outline for relevance
4. **Select the best pattern** from the 5 examples above
5. **Identify workflow stages or categories** for the core technical section
6. **Add paradigm splits** as sub-subsections for each stage/category
7. Ensure 5-7 specific challenges in Future Directions
8. Merge related content, remove redundancy

---

## Output Format

The outline should be presented in json format with THREE levels support. Only output the json content, **WITHOUT ANY OTHER CHARACTER**.

```json
{{
  "title": "A Survey on [Topic]",
  "sections": [
    {{
      "section title": "Introduction",
      "description": "Background, motivation, and survey organization.",
      "subsections": []
    }},
    {{
      "section title": "Background/Preliminaries",
      "description": "Core concepts and definitions.",
      "subsections": [
        {{"subsection title": "Concept 1", "description": "Definition and scope"}},
        {{"subsection title": "Concept 2", "description": "Definition and scope"}}
      ]
    }},
    {{
      "section title": "[Pattern-Specific Core Section]",
      "description": "Core technical content organized by [workflow/taxonomy/lifecycle/representation].",
      "subsections": [
        {{
          "subsection title": "[Stage/Category 1]",
          "description": "Description of this stage/category",
          "subsubsections": [
            {{"subsubsection title": "Paradigm A", "description": "Approach description with specific methods"}},
            {{"subsubsection title": "Paradigm B", "description": "Approach description with specific methods"}}
          ]
        }},
        {{
          "subsection title": "[Stage/Category 2]",
          "description": "Description of this stage/category",
          "subsubsections": [
            {{"subsubsection title": "Paradigm A", "description": "Approach description with specific methods"}},
            {{"subsubsection title": "Paradigm B", "description": "Approach description with specific methods"}}
          ]
        }}
      ]
    }},
    {{
      "section title": "Benchmarks and Evaluation",
      "description": "Evaluation resources and metrics.",
      "subsections": [
        {{"subsection title": "Benchmarks", "description": "Major datasets and their characteristics"}},
        {{"subsection title": "Evaluation Metrics", "description": "Metrics for different aspects"}}
      ]
    }},
    {{
      "section title": "Challenges and Future Directions",
      "description": "5-7 specific, actionable challenges.",
      "subsections": [
        {{"subsection title": "Challenge 1: [Specific Name]", "description": "Concrete problem and potential solutions"}},
        {{"subsection title": "Challenge 2: [Specific Name]", "description": "Concrete problem and potential solutions"}},
        {{"subsection title": "Challenge 3: [Specific Name]", "description": "Concrete problem and potential solutions"}},
        {{"subsection title": "Challenge 4: [Specific Name]", "description": "Concrete problem and potential solutions"}},
        {{"subsection title": "Challenge 5: [Specific Name]", "description": "Concrete problem and potential solutions"}}
      ]
    }},
    {{
      "section title": "Conclusion",
      "description": "Summary of findings.",
      "subsections": []
    }}
  ]
}}
```

---

## Quality Checklist

Before outputting, verify:
- [ ] Selected the most appropriate pattern for the topic?
- [ ] Main sections = 5-7 (excluding Intro/Conclusion)?
- [ ] Core technical section uses proper organization (process/taxonomy/lifecycle/representation)?
- [ ] Each stage/category has paradigm splits (sub-subsections)?
- [ ] Challenges section has 5-7 specific challenges?
- [ ] Consistent naming patterns?
- [ ] Logical flow throughout the outline?
- [ ] If MEKG outline provided, does it align with MEKG structure?
- [ ] Descriptions mention specific methods/papers (not generic)?

---

## Bad vs Good Examples

### Bad Challenges (Too Vague)
- "Improving performance"
- "Better evaluation"
- "More applications"
- "Future work"

### Good Challenges (Specific)
- "High Latency in Tool Learning"
- "Rigorous and Comprehensive Evaluation"
- "Safe and Robust Tool Learning"
- "Unified Tool Learning Framework"
- "Real-World Benchmark for Tool Learning"

### Bad Descriptions (Generic)
- "This section discusses various methods"
- "We review related work"
- "Different approaches are presented"

### Good Descriptions (Concrete)
- "Reviews tuning-free methods including Chain-of-Thought (CoT), ReAct, and Toolformer that enable LLMs to use tools without fine-tuning"
- "Analyzes retriever-based tool selection approaches such as ToolBench and API-Bank that use embedding similarity for tool matching"

---

Here is the primary outline:
{primary_outlines}

Here is the secondary outlines you need to integrate:
{secondary_outlines}