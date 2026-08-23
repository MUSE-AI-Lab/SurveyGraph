"""
Professional Survey Table Builder

This module provides functionality to generate professional, systematic tables
for academic survey papers, similar to high-quality tables found in top venues.

Features:
- Router mechanism to select appropriate table types
- Diverse table generation (no duplicate types)
- Categorical organization with colored header rows
- Multi-dimensional comparison columns
- Citation integration
- Symbol system (✓/✗) for binary features
- Support for 10+ table types
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum

from tenacity import retry, stop_after_attempt, wait_fixed

from src.configs.config import ADVANCED_CHATAGENT_MODEL, BASE_DIR
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.modules.latex_handler.latex_base_table_builder import LatexBaseTableBuilder
from src.modules.utils import (
    load_file_as_string,
    load_prompt,
    load_single_file,
    save_result,
)

logger = get_logger("src.modules.latex_handler.LatexSurveyTableBuilder")


class SurveyTableType(Enum):
    """Enumeration of supported survey table types."""
    # Original types
    BENCHMARK_COMPARISON = "benchmark_comparison"
    METHOD_COMPARISON = "method_comparison"
    TOOL_COMPARISON = "tool_comparison"
    TAXONOMY_TABLE = "taxonomy_table"
    CHRONOLOGICAL_SUMMARY = "chronological_summary"
    FEATURE_MATRIX = "feature_matrix"
    # New types based on professional survey tables
    STATISTICS_TABLE = "statistics_table"
    ANNOTATION_SCHEME_TABLE = "annotation_scheme_table"
    DISTRIBUTION_MATRIX_TABLE = "distribution_matrix_table"
    PERFORMANCE_COMPARISON_TABLE = "performance_comparison_table"
    EVIDENCE_TABLE = "evidence_table"
    TREND_ANALYSIS_TABLE = "trend_analysis_table"
    FORMULA_COMPARISON_TABLE = "formula_comparison_table"
    APPLICATION_OVERVIEW_TABLE = "application_overview_table"
    # New visually appealing table types
    CONTRIBUTION_SUMMARY_TABLE = "contribution_summary_table"
    RESEARCH_LANDSCAPE_TABLE = "research_landscape_table"


class LatexSurveyTableBuilder(LatexBaseTableBuilder):
    """
    Professional survey table builder for generating systematic,
    well-organized tables suitable for academic survey papers.
    
    This builder supports:
    - Router mechanism to intelligently select table types
    - Diverse table generation (no duplicate types)
    - Benchmark comparison tables
    - Method comparison tables with categorical organization
    - Performance comparison tables
    - Evidence tables with citations
    - Trend analysis tables
    - Application overview tables
    - And more...
    """
    
    # Maximum number of survey tables to generate
    MAX_SURVEY_TABLES = 4
    
    # Minimum number of tables to generate
    MIN_SURVEY_TABLES = 2
    
    def __init__(
        self,
        main_body_path: Path,
        tmp_path: Path,
        latex_path: Path,
        outline_path: Path,
        paper_dir: Path,
        prompt_dir: Path,
        chat_agent: ChatAgent,
        survey_topic: str = "",
    ):
        """
        Initialize the survey table builder.
        
        Args:
            main_body_path: Path to the main body tex file
            tmp_path: Path to temporary directory
            latex_path: Path to latex output directory
            outline_path: Path to outline file
            paper_dir: Path to paper data directory
            prompt_dir: Path to prompt templates directory
            chat_agent: ChatAgent instance for LLM calls
            survey_topic: Topic of the survey (used in table generation)
        """
        self.chat_agent = chat_agent
        super().__init__(chat_agent=self.chat_agent)
        
        self.main_body_path = main_body_path
        self.latex_path = latex_path
        self.outline_path = outline_path
        self.paper_dir = paper_dir
        self.prompt_dir = prompt_dir
        self.tmp_path = tmp_path
        self.survey_topic = survey_topic
        
        # Prompt paths
        self.survey_table_prompt_path = Path(BASE_DIR) / "resources/LLM/prompts/dynamic_visual/generate_survey_table.md"
        self.table_router_prompt_path = Path(BASE_DIR) / "resources/LLM/prompts/dynamic_visual/table_type_router.md"
        self.comparison_prompt_path = Path(BASE_DIR) / "resources/LLM/prompts/dynamic_visual/generate_comparison_table.md"
        self.summary_prompt_path = Path(BASE_DIR) / "resources/LLM/prompts/dynamic_visual/generate_summary_table.md"
        self.description_prompt_path = prompt_dir / "Table_description.txt"
        self.rewrite_prompt_path = prompt_dir / "Content_rewrite.txt"
        
        # Output paths
        self.survey_table_tex_path = latex_path / "survey_table.tex"
        
        # Counter for generated tables
        self.generated_tables = 0
        
        # Track generated table types to avoid duplicates
        self.generated_table_types: List[str] = []
        
        # Track used sections to avoid placing multiple tables in the same section
        self.used_sections: List[str] = []
        
        # Store generated table information for downstream use (e.g., avoiding duplicate visuals)
        self.generated_table_info: List[Dict[str, Any]] = []
        
        # Table type categories for diversity checking
        self.table_type_categories = {
            "comparison": ["benchmark_comparison", "method_comparison", "performance_comparison_table"],
            "overview": ["application_overview_table", "taxonomy_table", "tool_comparison", "research_landscape_table"],
            "analysis": ["trend_analysis_table", "statistics_table", "distribution_matrix_table"],
            "detail": ["annotation_scheme_table", "evidence_table", "formula_comparison_table", "chronological_summary", "feature_matrix"],
            "summary": ["contribution_summary_table"],  # New category for summary-style tables
        }
        
        # Track used categories
        self.used_categories: List[str] = []

    def _optional_remote_chat(
        self,
        prompt: str,
        *,
        purpose: str,
        timeout: int = 180,
    ) -> Optional[str]:
        """
        Run an optional table-generation LLM call without retry stacking.

        Table routing/generation is useful for final paper polish, but it is not
        allowed to block an otherwise complete pipeline for many retry attempts.
        Prefer ChatAgent.remote_chat_no_retry when available; fall back to a
        single timeout-bounded remote_chat call for older injected agents.
        """
        try:
            if hasattr(self.chat_agent, "remote_chat_no_retry"):
                response = self.chat_agent.remote_chat_no_retry(
                    text_content=prompt,
                    model=ADVANCED_CHATAGENT_MODEL,
                    timeout=timeout,
                )
            else:
                response = self.chat_agent.remote_chat(
                    text_content=prompt,
                    model=ADVANCED_CHATAGENT_MODEL,
                    timeout=timeout,
                )
        except Exception as e:
            logger.warning(f"Optional {purpose} LLM call failed: {e}")
            return None

        if response is None:
            logger.warning(f"Optional {purpose} LLM call returned None")
            return None

        if isinstance(response, str) and response.startswith("Error:"):
            logger.warning(f"Optional {purpose} LLM call returned error: {response[:200]}")
            return None

        return response
    
    def _extract_topic_from_outline(self) -> str:
        """Extract the survey topic from the outline."""
        try:
            outlines = load_single_file(self.outline_path)
            if isinstance(outlines, dict) and "title" in outlines:
                return outlines["title"]
            elif isinstance(outlines, dict) and "sections" in outlines:
                # Try to infer topic from section titles
                sections = outlines.get("sections", [])
                if sections:
                    first_section = sections[0].get("section title", "")
                    return first_section
        except Exception as e:
            logger.warning(f"Could not extract topic from outline: {e}")
        return self.survey_topic or "Survey Topic"
    
    def _find_parent_section_for_subsection(self, subsection_name: str) -> Optional[str]:
        """
        Find the parent section name for a given subsection name from the outline.
        
        Args:
            subsection_name: The name of the subsection to find parent for
            
        Returns:
            The parent section name or None if not found
        """
        try:
            outlines = load_single_file(self.outline_path)
            if not isinstance(outlines, dict) or "sections" not in outlines:
                return None
            
            for section in outlines.get("sections", []):
                # Check section title (handle both "title" and "section title" keys)
                section_title = section.get("title") or section.get("section title", "")
                
                # Check if the subsection_name matches this section's title
                if section_title.lower() == subsection_name.lower():
                    return section_title
                
                # Check subsections
                for subsection in section.get("subsections", []):
                    subsection_title = subsection.get("title") or subsection.get("subsection title", "")
                    if subsection_title.lower() == subsection_name.lower():
                        return section_title
                    
                    # Check sub-subsections (level 3)
                    for subsubsection in subsection.get("subsections", []):
                        subsubsection_title = subsubsection.get("title") or subsubsection.get("subsection title", "")
                        if subsubsection_title.lower() == subsection_name.lower():
                            return section_title
            
            return None
        except Exception as e:
            logger.warning(f"Could not find parent section for '{subsection_name}': {e}")
            return None
    
    def _extract_content_with_fallback(self, section_name: str) -> Optional[str]:
        """
        Try to extract content using multiple fallback strategies.
        
        1. First try exact section match
        2. Then try exact subsection match
        3. Then try to find parent section and extract that
        4. Finally try case-insensitive matching
        
        Args:
            section_name: The name of the section/subsection to extract
            
        Returns:
            The extracted content or None if all strategies fail
        """
        try:
            # Load the tex file content
            from src.modules.utils import load_file_as_string
            content = load_file_as_string(self.main_body_path)
            
            # Strategy 1: Try case-insensitive section match
            pattern = re.compile(
                r"(\\section\{" + re.escape(section_name) + r"\}.*?)(?=\\section|$)",
                re.DOTALL | re.IGNORECASE,
            )
            match = pattern.search(content)
            if match:
                return match.group(1).strip()
            
            # Strategy 2: Try case-insensitive subsection match
            pattern = re.compile(
                rf"(\\subsection\{{{re.escape(section_name)}\}}.*?)(?=(\\section|\\subsection|$))",
                re.DOTALL | re.IGNORECASE,
            )
            match = pattern.search(content)
            if match:
                return match.group(1).strip()
            
            # Strategy 3: Find parent section from outline and extract that
            parent_section = self._find_parent_section_for_subsection(section_name)
            if parent_section:
                logger.info(f"Found parent section '{parent_section}' for subsection '{section_name}'")
                section_content = self.extract_section_content(self.main_body_path, parent_section)
                if section_content:
                    return section_content
            
            # Strategy 4: Try partial matching - find any section/subsection containing the name
            # This handles cases where the name might be slightly different
            escaped_words = [re.escape(word) for word in section_name.split() if len(word) > 3]
            if escaped_words:
                partial_pattern = r".*".join(escaped_words)
                pattern = re.compile(
                    r"(\\(?:sub)?section\{[^}]*" + partial_pattern + r"[^}]*\}.*?)(?=\\section|$)",
                    re.DOTALL | re.IGNORECASE,
                )
                match = pattern.search(content)
                if match:
                    logger.info(f"Found partial match for '{section_name}'")
                    return match.group(1).strip()
            
            return None
        except Exception as e:
            logger.warning(f"Error in fallback content extraction for '{section_name}': {e}")
            return None
    
    def _determine_table_type(self, section_content: str) -> SurveyTableType:
        """
        Determine the most appropriate table type based on section content.
        
        Args:
            section_content: The content of the section to analyze
            
        Returns:
            The most appropriate SurveyTableType
        """
        content_lower = section_content.lower()
        
        # Check for benchmark-related content
        if any(keyword in content_lower for keyword in ["benchmark", "dataset", "evaluation", "test set"]):
            return SurveyTableType.BENCHMARK_COMPARISON
        
        # Check for method comparison content
        if any(keyword in content_lower for keyword in ["method", "approach", "technique", "algorithm"]):
            return SurveyTableType.METHOD_COMPARISON
        
        # Check for tool/system content
        if any(keyword in content_lower for keyword in ["tool", "system", "framework", "platform", "library"]):
            return SurveyTableType.TOOL_COMPARISON
        
        # Check for taxonomy content
        if any(keyword in content_lower for keyword in ["taxonomy", "classification", "category", "type"]):
            return SurveyTableType.TAXONOMY_TABLE
        
        # Check for chronological content
        if any(keyword in content_lower for keyword in ["evolution", "history", "development", "timeline", "progress"]):
            return SurveyTableType.CHRONOLOGICAL_SUMMARY
        
        # Default to method comparison
        return SurveyTableType.METHOD_COMPARISON
    
    def _build_data_requirements(self, section_content: str, table_type: SurveyTableType) -> str:
        """
        Build data requirements string based on table type and content analysis.
        
        Args:
            section_content: The section content to analyze
            table_type: The type of table to generate
            
        Returns:
            A string describing the data requirements
        """
        # Extract citations from content
        citations = self.extract_cite_name(section_content)
        num_citations = len(citations)
        
        requirements = []
        
        if table_type == SurveyTableType.BENCHMARK_COMPARISON:
            requirements = [
                f"- Include approximately {min(num_citations, 15)} benchmarks/datasets",
                "- Columns should include: Name, Focus/Domain, Size metrics, Source type, Key features (binary), Year",
                "- Group benchmarks into categories (e.g., General vs. Domain-Specific)",
                "- Use $\\checkmark$/$\\times$ symbols for binary features",
                "- Include quantitative data where available (# of instances, # of tools, etc.)",
            ]
        elif table_type == SurveyTableType.METHOD_COMPARISON:
            requirements = [
                f"- Include approximately {min(num_citations, 12)} representative methods",
                "- Columns should include: Method name, Core technique, Key features (binary), Performance, Year",
                "- Group methods by category/approach type",
                "- Use $\\checkmark$/$\\times$ symbols for feature support",
                "- Highlight best performing methods with bold",
            ]
        elif table_type == SurveyTableType.TOOL_COMPARISON:
            requirements = [
                f"- Include approximately {min(num_citations, 10)} tools/systems",
                "- Columns should include: Tool name, Focus area, Capabilities (binary features), Platform, Year",
                "- Use $\\checkmark$/$\\times$ symbols for feature checklist",
                "- Group by tool category if applicable",
            ]
        elif table_type == SurveyTableType.TAXONOMY_TABLE:
            requirements = [
                "- Present hierarchical taxonomy with 2-3 levels",
                "- Columns should include: Category/Subcategory, Description, Representative works",
                "- Use indentation to show hierarchy",
                "- Include 3-5 representative works per subcategory",
            ]
        elif table_type == SurveyTableType.CHRONOLOGICAL_SUMMARY:
            requirements = [
                f"- Include approximately {min(num_citations, 15)} key milestones",
                "- Columns should include: Year, Method/Work, Key Innovation, Impact/Significance",
                "- Order chronologically from earliest to most recent",
                "- Group by era/period if spanning many years",
            ]
        elif table_type == SurveyTableType.STATISTICS_TABLE:
            requirements = [
                "- Present numerical statistics in a clean format",
                "- Columns should include: Category/Source, Year-wise counts or metrics, Totals",
                "- Use proper number formatting (commas for thousands)",
                "- Include summary rows with totals",
            ]
        elif table_type == SurveyTableType.ANNOTATION_SCHEME_TABLE:
            requirements = [
                "- Present classification/annotation scheme clearly",
                "- Columns should include: Label/Rating, Description, Count or Percentage",
                "- Keep descriptions concise but informative",
                "- Order labels logically (e.g., 0-5 for ratings)",
            ]
        elif table_type == SurveyTableType.DISTRIBUTION_MATRIX_TABLE:
            requirements = [
                "- Create a cross-tabulation matrix",
                "- Rows and columns represent different dimensions",
                "- Include row and column totals",
                "- Use compact numeric format",
            ]
        elif table_type == SurveyTableType.PERFORMANCE_COMPARISON_TABLE:
            requirements = [
                f"- Include approximately {min(num_citations, 10)} models/methods",
                "- Columns should include: Model name, Configuration/Variant, Multiple metrics",
                "- Highlight best results with \\textbf{bold}",
                "- Use \\underline{underline} for second-best or per-category best",
                "- Use multirow for models with multiple configurations",
            ]
        elif table_type == SurveyTableType.EVIDENCE_TABLE:
            requirements = [
                "- Present qualitative evidence with proper citations",
                "- Columns should include: Topic/Category, Evidence quote, Source citation",
                "- Use proper quotation marks for quotes",
                "- Keep quotes concise but meaningful",
                "- Include venue and year in source column",
            ]
        elif table_type == SurveyTableType.TREND_ANALYSIS_TABLE:
            requirements = [
                "- Show trends using arrow symbols: $\\uparrow$ (increasing), $\\downarrow$ (decreasing), $\\rightarrow$ (stable)",
                "- Columns should include: Topic, Trend indicators, Agreement/Match, Correlation metrics",
                "- Use $\\checkmark$/$\\times$ for agreement indicators",
                "- Include statistical significance markers (*) where applicable",
            ]
        elif table_type == SurveyTableType.FORMULA_COMPARISON_TABLE:
            requirements = [
                "- Present mathematical formulas in proper LaTeX math mode",
                "- Columns should include: Type/Category, Model name, Formula/Equation, Objective",
                "- Use consistent notation across all formulas",
                "- Group by model type or approach",
                "- Use \\multirow for grouping related models",
            ]
        elif table_type == SurveyTableType.APPLICATION_OVERVIEW_TABLE:
            requirements = [
                "- List applications/methods by category",
                "- Columns should include: Domain/Modality, Category/Task, List of approaches with citations",
                "- Use \\multirow for domain grouping",
                "- Use \\cmidrule for visual separation between categories",
                "- Include multiple citations per row where applicable",
            ]
        elif table_type == SurveyTableType.CONTRIBUTION_SUMMARY_TABLE:
            requirements = [
                f"- Include approximately {min(num_citations, 10)} key contributions",
                "- Columns should include: Work/Paper, Main Contribution, Innovation Type (tags), Impact Level",
                "- **CRITICAL for Work/Paper column**: ALWAYS use a descriptive name (method name, system name, or author name) followed by citation. Format: 'MethodName \\cite{bibkey}' or 'AuthorName et al. \\cite{bibkey}'. NEVER use just citation numbers like '[1]' alone.",
                "- Use colored tags (\\colorbox) for innovation types: Architecture, Training, Efficiency, Safety, etc.",
                "- Use star symbols (\\ding{72}) for impact levels: \\ding{72}\\ding{72}\\ding{72} (High), \\ding{72}\\ding{72} (Medium), \\ding{72} (Low)",
                "- Group contributions by research theme (e.g., Foundational Methods, Efficiency Improvements, Applications)",
                "- Use \\rowcolor{categorygreen} for category headers",
                "- Keep contribution descriptions concise but impactful (1-2 sentences)",
                "- Tag colors: \\colorbox{blue!15}{Architecture}, \\colorbox{green!15}{Scale}, \\colorbox{orange!15}{Open-Source}, \\colorbox{purple!15}{Safety}, \\colorbox{red!15}{Training}, \\colorbox{cyan!15}{Efficiency}, \\colorbox{yellow!15}{Memory}",
            ]
        elif table_type == SurveyTableType.RESEARCH_LANDSCAPE_TABLE:
            requirements = [
                "- Present multi-dimensional research landscape analysis",
                "- Columns should include: Dimension, Sub-area, Representative Works, Maturity, Papers count, Trend",
                "- Use maturity indicators: \\ding{108} (Mature/filled circle), \\ding{119} (Developing/half-filled), \\ding{109} (Emerging/empty circle)",
                "- Use trend arrows: $\\uparrow\\uparrow$ (Rapidly Growing), $\\uparrow$ (Growing), $\\rightarrow$ (Stable), $\\downarrow$ (Declining)",
                "- Use alternating row colors for different dimensions: \\rowcolor{blue!8}, \\rowcolor{green!8}, \\rowcolor{orange!8}, \\rowcolor{purple!8}",
                "- Group by major research dimensions (e.g., Architecture, Training, Inference, Evaluation)",
                "- Include approximate paper counts (e.g., 450+, 120+)",
                "- **CRITICAL**: Do NOT use \\multirow with \\rowcolor - it causes text to disappear! Instead, put the dimension name only in the FIRST row of each group, and leave the Dimension column EMPTY for subsequent rows in the same group",
                "- Use p{2.5cm} for Dimension column and p{3.5cm} for Sub-area column to ensure proper text wrapping",
                "- Include 3-4 representative works per sub-area with citations",
            ]
        else:  # FEATURE_MATRIX or unknown
            requirements = [
                f"- Include approximately {min(num_citations, 12)} items",
                "- Create a feature matrix with items as rows and features as columns",
                "- Use $\\checkmark$/$\\times$ symbols for feature support levels",
                "- Include legend explaining symbols in caption",
            ]
        
        return "\n".join(requirements)
    
    def _get_style_for_table_type(self, table_type: SurveyTableType) -> str:
        """Get the appropriate style string for a table type."""
        style_map = {
            SurveyTableType.BENCHMARK_COMPARISON: "vertical_comparison",
            SurveyTableType.METHOD_COMPARISON: "categorized_summary",
            SurveyTableType.TOOL_COMPARISON: "feature_checklist",
            SurveyTableType.TAXONOMY_TABLE: "hierarchical_summary",
            SurveyTableType.CHRONOLOGICAL_SUMMARY: "chronological_summary",
            SurveyTableType.FEATURE_MATRIX: "matrix_comparison",
        }
        return style_map.get(table_type, "vertical_comparison")
    
    def _extract_latex_from_response(self, response: str) -> Optional[str]:
        """
        Extract LaTeX code from LLM response.
        
        Args:
            response: The LLM response containing LaTeX code
            
        Returns:
            The extracted LaTeX code or None if not found
        """
        # Try to find latex code block
        latex_pattern = r"```latex\s*(.*?)\s*```"
        match = re.search(latex_pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Try to find table environment directly
        table_pattern = r"(\\begin\{table\}.*?\\end\{table\})"
        match = re.search(table_pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Try longtable
        longtable_pattern = r"(\\begin\{longtable\}.*?\\end\{longtable\})"
        match = re.search(longtable_pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        return None
    
    def _post_process_latex(self, latex_code: str) -> str:
        """
        Post-process the generated LaTeX code to ensure compatibility.
        
        This method removes document structure elements that should not be present
        when the table is included via \input{} in the main document.
        
        Args:
            latex_code: The raw LaTeX code
            
        Returns:
            Processed LaTeX code (table environment only, no document structure)
        """
        # Remove document class declaration
        latex_code = re.sub(r"\\documentclass(\[.*?\])?\{.*?\}\s*", "", latex_code)
        
        # Remove all \usepackage commands
        latex_code = re.sub(r"\\usepackage(\[.*?\])?\{.*?\}\s*", "", latex_code)
        
        # Remove color definitions (these are already in the main document)
        latex_code = re.sub(r"\\definecolor\{.*?\}\{.*?\}\{.*?\}\s*", "", latex_code)
        
        # Remove newcommand definitions for cmark/xmark (these are already in the main document)
        latex_code = re.sub(r"\\newcommand\{\\cmark\}.*?\n", "", latex_code)
        latex_code = re.sub(r"\\newcommand\{\\xmark\}.*?\n", "", latex_code)
        latex_code = re.sub(r"\\renewcommand\{\\cmark\}.*?\n", "", latex_code)
        latex_code = re.sub(r"\\renewcommand\{\\xmark\}.*?\n", "", latex_code)
        
        # Remove \begin{document} and \end{document}
        latex_code = re.sub(r"\\begin\{document\}\s*", "", latex_code)
        latex_code = re.sub(r"\\end\{document\}\s*", "", latex_code)
        
        # Remove any "% Requires:" comments that reference packages/commands
        latex_code = re.sub(r"%\s*Requires:.*?\n", "", latex_code)
        
        # Remove % Color Definitions and % Symbol Definitions comment headers
        latex_code = re.sub(r"%\s*Color Definitions\s*\n", "", latex_code)
        latex_code = re.sub(r"%\s*Symbol Definitions\s*\n", "", latex_code)
        
        # Ensure proper table placement
        latex_code = re.sub(r"\\begin\{table\}\[.*?\]", r"\\begin{table}[H]", latex_code)
        
        # Fix unescaped ampersands in text content (not column separators)
        # This handles cases like "Reasoning & Optimization" -> "Reasoning \& Optimization"
        latex_code = self._fix_unescaped_ampersands(latex_code)
        latex_code = self._fix_malformed_multicolumn_headers(latex_code)
        latex_code = self._wrap_wide_tabular_in_resizebox(latex_code)
        
        # Clean up excessive blank lines (more than 2 consecutive)
        latex_code = re.sub(r"\n{3,}", "\n\n", latex_code)
        
        # Strip leading/trailing whitespace
        latex_code = latex_code.strip()
        
        return latex_code

    def _fix_malformed_multicolumn_headers(self, latex_code: str) -> str:
        """Close common LLM-generated category header rows with a missing brace.

        Some generated tables contain rows such as:
        ``\rowcolor{...} \multicolumn{4}{l}{\textbf{Title} \\``
        where the closing brace for ``\multicolumn`` is missing before the row
        terminator.  That causes a runaway argument and makes all following
        floats fail.  Correct rows already ending in ``}} \\`` are left intact.
        """
        return re.sub(
            r"(\\rowcolor\{[^}]*\}\s*\\multicolumn\{[^}]*\}\{[^}]*\}\{\\textbf\{[^{}\n]*\})\s*\\\\",
            lambda match: match.group(1) + r"} \\",
            latex_code,
        )

    def _wrap_wide_tabular_in_resizebox(self, latex_code: str) -> str:
        """Wrap wide tabular environments to prevent page-edge clipping."""
        if "\\resizebox{" in latex_code:
            return latex_code

        match = re.search(r"\\begin\{tabular\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", latex_code)
        if not match:
            return latex_code

        column_spec = match.group(1)
        if self._estimate_table_columns(column_spec) < 6:
            return latex_code

        begin = match.group(0)
        start = match.start()
        end_marker = "\\end{tabular}"
        end = latex_code.find(end_marker, match.end())
        if end == -1:
            return latex_code

        before = latex_code[:start]
        tabular_block = latex_code[start:end + len(end_marker)]
        after = latex_code[end + len(end_marker):]
        return before + "\\resizebox{\\textwidth}{!}{%\n" + tabular_block + "%\n}" + after

    def _estimate_table_columns(self, column_spec: str) -> int:
        """Best-effort column count for tabular specs including p/m/b columns."""
        spec = re.sub(r"@\{[^{}]*\}", "", column_spec)
        spec = re.sub(r"[><]\{[^{}]*\}", "", spec)
        count = 0
        i = 0
        while i < len(spec):
            ch = spec[i]
            if ch in "lcrX":
                count += 1
                i += 1
            elif ch in "pmb" and i + 1 < len(spec) and spec[i + 1] == "{":
                count += 1
                depth = 0
                i += 1
                while i < len(spec):
                    if spec[i] == "{":
                        depth += 1
                    elif spec[i] == "}":
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                    i += 1
            else:
                i += 1
        return count
    
    def _fix_unescaped_ampersands(self, latex_code: str) -> str:
        """
        Fix unescaped ampersands in LaTeX table content.
        
        In LaTeX tables, & is used as a column separator. However, if & appears
        inside text content (like "Reasoning & Optimization"), it needs to be
        escaped as \&.
        
        This method detects and fixes such cases by looking for & characters
        that appear inside LaTeX commands like \textbf{}, \textit{}, \multicolumn{}, etc.
        
        Args:
            latex_code: The LaTeX code to process
            
        Returns:
            LaTeX code with properly escaped ampersands
        """
        # Pattern to find text inside common LaTeX commands that might contain unescaped &
        # We look for patterns like \textbf{...&...} where & is not escaped
        patterns = [
            # \textbf{...} - bold text
            (r'(\\textbf\{)([^}]*[^\\])(&)([^}]*\})', r'\1\2\\&\4'),
            # \textit{...} - italic text
            (r'(\\textit\{)([^}]*[^\\])(&)([^}]*\})', r'\1\2\\&\4'),
            # \texttt{...} - monospace text
            (r'(\\texttt\{)([^}]*[^\\])(&)([^}]*\})', r'\1\2\\&\4'),
            # \emph{...} - emphasized text
            (r'(\\emph\{)([^}]*[^\\])(&)([^}]*\})', r'\1\2\\&\4'),
            # \multicolumn{n}{spec}{...} - multicolumn content
            (r'(\\multicolumn\{[^}]*\}\{[^}]*\}\{)([^}]*[^\\])(&)([^}]*\})', r'\1\2\\&\4'),
            # \rowcolor{...} followed by text with &
            # This is trickier - we need to handle the case where & appears after \rowcolor
            # but before the actual column separator
        ]
        
        result = latex_code
        for pattern, replacement in patterns:
            # Apply the pattern multiple times to handle multiple & in the same command
            prev_result = ""
            while prev_result != result:
                prev_result = result
                result = re.sub(pattern, replacement, result)
        
        # Special handling for category header rows with \rowcolor
        # Pattern: \rowcolor{...} \multicolumn{n}{l}{\textbf{Text & More Text}}
        # The & inside \textbf{} needs to be escaped
        result = re.sub(
            r'(\\rowcolor\{[^}]*\}\s*\\multicolumn\{[^}]*\}\{[^}]*\}\{\\textbf\{)([^}]*[^\\])(&)([^}]*\}\})',
            r'\1\2\\&\4',
            result
        )
        
        return result
    
    def _validate_and_fix_citations(self, latex_code: str, available_citations: List[str]) -> str:
        """
        Validate citations in the generated LaTeX code and remove/fix invalid ones.
        
        This method checks all \cite{} commands in the generated table and:
        1. Removes citations that are not in the available list
        2. Logs warnings about invalid citations
        3. Optionally removes entire rows if they have no valid citations
        
        Args:
            latex_code: The generated LaTeX code
            available_citations: List of valid bib keys
            
        Returns:
            LaTeX code with invalid citations removed or fixed
        """
        if not available_citations:
            return latex_code
        
        # Convert to set for faster lookup
        valid_citations = set(available_citations)
        
        # Find all citations in the latex code
        cite_pattern = r'\\cite\{([^}]+)\}'
        citations_found = re.findall(cite_pattern, latex_code)
        
        invalid_citations = []
        for cite in citations_found:
            # Handle multiple citations in one \cite{} command (e.g., \cite{ref1,ref2})
            individual_cites = [c.strip() for c in cite.split(',')]
            for individual_cite in individual_cites:
                if individual_cite and individual_cite not in valid_citations:
                    invalid_citations.append(individual_cite)
        
        if invalid_citations:
            logger.warning(f"Found {len(invalid_citations)} invalid citations in generated table: {invalid_citations[:10]}...")
            
            # Strategy 1: Remove invalid citations from \cite{} commands
            def fix_cite_command(match):
                cite_content = match.group(1)
                individual_cites = [c.strip() for c in cite_content.split(',')]
                valid_cites = [c for c in individual_cites if c in valid_citations]
                
                if valid_cites:
                    return f"\\cite{{{','.join(valid_cites)}}}"
                else:
                    # No valid citations - return empty string to remove the citation
                    return ""
            
            latex_code = re.sub(cite_pattern, fix_cite_command, latex_code)
            
            # Clean up any double spaces or trailing spaces before \\
            latex_code = re.sub(r'\s+\\\\', r' \\\\', latex_code)
            latex_code = re.sub(r'\s{2,}', ' ', latex_code)
            
            logger.info(f"Removed/fixed {len(invalid_citations)} invalid citations from table")
        
        return latex_code
    
    def _extract_available_citations(self, section_content: str) -> str:
        """
        Extract available citations from section content and format them for the prompt.
        
        Args:
            section_content: The content of the section
            
        Returns:
            A formatted string listing all available bib keys
        """
        citations = self.extract_cite_name(section_content)
        if not citations:
            return "No citations found in the reference content. Generate a table without citations or use general descriptions."
        
        # Format as a clear list
        citation_list = "\n".join([f"- {cite}" for cite in citations])
        return f"""The following {len(citations)} bib keys are available for use in this table:

{citation_list}

**IMPORTANT**: You MUST use these EXACT bib keys in your \\cite{{}} commands. Do NOT modify them or use alternative formats."""
    
    def generate_survey_table(
        self,
        section_name: str,
        table_type: Optional[SurveyTableType] = None,
        custom_description: str = "",
    ) -> Optional[str]:
        """
        Generate a professional survey table for a specific section.
        
        Args:
            section_name: Name of the section or subsection to generate table for
            table_type: Optional specific table type (auto-detected if not provided)
            custom_description: Optional custom description for the table
            
        Returns:
            The generated LaTeX code or None if generation failed
        """
        # Check if we've reached the limit
        if self.generated_tables >= self.MAX_SURVEY_TABLES:
            logger.info(f"Reached max survey tables limit ({self.MAX_SURVEY_TABLES})")
            return None
        
        # Try to extract section content first, then subsection if section fails
        section_content = self.extract_section_content(self.main_body_path, section_name)
        if section_content is None:
            # Try extracting as subsection
            section_content = self.extract_subsection_content(self.main_body_path, section_name)
        
        if section_content is None:
            # Try to find the parent section from outline and extract that
            section_content = self._extract_content_with_fallback(section_name)
        
        if section_content is None:
            logger.warning(f"Could not extract content for section/subsection: {section_name}")
            return None
        
        # Determine table type if not specified
        if table_type is None:
            table_type = self._determine_table_type(section_content)
        
        logger.info(f"Generating {table_type.value} table for section: {section_name}")
        
        # Get topic
        topic = self._extract_topic_from_outline()
        
        # Build description
        description = custom_description or f"A comprehensive {table_type.value.replace('_', ' ')} table for the section on {section_name}"
        
        # Build data requirements
        data_requirements = self._build_data_requirements(section_content, table_type)
        
        # Extract available citations for the prompt
        available_citations = self._extract_available_citations(section_content)
        
        # Get style
        style = self._get_style_for_table_type(table_type)
        
        # Load and format prompt
        prompt = load_prompt(
            str(self.survey_table_prompt_path),
            topic=topic,
            description=description,
            table_type=table_type.value,
            data_requirements=data_requirements,
            available_citations=available_citations,
            section_content=section_content[:8000],  # Limit content length
        )
        
        # Extract citations list for validation
        citations_list = self.extract_cite_name(section_content)
        
        # Generate table using a cost-capped no-retry LLM call
        response = self._optional_remote_chat(
            prompt,
            purpose=f"{table_type.value} table generation",
            timeout=180,
        )
        
        if response is None:
            logger.warning("Skipping table because optional LLM generation failed")
            return None
        
        # Extract LaTeX code
        latex_code = self._extract_latex_from_response(response)
        if latex_code is None:
            logger.error("Could not extract LaTeX code from response")
            return None
        
        # Post-process
        latex_code = self._post_process_latex(latex_code)
        
        # Validate and fix citations - remove any citations not in the available list
        latex_code = self._validate_and_fix_citations(latex_code, citations_list)
        
        # Increment counter
        self.generated_tables += 1
        
        return latex_code
    
    def find_best_section_for_table(self) -> Optional[str]:
        """
        Find the best section in the survey for generating a table.
        
        Returns:
            The name of the best section or None if not found
        """
        outlines = load_single_file(self.outline_path)
        section_titles, subsection_titles = self.parse_outline(outlines)
        
        # Priority keywords for table generation
        priority_keywords = [
            ("benchmark", "dataset", "evaluation"),
            ("method", "approach", "technique"),
            ("tool", "system", "framework"),
            ("comparison", "analysis", "overview"),
        ]
        
        for keywords in priority_keywords:
            for section_title in section_titles:
                if any(kw in section_title.lower() for kw in keywords):
                    return section_title
        
        # If no priority match, return the first non-intro/conclusion section
        for section_title in section_titles:
            if not any(skip in section_title.lower() for skip in ["introduction", "conclusion", "related", "future"]):
                return section_title
        
        return section_titles[1] if len(section_titles) > 1 else None
    
    def insert_table_into_document(
        self,
        latex_code: str,
        section_name: str,
        table_filename: str,
    ) -> bool:
        """
        Insert the generated table into the document.
        
        Args:
            latex_code: The LaTeX code for the table
            section_name: The section to insert the table into
            table_filename: The filename for the table tex file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Save table to file
            table_path = self.latex_path / table_filename
            self.save_table_file(latex_code, table_path)
            logger.info(f"Survey table saved to {table_path}")
            
            # Insert input command into main body
            tex = load_file_as_string(self.main_body_path)
            section_content = self.extract_section_content(self.main_body_path, section_name)
            
            if section_content:
                # Get section title with label
                section_title = self.extract_section_title(section_content)
                if section_title:
                    # Insert after section title
                    input_cmd = f"\n\n\\input{{{table_filename.replace('.tex', '')}}}"
                    tex = tex.replace(section_title, f"{section_title}{input_cmd}")
                    save_result(tex, self.main_body_path)
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error inserting table into document: {e}")
            return False
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def run(self, table_type: Optional[SurveyTableType] = None) -> Optional[str]:
        """
        Main entry point for generating a survey table.
        
        Args:
            table_type: Optional specific table type to generate
            
        Returns:
            The generated LaTeX code or None if generation failed
        """
        # Find best section
        section_name = self.find_best_section_for_table()
        if section_name is None:
            logger.warning("Could not find suitable section for table generation")
            return None
        
        # Generate table
        latex_code = self.generate_survey_table(section_name, table_type)
        if latex_code is None:
            return None
        
        # Insert into document
        table_filename = f"survey_table_{self.generated_tables}.tex"
        success = self.insert_table_into_document(latex_code, section_name, table_filename)
        
        if success:
            logger.info(f"Successfully generated and inserted survey table ({self.generated_tables}/{self.MAX_SURVEY_TABLES})")
            return latex_code
        else:
            logger.warning("Table generated but could not be inserted into document")
            return latex_code
    
    def _get_content_summary(self) -> str:
        """Get a summary of the survey content for the router."""
        try:
            content = load_file_as_string(self.main_body_path)
            # Truncate to reasonable length for LLM
            if len(content) > 15000:
                content = content[:15000] + "\n... [content truncated]"
            return content
        except Exception as e:
            logger.warning(f"Could not load content summary: {e}")
            return ""
    
    def _get_outline_summary(self) -> str:
        """Get the outline as a formatted string."""
        try:
            outlines = load_single_file(self.outline_path)
            if isinstance(outlines, dict):
                return json.dumps(outlines, indent=2, ensure_ascii=False)
            return str(outlines)
        except Exception as e:
            logger.warning(f"Could not load outline: {e}")
            return ""
    
    def route_table_types(self) -> List[Dict[str, Any]]:
        """
        Use LLM to intelligently select which table types to generate.
        
        Returns:
            List of recommended table configurations
        """
        logger.info("Running table type router to select appropriate table types...")
        
        # Get survey information
        topic = self._extract_topic_from_outline()
        outline = self._get_outline_summary()
        content_summary = self._get_content_summary()
        
        # Load router prompt
        try:
            prompt = load_prompt(
                str(self.table_router_prompt_path),
                topic=topic,
                outline=outline,
                content_summary=content_summary,
            )
        except Exception as e:
            logger.warning(f"Could not load router prompt: {e}, using default selection")
            return self._get_default_table_recommendations()
        
        # Call LLM for routing decision with no retry stacking; fallback is enough
        # for this optional table-selection stage.
        response = self._optional_remote_chat(
            prompt,
            purpose="table routing",
            timeout=180,
        )
        
        if response is None:
            logger.warning("Router LLM failed, using default selection")
            return self._get_default_table_recommendations()
        
        # Parse JSON response
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*"recommended_tables"[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                recommendations = result.get("recommended_tables", [])
                if recommendations:
                    logger.info(f"Router recommended {len(recommendations)} table types")
                    return recommendations
        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse router response as JSON: {e}")
        
        return self._get_default_table_recommendations()
    
    def _get_default_table_recommendations(self) -> List[Dict[str, Any]]:
        """Get default table recommendations when router fails."""
        outlines = load_single_file(self.outline_path)
        section_titles, _ = self.parse_outline(outlines)
        
        # Filter sections
        suitable_sections = [
            title for title in section_titles
            if not any(skip in title.lower() for skip in ["introduction", "conclusion", "abstract", "future"])
        ]
        
        recommendations = []
        
        # Default: generate benchmark and method comparison tables
        if len(suitable_sections) >= 1:
            recommendations.append({
                "table_type": "benchmark_comparison",
                "target_section": suitable_sections[0],
                "description": "Comparison of evaluation benchmarks and datasets",
                "priority": 1,
            })
        
        if len(suitable_sections) >= 2:
            recommendations.append({
                "table_type": "method_comparison",
                "target_section": suitable_sections[1] if len(suitable_sections) > 1 else suitable_sections[0],
                "description": "Comparison of representative methods and approaches",
                "priority": 2,
            })
        
        if len(suitable_sections) >= 3:
            recommendations.append({
                "table_type": "performance_comparison_table",
                "target_section": suitable_sections[2] if len(suitable_sections) > 2 else suitable_sections[0],
                "description": "Performance comparison across different models",
                "priority": 3,
            })
        
        return recommendations
    
    def _string_to_table_type(self, type_string: str) -> Optional[SurveyTableType]:
        """Convert a string to SurveyTableType enum."""
        type_map = {
            "benchmark_comparison": SurveyTableType.BENCHMARK_COMPARISON,
            "method_comparison": SurveyTableType.METHOD_COMPARISON,
            "tool_comparison": SurveyTableType.TOOL_COMPARISON,
            "taxonomy_table": SurveyTableType.TAXONOMY_TABLE,
            "chronological_summary": SurveyTableType.CHRONOLOGICAL_SUMMARY,
            "feature_matrix": SurveyTableType.FEATURE_MATRIX,
            "statistics_table": SurveyTableType.STATISTICS_TABLE,
            "annotation_scheme_table": SurveyTableType.ANNOTATION_SCHEME_TABLE,
            "distribution_matrix_table": SurveyTableType.DISTRIBUTION_MATRIX_TABLE,
            "performance_comparison_table": SurveyTableType.PERFORMANCE_COMPARISON_TABLE,
            "evidence_table": SurveyTableType.EVIDENCE_TABLE,
            "trend_analysis_table": SurveyTableType.TREND_ANALYSIS_TABLE,
            "formula_comparison_table": SurveyTableType.FORMULA_COMPARISON_TABLE,
            "application_overview_table": SurveyTableType.APPLICATION_OVERVIEW_TABLE,
            # New visually appealing table types
            "contribution_summary_table": SurveyTableType.CONTRIBUTION_SUMMARY_TABLE,
            "research_landscape_table": SurveyTableType.RESEARCH_LANDSCAPE_TABLE,
        }
        return type_map.get(type_string.lower())
    
    def _get_category_for_type(self, table_type_str: str) -> Optional[str]:
        """Get the category for a table type."""
        for category, types in self.table_type_categories.items():
            if table_type_str in types:
                return category
        return None
    
    def _normalize_section_name(self, section_name: str) -> str:
        """Normalize section name for comparison (case-insensitive, strip whitespace)."""
        return section_name.lower().strip()
    
    def _clean_section_name(self, section_name: str) -> str:
        """
        Clean section name by removing common prefixes like 'Section X:'.
        
        Router often returns section names in format like:
        - "Section 4: How DocVQA? Technical Workflow and Paradigms"
        - "Section 2: Background and Problem Formulation"
        
        But the actual LaTeX file has:
        - "How DocVQA? Technical Workflow and Paradigms"
        - "Background and Problem Formulation"
        
        This method removes such prefixes to match the actual section titles.
        
        Args:
            section_name: The section name potentially with prefix
            
        Returns:
            Cleaned section name without prefix
        """
        import re
        
        # Pattern to match "Section X:" or "Section X." prefix (case-insensitive)
        # Also handles variations like "Sec. X:", "Sec X:", etc.
        patterns = [
            r'^Section\s+\d+[\.:]\s*',  # "Section 4: " or "Section 4. "
            r'^Sec\.?\s+\d+[\.:]\s*',   # "Sec. 4: " or "Sec 4: "
            r'^\d+[\.:]\s*',             # "4: " or "4. "
            r'^\d+\.\d+[\.:]\s*',        # "4.1: " or "4.1. "
        ]
        
        cleaned = section_name.strip()
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()
    
    def _validate_and_enhance_recommendations(
        self,
        recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Validate and enhance table recommendations to ensure diversity.
        
        Rules:
        1. No duplicate table types
        2. No duplicate sections (each section gets at most one table)
        3. Prefer tables from different categories
        
        Args:
            recommendations: Original recommendations from router
            
        Returns:
            Validated and potentially enhanced recommendations
        """
        validated = []
        used_types = set()
        used_sections = set()
        used_categories = set()
        
        # First pass: filter out duplicates
        for rec in recommendations:
            table_type = rec.get("table_type", "")
            target_section = rec.get("target_section", "")
            normalized_section = self._normalize_section_name(target_section)
            category = self._get_category_for_type(table_type)
            
            # Skip if type already used
            if table_type in used_types:
                logger.info(f"Skipping duplicate table type: {table_type}")
                continue
            
            # Skip if section already has a table
            if normalized_section in used_sections:
                logger.info(f"Skipping table for section '{target_section}' - section already has a table")
                continue
            
            # Warn if category already used (but don't skip)
            if category and category in used_categories:
                logger.warning(f"Table type '{table_type}' is from category '{category}' which already has a table")
            
            validated.append(rec)
            used_types.add(table_type)
            used_sections.add(normalized_section)
            if category:
                used_categories.add(category)
        
        # If we don't have enough tables, try to add more from different categories
        if len(validated) < self.MIN_SURVEY_TABLES:
            logger.info(f"Only {len(validated)} tables validated, trying to add more for diversity")
            
            # Get available sections
            outlines = load_single_file(self.outline_path)
            section_titles, _ = self.parse_outline(outlines)
            available_sections = [
                s for s in section_titles
                if self._normalize_section_name(s) not in used_sections
                and not any(skip in s.lower() for skip in ["introduction", "conclusion", "abstract", "future", "related"])
            ]
            
            # Try to add tables from unused categories
            for category, types in self.table_type_categories.items():
                if category in used_categories:
                    continue
                if len(validated) >= self.MAX_SURVEY_TABLES:
                    break
                if not available_sections:
                    break
                
                # Pick the first available type from this category
                for table_type in types:
                    if table_type not in used_types:
                        target_section = available_sections.pop(0)
                        validated.append({
                            "table_type": table_type,
                            "target_section": target_section,
                            "description": f"Auto-added {table_type.replace('_', ' ')} for diversity",
                            "priority": len(validated) + 1,
                        })
                        used_types.add(table_type)
                        used_sections.add(self._normalize_section_name(target_section))
                        used_categories.add(category)
                        logger.info(f"Auto-added {table_type} table for section '{target_section}' (category: {category})")
                        break
        
        return validated
    
    def run_all(self) -> List[str]:
        """
        Generate multiple survey tables for different sections.
        Uses router to intelligently select table types.
        
        Returns:
            List of generated LaTeX codes
        """
        results = []
        
        # Reset tracking
        self.generated_table_types = []
        self.used_sections = []
        self.used_categories = []
        
        # Use router to get table recommendations
        recommendations = self.route_table_types()
        
        # Sort by priority
        recommendations.sort(key=lambda x: x.get("priority", 99))
        
        # Validate and enhance recommendations for diversity
        recommendations = self._validate_and_enhance_recommendations(recommendations)
        
        # Limit to MAX_SURVEY_TABLES
        recommendations = recommendations[:self.MAX_SURVEY_TABLES]
        
        logger.info(f"Will generate {len(recommendations)} tables based on validated recommendations")
        
        for rec in recommendations:
            table_type_str = rec.get("table_type", "")
            target_section = rec.get("target_section", "")
            description = rec.get("description", "")
            
            # Skip if we've already generated this type
            if table_type_str in self.generated_table_types:
                logger.info(f"Skipping duplicate table type: {table_type_str}")
                continue
            
            # Skip if section already has a table
            normalized_section = self._normalize_section_name(target_section)
            if normalized_section in self.used_sections:
                logger.info(f"Skipping table for section '{target_section}' - already has a table")
                continue
            
            # Convert string to enum
            table_type = self._string_to_table_type(table_type_str)
            if table_type is None:
                logger.warning(f"Unknown table type: {table_type_str}, skipping")
                continue
            
            # Find the target section if not specified
            if not target_section:
                # Find a section that doesn't have a table yet
                outlines = load_single_file(self.outline_path)
                section_titles, _ = self.parse_outline(outlines)
                for section in section_titles:
                    if self._normalize_section_name(section) not in self.used_sections:
                        if not any(skip in section.lower() for skip in ["introduction", "conclusion", "abstract"]):
                            target_section = section
                            break
            
            if not target_section:
                logger.warning("Could not find target section, skipping")
                continue
            
            # Clean the section name to remove prefixes like "Section X:"
            # Router often returns names like "Section 4: How DocVQA?" but LaTeX has "How DocVQA?"
            original_target_section = target_section
            target_section = self._clean_section_name(target_section)
            if target_section != original_target_section:
                logger.info(f"Cleaned section name: '{original_target_section}' -> '{target_section}'")
            
            # Generate table
            logger.info(f"Generating {table_type.value} table for section: {target_section}")
            latex_code = self.generate_survey_table(
                section_name=target_section,
                table_type=table_type,
                custom_description=description,
            )
            
            if latex_code:
                # Track generated type and section
                self.generated_table_types.append(table_type_str)
                self.used_sections.append(self._normalize_section_name(target_section))
                
                # Track category
                category = self._get_category_for_type(table_type_str)
                if category:
                    self.used_categories.append(category)
                
                # Save and insert
                table_filename = f"survey_table_{self.generated_tables}.tex"
                self.insert_table_into_document(latex_code, target_section, table_filename)
                results.append(latex_code)
                
                # Store table info for downstream use
                self.generated_table_info.append({
                    "caption": description or f"{table_type.value.replace('_', ' ')} table",
                    "description": description,
                    "section": target_section,
                    "table_type": table_type_str,
                    "topics": self._extract_topics_from_table_type(table_type_str, target_section)
                })
                
                logger.info(f"Successfully generated {table_type.value} table ({len(results)}/{self.MAX_SURVEY_TABLES})")
        
        logger.info(f"Generated {len(results)} survey tables in total")
        logger.info(f"Table types: {self.generated_table_types}")
        logger.info(f"Sections used: {self.used_sections}")
        logger.info(f"Categories used: {self.used_categories}")
        return results
    
    def _extract_topics_from_table_type(self, table_type: str, section_name: str) -> List[str]:
        """
        Extract topic keywords from table type and section name.
        
        Args:
            table_type: The type of table generated
            section_name: The section name where the table is placed
            
        Returns:
            List of topic keywords
        """
        topics = []
        
        # Add topics based on table type
        type_topics = {
            "benchmark_comparison": ["benchmark", "dataset", "evaluation", "comparison"],
            "method_comparison": ["method", "approach", "technique", "comparison"],
            "tool_comparison": ["tool", "system", "framework", "comparison"],
            "taxonomy_table": ["taxonomy", "classification", "category", "hierarchy"],
            "chronological_summary": ["timeline", "history", "evolution", "chronological"],
            "feature_matrix": ["feature", "matrix", "comparison"],
            "statistics_table": ["statistics", "data", "numbers"],
            "annotation_scheme_table": ["annotation", "scheme", "labeling"],
            "distribution_matrix_table": ["distribution", "matrix", "cross-tabulation"],
            "performance_comparison_table": ["performance", "benchmark", "metrics", "comparison"],
            "evidence_table": ["evidence", "citation", "quote"],
            "trend_analysis_table": ["trend", "analysis", "growth"],
            "formula_comparison_table": ["formula", "equation", "mathematical"],
            "application_overview_table": ["application", "overview", "domain"],
            "contribution_summary_table": ["contribution", "summary", "innovation"],
            "research_landscape_table": ["landscape", "research", "overview"],
        }
        
        if table_type in type_topics:
            topics.extend(type_topics[table_type])
        
        # Add topics from section name
        section_lower = section_name.lower()
        section_keywords = [
            "training", "inference", "evaluation", "benchmark", "method",
            "architecture", "model", "data", "application", "tool",
            "framework", "pipeline", "workflow", "taxonomy", "classification"
        ]
        for kw in section_keywords:
            if kw in section_lower and kw not in topics:
                topics.append(kw)
        
        return topics
    
    def get_generated_table_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all generated tables.
        
        This method is used by downstream components (like DynamicVisualGenerator
        and AIImageGenerator) to avoid generating duplicate visual elements.
        
        Returns:
            List of dictionaries containing table information:
            - caption: Table caption/title
            - description: Table description
            - section: Target section name
            - table_type: Type of table
            - topics: List of topic keywords
        """
        return self.generated_table_info
    
    def run_with_router(self) -> List[str]:
        """
        Main entry point that uses the router mechanism.
        Alias for run_all() with router.
        
        Returns:
            List of generated LaTeX codes
        """
        return self.run_all()
