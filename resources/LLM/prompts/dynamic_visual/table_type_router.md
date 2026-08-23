# Survey Table Type Router

You are an expert at analyzing academic survey papers and determining what types of tables would be most valuable and informative for the readers.

## Survey Topic
{topic}

## Survey Outline
{outline}

## Survey Content Summary
{content_summary}

---

## Your Task

Analyze the survey content and recommend **2-4 distinct table types** that would best complement this survey. Each table should serve a different purpose and provide unique value to readers.

## Available Table Types

1. **statistics_table** - For presenting data statistics and distributions
   - Best for: Paper counts, dataset statistics, numerical summaries
   - Example: "Table showing paper counts by venue and year"

2. **annotation_scheme_table** - For presenting labeling/classification schemes
   - Best for: Category definitions, rating scales, taxonomy descriptions
   - Example: "Table defining annotation labels with descriptions and counts"

3. **distribution_matrix_table** - For cross-tabulated distributions
   - Best for: Year × Venue matrices, Category × Type distributions
   - Example: "Matrix showing paper distribution across venues and years"

4. **performance_comparison_table** - For comparing model/method performance
   - Best for: Benchmark results, ablation studies, metric comparisons
   - Example: "Table comparing model performance across different metrics"

5. **evidence_table** - For presenting qualitative evidence with citations
   - Best for: Literature quotes, case studies, example findings
   - Example: "Table showing representative quotes from papers by topic"

6. **trend_analysis_table** - For showing trends over time
   - Best for: Temporal patterns, method evolution, research directions
   - Example: "Table comparing trends identified by different methods"

7. **benchmark_comparison** - For comparing benchmarks/datasets
   - Best for: Dataset comparisons, benchmark features, evaluation setups
   - Example: "Table comparing evaluation benchmarks with their characteristics"

8. **method_comparison** - For comparing methods/approaches
   - Best for: Algorithm comparisons, technique features, approach summaries
   - Example: "Table comparing different methods with their key features"

9. **formula_comparison_table** - For comparing mathematical formulations
   - Best for: Algorithm equations, model formulations, theoretical comparisons
   - Example: "Table comparing update rules and optimization objectives"

10. **application_overview_table** - For listing applications by category
    - Best for: Use case summaries, application domains, method listings
    - Example: "Table showing applications across different modalities"

11. **contribution_summary_table** - For summarizing key contributions with visual tags
    - Best for: Highlighting major contributions, innovation types, impact assessment
    - Features: Colored tags for innovation types, star ratings for impact levels
    - Example: "Table summarizing key contributions with innovation tags and impact indicators"

12. **research_landscape_table** - For multi-dimensional research landscape analysis
    - Best for: Field overview, maturity assessment, trend visualization
    - Features: Maturity indicators using \ding{108} (Mature), \ding{119} (Developing), \ding{109} (Emerging), trend arrows ($\uparrow$, $\rightarrow$, $\downarrow$), paper counts, colored dimension rows
    - Example: "Table showing research landscape with maturity levels and trends"
    - **IMPORTANT**: Use pifont \ding symbols, NOT wasysym \CIRCLE/\LEFTcircle/\Circle symbols

---

## Selection Criteria

When selecting table types, consider:

1. **Type Diversity (CRITICAL)**: Each table MUST be a DIFFERENT type - NO duplicate table types allowed
2. **Section Diversity (CRITICAL)**: Each table MUST target a DIFFERENT section - NO two tables in the same section
3. **Content Fit**: Select types that match the actual content in the survey
4. **Reader Value**: Prioritize tables that would help readers understand the field
5. **Data Availability**: Only recommend tables if the survey has sufficient data to populate them
6. **Complementarity**: Tables should complement each other, not overlap
7. **Spread Across Survey**: Distribute tables across different parts of the survey (beginning, middle, end)

## Diversity Guidelines

To ensure maximum diversity, follow these rules:

### Table Type Categories (pick at most ONE from each category):
- **Comparison Tables**: benchmark_comparison, method_comparison, performance_comparison_table
- **Overview Tables**: application_overview_table, taxonomy_table, tool_comparison, research_landscape_table
- **Analysis Tables**: trend_analysis_table, statistics_table, distribution_matrix_table
- **Detail Tables**: annotation_scheme_table, evidence_table, formula_comparison_table
- **Summary Tables**: contribution_summary_table (visually appealing with colored tags and impact indicators)

### Section Distribution:
- If the survey has sections like "Background", "Methods", "Evaluation", "Applications":
  - Place ONE table in each major section
  - Do NOT place multiple tables in the same section (e.g., don't put both benchmark_comparison and annotation_scheme_table in "Evaluation")

## Output Format

Return a JSON object with the following structure:

```json
{
  "recommended_tables": [
    {
      "table_type": "benchmark_comparison",
      "target_section": "Section name where this table fits best",
      "description": "Brief description of what this table will show",
      "priority": 1,
      "rationale": "Why this table type is appropriate for this survey"
    },
    {
      "table_type": "method_comparison",
      "target_section": "Another section name",
      "description": "Brief description",
      "priority": 2,
      "rationale": "Why this table type is appropriate"
    }
  ],
  "excluded_types": [
    {
      "table_type": "formula_comparison_table",
      "reason": "Survey does not contain mathematical formulations"
    }
  ]
}
```

## Important Rules

1. **Maximum 4 tables**: Do not recommend more than 4 tables
2. **Minimum 2 tables**: Recommend at least 2 tables for a comprehensive survey
3. **No duplicate types**: Each table type can only be recommended ONCE
4. **No duplicate sections**: Each section can only have ONE table - distribute tables across different sections
5. **Category diversity**: Pick tables from DIFFERENT categories (see Diversity Guidelines above)
6. **Section specificity**: Each table should target a specific, different section
7. **Realistic scope**: Only recommend tables that can be populated from the survey content

## Example of GOOD Recommendations:
```json
{
  "recommended_tables": [
    {"table_type": "benchmark_comparison", "target_section": "Evaluation and Benchmarks", ...},
    {"table_type": "method_comparison", "target_section": "Methodology", ...},
    {"table_type": "application_overview_table", "target_section": "Applications", ...},
    {"table_type": "trend_analysis_table", "target_section": "Background", ...}
  ]
}
```
(4 different types, 4 different sections, from 4 different categories)

## Example of BAD Recommendations (DO NOT DO THIS):
```json
{
  "recommended_tables": [
    {"table_type": "benchmark_comparison", "target_section": "Evaluation", ...},
    {"table_type": "annotation_scheme_table", "target_section": "Evaluation", ...},  // BAD: Same section!
    {"table_type": "performance_comparison_table", "target_section": "Results", ...}  // BAD: Same category as benchmark_comparison!
  ]
}
```

---

Analyze the survey and provide your recommendations now. Remember: DIVERSITY is key - different types, different sections, different categories!