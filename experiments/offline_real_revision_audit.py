from __future__ import annotations

import json
import math
import itertools
import re
import statistics
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import networkx as nx


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "minimal_real_revision_20260524"
ARTIFACT_COMPARISON_ROWS = ROOT / "outputs" / "artifact_level_comparison_20260524" / "artifact_level_comparison_rows.csv"


ARCHIVED_RUNS: List[Dict[str, str]] = [
    {"id": "2025-12-23-1426_Large_Language_Model", "label": "Large Language Model Function Calling"},
    {"id": "2025-12-23-2215_Document_Visual_Ques", "label": "Document Visual Question Answering"},
    {"id": "2025-12-23-2226_Memory_in_the_Age_of", "label": "Memory in the Age of AI Agents"},
    {"id": "20251224_150533_b6e78791", "label": "Embodied Question Answering in City Airspace (run 1)"},
    {"id": "20251224_191320_a9e4ed89", "label": "Text-to-SQL Agent"},
    {"id": "20251224_203155_24d6a93b", "label": "Embodied Question Answering in City Airspace (run 2)"},
    {"id": "20251224_204059_d990305f", "label": "Approach of Document Question Answer"},
    {"id": "20251227_090841_b5a8b031", "label": "Agent"},
]

FRESH_RUNS: List[Dict[str, str]] = [
    {"id": "20260523_225649_stable_glm_smoke_2506_12689v2", "label": "GLM fresh smoke"},
    {"id": "20260524_003805_stable_qwen_smoke_2506_12689v2", "label": "Qwen fresh smoke"},
]

SCISAGE_PARTIAL = ROOT / "outputs" / "scisage_outline_only_live_20260524" / "scisage_outline_live_result.json"


SECTION_STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "for", "in", "on", "to", "with", "by", "from", "via",
    "using", "based", "approach", "approaches", "framework", "frameworks", "survey",
    "comprehensive", "why", "how", "data", "resources", "system", "optimization", "background",
    "preliminaries", "future", "directions", "challenges", "introduction", "conclusion",
    "benchmarks", "evaluation", "perspective", "oriented", "methods", "method", "applications",
    "architecture", "architectures", "trends", "overview", "foundational", "technical", "systems",
}

SECTION_EXCLUDE_TITLES = {
    "Introduction",
    "Conclusion",
    "Conclusion and Future Directions",
}

SEMANTIC_RELATIONS = ("extends", "improves", "applies")
EDGE_CONFIDENCE_THRESHOLDS = (0.5, 0.7, 0.9)

ALL_RELATION_TYPES = frozenset(
    {
        "supports",
        "same_author",
        "shares_architecture",
        "is_instance_of",
        "is_variant_of",
        "compares",
        "extends",
        "improves",
        "applies",
        "refutes",
    }
)

RELATION_FAMILY_VARIANTS = {
    "full": None,
    "no_support": frozenset(ALL_RELATION_TYPES - {"supports"}),
    "structural_only": frozenset(
        {
            "supports",
            "same_author",
            "shares_architecture",
            "is_instance_of",
            "is_variant_of",
            "compares",
        }
    ),
    "semantic_only": frozenset({"extends", "improves", "applies", "refutes"}),
}

MANUAL_SPOT_AUDIT_RUN_ID = "2025-12-23-1426_Large_Language_Model"
GENERATED_CITATION_SPOT_AUDIT_RUN_ID = "20251224_204059_d990305f"
FAILURE_MODE_MAP = {
    "shared_benchmark_theme_only": "topical_overlap_without_explicit_lineage",
    "evaluation_theme_overlap": "topical_overlap_without_explicit_lineage",
    "personalized_tool_learning_follow_on": "topical_overlap_without_explicit_lineage",
    "generic_tool_use_overlap": "topical_overlap_without_explicit_lineage",
    "efficiency_overlap_without_direct_lineage": "topical_overlap_without_explicit_lineage",
    "shared_tool_context_optimization": "topical_overlap_without_explicit_lineage",
    "planning_vs_api_call_quality_overlap": "topical_overlap_without_explicit_lineage",
    "benchmark_method_overlap": "topical_overlap_without_explicit_lineage",
    "multi_turn_tool_use_overlap": "topical_overlap_without_explicit_lineage",
    "domain_specific_function_calling": "topical_overlap_without_explicit_lineage",
    "educational_domain_application": "topical_overlap_without_explicit_lineage",
    "survey_target_mismatch": "target_role_mismatch",
    "method_to_dataset_mismatch": "target_role_mismatch",
    "method_to_benchmark_mismatch": "target_role_mismatch",
    "cross_task_mismatch": "cross_task_mismatch",
    "temporal_reversal": "temporal_reversal",
}

FAILURE_MODE_DISPLAY = {
    "topical_overlap_without_explicit_lineage": "topical-overlap without explicit lineage",
    "target_role_mismatch": "target-role mismatch",
    "cross_task_mismatch": "cross-task mismatch",
    "temporal_reversal": "temporal reversal",
}

GENERATED_CITATION_ISSUE_DISPLAY = {
    "well_supported": "well supported",
    "temporal_trend_overgeneralization": "temporal-trend overgeneralization",
    "detail_not_evident_in_abstract": "detail not evident in abstract",
    "formalization_not_in_source": "formalization not in source",
}

GENERATED_CITATION_SUPPORT_SPOT_AUDIT = [
    {
        "citation_key": "arXiv_2510.13366",
        "anchor_text": "architectural landscape shifted fundamentally from rule-based systems and encoder-decoder frameworks toward scalable, decoder-only Large Language Models",
        "label": "supported",
        "issue_tag": "well_supported",
        "rationale": "The cited survey abstract explicitly contrasts earlier encoder-decoder approaches with newer decoder-only LLMs in document AI.",
    },
    {
        "citation_key": "arXiv_2512.12694",
        "anchor_text": "Traditional OCR-based pipelines frequently fail when processing historical archives or low-quality scans",
        "label": "supported",
        "issue_tag": "well_supported",
        "rationale": "The cited paper abstract directly highlights OCR corruption and temporal language drift in noisy historical document QA.",
    },
    {
        "citation_key": "arXiv_2510.15253",
        "anchor_text": "This scalability challenge has precipitated a surge in research focused on Multimodal Retrieval-Augmented Generation",
        "label": "partial",
        "issue_tag": "temporal_trend_overgeneralization",
        "rationale": "The cited survey supports the importance of multimodal RAG for document understanding, but the stronger trend claim about a 2024--2025 surge is not directly established in the abstract.",
    },
    {
        "citation_key": "arXiv_2510.27261",
        "anchor_text": "shifting the retrieval unit from entire pages to specific semantic regions significantly reduces context pollution and improves answer fidelity",
        "label": "supported",
        "issue_tag": "well_supported",
        "rationale": "The RegionRAG abstract directly motivates moving from full-document retrieval to region-level retrieval because irrelevant context degrades performance.",
    },
    {
        "citation_key": "arXiv_2510.14592",
        "anchor_text": "hybrid retrieval architectures like MAHA, which integrate semantic vector search with structured knowledge graphs",
        "label": "supported",
        "issue_tag": "well_supported",
        "rationale": "The MAHA abstract explicitly describes integrating dense vector retrieval with a modality-aware knowledge graph for multimodal QA.",
    },
    {
        "citation_key": "arXiv_2509.10129",
        "anchor_text": "modern generative Vision-Language Models (VLMs) achieve high textual accuracy, they frequently suffer from poor spatial grounding",
        "label": "supported",
        "issue_tag": "well_supported",
        "rationale": "The cited abstract explicitly emphasizes the gap between textual answer correctness and reliable spatial localization.",
    },
    {
        "citation_key": "arXiv_2510.12668",
        "anchor_text": "shifts the storage of external knowledge from the context window to the model's parameters themselves",
        "label": "supported",
        "issue_tag": "well_supported",
        "rationale": "The PRAG abstract directly states that documents are encoded as model parameters such as LoRA modules rather than passed only in the input context.",
    },
    {
        "citation_key": "arXiv_2510.13366",
        "anchor_text": "DocQA operates on a multi-modal tuple",
        "label": "unsupported",
        "issue_tag": "formalization_not_in_source",
        "rationale": "The cited survey abstract does not supply this five-modality tuple formalization, so the generated statement is more specific than the source evidence.",
    },
    {
        "citation_key": "arXiv_2509.10129",
        "anchor_text": "Spatial grounding is typically formalized through normalized bounding box coordinates",
        "label": "partial",
        "issue_tag": "detail_not_evident_in_abstract",
        "rationale": "The cited abstract supports bounding-box localization as a task, but not the more specific normalized-coordinate convention described in the generated sentence.",
    },
    {
        "citation_key": "arXiv_2512.12694",
        "anchor_text": "OCR noise, archaic orthography, and complex multi-column layouts",
        "label": "partial",
        "issue_tag": "detail_not_evident_in_abstract",
        "rationale": "The cited abstract supports OCR corruption and orthographic variation in historical documents, but the multi-column-layout detail is not clearly stated there.",
    },
    {
        "citation_key": "arXiv_2511.11468",
        "anchor_text": "redefines the task to include an \"unanswerability detection\" constraint",
        "label": "supported",
        "issue_tag": "well_supported",
        "rationale": "The cited benchmark abstract explicitly focuses on detecting plausible but unanswerable questions in visually rich documents.",
    },
    {
        "citation_key": "arXiv_2510.14337",
        "anchor_text": "can be modeled as a finite-horizon Markov Decision Process",
        "label": "supported",
        "issue_tag": "well_supported",
        "rationale": "The Stop-RAG abstract explicitly casts iterative RAG as a finite-horizon Markov decision process.",
    },
]

MANUAL_CITATION_SPOT_AUDIT = [
    {
        "relation_type": "extends",
        "source_title": "CallNavi, A Challenge and Empirical Study on LLM Function Calling and Routing",
        "target_title": "GTA: A Benchmark for General Tool Agents",
        "label": "partial",
        "issue_tag": "shared_benchmark_theme_only",
        "rationale": "Both are benchmark/function-calling centered, but the abstract does not explicitly state inheritance.",
    },
    {
        "relation_type": "extends",
        "source_title": "ComplexFuncBench: Exploring Multi-Step and Constrained Function Calling under Long-Context Scenario",
        "target_title": "Quality Matters: Evaluating Synthetic Data for Tool-Using LLMs",
        "label": "partial",
        "issue_tag": "evaluation_theme_overlap",
        "rationale": "The two papers share a tool-learning evaluation theme, but the abstract does not explicitly ground an extends relation.",
    },
    {
        "relation_type": "extends",
        "source_title": "Evaluating LLMs on Sequential API Call Through Automated Test Generation",
        "target_title": "Large Language Models as Zero-shot Dialogue State Tracker through Function Calling",
        "label": "supported",
        "issue_tag": "sequential_function_calling_follow_on",
        "rationale": "Both focus on function-calling evaluation for sequential API-style behavior, which makes the inheritance claim plausible.",
    },
    {
        "relation_type": "extends",
        "source_title": "RRTL: Red Teaming Reasoning Large Language Models in Tool Learning",
        "target_title": "CRITICTOOL: Evaluating Self-Critique Capabilities of Large Language Models in Tool-Calling Error Scenarios",
        "label": "supported",
        "issue_tag": "tool_error_analysis_follow_on",
        "rationale": "The source and target are both error-analysis / red-teaming studies of tool-calling behavior.",
    },
    {
        "relation_type": "extends",
        "source_title": "PEToolLLM: Towards Personalized Tool Learning in Large Language Models",
        "target_title": "Facilitating Multi-turn Function Calling for LLMs via Compositional Instruction Tuning",
        "label": "partial",
        "issue_tag": "personalized_tool_learning_follow_on",
        "rationale": "The source narrows generic tool learning to personalized settings, but the abstract does not make a direct inheritance claim over the target method.",
    },
    {
        "relation_type": "extends",
        "source_title": "AppBench: Planning of Multiple APIs from Various APPs for Complex User Instruction",
        "target_title": "Toolformer: Language Models Can Teach Themselves to Use Tools",
        "label": "supported",
        "issue_tag": "multi_api_follow_on_from_tool_use",
        "rationale": "The source clearly treats general tool use as a starting point and extends it to multi-app, graph-structured API planning.",
    },
    {
        "relation_type": "extends",
        "source_title": "ToolHaystack: Stress-Testing Tool-Augmented Language Models in Realistic Long-Term Interactions",
        "target_title": "LLM With Tools: A Survey",
        "label": "unsupported",
        "issue_tag": "survey_target_mismatch",
        "rationale": "The target is a survey rather than a concrete technical precursor, so an extends relation is not directly supported by the paper pair.",
    },
    {
        "relation_type": "extends",
        "source_title": "Repairing Tool Calls Using Post-tool Execution Reflection and RAG",
        "target_title": "Large Language Models as Zero-shot Dialogue State Tracker through Function Calling",
        "label": "unsupported",
        "issue_tag": "cross_task_mismatch",
        "rationale": "The source studies post-execution tool-call repair for infrastructure workflows, whereas the target focuses on dialogue state tracking through function calling.",
    },
    {
        "relation_type": "improves",
        "source_title": "ToolACE-DEV: Self-Improving Tool Learning via Decomposition and EVolution",
        "target_title": "NesTools: A Dataset for Evaluating Nested Tool Learning Abilities of Large Language Models",
        "label": "unsupported",
        "issue_tag": "method_to_dataset_mismatch",
        "rationale": "The source is a method paper and the target is a dataset paper; the abstract does not support an improves relation.",
    },
    {
        "relation_type": "improves",
        "source_title": "Confucius: Iterative Tool Learning from Introspection Feedback by Easy-to-Difficult Curriculum",
        "target_title": "Tool Preferences in Agentic LLMs are Unreliable",
        "label": "unsupported",
        "issue_tag": "temporal_reversal",
        "rationale": "The target is published later than the source, and the abstract text does not justify a forward improvement relation.",
    },
    {
        "relation_type": "improves",
        "source_title": "Asynchronous LLM Function Calling",
        "target_title": "Graph-ToolFormer: To Empower LLMs with Graph Reasoning Ability via Prompt Augmented by ChatGPT",
        "label": "partial",
        "issue_tag": "generic_tool_use_overlap",
        "rationale": "Both discuss tool/function-calling improvements, but the graph-reasoning connection is indirect in the abstract.",
    },
    {
        "relation_type": "improves",
        "source_title": "Divide-Then-Aggregate: An Efficient Tool Learning Method via Parallel Tool Invocation",
        "target_title": "Achieving Tool Calling Functionality in LLMs Using Only Prompt Engineering Without Fine-Tuning",
        "label": "partial",
        "issue_tag": "efficiency_overlap_without_direct_lineage",
        "rationale": "The papers are thematically aligned on tool-calling efficiency, but the abstract does not spell out a direct improvement relation.",
    },
    {
        "relation_type": "improves",
        "source_title": "Verification-Guided Context Optimization for Tool Calling via Hierarchical LLMs-as-Editors",
        "target_title": "Middleware for LLMs: Tools Are Instrumental for Language Agents in Complex Environments",
        "label": "partial",
        "issue_tag": "shared_tool_context_optimization",
        "rationale": "Both papers focus on making tool use more robust in complex environments, but the source does not explicitly claim improvement over the target framework.",
    },
    {
        "relation_type": "improves",
        "source_title": "Distilling LLM Agent into Small Models with Retrieval and Code Tools",
        "target_title": "Octopus: On-device language model for function calling of software APIs",
        "label": "supported",
        "issue_tag": "small_model_function_calling_improvement",
        "rationale": "Both papers optimize smaller tool-using models, and the source explicitly frames itself as improving practical tool-use performance under tighter model budgets.",
    },
    {
        "relation_type": "improves",
        "source_title": "CATP-LLM: Empowering Large Language Models for Cost-Aware Tool Planning",
        "target_title": "Gorilla: Large Language Model Connected with Massive APIs",
        "label": "partial",
        "issue_tag": "planning_vs_api_call_quality_overlap",
        "rationale": "The source improves a different part of the tool-use pipeline---cost-aware planning rather than API-call generation accuracy---so the link is plausible but indirect.",
    },
    {
        "relation_type": "improves",
        "source_title": "Improving Large Language Models Function Calling and Interpretability via Guided-Structured Templates",
        "target_title": "AppBench: Planning of Multiple APIs from Various APPs for Complex User Instruction",
        "label": "unsupported",
        "issue_tag": "method_to_benchmark_mismatch",
        "rationale": "The target is a benchmark, not a precursor method that the source clearly improves upon.",
    },
    {
        "relation_type": "applies",
        "source_title": "MCP-Bench: Benchmarking Tool-Using LLM Agents with Complex Real-World Tasks via MCP Servers",
        "target_title": "Adapting While Learning: Grounding LLMs for Scientific Problems with Intelligent Tool Usage Adaptation",
        "label": "partial",
        "issue_tag": "benchmark_method_overlap",
        "rationale": "The two works share benchmark-and-adaptation framing, but the abstract does not explicitly support an applies relation.",
    },
    {
        "relation_type": "applies",
        "source_title": "CheMatAgent: Enhancing LLMs for Chemistry and Materials Science through Tree-Search Based Tool Learning",
        "target_title": "Toolformer: Language Models Can Teach Themselves to Use Tools",
        "label": "supported",
        "issue_tag": "downstream_domain_application",
        "rationale": "The source explicitly instantiates tool learning in a downstream scientific domain, which matches an apply-style relation.",
    },
    {
        "relation_type": "applies",
        "source_title": "CarbonCall: Sustainability-Aware Function Calling for Large Language Models on Edge Devices",
        "target_title": "MINT: Evaluating LLMs in Multi-turn Interaction with Tools and Language Feedback",
        "label": "partial",
        "issue_tag": "multi_turn_tool_use_overlap",
        "rationale": "Both are multi-turn tool-use papers, but the source abstract does not explicitly claim it applies the target work.",
    },
    {
        "relation_type": "applies",
        "source_title": "Connecting Large Language Model Agent to High Performance Computing Resource",
        "target_title": "Evaluating and Improving Tool-Augmented Computation-Intensive Math Reasoning",
        "label": "supported",
        "issue_tag": "compute_intensive_application",
        "rationale": "The source directly describes a tool-augmented application to computationally intensive reasoning, matching the apply relation.",
    },
    {
        "relation_type": "applies",
        "source_title": "ScaleCall -- Agentic Tool Calling at Scale for Fintech: Challenges, Methods, and Deployment Insights",
        "target_title": "Toolformer: Language Models Can Teach Themselves to Use Tools",
        "label": "supported",
        "issue_tag": "enterprise_domain_application",
        "rationale": "The source clearly applies general tool-calling ideas to a regulated fintech environment with concrete deployment constraints.",
    },
    {
        "relation_type": "applies",
        "source_title": "You Have Thirteen Hours in Which to Solve the Labyrinth: Enhancing AI Game Masters with Function Calling",
        "target_title": "ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs",
        "label": "partial",
        "issue_tag": "domain_specific_function_calling",
        "rationale": "The source is a domain-specific use of function calling, but the target is a broad API-use framework rather than an explicit precursor used by the source.",
    },
    {
        "relation_type": "applies",
        "source_title": "Alopex: A Computational Framework for Enabling On-Device Function Calls with LLMs",
        "target_title": "Gorilla: Large Language Model Connected with Massive APIs",
        "label": "supported",
        "issue_tag": "on_device_api_application",
        "rationale": "The source adapts API-calling ideas to the on-device setting and remains close to the target's API-centric tool-use formulation.",
    },
    {
        "relation_type": "applies",
        "source_title": "EduMod-LLM: A Modular Approach for Designing Flexible and Transparent Educational Assistants",
        "target_title": "Learning to Use Tools via Cooperative and Interactive Agents",
        "label": "partial",
        "issue_tag": "educational_domain_application",
        "rationale": "The source applies modular function-calling ideas in educational QA, but the target's multi-agent training framework is only indirectly connected in the abstract.",
    },
]


@dataclass
class RunBundle:
    run_id: str
    label: str
    base_dir: Path
    mekg: Dict[str, Any]
    outline: Dict[str, Any]


def sanitize_key(key: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", str(key))


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]+", (text or "").lower())
    return [t for t in tokens if t not in SECTION_STOPWORDS and len(t) > 2]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def load_archived_runs() -> List[RunBundle]:
    runs: List[RunBundle] = []
    for item in ARCHIVED_RUNS:
        base = ROOT / "outputs" / item["id"]
        runs.append(
            RunBundle(
                run_id=item["id"],
                label=item["label"],
                base_dir=base,
                mekg=load_json(base / "mekg" / "mekg_data.json"),
                outline=load_json(base / "outline.json"),
            )
        )
    return runs


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def median(values: Iterable[float]) -> float:
    values = list(values)
    return statistics.median(values) if values else 0.0


def exact_paired_sign_flip_test(deltas: Iterable[float]) -> Dict[str, Any]:
    deltas = [float(x) for x in deltas]
    nonzero = [x for x in deltas if x != 0.0]
    observed_mean = mean(deltas)
    observed_median = median(deltas)

    if not nonzero:
        return {
            "sample_size": len(deltas),
            "nonzero_pairs": 0,
            "zero_pairs": len(deltas),
            "positive_pairs": 0,
            "negative_pairs": 0,
            "observed_mean_delta": observed_mean,
            "observed_median_delta": observed_median,
            "one_sided_p_greater": 1.0,
            "two_sided_p": 1.0,
        }

    signed_means: List[float] = []
    denom = len(nonzero)
    for signs in itertools.product((-1.0, 1.0), repeat=len(nonzero)):
        signed_means.append(sum(sign * abs(delta) for sign, delta in zip(signs, nonzero)) / denom)

    observed_nonzero_mean = mean(nonzero)
    observed_abs_mean = abs(observed_nonzero_mean)
    one_sided_p_greater = sum(1 for value in signed_means if value >= observed_nonzero_mean) / len(signed_means)
    two_sided_p = sum(1 for value in signed_means if abs(value) >= observed_abs_mean) / len(signed_means)

    return {
        "sample_size": len(deltas),
        "nonzero_pairs": len(nonzero),
        "zero_pairs": len(deltas) - len(nonzero),
        "positive_pairs": sum(1 for x in deltas if x > 0.0),
        "negative_pairs": sum(1 for x in deltas if x < 0.0),
        "observed_mean_delta": observed_mean,
        "observed_median_delta": observed_median,
        "one_sided_p_greater": one_sided_p_greater,
        "two_sided_p": two_sided_p,
    }


def compute_elbow_count(sorted_scores: List[float], default_count: int) -> int:
    if len(sorted_scores) < 10:
        return default_count
    first_diff = [sorted_scores[i - 1] - sorted_scores[i] for i in range(1, len(sorted_scores))]
    if not first_diff:
        return default_count
    second_diff = [first_diff[i - 1] - first_diff[i] for i in range(1, len(first_diff))]
    if not second_diff:
        return default_count
    max_second_diff = max(second_diff)
    if max_second_diff <= 0:
        return default_count
    elbow_index = second_diff.index(max_second_diff) + 2
    min_count = max(10, len(sorted_scores) // 20)
    max_count = min(200, len(sorted_scores) // 5)
    return max(min_count, min(elbow_index, max_count))


def build_idf(papers: List[Dict[str, Any]]) -> Dict[str, float]:
    df = Counter()
    total_docs = len(papers)
    for paper in papers:
        tokens = set(tokenize(f"{paper.get('title', '')} {paper.get('abstract', '')}"))
        for token in tokens:
            df[token] += 1
    return {token: math.log((total_docs + 1) / (count + 1)) + 1.0 for token, count in df.items()}


def lexical_scores(
    papers: List[Dict[str, Any]],
    idf: Dict[str, float],
    query_title: str,
    query_desc: str = "",
) -> List[Tuple[str, float]]:
    qtf = Counter(tokenize(f"{query_title} {query_desc}"))
    scores: List[Tuple[str, float]] = []
    for paper in papers:
        pid = sanitize_key(paper["id"])
        ptf = Counter(tokenize(f"{paper.get('title', '')} {paper.get('abstract', '')}"))
        score = 0.0
        for token in qtf:
            if ptf.get(token):
                score += idf.get(token, 1.0) * min(ptf[token], 3)
        scores.append((pid, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def compute_pagerank_centrality(mekg_data: Dict[str, Any]) -> Dict[str, float]:
    paper_ids = {sanitize_key(p["id"]) for p in mekg_data.get("papers", [])}
    graph = nx.DiGraph()
    graph.add_nodes_from(paper_ids)
    for rel in mekg_data.get("relations", []):
        src = sanitize_key(rel.get("source", ""))
        tgt = sanitize_key(rel.get("target", ""))
        if src in paper_ids and tgt in paper_ids:
            graph.add_edge(src, tgt)
    pagerank = nx.pagerank(graph) if graph.number_of_nodes() else {}
    if not pagerank:
        return {pid: 0.0 for pid in paper_ids}
    max_pr = max(pagerank.values()) or 1.0
    return {pid: score / max_pr for pid, score in pagerank.items()}


def relation_bonus(rel_type: str) -> float:
    if rel_type in {"extends", "improves", "applies", "supports", "is_variant_of", "is_instance_of", "shares_architecture", "compares"}:
        return 0.5
    return 0.15


def build_retrieval_context(run: RunBundle) -> Dict[str, Any]:
    papers = run.mekg["papers"]
    paper_map = {sanitize_key(p["id"]): p for p in papers}
    all_categories = {p.get("category", "") for p in papers if p.get("category")}
    idf = build_idf(papers)
    centrality = compute_pagerank_centrality(run.mekg)
    sorted_core = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
    core_papers = {pid for pid, _ in sorted_core[: max(1, len(sorted_core) // 5)]}
    return {
        "papers": papers,
        "paper_map": paper_map,
        "all_categories": all_categories,
        "idf": idf,
        "centrality": centrality,
        "core_papers": core_papers,
    }


def build_adjacency(
    run: RunBundle,
    paper_map: Dict[str, Dict[str, Any]],
    allowed_rel_types: frozenset[str] | set[str] | None = None,
) -> Tuple[Dict[str, List[Tuple[str, float, str]]], set[Tuple[str, str]]]:
    adjacency: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)
    undirected_relation_pairs: set[Tuple[str, str]] = set()
    for rel in run.mekg.get("relations", []):
        rel_type = rel.get("type", "")
        if allowed_rel_types is not None and rel_type not in allowed_rel_types:
            continue
        src = sanitize_key(rel.get("source", ""))
        tgt = sanitize_key(rel.get("target", ""))
        if src not in paper_map or tgt not in paper_map:
            continue
        conf = float(rel.get("confidence", 0.5) or 0.5)
        adjacency[src].append((tgt, conf, rel_type))
        adjacency[tgt].append((src, conf, rel_type))
        undirected_relation_pairs.add(tuple(sorted((src, tgt))))
    return adjacency, undirected_relation_pairs


def make_flat_ranker(papers: List[Dict[str, Any]], idf: Dict[str, float]):
    def flat_rank(section_title: str, section_desc: str) -> List[Tuple[str, float]]:
        return lexical_scores(papers, idf, section_title, section_desc)

    return flat_rank


def make_graph_ranker(
    papers: List[Dict[str, Any]],
    paper_map: Dict[str, Dict[str, Any]],
    idf: Dict[str, float],
    centrality: Dict[str, float],
    adjacency: Dict[str, List[Tuple[str, float, str]]],
    max_hops: int,
    overlap_weight: float = 0.8,
    seed_centrality_weight: float = 1.0,
    expansion_centrality_weight: float = 0.5,
):
    flat_rank = make_flat_ranker(papers, idf)

    def graph_rank(section_title: str, section_desc: str) -> Tuple[List[Tuple[str, float]], Dict[str, float]]:
        base = flat_rank(section_title, section_desc)
        query_tokens = set(tokenize(f"{section_title} {section_desc}"))
        scores: Dict[str, float] = {}
        expanded_nodes: set[str] = set()
        traversed_edges = 0

        for pid, lexical in base:
            paper = paper_map[pid]
            community_tokens = set(tokenize(f"{paper.get('category', '')} {paper.get('subcategory', '')}"))
            scores[pid] = (
                lexical
                + overlap_weight * len(query_tokens & community_tokens)
                + seed_centrality_weight * centrality.get(pid, 0.0)
            )

        frontier: List[Tuple[str, float, int]] = [(seed_id, seed_score, 0) for seed_id, seed_score in base[:5]]
        best_depth: Dict[str, int] = {seed_id: 0 for seed_id, _ in base[:5]}
        while frontier:
            node_id, seed_score, depth = frontier.pop(0)
            if depth >= max_hops:
                continue
            for nb_id, conf, rel_type in adjacency.get(node_id, []):
                hop = depth + 1
                traversed_edges += 1
                expanded_nodes.add(nb_id)
                scores[nb_id] = scores.get(nb_id, 0.0) + (0.5 ** (hop - 1)) * (
                    0.25 * seed_score + relation_bonus(rel_type) * conf + expansion_centrality_weight * centrality.get(nb_id, 0.0)
                )
                if best_depth.get(nb_id, 999) > hop:
                    best_depth[nb_id] = hop
                    frontier.append((nb_id, seed_score, hop))

        return sorted(scores.items(), key=lambda x: x[1], reverse=True), {
            "expanded_nodes": float(len(expanded_nodes)),
            "traversed_edges": float(traversed_edges),
        }

    return graph_rank


def evaluate_union_with_context(
    run: RunBundle,
    ranker,
    context: Dict[str, Any],
    undirected_relation_pairs: set[Tuple[str, str]],
    top_k: int = 5,
) -> Dict[str, Any]:
    paper_map = context["paper_map"]
    core_papers = context["core_papers"]
    all_categories = context["all_categories"]
    centrality = context["centrality"]

    union_ids: List[str] = []
    section_rows = []
    for section in run.outline.get("sections", []):
        title = section.get("title", "")
        if title in SECTION_EXCLUDE_TITLES:
            continue
        ranked = ranker(title, section.get("description", ""))
        chosen = [pid for pid, _ in ranked[:top_k]]
        union_ids.extend(chosen)
        section_rows.append({"title": title, "top_k_ids": chosen})

    unique_ids = list(dict.fromkeys(union_ids))
    retrieved_categories = {
        paper_map[pid].get("category", "")
        for pid in unique_ids
        if pid in paper_map and paper_map[pid].get("category")
    }

    pair_total = 0
    linked_pairs = 0
    for i in range(len(unique_ids)):
        for j in range(i + 1, len(unique_ids)):
            pair_total += 1
            if tuple(sorted((unique_ids[i], unique_ids[j]))) in undirected_relation_pairs:
                linked_pairs += 1

    return {
        "unique_papers": len(unique_ids),
        "core_paper_recall": len(set(unique_ids) & core_papers) / len(core_papers) if core_papers else 0.0,
        "community_coverage": len(retrieved_categories) / len(all_categories) if all_categories else 0.0,
        "avg_pagerank": mean(centrality.get(pid, 0.0) for pid in unique_ids),
        "relation_density": linked_pairs / pair_total if pair_total else 0.0,
        "sections_evaluated": len(section_rows),
        "section_topk": section_rows,
    }


def run_graph_retrieval_diagnostic(runs: List[RunBundle]) -> Dict[str, Any]:
    per_run: List[Dict[str, Any]] = []

    for run in runs:
        context = build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]

        adjacency, undirected_relation_pairs = build_adjacency(run, paper_map)
        flat_rank = make_flat_ranker(papers, idf)
        graph_rank_1 = make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)
        graph_rank_2 = make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=2)
        graph_rank_no_overlap = make_graph_ranker(
            papers,
            paper_map,
            idf,
            centrality,
            adjacency,
            max_hops=1,
            overlap_weight=0.0,
        )
        graph_rank_no_centrality = make_graph_ranker(
            papers,
            paper_map,
            idf,
            centrality,
            adjacency,
            max_hops=1,
            seed_centrality_weight=0.0,
            expansion_centrality_weight=0.0,
        )
        graph_rank_no_expansion = make_graph_ranker(
            papers,
            paper_map,
            idf,
            centrality,
            adjacency,
            max_hops=0,
        )

        flat = evaluate_union_with_context(run, flat_rank, context, undirected_relation_pairs)
        one_hop = evaluate_union_with_context(run, lambda t, d: graph_rank_1(t, d)[0], context, undirected_relation_pairs)
        two_hop = evaluate_union_with_context(run, lambda t, d: graph_rank_2(t, d)[0], context, undirected_relation_pairs)
        no_overlap = evaluate_union_with_context(
            run,
            lambda t, d: graph_rank_no_overlap(t, d)[0],
            context,
            undirected_relation_pairs,
        )
        no_centrality = evaluate_union_with_context(
            run,
            lambda t, d: graph_rank_no_centrality(t, d)[0],
            context,
            undirected_relation_pairs,
        )
        no_expansion = evaluate_union_with_context(
            run,
            lambda t, d: graph_rank_no_expansion(t, d)[0],
            context,
            undirected_relation_pairs,
        )

        one_hop_traversal = []
        two_hop_traversal = []
        for section in run.outline.get("sections", []):
            title = section.get("title", "")
            if title in SECTION_EXCLUDE_TITLES:
                continue
            _, stats_1 = graph_rank_1(title, section.get("description", ""))
            _, stats_2 = graph_rank_2(title, section.get("description", ""))
            one_hop_traversal.append(stats_1)
            two_hop_traversal.append(stats_2)

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "flat": flat,
                "one_hop": {
                    **one_hop,
                    "avg_expanded_nodes": mean(row["expanded_nodes"] for row in one_hop_traversal),
                    "avg_traversed_edges": mean(row["traversed_edges"] for row in one_hop_traversal),
                },
                "two_hop": {
                    **two_hop,
                    "avg_expanded_nodes": mean(row["expanded_nodes"] for row in two_hop_traversal),
                    "avg_traversed_edges": mean(row["traversed_edges"] for row in two_hop_traversal),
                },
                "delta": {
                    "core_paper_recall": one_hop["core_paper_recall"] - flat["core_paper_recall"],
                    "community_coverage": one_hop["community_coverage"] - flat["community_coverage"],
                    "avg_pagerank": one_hop["avg_pagerank"] - flat["avg_pagerank"],
                    "relation_density": one_hop["relation_density"] - flat["relation_density"],
                    "unique_papers": one_hop["unique_papers"] - flat["unique_papers"],
                },
                "signal_component_ablation": {
                    "flat": flat,
                    "full": one_hop,
                    "no_overlap": no_overlap,
                    "no_centrality": no_centrality,
                    "no_expansion": no_expansion,
                },
            }
        )

    metrics = ["core_paper_recall", "community_coverage", "avg_pagerank", "relation_density", "unique_papers"]
    aggregate: Dict[str, Any] = {}
    paired_significance: Dict[str, Any] = {}
    for metric in metrics:
        flat_vals = [row["flat"][metric] for row in per_run]
        graph_vals = [row["one_hop"][metric] for row in per_run]
        deltas = [g - f for f, g in zip(flat_vals, graph_vals)]
        aggregate[metric] = {
            "flat_mean": mean(flat_vals),
            "graph_mean": mean(graph_vals),
            "delta_mean": mean(deltas),
            "graph_better_runs": sum(1 for f, g in zip(flat_vals, graph_vals) if g > f),
            "flat_better_runs": sum(1 for f, g in zip(flat_vals, graph_vals) if f > g),
            "ties": sum(1 for f, g in zip(flat_vals, graph_vals) if f == g),
        }
        paired_significance[metric] = exact_paired_sign_flip_test(deltas)

    depth_sweep: Dict[str, Any] = {
        "variants": ["flat", "one_hop", "two_hop"],
        "aggregate": {},
        "pairwise": {},
    }
    for variant in ["flat", "one_hop", "two_hop"]:
        depth_sweep["aggregate"][variant] = {}
        for metric in ["core_paper_recall", "community_coverage", "avg_pagerank", "relation_density", "unique_papers", "avg_expanded_nodes", "avg_traversed_edges"]:
            vals = [row[variant][metric] if metric in row[variant] else 0.0 for row in per_run]
            depth_sweep["aggregate"][variant][metric] = {
                "mean": mean(vals),
                "median": median(vals),
            }
    for left, right, key in [("flat", "one_hop", "flat_vs_one_hop"), ("one_hop", "two_hop", "one_hop_vs_two_hop")]:
        depth_sweep["pairwise"][key] = {}
        for metric in ["core_paper_recall", "community_coverage", "avg_pagerank", "relation_density", "unique_papers", "avg_expanded_nodes", "avg_traversed_edges"]:
            left_vals = [row[left][metric] if metric in row[left] else 0.0 for row in per_run]
            right_vals = [row[right][metric] if metric in row[right] else 0.0 for row in per_run]
            depth_sweep["pairwise"][key][metric] = {
                "left_mean": mean(left_vals),
                "right_mean": mean(right_vals),
                "delta_mean": mean(r - l for l, r in zip(left_vals, right_vals)),
                "right_better_runs": sum(1 for l, r in zip(left_vals, right_vals) if r > l),
                "left_better_runs": sum(1 for l, r in zip(left_vals, right_vals) if l > r),
                "ties": sum(1 for l, r in zip(left_vals, right_vals) if l == r),
            }

    signal_component_ablation: Dict[str, Any] = {
        "variants": ["flat", "full", "no_overlap", "no_centrality", "no_expansion"],
        "aggregate": {},
        "pairwise_vs_full": {},
    }
    for variant in signal_component_ablation["variants"]:
        signal_component_ablation["aggregate"][variant] = {}
        for metric in metrics:
            vals = [row["signal_component_ablation"][variant][metric] for row in per_run]
            signal_component_ablation["aggregate"][variant][metric] = {
                "mean": mean(vals),
                "median": median(vals),
                "min": min(vals) if vals else 0.0,
                "max": max(vals) if vals else 0.0,
            }

    for variant in signal_component_ablation["variants"]:
        if variant == "full":
            continue
        signal_component_ablation["pairwise_vs_full"][variant] = {}
        for metric in metrics:
            full_vals = [row["signal_component_ablation"]["full"][metric] for row in per_run]
            variant_vals = [row["signal_component_ablation"][variant][metric] for row in per_run]
            deltas = [v - f for f, v in zip(full_vals, variant_vals)]
            signal_component_ablation["pairwise_vs_full"][variant][metric] = {
                "full_mean": mean(full_vals),
                "variant_mean": mean(variant_vals),
                "delta_mean": mean(deltas),
                "variant_better_runs": sum(1 for f, v in zip(full_vals, variant_vals) if v > f),
                "full_better_runs": sum(1 for f, v in zip(full_vals, variant_vals) if f > v),
                "ties": sum(1 for f, v in zip(full_vals, variant_vals) if f == v),
                "paired_significance": exact_paired_sign_flip_test(deltas),
            }

    return {
        "experiment_type": "offline_graph_retrieval_diagnostic",
        "scope_note": "Diagnostic retrieval-side ablation on archived artifacts; not a public benchmark.",
        "top_k_per_section": 5,
        "graph_variant": {
            "base": "lexical section-to-paper retrieval",
            "extra_signals": ["category/subcategory overlap", "PageRank centrality", "1-hop relation expansion from top lexical seeds"],
        },
        "per_run": per_run,
        "aggregate": aggregate,
        "paired_significance": paired_significance,
        "depth_sweep": depth_sweep,
        "signal_component_ablation": signal_component_ablation,
    }


def run_retrieval_budget_sweep(
    runs: List[RunBundle],
    budgets: Iterable[int] = (3, 5, 7),
) -> Dict[str, Any]:
    budget_list: List[int] = []
    for budget in budgets:
        budget_int = int(budget)
        if budget_int > 0 and budget_int not in budget_list:
            budget_list.append(budget_int)
    if not budget_list:
        budget_list = [5]

    per_run: List[Dict[str, Any]] = []

    for run in runs:
        context = build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]
        adjacency, undirected_relation_pairs = build_adjacency(run, paper_map)
        flat_rank = make_flat_ranker(papers, idf)
        graph_rank = make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)

        budget_rows: Dict[str, Any] = {}
        for budget in budget_list:
            flat_metrics = evaluate_union_with_context(
                run,
                flat_rank,
                context,
                undirected_relation_pairs,
                top_k=budget,
            )
            graph_metrics = evaluate_union_with_context(
                run,
                lambda t, d: graph_rank(t, d)[0],
                context,
                undirected_relation_pairs,
                top_k=budget,
            )
            budget_rows[str(budget)] = {
                "flat": flat_metrics,
                "graph": graph_metrics,
                "delta": {
                    "core_paper_recall": graph_metrics["core_paper_recall"] - flat_metrics["core_paper_recall"],
                    "community_coverage": graph_metrics["community_coverage"] - flat_metrics["community_coverage"],
                    "avg_pagerank": graph_metrics["avg_pagerank"] - flat_metrics["avg_pagerank"],
                    "relation_density": graph_metrics["relation_density"] - flat_metrics["relation_density"],
                    "unique_papers": graph_metrics["unique_papers"] - flat_metrics["unique_papers"],
                },
            }

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "budgets": budget_rows,
            }
        )

    metrics = ["core_paper_recall", "community_coverage", "avg_pagerank", "relation_density", "unique_papers"]
    aggregate: Dict[str, Any] = {}
    for budget in budget_list:
        key = str(budget)
        aggregate[key] = {}
        for metric in metrics:
            flat_vals = [row["budgets"][key]["flat"][metric] for row in per_run]
            graph_vals = [row["budgets"][key]["graph"][metric] for row in per_run]
            aggregate[key][metric] = {
                "flat_mean": mean(flat_vals),
                "graph_mean": mean(graph_vals),
                "delta_mean": mean(g - f for f, g in zip(flat_vals, graph_vals)),
                "graph_better_runs": sum(1 for f, g in zip(flat_vals, graph_vals) if g > f),
                "flat_better_runs": sum(1 for f, g in zip(flat_vals, graph_vals) if f > g),
                "ties": sum(1 for f, g in zip(flat_vals, graph_vals) if f == g),
            }

    return {
        "experiment_type": "retrieval_budget_sweep",
        "scope_note": "Diagnostic sweep over top-k retrieval budgets on archived artifacts; not a public benchmark.",
        "budgets": budget_list,
        "per_run": per_run,
        "aggregate": aggregate,
    }


def run_confidence_threshold_sweep(
    runs: List[RunBundle],
    thresholds: Iterable[float] = (0.5, 0.7, 0.9),
    top_k: int = 5,
) -> Dict[str, Any]:
    threshold_list: List[float] = []
    for threshold in thresholds:
        threshold_float = round(float(threshold), 2)
        if 0.0 <= threshold_float <= 1.0 and threshold_float not in threshold_list:
            threshold_list.append(threshold_float)
    if not threshold_list:
        threshold_list = [0.5, 0.7, 0.9]

    per_run: List[Dict[str, Any]] = []

    for run in runs:
        context = build_retrieval_context(run)
        papers = context["papers"]
        paper_map = context["paper_map"]
        idf = context["idf"]
        centrality = context["centrality"]
        total_relations = len(run.mekg.get("relations", []))
        flat_rank = make_flat_ranker(papers, idf)

        threshold_rows: Dict[str, Any] = {}
        for threshold in threshold_list:
            threshold_key = f"{threshold:.1f}"
            adjacency: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)
            undirected_relation_pairs: set[Tuple[str, str]] = set()
            active_relation_count = 0

            for rel in run.mekg.get("relations", []):
                conf = float(rel.get("confidence", 0.5) or 0.5)
                if conf < threshold:
                    continue
                src = sanitize_key(rel.get("source", ""))
                tgt = sanitize_key(rel.get("target", ""))
                if src not in paper_map or tgt not in paper_map:
                    continue
                rel_type = rel.get("type", "")
                adjacency[src].append((tgt, conf, rel_type))
                adjacency[tgt].append((src, conf, rel_type))
                undirected_relation_pairs.add(tuple(sorted((src, tgt))))
                active_relation_count += 1

            graph_rank = make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)
            flat_metrics = evaluate_union_with_context(
                run,
                flat_rank,
                context,
                undirected_relation_pairs,
                top_k=top_k,
            )
            graph_metrics = evaluate_union_with_context(
                run,
                lambda t, d: graph_rank(t, d)[0],
                context,
                undirected_relation_pairs,
                top_k=top_k,
            )
            threshold_rows[threshold_key] = {
                "active_relation_count": active_relation_count,
                "active_relation_share": active_relation_count / total_relations if total_relations else 0.0,
                "flat": flat_metrics,
                "graph": graph_metrics,
                "delta": {
                    "core_paper_recall": graph_metrics["core_paper_recall"] - flat_metrics["core_paper_recall"],
                    "community_coverage": graph_metrics["community_coverage"] - flat_metrics["community_coverage"],
                    "avg_pagerank": graph_metrics["avg_pagerank"] - flat_metrics["avg_pagerank"],
                    "relation_density": graph_metrics["relation_density"] - flat_metrics["relation_density"],
                    "unique_papers": graph_metrics["unique_papers"] - flat_metrics["unique_papers"],
                },
            }

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "total_relations": total_relations,
                "thresholds": threshold_rows,
            }
        )

    metrics = ["core_paper_recall", "community_coverage", "avg_pagerank", "relation_density", "unique_papers"]
    aggregate: Dict[str, Any] = {}
    for threshold in threshold_list:
        key = f"{threshold:.1f}"
        aggregate[key] = {
            "active_relation_count_mean": mean(row["thresholds"][key]["active_relation_count"] for row in per_run),
            "active_relation_share_mean": mean(row["thresholds"][key]["active_relation_share"] for row in per_run),
        }
        for metric in metrics:
            flat_vals = [row["thresholds"][key]["flat"][metric] for row in per_run]
            graph_vals = [row["thresholds"][key]["graph"][metric] for row in per_run]
            aggregate[key][metric] = {
                "flat_mean": mean(flat_vals),
                "graph_mean": mean(graph_vals),
                "delta_mean": mean(g - f for f, g in zip(flat_vals, graph_vals)),
                "graph_better_runs": sum(1 for f, g in zip(flat_vals, graph_vals) if g > f),
                "flat_better_runs": sum(1 for f, g in zip(flat_vals, graph_vals) if f > g),
                "ties": sum(1 for f, g in zip(flat_vals, graph_vals) if f == g),
            }

    return {
        "experiment_type": "relation_confidence_threshold_sweep",
        "scope_note": (
            "Diagnostic robustness sweep over relation-confidence cutoffs under a fixed top-5 section budget on "
            "archived artifacts; not a public benchmark."
        ),
        "top_k_per_section": top_k,
        "thresholds": threshold_list,
        "per_run": per_run,
        "aggregate": aggregate,
    }


def run_relation_family_ablation(runs: List[RunBundle]) -> Dict[str, Any]:
    per_run: List[Dict[str, Any]] = []

    for run in runs:
        papers = run.mekg["papers"]
        paper_map = {sanitize_key(p["id"]): p for p in papers}
        all_categories = {p.get("category", "") for p in papers if p.get("category")}
        idf = build_idf(papers)
        centrality = compute_pagerank_centrality(run.mekg)
        sorted_core = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        core_papers = {pid for pid, _ in sorted_core[: max(1, len(sorted_core) // 5)]}

        variant_rows: Dict[str, Dict[str, Any]] = {}
        for variant_name, allowed_rel_types in RELATION_FAMILY_VARIANTS.items():
            adjacency, undirected_relation_pairs = (
                defaultdict(list),
                set(),
            )
            for rel in run.mekg.get("relations", []):
                rel_type = rel.get("type", "")
                if allowed_rel_types is not None and rel_type not in allowed_rel_types:
                    continue
                src = sanitize_key(rel.get("source", ""))
                tgt = sanitize_key(rel.get("target", ""))
                if src not in paper_map or tgt not in paper_map:
                    continue
                conf = float(rel.get("confidence", 0.5) or 0.5)
                adjacency[src].append((tgt, conf, rel_type))
                adjacency[tgt].append((src, conf, rel_type))
                undirected_relation_pairs.add(tuple(sorted((src, tgt))))

            flat_rank = make_flat_ranker(papers, idf)
            graph_rank = make_graph_ranker(papers, paper_map, idf, centrality, adjacency, max_hops=1)
            metrics = evaluate_union_with_context(
                run,
                lambda t, d: graph_rank(t, d)[0],
                {
                    "paper_map": paper_map,
                    "core_papers": core_papers,
                    "all_categories": all_categories,
                    "centrality": centrality,
                },
                undirected_relation_pairs,
            )
            metrics["active_relation_count"] = sum(
                1
                for rel in run.mekg.get("relations", [])
                if allowed_rel_types is None or rel.get("type", "") in allowed_rel_types
            )
            variant_rows[variant_name] = metrics

        full_metrics = variant_rows["full"]
        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "variants": variant_rows,
                "delta_vs_full": {
                    variant_name: {
                        metric: variant_rows[variant_name][metric] - full_metrics[metric]
                        for metric in [
                            "core_paper_recall",
                            "community_coverage",
                            "avg_pagerank",
                            "relation_density",
                            "unique_papers",
                        ]
                    }
                    for variant_name in variant_rows
                    if variant_name != "full"
                },
            }
        )

    metrics = ["core_paper_recall", "community_coverage", "avg_pagerank", "relation_density", "unique_papers"]
    aggregate: Dict[str, Any] = {}
    for variant_name in RELATION_FAMILY_VARIANTS:
        aggregate[variant_name] = {}
        for metric in metrics:
            values = [row["variants"][variant_name][metric] for row in per_run]
            aggregate[variant_name][metric] = {
                "mean": mean(values),
                "median": median(values),
                "min": min(values) if values else 0.0,
                "max": max(values) if values else 0.0,
            }
        aggregate[variant_name]["active_relation_count_mean"] = mean(
            row["variants"][variant_name]["active_relation_count"] for row in per_run
        )

    pairwise: Dict[str, Any] = {}
    full_rows = [row["variants"]["full"] for row in per_run]
    for variant_name in RELATION_FAMILY_VARIANTS:
        if variant_name == "full":
            continue
        pairwise[variant_name] = {}
        for metric in metrics:
            left_vals = [row["variants"]["full"][metric] for row in per_run]
            right_vals = [row["variants"][variant_name][metric] for row in per_run]
            pairwise[variant_name][metric] = {
                "full_mean": mean(left_vals),
                "variant_mean": mean(right_vals),
                "delta_mean": mean(r - l for l, r in zip(left_vals, right_vals)),
                "variant_better_runs": sum(1 for l, r in zip(left_vals, right_vals) if r > l),
                "full_better_runs": sum(1 for l, r in zip(left_vals, right_vals) if l > r),
                "ties": sum(1 for l, r in zip(left_vals, right_vals) if l == r),
            }

    return {
        "experiment_type": "relation_family_ablation",
        "scope_note": "Diagnostic retrieval-side ablation over archived artifacts; not a public benchmark.",
        "variants": {
            "full": "All relation families enabled.",
            "no_support": "All relations except generic support edges.",
            "structural_only": "Generic support + structural/meta relations, without evolutionary semantic edges.",
            "semantic_only": "Only extends/improves/applies/refutes edges.",
        },
        "per_run": per_run,
        "aggregate": aggregate,
        "pairwise_vs_full": pairwise,
    }


def run_core_score_weight_sensitivity_audit(runs: List[RunBundle]) -> Dict[str, Any]:
    weight_variants = {
        "base": {"pagerank": 0.4, "citation": 0.3, "recency": 0.2, "degree": 0.1},
        "pr_heavy": {"pagerank": 0.55, "citation": 0.2, "recency": 0.15, "degree": 0.1},
        "citation_heavy": {"pagerank": 0.3, "citation": 0.45, "recency": 0.15, "degree": 0.1},
        "recency_heavy": {"pagerank": 0.3, "citation": 0.2, "recency": 0.4, "degree": 0.1},
        "degree_heavy": {"pagerank": 0.3, "citation": 0.25, "recency": 0.15, "degree": 0.3},
    }

    per_run: List[Dict[str, Any]] = []
    overlap_rows: Dict[str, List[float]] = {name: [] for name in weight_variants if name != "base"}
    citation_signal_nonzero_runs = 0

    for run in runs:
        papers = run.mekg.get("papers", [])
        paper_map = {paper["id"]: paper for paper in papers}

        graph = nx.DiGraph()
        graph.add_nodes_from(paper_map)
        for rel in run.mekg.get("relations", []):
            src = rel.get("source")
            tgt = rel.get("target")
            if src in paper_map and tgt in paper_map:
                graph.add_edge(src, tgt)

        pagerank = nx.pagerank(graph, alpha=0.85) if graph.number_of_nodes() else {}
        if pagerank:
            max_pr = max(pagerank.values())
            min_pr = min(pagerank.values())
            pr_range = max_pr - min_pr if max_pr != min_pr else 1.0
            pagerank = {pid: (score - min_pr) / pr_range for pid, score in pagerank.items()}
        else:
            pagerank = {pid: 0.0 for pid in paper_map}

        all_citations = []
        all_years = []
        all_degrees = []
        for pid in graph.nodes():
            paper = paper_map.get(pid, {})
            citations = paper.get("citations", paper.get("citation_count", 0))
            if isinstance(citations, (int, float)) and citations >= 0:
                all_citations.append(citations)
            year = paper.get("year", 2024)
            if isinstance(year, int) and 1900 < year <= 2024:
                all_years.append(year)
            all_degrees.append(graph.in_degree(pid) + graph.out_degree(pid))

        if any(value > 0 for value in all_citations):
            citation_signal_nonzero_runs += 1

        max_citation = max(all_citations) if all_citations else 1
        min_year = min(all_years) if all_years else 2014
        max_year = max(all_years) if all_years else 2024
        year_range = max_year - min_year if max_year > min_year else 1
        max_degree = max(all_degrees) if all_degrees else 1

        def compute_variant_scores(weights: Dict[str, float]) -> Dict[str, float]:
            scores: Dict[str, float] = {}
            for pid in graph.nodes():
                paper = paper_map.get(pid, {})
                pr_score = pagerank.get(pid, 0.0)

                citations = paper.get("citations", paper.get("citation_count", 0))
                if not isinstance(citations, (int, float)) or citations < 0:
                    citations = 0
                citation_score = math.log1p(citations) / math.log1p(max_citation) if max_citation > 0 else 0.0

                year = paper.get("year", 2024)
                if not isinstance(year, int) or year < 1900 or year > 2024:
                    year = 2024
                recency_score = (year - min_year) / year_range if year_range > 0 else 0.5

                degree = graph.in_degree(pid) + graph.out_degree(pid)
                degree_score = degree / max_degree if max_degree > 0 else 0.0

                scores[pid] = (
                    weights["pagerank"] * pr_score
                    + weights["citation"] * citation_score
                    + weights["recency"] * recency_score
                    + weights["degree"] * degree_score
                )
            return scores

        variant_rankings: Dict[str, List[Tuple[str, float]]] = {}
        variant_summaries: Dict[str, Any] = {}

        for name, weights in weight_variants.items():
            scores = compute_variant_scores(weights)
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            variant_rankings[name] = ranked
            top10 = [pid for pid, _ in ranked[:10]]
            variant_summaries[name] = {
                "weights": weights,
                "top10_ids": top10,
                "top10_titles": [paper_map[pid].get("title", "") for pid in top10],
                "avg_top10_year": mean(paper_map[pid].get("year", 2024) for pid in top10),
                "avg_top10_pagerank": mean(pagerank.get(pid, 0.0) for pid in top10),
            }

        base_top10 = set(variant_summaries["base"]["top10_ids"])
        for name in weight_variants:
            if name == "base":
                continue
            overlap = len(base_top10 & set(variant_summaries[name]["top10_ids"]))
            variant_summaries[name]["overlap_with_base_top10"] = overlap
            overlap_rows[name].append(float(overlap))

        base_scores = [score for _, score in variant_rankings["base"]]
        default_count = max(10, min(int(len(base_scores) * 0.1), 200, len(base_scores)))
        elbow_count = compute_elbow_count(base_scores, default_count)

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "paper_count": len(papers),
                "relation_count": len(run.mekg.get("relations", [])),
                "citation_signal_nonzero": any(value > 0 for value in all_citations),
                "default_core_count": default_count,
                "elbow_count": elbow_count,
                "variants": variant_summaries,
            }
        )

    aggregate = {
        "runs": len(per_run),
        "citation_signal_nonzero_runs": citation_signal_nonzero_runs,
        "variant_overlap_vs_base": {
            name: {
                "mean": mean(values),
                "median": median(values),
                "min": min(values) if values else 0.0,
                "max": max(values) if values else 0.0,
            }
            for name, values in overlap_rows.items()
        },
        "default_core_count_mean": mean(row["default_core_count"] for row in per_run),
        "elbow_count_mean": mean(row["elbow_count"] for row in per_run),
    }

    return {
        "experiment_type": "core_score_weight_sensitivity_audit",
        "scope_note": (
            "Local graph-only sensitivity analysis over archived MEKG artifacts using the repository's hand-tuned "
            "core-score form; diagnostic only, not a learned ablation or public benchmark."
        ),
        "weight_variants": list(weight_variants.keys()),
        "per_run": per_run,
        "aggregate": aggregate,
    }


def normalize_title_for_audit(title: str) -> str:
    title = (title or "").lower()
    title = re.sub(r"[^\w\s]", "", title)
    title = " ".join(title.split())
    return title


def run_archived_input_integrity_audit(runs: List[RunBundle]) -> Dict[str, Any]:
    paper_fields = ("id", "title", "abstract", "category", "subcategory", "year", "source")
    relation_fields = ("source", "target", "type", "confidence")

    per_run: List[Dict[str, Any]] = []
    total_paper_missing = Counter({field: 0 for field in paper_fields})
    total_relation_missing = Counter({field: 0 for field in relation_fields})
    total_source_counts: Counter[str] = Counter()
    total_exact_title_duplicate_rows = 0
    total_normalized_title_duplicate_rows = 0
    total_unresolved_source_count = 0
    total_unresolved_target_count = 0
    all_confidences: List[float] = []
    total_papers = 0
    total_relations = 0

    for run in runs:
        papers = run.mekg.get("papers", [])
        relations = run.mekg.get("relations", [])
        total_papers += len(papers)
        total_relations += len(relations)

        ids = set()
        paper_missing = Counter({field: 0 for field in paper_fields})
        relation_missing = Counter({field: 0 for field in relation_fields})
        source_counts: Counter[str] = Counter()
        titles: List[str] = []
        normalized_titles: List[str] = []

        for paper in papers:
            ids.add(str(paper.get("id", "")))
            title = str(paper.get("title", ""))
            titles.append(title)
            normalized_titles.append(normalize_title_for_audit(title))
            for field in paper_fields:
                value = paper.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    paper_missing[field] += 1
                    total_paper_missing[field] += 1
            source_counts[str(paper.get("source", ""))] += 1
            total_source_counts[str(paper.get("source", ""))] += 1

        exact_title_duplicate_rows = len(titles) - len(set(titles))
        normalized_title_duplicate_rows = len(normalized_titles) - len(set(normalized_titles))
        total_exact_title_duplicate_rows += exact_title_duplicate_rows
        total_normalized_title_duplicate_rows += normalized_title_duplicate_rows

        unresolved_source_count = 0
        unresolved_target_count = 0
        confidences: List[float] = []
        for relation in relations:
            for field in relation_fields:
                value = relation.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    relation_missing[field] += 1
                    total_relation_missing[field] += 1
            src = str(relation.get("source", ""))
            tgt = str(relation.get("target", ""))
            if src not in ids:
                unresolved_source_count += 1
            if tgt not in ids:
                unresolved_target_count += 1
            conf = float(relation.get("confidence", 0.0) or 0.0)
            confidences.append(conf)
            all_confidences.append(conf)

        total_unresolved_source_count += unresolved_source_count
        total_unresolved_target_count += unresolved_target_count

        per_run.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "paper_count": len(papers),
                "relation_count": len(relations),
                "paper_missing_field_counts": dict(paper_missing),
                "relation_missing_field_counts": dict(relation_missing),
                "source_counts": dict(source_counts),
                "exact_title_duplicate_rows": exact_title_duplicate_rows,
                "normalized_title_duplicate_rows": normalized_title_duplicate_rows,
                "unresolved_relation_source_count": unresolved_source_count,
                "unresolved_relation_target_count": unresolved_target_count,
                "confidence_min": min(confidences) if confidences else 0.0,
                "confidence_mean": mean(confidences),
                "confidence_max": max(confidences) if confidences else 0.0,
            }
        )

    return {
        "experiment_type": "archived_input_integrity_audit",
        "scope_note": (
            "Repository-local audit over archived MEKG paper/relation records. "
            "It checks whether the saved inputs expose obvious within-run title duplication, "
            "missing core metadata fields, or dangling relation endpoints."
        ),
        "per_run": per_run,
        "aggregate": {
            "total_runs": len(runs),
            "total_papers": total_papers,
            "total_relations": total_relations,
            "paper_missing_field_counts": dict(total_paper_missing),
            "relation_missing_field_counts": dict(total_relation_missing),
            "source_counts": dict(total_source_counts),
            "exact_title_duplicate_rows": total_exact_title_duplicate_rows,
            "normalized_title_duplicate_rows": total_normalized_title_duplicate_rows,
            "unresolved_relation_source_count": total_unresolved_source_count,
            "unresolved_relation_target_count": total_unresolved_target_count,
            "confidence_min": min(all_confidences) if all_confidences else 0.0,
            "confidence_mean": mean(all_confidences),
            "confidence_max": max(all_confidences) if all_confidences else 0.0,
        },
    }


def source_cue_present(rel_type: str, source_title: str, source_abstract: str) -> bool:
    text = f"{source_title} {source_abstract}".lower()
    if rel_type == "extends":
        return any(k in text for k in ["extend", "extended", "extension", "builds on", "build upon", "based on"])
    if rel_type == "improves":
        return any(k in text for k in ["improv", "outperform", "better than", "superior"])
    if rel_type == "applies":
        return any(k in text for k in ["apply", "application", "applied to", "use in"])
    return False


def run_edge_audit(runs: List[RunBundle]) -> Dict[str, Any]:
    per_run: List[Dict[str, Any]] = []
    aggregate_rows: Dict[str, Dict[str, float]] = {
        rel_type: {"count": 0.0, "temporal_ok": 0.0, "cue_support": 0.0, "confidence_sum": 0.0}
        for rel_type in SEMANTIC_RELATIONS
    }

    for run in runs:
        papers = {paper["id"]: paper for paper in run.mekg.get("papers", [])}
        per_type = {
            rel_type: {"count": 0, "temporal_ok": 0, "cue_support": 0, "confidence_sum": 0.0}
            for rel_type in SEMANTIC_RELATIONS
        }
        for rel in run.mekg.get("relations", []):
            rel_type = rel.get("type", "")
            if rel_type not in SEMANTIC_RELATIONS:
                continue
            src = papers.get(rel.get("source"))
            tgt = papers.get(rel.get("target"))
            if not src or not tgt:
                continue
            row = per_type[rel_type]
            row["count"] += 1
            src_year = src.get("year")
            tgt_year = tgt.get("year")
            if isinstance(src_year, int) and isinstance(tgt_year, int) and src_year >= tgt_year:
                row["temporal_ok"] += 1
            if source_cue_present(rel_type, src.get("title", ""), src.get("abstract", "")):
                row["cue_support"] += 1
            row["confidence_sum"] += float(rel.get("confidence", 0.0) or 0.0)

        run_summary = {"run_id": run.run_id, "label": run.label, "by_relation_type": {}}
        for rel_type, row in per_type.items():
            count = row["count"]
            run_summary["by_relation_type"][rel_type] = {
                "count": count,
                "temporal_direction_consistency": row["temporal_ok"] / count if count else 0.0,
                "explicit_source_cue_support": row["cue_support"] / count if count else 0.0,
                "avg_confidence": row["confidence_sum"] / count if count else 0.0,
            }
            aggregate_rows[rel_type]["count"] += count
            aggregate_rows[rel_type]["temporal_ok"] += row["temporal_ok"]
            aggregate_rows[rel_type]["cue_support"] += row["cue_support"]
            aggregate_rows[rel_type]["confidence_sum"] += row["confidence_sum"]
        per_run.append(run_summary)

    aggregate = {}
    for rel_type, row in aggregate_rows.items():
        count = row["count"]
        aggregate[rel_type] = {
            "count": int(count),
            "temporal_direction_consistency": row["temporal_ok"] / count if count else 0.0,
            "explicit_source_cue_support": row["cue_support"] / count if count else 0.0,
            "avg_confidence": row["confidence_sum"] / count if count else 0.0,
        }

    return {
        "experiment_type": "mekg_semantic_edge_consistency_audit",
        "scope_note": "Consistency audit on archived MEKG edges; this is not human-annotated precision/recall.",
        "relation_types": list(SEMANTIC_RELATIONS),
        "per_run": per_run,
        "aggregate": aggregate,
    }


def run_edge_confidence_profile(runs: List[RunBundle]) -> Dict[str, Any]:
    profile: Dict[str, Any] = {
        "experiment_type": "mekg_semantic_edge_confidence_profile",
        "scope_note": (
            "Confidence-stratified consistency profile over archived semantic MEKG edges; "
            "still diagnostic only, not human-annotated precision/recall."
        ),
        "thresholds": list(EDGE_CONFIDENCE_THRESHOLDS),
        "aggregate": {},
    }

    for threshold in EDGE_CONFIDENCE_THRESHOLDS:
        key = f"{threshold:.1f}"
        by_relation = {
            rel_type: {"count": 0, "temporal_ok": 0, "cue_support": 0, "confidence_sum": 0.0}
            for rel_type in SEMANTIC_RELATIONS
        }
        overall = {"count": 0, "temporal_ok": 0, "cue_support": 0, "confidence_sum": 0.0}

        for run in runs:
            papers = {paper["id"]: paper for paper in run.mekg.get("papers", [])}
            for rel in run.mekg.get("relations", []):
                rel_type = rel.get("type", "")
                if rel_type not in SEMANTIC_RELATIONS:
                    continue
                confidence = float(rel.get("confidence", 0.0) or 0.0)
                if confidence < threshold:
                    continue
                src = papers.get(rel.get("source"))
                tgt = papers.get(rel.get("target"))
                if not src or not tgt:
                    continue

                row = by_relation[rel_type]
                row["count"] += 1
                row["confidence_sum"] += confidence
                overall["count"] += 1
                overall["confidence_sum"] += confidence

                src_year = src.get("year")
                tgt_year = tgt.get("year")
                temporal_ok = isinstance(src_year, int) and isinstance(tgt_year, int) and src_year >= tgt_year
                if temporal_ok:
                    row["temporal_ok"] += 1
                    overall["temporal_ok"] += 1
                if source_cue_present(rel_type, src.get("title", ""), src.get("abstract", "")):
                    row["cue_support"] += 1
                    overall["cue_support"] += 1

        def finalize(row: Dict[str, float]) -> Dict[str, float]:
            count = row["count"]
            return {
                "count": int(count),
                "temporal_direction_consistency": row["temporal_ok"] / count if count else 0.0,
                "explicit_source_cue_support": row["cue_support"] / count if count else 0.0,
                "avg_confidence": row["confidence_sum"] / count if count else 0.0,
            }

        profile["aggregate"][key] = {
            "overall": finalize(overall),
            "by_relation_type": {rel_type: finalize(row) for rel_type, row in by_relation.items()},
        }

    return profile


def summarize_stage_durations(stage_rows: List[Dict[str, float]]) -> Dict[str, float]:
    stage_names = {name for row in stage_rows for name in row}
    summary = {}
    for stage in sorted(stage_names):
        summary[stage] = mean(row.get(stage, 0.0) for row in stage_rows)
    return summary


def run_runtime_cost_summary(runs: List[RunBundle]) -> Dict[str, Any]:
    archived_rows: List[Dict[str, Any]] = []
    archived_stage_minutes: List[Dict[str, float]] = []

    for run in runs:
        time_monitor = load_json(run.base_dir / "metrics" / "time_monitor.json")
        stage_minutes = {stage: float(stats.get("duration", 0.0)) / 60.0 for stage, stats in time_monitor.items()}
        total_minutes = sum(stage_minutes.values())
        archived_rows.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "stage_minutes": stage_minutes,
                "total_minutes": total_minutes,
            }
        )
        archived_stage_minutes.append(stage_minutes)

    archived_totals = [row["total_minutes"] for row in archived_rows]
    mean_stage_minutes = summarize_stage_durations(archived_stage_minutes)
    mean_total_minutes = mean(archived_totals)
    stage_share_mean = {
        stage: (minutes / mean_total_minutes if mean_total_minutes else 0.0)
        for stage, minutes in mean_stage_minutes.items()
    }

    fresh_rows: List[Dict[str, Any]] = []
    for item in FRESH_RUNS:
        base = ROOT / "outputs" / item["id"]
        time_monitor = load_json(base / "metrics" / "time_monitor.json")
        token_monitor = load_json(base / "metrics" / "token_monitor.json")

        stage_minutes = {stage: float(stats.get("duration", 0.0)) / 60.0 for stage, stats in time_monitor.items()}
        total_minutes = sum(stage_minutes.values())

        input_tokens = 0
        output_tokens = 0
        total_cost = 0.0
        provider_breakdown = []
        for stage_name, models in token_monitor.items():
            for model_name, stats in models.items():
                input_tokens += int(stats.get("input_tokens", 0) or 0)
                output_tokens += int(stats.get("output_tokens", 0) or 0)
                total_cost += float(stats.get("total_cost", 0.0) or 0.0)
                provider_breakdown.append(
                    {
                        "stage": stage_name,
                        "model": model_name,
                        "input_tokens": int(stats.get("input_tokens", 0) or 0),
                        "output_tokens": int(stats.get("output_tokens", 0) or 0),
                        "cost": float(stats.get("total_cost", 0.0) or 0.0),
                    }
                )

        fresh_rows.append(
            {
                "run_id": item["id"],
                "label": item["label"],
                "stage_minutes": stage_minutes,
                "total_minutes": total_minutes,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_cost": total_cost,
                "provider_breakdown": provider_breakdown,
            }
        )

    scisage = load_json(SCISAGE_PARTIAL)

    return {
        "experiment_type": "runtime_and_cost_summary",
        "archived_full_runs": {
            "per_run": archived_rows,
            "summary": {
                "count": len(archived_rows),
                "total_minutes_mean": mean(archived_totals),
                "total_minutes_median": median(archived_totals),
                "total_minutes_min": min(archived_totals) if archived_totals else 0.0,
                "total_minutes_max": max(archived_totals) if archived_totals else 0.0,
                "stage_minutes_mean": mean_stage_minutes,
                "stage_share_mean": stage_share_mean,
            },
        },
        "fresh_low_cost_runs": fresh_rows,
        "scisage_outline_partial": {
            "latency_seconds": float(scisage["runtime"]["latency_seconds"]),
            "top_level_sections": int(scisage["artifact_stats"]["top_level_sections"]),
            "total_outline_nodes": int(scisage["artifact_stats"]["total_outline_nodes"]),
        },
    }


def summarize_numeric_rows(rows: List[Dict[str, Any]], key: str) -> Dict[str, float]:
    values = [float(row.get(key, 0.0) or 0.0) for row in rows]
    return {
        "mean": mean(values),
        "median": median(values),
        "min": min(values) if values else 0.0,
        "max": max(values) if values else 0.0,
    }


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def run_artifact_dedup_robustness_audit() -> Dict[str, Any]:
    if not ARTIFACT_COMPARISON_ROWS.exists():
        return {
            "experiment_type": "artifact_dedup_robustness_audit",
            "scope_note": "Artifact-level comparison rows not found.",
            "rows_found": 0,
            "duplicate_groups": [],
            "systems": {},
        }

    with ARTIFACT_COMPARISON_ROWS.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    by_hash: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_hash[str(row.get("pdf_sha256_12", ""))].append(row)

    duplicate_groups = []
    for digest, dup_rows in sorted(by_hash.items()):
        if len(dup_rows) <= 1:
            continue
        duplicate_groups.append(
            {
                "pdf_sha256_12": digest,
                "count": len(dup_rows),
                "systems": sorted({str(row.get("system", "")) for row in dup_rows}),
                "pdf_names": [str(row.get("pdf_name", "")) for row in dup_rows],
                "paths": [str(row.get("pdf_path", "")) for row in dup_rows],
            }
        )

    dedup_rows: List[Dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for row in rows:
        digest = str(row.get("pdf_sha256_12", ""))
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        dedup_rows.append(row)

    systems = sorted({str(row.get("system", "")) for row in rows})
    systems_summary: Dict[str, Any] = {}
    numeric_keys = ("page_count", "text_chars", "citation_mentions_total", "section_heading_count", "figure_mentions", "table_mentions")
    for system in systems:
        original = [row for row in rows if str(row.get("system", "")) == system]
        dedup = [row for row in dedup_rows if str(row.get("system", "")) == system]
        system_row = {
            "original_count": len(original),
            "dedup_count": len(dedup),
            "removed_duplicates": len(original) - len(dedup),
            "duplicate_share": (len(original) - len(dedup)) / len(original) if original else 0.0,
            "metrics": {},
        }
        for key in numeric_keys:
            original_stats = summarize_numeric_rows(original, key)
            dedup_stats = summarize_numeric_rows(dedup, key)
            system_row["metrics"][key] = {
                "original_mean": original_stats["mean"],
                "dedup_mean": dedup_stats["mean"],
                "mean_delta": dedup_stats["mean"] - original_stats["mean"],
            }
        systems_summary[system] = system_row

    return {
        "experiment_type": "artifact_dedup_robustness_audit",
        "scope_note": (
            "Repository-local robustness audit over artifact-level comparison rows. Exact-PDF duplicates are removed "
            "by SHA-256 prefix to check whether released-artifact summary trends depend on duplicated files."
        ),
        "rows_found": len(rows),
        "unique_hash_rows": len(dedup_rows),
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_row_count": len(rows) - len(dedup_rows),
        "duplicate_groups": duplicate_groups,
        "systems": systems_summary,
    }


def run_artifact_structure_proxy_robustness_audit() -> Dict[str, Any]:
    if not ARTIFACT_COMPARISON_ROWS.exists():
        return {
            "experiment_type": "artifact_structure_proxy_robustness_audit",
            "scope_note": "Artifact-level comparison rows not found.",
            "rows_found": 0,
            "systems": {},
        }

    with ARTIFACT_COMPARISON_ROWS.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    rows_with_toc = [row for row in rows if int(row.get("toc_entries", 0) or 0) > 0]
    exact_match_rows = [
        row
        for row in rows_with_toc
        if int(row.get("toc_entries", 0) or 0) == int(row.get("section_heading_count", 0) or 0)
    ]
    mismatch_rows = [
        {
            "system": str(row.get("system", "")),
            "topic": str(row.get("topic", "")),
            "pdf_name": str(row.get("pdf_name", "")),
            "toc_entries": int(row.get("toc_entries", 0) or 0),
            "section_heading_count": int(row.get("section_heading_count", 0) or 0),
            "heading_minus_toc": int(row.get("section_heading_count", 0) or 0) - int(row.get("toc_entries", 0) or 0),
        }
        for row in rows
        if int(row.get("toc_entries", 0) or 0) != int(row.get("section_heading_count", 0) or 0)
    ]

    systems = sorted({str(row.get("system", "")) for row in rows})
    systems_summary: Dict[str, Any] = {}
    for system in systems:
        system_rows = [row for row in rows if str(row.get("system", "")) == system]
        system_rows_with_toc = [row for row in system_rows if int(row.get("toc_entries", 0) or 0) > 0]
        exact_matches = [
            row
            for row in system_rows_with_toc
            if int(row.get("toc_entries", 0) or 0) == int(row.get("section_heading_count", 0) or 0)
        ]
        references_heading_present = [_parse_bool(row.get("references_heading_present", False)) for row in system_rows]

        systems_summary[system] = {
            "count": len(system_rows),
            "rows_with_toc": len(system_rows_with_toc),
            "toc_heading_exact_match_rate": len(exact_matches) / len(system_rows_with_toc) if system_rows_with_toc else 0.0,
            "mean_abs_heading_minus_toc": mean(
                abs(int(row.get("section_heading_count", 0) or 0) - int(row.get("toc_entries", 0) or 0))
                for row in system_rows
            ),
            "references_heading_rate": mean(1.0 if flag else 0.0 for flag in references_heading_present),
            "toc_presence_rate": mean(1.0 if int(row.get("toc_entries", 0) or 0) > 0 else 0.0 for row in system_rows),
        }

    references_heading_present = [_parse_bool(row.get("references_heading_present", False)) for row in rows]
    return {
        "experiment_type": "artifact_structure_proxy_robustness_audit",
        "scope_note": (
            "Repository-local structural-proxy audit over artifact-level comparison rows. "
            "It checks whether two cheap heading-count proxies (TOC entries and extracted section-heading counts) "
            "track each other and whether a references heading is consistently recoverable from released/fresh artifacts."
        ),
        "rows_found": len(rows),
        "rows_with_toc": len(rows_with_toc),
        "rows_without_toc": len(rows) - len(rows_with_toc),
        "toc_heading_exact_match_rate": len(exact_match_rows) / len(rows_with_toc) if rows_with_toc else 0.0,
        "heading_count_mismatch_rows": len(mismatch_rows),
        "references_heading_rate": mean(1.0 if flag else 0.0 for flag in references_heading_present),
        "mismatch_rows": mismatch_rows,
        "systems": systems_summary,
    }


def run_artifact_length_normalized_proxy_audit() -> Dict[str, Any]:
    if not ARTIFACT_COMPARISON_ROWS.exists():
        return {
            "experiment_type": "artifact_length_normalized_proxy_audit",
            "scope_note": "Artifact-level comparison rows not found.",
            "rows_found": 0,
            "dedup_rows": 0,
            "systems": {},
            "surveygraph_fresh_combined": {},
        }

    with ARTIFACT_COMPARISON_ROWS.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    dedup_rows: List[Dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for row in rows:
        digest = str(row.get("pdf_sha256_12", ""))
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        dedup_rows.append(row)

    def _density_summary(target_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        citation_density = []
        heading_density = []
        table_figure_density = []
        toc_heading_gap = []
        tex_flags = []
        bib_flags = []
        review_flags = []
        markdown_flags = []
        multi_round_flags = []
        references_flags = []

        for row in target_rows:
            word_count = max(float(row.get("word_count", 0) or 0), 1.0)
            citation_density.append(float(row.get("citation_mentions_total", 0) or 0) / word_count * 1000.0)
            heading_density.append(float(row.get("section_heading_count", 0) or 0) / word_count * 10000.0)
            table_figure_density.append(
                (float(row.get("figure_mentions", 0) or 0) + float(row.get("table_mentions", 0) or 0)) / word_count * 10000.0
            )
            toc_heading_gap.append(
                abs(float(row.get("section_heading_count", 0) or 0) - float(row.get("toc_entries", 0) or 0))
            )
            tex_flags.append(1.0 if _parse_bool(row.get("has_tex", False)) else 0.0)
            bib_flags.append(1.0 if _parse_bool(row.get("has_bib", False)) else 0.0)
            review_flags.append(1.0 if _parse_bool(row.get("has_review_logs", False)) else 0.0)
            markdown_flags.append(1.0 if _parse_bool(row.get("has_intermediate_markdown", False)) else 0.0)
            multi_round_flags.append(1.0 if _parse_bool(row.get("has_multi_round_outputs", False)) else 0.0)
            references_flags.append(1.0 if _parse_bool(row.get("references_heading_present", False)) else 0.0)

        editable_flags = [1.0 if tex and bib else 0.0 for tex, bib in zip(tex_flags, bib_flags)]
        return {
            "count": len(target_rows),
            "citation_density_per_1k_words_median": median(citation_density),
            "heading_density_per_10k_words_median": median(heading_density),
            "table_figure_density_per_10k_words_median": median(table_figure_density),
            "toc_heading_gap_mean": mean(toc_heading_gap),
            "tex_rate": mean(tex_flags),
            "bib_rate": mean(bib_flags),
            "editable_artifact_rate": mean(editable_flags),
            "references_heading_rate": mean(references_flags),
            "review_trace_rate": mean(review_flags),
            "markdown_trace_rate": mean(markdown_flags),
            "multi_round_rate": mean(multi_round_flags),
        }

    systems = sorted({str(row.get("system", "")) for row in dedup_rows})
    systems_summary = {
        system: _density_summary([row for row in dedup_rows if str(row.get("system", "")) == system])
        for system in systems
    }

    surveygraph_fresh_rows = [
        row
        for row in dedup_rows
        if str(row.get("system", "")) in {"SurveyGraph-GLM-fresh", "SurveyGraph-Qwen-fresh"}
    ]

    return {
        "experiment_type": "artifact_length_normalized_proxy_audit",
        "scope_note": (
            "Repository-local length-normalized artifact audit over deduplicated released/fresh comparison rows. "
            "The goal is to check whether cross-framework structural differences persist after normalizing by document length, "
            "rather than depending only on raw page or word counts."
        ),
        "rows_found": len(rows),
        "dedup_rows": len(dedup_rows),
        "systems": systems_summary,
        "surveygraph_fresh_combined": _density_summary(surveygraph_fresh_rows),
    }


def run_manual_spot_audit(runs: List[RunBundle]) -> Dict[str, Any]:
    target_run = next((run for run in runs if run.run_id == MANUAL_SPOT_AUDIT_RUN_ID), None)
    if target_run is None:
        return {
            "experiment_type": "manual_citation_support_spot_audit",
            "scope_note": "No target run found for spot audit.",
            "samples": [],
            "aggregate": {},
        }

    papers = {paper["title"]: paper for paper in target_run.mekg.get("papers", [])}
    paper_ids = {paper["title"]: paper.get("id") for paper in target_run.mekg.get("papers", [])}
    relations = {
        (rel.get("type"), rel.get("source"), rel.get("target")): rel
        for rel in target_run.mekg.get("relations", [])
    }
    samples: List[Dict[str, Any]] = []
    aggregate: Dict[str, Dict[str, int]] = defaultdict(lambda: {"supported": 0, "partial": 0, "unsupported": 0, "total": 0})
    overall = {"supported": 0, "partial": 0, "unsupported": 0, "total": 0}
    issue_tag_counts: Counter[str] = Counter()
    failure_mode_counts: Counter[str] = Counter()

    for sample in MANUAL_CITATION_SPOT_AUDIT:
        src = papers.get(sample["source_title"])
        tgt = papers.get(sample["target_title"])
        if not src or not tgt:
            continue
        rel = relations.get((sample["relation_type"], paper_ids.get(sample["source_title"]), paper_ids.get(sample["target_title"])), {})
        temporal_ok = None
        if src.get("year") is not None and tgt.get("year") is not None:
            temporal_ok = bool(src.get("year") >= tgt.get("year"))
        row = {
            "relation_type": sample["relation_type"],
            "source_title": sample["source_title"],
            "target_title": sample["target_title"],
            "source_year": src.get("year"),
            "target_year": tgt.get("year"),
            "confidence": rel.get("confidence"),
            "temporal_ok": temporal_ok,
            "label": sample["label"],
            "issue_tag": sample.get("issue_tag", "unspecified"),
            "rationale": sample["rationale"],
        }
        samples.append(row)
        aggregate[sample["relation_type"]][sample["label"]] += 1
        aggregate[sample["relation_type"]]["total"] += 1
        overall[sample["label"]] += 1
        overall["total"] += 1
        issue_tag_counts[row["issue_tag"]] += 1
        if sample["label"] != "supported":
            failure_mode_counts[FAILURE_MODE_MAP.get(row["issue_tag"], "other")] += 1

    supported_or_partial_rate = (overall["supported"] + overall["partial"]) / overall["total"] if overall["total"] else 0.0
    overall["supported_or_partial_rate"] = supported_or_partial_rate

    return {
        "experiment_type": "manual_citation_support_spot_audit",
        "scope_note": "Single-annotator author-side spot audit over sampled semantic edges; exploratory only.",
        "run_id": target_run.run_id,
        "samples": samples,
        "aggregate": dict(aggregate),
        "overall": overall,
        "supported_or_partial_rate": supported_or_partial_rate,
        "issue_tag_counts": dict(issue_tag_counts),
        "weak_case_total": overall["partial"] + overall["unsupported"],
        "failure_mode_counts": dict(failure_mode_counts),
    }


def extract_sentence_by_anchor(text: str, anchor_text: str) -> str:
    normalized_text = normalize_whitespace(re.sub(r"(?m)^%.*$", "", text))
    anchor = normalize_whitespace(anchor_text)
    anchor_lower = anchor.lower()
    normalized_lower = normalized_text.lower()
    start_idx = normalized_lower.find(anchor_lower)
    if start_idx < 0:
        raise ValueError(f"Anchor not found in text: {anchor_text}")

    sentence_end_matches = list(re.finditer(r"[.!?](?=\s+[A-Z\\\\])", normalized_text))

    left = 0
    for match in sentence_end_matches:
        if match.start() < start_idx:
            left = match.end()
        else:
            break
    while left < len(normalized_text) and normalized_text[left].isspace():
        left += 1

    right = len(normalized_text)
    for match in sentence_end_matches:
        if match.start() >= start_idx:
            right = match.start() + 1
            break

    return normalized_text[left:right].strip()


def run_generated_citation_support_spot_audit() -> Dict[str, Any]:
    run_dir = ROOT / "outputs" / GENERATED_CITATION_SPOT_AUDIT_RUN_ID
    survey_tex_path = run_dir / "latex" / "survey.tex"
    papers_dir = run_dir / "papers"

    survey_tex = survey_tex_path.read_text(encoding="utf-8", errors="ignore")

    samples: List[Dict[str, Any]] = []
    overall = {"supported": 0, "partial": 0, "unsupported": 0, "total": 0}
    issue_tag_counts: Counter[str] = Counter()

    for sample in GENERATED_CITATION_SUPPORT_SPOT_AUDIT:
        paper_path = papers_dir / f"{sample['citation_key']}.json"
        paper = load_json(paper_path)
        sentence = extract_sentence_by_anchor(survey_tex, sample["anchor_text"])
        row = {
            "citation_key": sample["citation_key"],
            "sentence": sentence,
            "paper_title": paper.get("title", ""),
            "label": sample["label"],
            "issue_tag": sample["issue_tag"],
            "rationale": sample["rationale"],
        }
        samples.append(row)
        overall[sample["label"]] += 1
        overall["total"] += 1
        issue_tag_counts[sample["issue_tag"]] += 1

    supported_or_partial_rate = (overall["supported"] + overall["partial"]) / overall["total"] if overall["total"] else 0.0

    return {
        "experiment_type": "generated_citation_support_spot_audit",
        "scope_note": (
            "Single-annotator author-side spot audit over 12 single-citation body sentences sampled from one archived generated survey. "
            "Each judgment is based on the repository-local cited-paper cache and is intended as a low-cost claim-to-citation sanity check rather than a benchmark-grade human evaluation."
        ),
        "run_id": GENERATED_CITATION_SPOT_AUDIT_RUN_ID,
        "samples": samples,
        "overall": overall,
        "supported_or_partial_rate": supported_or_partial_rate,
        "issue_tag_counts": dict(issue_tag_counts),
    }


def fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}\\%"


def fmt_float(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}"


def build_markdown_report(
    graph_summary: Dict[str, Any],
    budget_sweep_summary: Dict[str, Any],
    confidence_sweep_summary: Dict[str, Any],
    relation_family_summary: Dict[str, Any],
    core_score_summary: Dict[str, Any],
    input_integrity_summary: Dict[str, Any],
    edge_summary: Dict[str, Any],
    edge_confidence_profile: Dict[str, Any],
    runtime_summary: Dict[str, Any],
    artifact_dedup_summary: Dict[str, Any],
    artifact_structure_summary: Dict[str, Any],
    artifact_length_normalized_summary: Dict[str, Any],
    spot_audit_summary: Dict[str, Any],
    generated_spot_audit_summary: Dict[str, Any] | None = None,
) -> str:
    lines: List[str] = []
    generated_spot_audit_summary = generated_spot_audit_summary or {}
    lines.append("# Minimal Real Revision Audit (2026-05-24)")
    lines.append("")
    lines.append("This report aggregates locally computed diagnostics over archived/fresh artifacts:")
    lines.append("1. offline graph retrieval diagnostic ablation,")
    lines.append("2. retrieval budget sweep plus a confidence-threshold robustness sweep,")
    lines.append("3. relation-family retrieval ablation,")
    lines.append("4. core-score weight sensitivity audit,")
    lines.append("5. archived input/title-integrity audit,")
    lines.append("6. MEKG semantic-edge consistency audit,")
    lines.append("7. runtime/cost summary,")
    lines.append("8. released-artifact dedup robustness audit,")
    lines.append("9. structural-proxy robustness audit,")
    lines.append("10. length-normalized artifact proxy audit,")
    lines.append("11. a small single-annotator citation-support spot audit,")
    lines.append("12. and a generated-survey claim-to-citation spot audit over single-citation body sentences.")
    lines.append("")
    lines.append("## 1. Offline Graph Retrieval Diagnostic")
    lines.append("")
    lines.append("| Metric | Flat mean | Graph-aware mean | Mean delta | Graph better runs |")
    lines.append("|---|---:|---:|---:|---:|")
    for metric, pretty in [
        ("core_paper_recall", "Core-paper recall"),
        ("community_coverage", "Community coverage"),
        ("avg_pagerank", "Average PageRank"),
        ("relation_density", "Relation density"),
        ("unique_papers", "Unique papers"),
    ]:
        row = graph_summary["aggregate"][metric]
        lines.append(
            f"| {pretty} | {fmt_float(row['flat_mean'])} | {fmt_float(row['graph_mean'])} | {fmt_float(row['delta_mean'])} | {row['graph_better_runs']}/8 |"
        )
    lines.append("")
    lines.append("### Paired Sign-Flip Summary")
    lines.append("")
    lines.append("| Metric | Positive / nonzero pairs | Mean delta | Median delta | One-sided p (>0) | Two-sided p |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for metric, pretty in [
        ("core_paper_recall", "Core-paper recall"),
        ("community_coverage", "Community coverage"),
        ("avg_pagerank", "Average PageRank"),
        ("relation_density", "Relation density"),
        ("unique_papers", "Unique papers"),
    ]:
        row = graph_summary["paired_significance"][metric]
        lines.append(
            f"| {pretty} | {row['positive_pairs']}/{row['nonzero_pairs']} | {fmt_float(row['observed_mean_delta'])} | {fmt_float(row['observed_median_delta'])} | {fmt_float(row['one_sided_p_greater'], 4)} | {fmt_float(row['two_sided_p'], 4)} |"
        )
    lines.append("")
    lines.append("### Signal-Component Ablation")
    lines.append("")
    lines.append("| Variant | Core recall | Community cov. | Avg PageRank | Relation density | Unique papers |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for key, pretty in [
        ("full", "Full graph-aware"),
        ("no_overlap", "No overlap"),
        ("no_centrality", "No centrality"),
        ("no_expansion", "No expansion"),
        ("flat", "Flat lexical"),
    ]:
        row = graph_summary["signal_component_ablation"]["aggregate"][key]
        lines.append(
            f"| {pretty} | {fmt_float(row['core_paper_recall']['mean'])} | {fmt_float(row['community_coverage']['mean'])} | {fmt_float(row['avg_pagerank']['mean'])} | {fmt_float(row['relation_density']['mean'])} | {fmt_float(row['unique_papers']['mean'])} |"
        )
    lines.append("")
    lines.append("| Variant vs. full | Core recall Δ | Community cov. Δ | Avg PageRank Δ | Relation density Δ | Full better runs (core recall) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for key, pretty in [
        ("no_overlap", "No overlap"),
        ("no_centrality", "No centrality"),
        ("no_expansion", "No expansion"),
        ("flat", "Flat lexical"),
    ]:
        row = graph_summary["signal_component_ablation"]["pairwise_vs_full"][key]
        lines.append(
            f"| {pretty} | {fmt_float(row['core_paper_recall']['delta_mean'])} | {fmt_float(row['community_coverage']['delta_mean'])} | {fmt_float(row['avg_pagerank']['delta_mean'])} | {fmt_float(row['relation_density']['delta_mean'])} | {row['core_paper_recall']['full_better_runs']}/8 |"
        )
    lines.append("")
    lines.append("> Interpretation: the largest drop comes from removing 1-hop expansion, which nearly reverts the diagnostic to the flat lexical baseline. Removing centrality causes only a mild degradation on recall/PageRank exposure, while removing category/subcategory overlap is nearly neutral on this archived slice.")
    lines.append("")
    lines.append("> Interpretation: this is a retrieval-side diagnostic under a fixed budget of top-5 papers per non-intro/non-conclusion section, not a public benchmark.")
    lines.append("")
    lines.append("## 2. Relation-Family Retrieval Ablation")
    lines.append("")
    lines.append("| Variant | Core recall | Community cov. | Avg PageRank | Relation density | Unique papers |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for key, pretty in [
        ("full", "Full graph"),
        ("no_support", "No support"),
        ("structural_only", "Structural-only"),
        ("semantic_only", "Semantic-only"),
    ]:
        row = relation_family_summary["aggregate"][key]
        lines.append(
            f"| {pretty} | {fmt_float(row['core_paper_recall']['mean'])} | {fmt_float(row['community_coverage']['mean'])} | {fmt_float(row['avg_pagerank']['mean'])} | {fmt_float(row['relation_density']['mean'])} | {fmt_float(row['unique_papers']['mean'])} |"
        )
    lines.append("")
    lines.append("| Variant vs. full | Core recall Δ | Community cov. Δ | Avg PageRank Δ | Relation density Δ | Full better runs (core recall) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for key, pretty in [
        ("no_support", "No support"),
        ("structural_only", "Structural-only"),
        ("semantic_only", "Semantic-only"),
    ]:
        row = relation_family_summary["pairwise_vs_full"][key]
        lines.append(
            f"| {pretty} | {fmt_float(row['core_paper_recall']['delta_mean'])} | {fmt_float(row['community_coverage']['delta_mean'])} | {fmt_float(row['avg_pagerank']['delta_mean'])} | {fmt_float(row['relation_density']['delta_mean'])} | {row['core_paper_recall']['full_better_runs']}/8 |"
        )
    lines.append("")
    lines.append("> Interpretation: removing only generic `supports` edges changes retrieval little on average, while restricting the graph to structural-only or semantic-only relation families degrades core-paper recall and average PageRank exposure, indicating that the current retrieval signal benefits from a mixed relation inventory rather than any single family alone.")
    lines.append("")
    lines.append("## 3. Retrieval Budget Sweep")
    lines.append("")
    lines.append("| Budget | Flat core recall | Graph core recall | Graph Δ | Graph better runs |")
    lines.append("|---|---:|---:|---:|---:|")
    for budget in budget_sweep_summary["budgets"]:
        row = budget_sweep_summary["aggregate"][str(budget)]["core_paper_recall"]
        lines.append(
            f"| top-{budget} | {fmt_float(row['flat_mean'])} | {fmt_float(row['graph_mean'])} | {fmt_float(row['delta_mean'])} | {row['graph_better_runs']}/8 |"
        )
    lines.append("")
    lines.append("| Budget | Flat relation density | Graph relation density | Graph Δ | Graph better runs |")
    lines.append("|---|---:|---:|---:|---:|")
    for budget in budget_sweep_summary["budgets"]:
        row = budget_sweep_summary["aggregate"][str(budget)]["relation_density"]
        lines.append(
            f"| top-{budget} | {fmt_float(row['flat_mean'])} | {fmt_float(row['graph_mean'])} | {fmt_float(row['delta_mean'])} | {row['graph_better_runs']}/8 |"
        )
    lines.append("")
    lines.append("> Interpretation: the graph-aware advantage is stable across modest top-k budgets, so using a fixed top-5 budget is a conservative middle ground rather than a cherry-picked setting.")
    lines.append("")
    lines.append("### Confidence-Threshold Robustness Sweep")
    lines.append("")
    lines.append("| Min confidence | Retained relations | Graph core recall | Recall Δ | Graph relation density | Recall wins |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for threshold in confidence_sweep_summary["thresholds"]:
        key = f"{float(threshold):.1f}"
        core_row = confidence_sweep_summary["aggregate"][key]["core_paper_recall"]
        density_row = confidence_sweep_summary["aggregate"][key]["relation_density"]
        retained_share = confidence_sweep_summary["aggregate"][key]["active_relation_share_mean"]
        lines.append(
            f"| ≥{key} | {retained_share * 100:.1f}% | {fmt_float(core_row['graph_mean'])} | {fmt_float(core_row['delta_mean'])} | {fmt_float(density_row['graph_mean'])} | {core_row['graph_better_runs']}/8 |"
        )
    lines.append("")
    lines.append("> Interpretation: even after pruning the archived graph to edges with confidence ≥0.7 or ≥0.9, graph-aware retrieval still stays above the flat baseline on core-paper recall and relation density, so the gain is not driven only by weak links.")
    lines.append("")
    lines.append("## 4. Core-Score Weight Sensitivity Audit")
    lines.append("")
    lines.append(
        f"- Across {core_score_summary['aggregate']['runs']} archived runs, the default 10\\% target count yields a mean default core-set size of **{core_score_summary['aggregate']['default_core_count_mean']:.2f}**, while the elbow heuristic expands this to **{core_score_summary['aggregate']['elbow_count_mean']:.2f}** on average."
    )
    lines.append(
        f"- Citation signal availability is structurally limited in the archived artifacts: **{core_score_summary['aggregate']['citation_signal_nonzero_runs']} / {core_score_summary['aggregate']['runs']}** runs contain non-zero citation counts."
    )
    lines.append("")
    lines.append("| Variant vs. base top-10 | Mean overlap | Median overlap | Range |")
    lines.append("|---|---:|---:|---:|")
    for key, pretty in [
        ("pr_heavy", "PageRank-heavy"),
        ("citation_heavy", "Citation-heavy"),
        ("recency_heavy", "Recency-heavy"),
        ("degree_heavy", "Degree-heavy"),
    ]:
        row = core_score_summary["aggregate"]["variant_overlap_vs_base"][key]
        lines.append(
            f"| {pretty} | {row['mean']:.2f} | {row['median']:.2f} | {int(row['min'])}--{int(row['max'])} |"
        )
    lines.append("")
    lines.append("> Interpretation: under the current archived data, the hand-tuned core-paper ranking is fairly stable to moderate weight changes, but the citation term is effectively dormant because the saved MEKG paper records contain zero citation counts.")
    lines.append("")
    lines.append("## 5. Archived Input / Title-Integrity Audit")
    lines.append("")
    input_agg = input_integrity_summary.get("aggregate", {})
    lines.append(
        f"- Scope: **{input_agg.get('total_runs', 0)}** archived runs, **{input_agg.get('total_papers', 0)}** paper records, **{input_agg.get('total_relations', 0)}** relation records."
    )
    lines.append(
        f"- We found **{input_agg.get('exact_title_duplicate_rows', 0)}** within-run exact title duplicates and **{input_agg.get('normalized_title_duplicate_rows', 0)}** within-run normalized title duplicates across the archived MEKG paper stores."
    )
    lines.append(
        f"- Dangling relation endpoints are absent in this archive slice: unresolved sources = **{input_agg.get('unresolved_relation_source_count', 0)}**, unresolved targets = **{input_agg.get('unresolved_relation_target_count', 0)}**."
    )
    lines.append(
        f"- Relation confidence ranges from **{fmt_float(input_agg.get('confidence_min', 0.0))}** to **{fmt_float(input_agg.get('confidence_max', 0.0))}**, with mean **{fmt_float(input_agg.get('confidence_mean', 0.0))}**."
    )
    lines.append("")
    lines.append("| Check | Result |")
    lines.append("|---|---:|")
    lines.append(f"| Missing paper titles | {input_agg.get('paper_missing_field_counts', {}).get('title', 0)} |")
    lines.append(f"| Missing paper abstracts | {input_agg.get('paper_missing_field_counts', {}).get('abstract', 0)} |")
    lines.append(f"| Missing paper categories | {input_agg.get('paper_missing_field_counts', {}).get('category', 0)} |")
    lines.append(f"| Missing paper subcategories | {input_agg.get('paper_missing_field_counts', {}).get('subcategory', 0)} |")
    lines.append(f"| Missing paper years | {input_agg.get('paper_missing_field_counts', {}).get('year', 0)} |")
    lines.append(f"| Missing paper sources | {input_agg.get('paper_missing_field_counts', {}).get('source', 0)} |")
    lines.append(f"| Missing relation source IDs | {input_agg.get('relation_missing_field_counts', {}).get('source', 0)} |")
    lines.append(f"| Missing relation target IDs | {input_agg.get('relation_missing_field_counts', {}).get('target', 0)} |")
    lines.append(f"| Missing relation types | {input_agg.get('relation_missing_field_counts', {}).get('type', 0)} |")
    lines.append(f"| Missing relation confidences | {input_agg.get('relation_missing_field_counts', {}).get('confidence', 0)} |")
    lines.append("")
    lines.append("> Interpretation: the repository's online fetcher already applies normalized-title deduplication when merging sources, and the archived eight-run slice shows zero within-run exact or normalized title duplicates, so the current graph size is unlikely to be an artifact of trivial paper-store duplication inside each saved run.")
    lines.append("")
    lines.append("## 6. MEKG Semantic-Edge Consistency Audit")
    lines.append("")
    lines.append("| Relation | Count | Temporal direction consistency | Explicit source cue support | Avg confidence |")
    lines.append("|---|---:|---:|---:|---:|")
    for rel_type in SEMANTIC_RELATIONS:
        row = edge_summary["aggregate"][rel_type]
        lines.append(
            f"| {rel_type} | {row['count']} | {fmt_pct(row['temporal_direction_consistency'])} | {fmt_pct(row['explicit_source_cue_support'])} | {fmt_float(row['avg_confidence'])} |"
        )
    lines.append("")
    lines.append("### Confidence-Stratified Semantic-Edge Profile")
    lines.append("")
    lines.append("| Min confidence | Retained semantic edges | Temporal direction consistency | Explicit source cue support | Avg confidence |")
    lines.append("|---|---:|---:|---:|---:|")
    for threshold in edge_confidence_profile["thresholds"]:
        key = f"{float(threshold):.1f}"
        row = edge_confidence_profile["aggregate"][key]["overall"]
        lines.append(
            f"| ≥{key} | {row['count']} | {fmt_pct(row['temporal_direction_consistency'])} | {fmt_pct(row['explicit_source_cue_support'])} | {fmt_float(row['avg_confidence'])} |"
        )
    lines.append("")
    lines.append("> Interpretation: higher-confidence semantic edges retain near-perfect temporal direction, while explicit lexical cue support rises modestly with the confidence threshold, suggesting that the archived confidence scores are not completely decoupled from local textual evidence.")
    lines.append("")
    lines.append("> Interpretation: this is a consistency audit only. It does **not** replace human precision/recall annotation.")
    lines.append("")
    lines.append("## 7. Runtime / Cost Summary")
    lines.append("")
    archived = runtime_summary["archived_full_runs"]["summary"]
    lines.append(
        f"- Archived full runs: mean end-to-end stage sum = **{archived['total_minutes_mean']:.2f} min**, median = **{archived['total_minutes_median']:.2f} min**, range = **{archived['total_minutes_min']:.2f}–{archived['total_minutes_max']:.2f} min**."
    )
    lines.append("- Mean stage share across archived full runs:")
    for stage, share in archived["stage_share_mean"].items():
        lines.append(f"  - `{stage}`: {share * 100:.1f}%")
    lines.append("")
    lines.append("| Fresh run | Total minutes | Input tokens | Output tokens | Cost |")
    lines.append("|---|---:|---:|---:|---:|")
    for row in runtime_summary["fresh_low_cost_runs"]:
        lines.append(
            f"| {row['label']} | {row['total_minutes']:.2f} | {row['input_tokens']} | {row['output_tokens']} | {row['total_cost']:.6f} |"
        )
    scisage = runtime_summary["scisage_outline_partial"]
    lines.append("")
    lines.append(
        f"- SciSage outline-only partial baseline: **{scisage['latency_seconds']:.2f} s**, {scisage['top_level_sections']} top-level sections, {scisage['total_outline_nodes']} outline nodes."
    )
    lines.append("")
    lines.append("## 8. Released-Artifact Dedup Robustness Audit")
    lines.append("")
    lines.append(
        f"- Across the released artifact comparison rows, we found **{artifact_dedup_summary.get('duplicate_group_count', 0)}** exact-PDF duplicate groups and **{artifact_dedup_summary.get('duplicate_row_count', 0)}** removable rows out of **{artifact_dedup_summary.get('rows_found', 0)}** total rows."
    )
    lines.append("")
    lines.append("| System | Original N | Dedup N | Page mean Δ | Citation mean Δ | Section mean Δ |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for system in ["ARISE", "AutoSurvey", "SurveyForge", "SurveyGraph-GLM-fresh", "SurveyGraph-Qwen-fresh", "SurveyX"]:
        row = artifact_dedup_summary.get("systems", {}).get(system)
        if not row:
            continue
        lines.append(
            f"| {system} | {row['original_count']} | {row['dedup_count']} | {fmt_float(row['metrics']['page_count']['mean_delta'])} | {fmt_float(row['metrics']['citation_mentions_total']['mean_delta'])} | {fmt_float(row['metrics']['section_heading_count']['mean_delta'])} |"
        )
    lines.append("")
    lines.append("> Interpretation: duplicate released PDFs exist, but removing them shifts system-level means only modestly and does not reverse the paper's artifact-level comparison narrative.")
    lines.append("")
    lines.append("## 9. Structural-Proxy Robustness Audit")
    lines.append("")
    lines.append(
        f"- Across all **{artifact_structure_summary.get('rows_found', 0)}** artifact rows, **{artifact_structure_summary.get('rows_with_toc', 0)}** expose non-zero TOC entries."
    )
    lines.append(
        f"- Among artifacts with TOC signals, the TOC-count vs. heading-count exact-match rate is **{artifact_structure_summary.get('toc_heading_exact_match_rate', 0.0) * 100:.1f}\\%**; references headings are recoverable in **{artifact_structure_summary.get('references_heading_rate', 0.0) * 100:.1f}\\%** of all rows."
    )
    lines.append("")
    lines.append("| System | N | TOC rows | Exact TOC=heading | References heading rate |")
    lines.append("|---|---:|---:|---:|---:|")
    for system in ["ARISE", "AutoSurvey", "SurveyForge", "SurveyGraph-GLM-fresh", "SurveyGraph-Qwen-fresh", "SurveyX"]:
        row = artifact_structure_summary.get("systems", {}).get(system)
        if not row:
            continue
        lines.append(
            f"| {system} | {row['count']} | {row['rows_with_toc']} | {row['toc_heading_exact_match_rate'] * 100:.1f}\\% | {row['references_heading_rate'] * 100:.1f}\\% |"
        )
    lines.append("")
    lines.append("> Interpretation: the cheap structure proxies used in the artifact-level comparison are internally consistent for almost all released/fresh PDFs, so the comparison is unlikely to hinge on a brittle heading extractor.")
    lines.append("")
    lines.append("## 10. Length-Normalized Artifact Proxy Audit")
    lines.append("")
    lines.append(
        f"- After SHA-based deduplication, the length-normalized audit covers **{artifact_length_normalized_summary.get('dedup_rows', 0)}** rows out of **{artifact_length_normalized_summary.get('rows_found', 0)}** original artifact-comparison rows."
    )
    sg_combined = artifact_length_normalized_summary.get("surveygraph_fresh_combined", {})
    lines.append(
        f"- The two fresh SurveyGraph reruns together retain non-zero normalized structure/media density (headings **{fmt_float(sg_combined.get('heading_density_per_10k_words_median', 0.0))}** per 10k words; figure+table mentions **{fmt_float(sg_combined.get('table_figure_density_per_10k_words_median', 0.0))}** per 10k words) with an editable-artifact rate of **{fmt_pct(sg_combined.get('editable_artifact_rate', 0.0))}**."
    )
    lines.append("")
    lines.append("| System | Dedup N | Cit./1k | Head./10k | Fig+Tab./10k | Editable |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for system in ["ARISE", "AutoSurvey", "SurveyForge", "SurveyX"]:
        row = artifact_length_normalized_summary.get("systems", {}).get(system)
        if not row:
            continue
        lines.append(
            f"| {system} | {row.get('count', 0)} | {fmt_float(row.get('citation_density_per_1k_words_median', 0.0))} | {fmt_float(row.get('heading_density_per_10k_words_median', 0.0))} | {fmt_float(row.get('table_figure_density_per_10k_words_median', 0.0))} | {row.get('editable_artifact_rate', 0.0) * 100:.1f}\\% |"
        )
    if sg_combined:
        lines.append(
            f"| SurveyGraph-fresh (combined) | {sg_combined.get('count', 0)} | {fmt_float(sg_combined.get('citation_density_per_1k_words_median', 0.0))} | {fmt_float(sg_combined.get('heading_density_per_10k_words_median', 0.0))} | {fmt_float(sg_combined.get('table_figure_density_per_10k_words_median', 0.0))} | {sg_combined.get('editable_artifact_rate', 0.0) * 100:.1f}\\% |"
        )
    lines.append("")
    lines.append("> Interpretation: the released/fresh structural comparison is not only a raw-length effect. After normalizing by word count, ARISE still shows high heading density, SurveyGraph fresh reruns retain non-zero figure/table density together with editable TeX/Bib artifacts, and AutoSurvey remains near zero on heading/table density.")
    lines.append("")
    lines.append("## 11. Single-Annotator Citation-Support Spot Audit")
    lines.append("")
    overall = spot_audit_summary.get("overall", {})
    lines.append(
        f"- Scope: one archived run (`{spot_audit_summary.get('run_id', 'N/A')}`), {overall.get('total', 0)} sampled semantic edges, exploratory single-annotator labels."
    )
    lines.append(
        f"- Overall labels: supported = **{overall.get('supported', 0)}**, partial = **{overall.get('partial', 0)}**, unsupported = **{overall.get('unsupported', 0)}**."
    )
    lines.append(
        f"- Supported-or-partial rate: **{spot_audit_summary.get('supported_or_partial_rate', 0.0) * 100:.1f}\\%**."
    )
    weak_case_total = spot_audit_summary.get("weak_case_total", 0)
    failure_mode_counts = spot_audit_summary.get("failure_mode_counts", {})
    if weak_case_total:
        lines.append(
            f"- Among the **{weak_case_total}** partial-or-unsupported cases, the dominant failure modes are:"
        )
        for key in [
            "topical_overlap_without_explicit_lineage",
            "target_role_mismatch",
            "cross_task_mismatch",
            "temporal_reversal",
        ]:
            if key in failure_mode_counts:
                lines.append(
                    f"  - {FAILURE_MODE_DISPLAY[key]}: **{failure_mode_counts[key]}**"
                )
    lines.append("")
    lines.append("| Relation | Supported | Partial | Unsupported | Total |")
    lines.append("|---|---:|---:|---:|---:|")
    for rel_type in SEMANTIC_RELATIONS:
        row = spot_audit_summary.get("aggregate", {}).get(rel_type, {})
        lines.append(
            f"| {rel_type} | {row.get('supported', 0)} | {row.get('partial', 0)} | {row.get('unsupported', 0)} | {row.get('total', 0)} |"
        )
    lines.append("")
    lines.append("> Interpretation: this is a tiny author-side spot audit, not a human-annotated benchmark or an inter-annotator agreement study.")
    lines.append("")
    lines.append("## 12. Generated-Survey Citation-Support Spot Audit")
    lines.append("")
    generated_overall = generated_spot_audit_summary.get("overall", {})
    lines.append(
        f"- Scope: one archived generated survey (`{generated_spot_audit_summary.get('run_id', 'N/A')}`), {generated_overall.get('total', 0)} sampled single-citation body sentences, with labels assigned against the repository-local cited-paper cache."
    )
    lines.append(
        f"- Overall labels: supported = **{generated_overall.get('supported', 0)}**, partial = **{generated_overall.get('partial', 0)}**, unsupported = **{generated_overall.get('unsupported', 0)}**."
    )
    lines.append(
        f"- Supported-or-partial rate: **{generated_spot_audit_summary.get('supported_or_partial_rate', 0.0) * 100:.1f}\\%**."
    )
    issue_tag_counts = generated_spot_audit_summary.get("issue_tag_counts", {})
    nontrivial_issue_rows = [
        (key, count)
        for key, count in issue_tag_counts.items()
        if key != "well_supported"
    ]
    if nontrivial_issue_rows:
        lines.append("- Non-fully-supported issue tags:")
        for key, count in sorted(nontrivial_issue_rows, key=lambda item: (-item[1], item[0])):
            pretty = GENERATED_CITATION_ISSUE_DISPLAY.get(key, key.replace("_", " "))
            lines.append(f"  - {pretty}: **{count}**")
    lines.append("")
    lines.append("| Label | Count |")
    lines.append("|---|---:|")
    for label in ["supported", "partial", "unsupported"]:
        lines.append(f"| {label} | {generated_overall.get(label, 0)} |")
    lines.append("")
    lines.append("> Interpretation: this second audit targets generated survey claims directly, but it is still a tiny single-annotator check over one archived run and should not be read as a substitute for full citation-faithfulness evaluation.")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ensure_dir(OUTPUT_ROOT)

    runs = load_archived_runs()
    graph_summary = run_graph_retrieval_diagnostic(runs)
    budget_sweep_summary = run_retrieval_budget_sweep(runs)
    confidence_sweep_summary = run_confidence_threshold_sweep(runs)
    relation_family_summary = run_relation_family_ablation(runs)
    core_score_summary = run_core_score_weight_sensitivity_audit(runs)
    input_integrity_summary = run_archived_input_integrity_audit(runs)
    edge_summary = run_edge_audit(runs)
    edge_confidence_profile = run_edge_confidence_profile(runs)
    runtime_summary = run_runtime_cost_summary(runs)
    artifact_dedup_summary = run_artifact_dedup_robustness_audit()
    artifact_structure_summary = run_artifact_structure_proxy_robustness_audit()
    artifact_length_normalized_summary = run_artifact_length_normalized_proxy_audit()
    spot_audit_summary = run_manual_spot_audit(runs)
    generated_spot_audit_summary = run_generated_citation_support_spot_audit()

    combined = {
        "generated_at": "2026-05-24",
        "graph_retrieval_diagnostic": graph_summary,
        "retrieval_budget_sweep": budget_sweep_summary,
        "relation_confidence_threshold_sweep": confidence_sweep_summary,
        "relation_family_ablation": relation_family_summary,
        "core_score_weight_sensitivity_audit": core_score_summary,
        "archived_input_integrity_audit": input_integrity_summary,
        "mekg_edge_audit": edge_summary,
        "mekg_edge_confidence_profile": edge_confidence_profile,
        "runtime_cost_summary": runtime_summary,
        "artifact_dedup_robustness_audit": artifact_dedup_summary,
        "artifact_structure_proxy_robustness_audit": artifact_structure_summary,
        "artifact_length_normalized_proxy_audit": artifact_length_normalized_summary,
        "manual_citation_support_spot_audit": spot_audit_summary,
        "generated_citation_support_spot_audit": generated_spot_audit_summary,
    }

    write_json(OUTPUT_ROOT / "graph_retrieval_diagnostic_summary.json", graph_summary)
    write_json(OUTPUT_ROOT / "retrieval_budget_sweep_summary.json", budget_sweep_summary)
    write_json(OUTPUT_ROOT / "relation_confidence_threshold_sweep_summary.json", confidence_sweep_summary)
    write_json(OUTPUT_ROOT / "relation_family_ablation_summary.json", relation_family_summary)
    write_json(OUTPUT_ROOT / "core_score_weight_sensitivity_audit.json", core_score_summary)
    write_json(OUTPUT_ROOT / "archived_input_integrity_audit.json", input_integrity_summary)
    write_json(OUTPUT_ROOT / "mekg_edge_audit_summary.json", edge_summary)
    write_json(OUTPUT_ROOT / "mekg_edge_confidence_profile_summary.json", edge_confidence_profile)
    write_json(OUTPUT_ROOT / "runtime_cost_summary.json", runtime_summary)
    write_json(OUTPUT_ROOT / "artifact_dedup_robustness_audit.json", artifact_dedup_summary)
    write_json(OUTPUT_ROOT / "artifact_structure_proxy_robustness_audit.json", artifact_structure_summary)
    write_json(OUTPUT_ROOT / "artifact_length_normalized_proxy_audit.json", artifact_length_normalized_summary)
    write_json(OUTPUT_ROOT / "manual_citation_support_spot_audit_summary.json", spot_audit_summary)
    write_json(OUTPUT_ROOT / "generated_citation_support_spot_audit_summary.json", generated_spot_audit_summary)
    write_json(OUTPUT_ROOT / "minimal_real_revision_combined.json", combined)
    (OUTPUT_ROOT / "minimal_real_revision_report.md").write_text(
        build_markdown_report(
            graph_summary,
            budget_sweep_summary,
            confidence_sweep_summary,
            relation_family_summary,
            core_score_summary,
            input_integrity_summary,
            edge_summary,
            edge_confidence_profile,
            runtime_summary,
            artifact_dedup_summary,
            artifact_structure_summary,
            artifact_length_normalized_summary,
            spot_audit_summary,
            generated_spot_audit_summary,
        ),
        encoding="utf-8",
    )

    print(f"Wrote outputs to: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
