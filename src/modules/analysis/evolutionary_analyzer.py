"""
演化叙事分析器 - EvolutionaryAnalyzer

分析研究领域的演化历程，生成时间线叙事，突出 MEKG 的独特价值。

核心功能:
1. 时间线分析: 识别领域发展的关键时间节点
2. 里程碑识别: 发现重要的技术突破和范式转变
3. 趋势预测: 基于历史数据预测未来发展方向
4. 演化叙事生成: 生成连贯的领域发展故事

这是 SurveyGraph 的独特功能，利用 MEKG 的时序关系进行深度分析。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime

from src.configs.config import BASE_DIR, ADVANCED_CHATAGENT_MODEL
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent

logger = get_logger("src.modules.analysis.EvolutionaryAnalyzer")


@dataclass
class Milestone:
    """研究里程碑"""
    year: int
    title: str
    description: str
    papers: List[str] = field(default_factory=list)  # 相关论文 ID
    impact: str = "medium"  # high, medium, low
    category: str = "method"  # method, dataset, application, theory
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "title": self.title,
            "description": self.description,
            "papers": self.papers,
            "impact": self.impact,
            "category": self.category
        }


@dataclass
class EvolutionPhase:
    """演化阶段"""
    name: str
    start_year: int
    end_year: int
    description: str
    key_characteristics: List[str] = field(default_factory=list)
    representative_works: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "description": self.description,
            "key_characteristics": self.key_characteristics,
            "representative_works": self.representative_works
        }


@dataclass
class TrendPrediction:
    """趋势预测"""
    trend_name: str
    confidence: float  # 0-1
    description: str
    supporting_evidence: List[str] = field(default_factory=list)
    potential_impact: str = "medium"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trend_name": self.trend_name,
            "confidence": self.confidence,
            "description": self.description,
            "supporting_evidence": self.supporting_evidence,
            "potential_impact": self.potential_impact
        }


@dataclass
class EvolutionaryAnalysis:
    """演化分析结果"""
    topic: str
    timeline: List[Milestone] = field(default_factory=list)
    phases: List[EvolutionPhase] = field(default_factory=list)
    trends: List[TrendPrediction] = field(default_factory=list)
    narrative: str = ""
    statistics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "timeline": [m.to_dict() for m in self.timeline],
            "phases": [p.to_dict() for p in self.phases],
            "trends": [t.to_dict() for t in self.trends],
            "narrative": self.narrative,
            "statistics": self.statistics
        }


class EvolutionaryAnalyzer:
    """
    演化叙事分析器
    
    利用 MEKG 的时序关系分析研究领域的演化历程。
    
    分析维度:
    1. 时间维度: 论文发表时间分布
    2. 引用维度: 引用关系的时序演化
    3. 方法维度: 技术方法的演进
    4. 应用维度: 应用领域的扩展
    """
    
    # 里程碑识别 Prompt
    MILESTONE_PROMPT = """You are an expert in analyzing the evolution of research fields.

Topic: {topic}

Papers (sorted by year):
{papers_info}

Identify the key milestones in the development of this research field.

For each milestone, provide:
1. Year of occurrence
2. Title/name of the milestone
3. Description of its significance
4. Related papers (by index)
5. Impact level (high/medium/low)
6. Category (method/dataset/application/theory)

Output format (JSON):
{{
    "milestones": [
        {{
            "year": 2020,
            "title": "Introduction of GPT-3",
            "description": "Demonstrated emergent capabilities in large language models",
            "paper_indices": [0, 5, 12],
            "impact": "high",
            "category": "method"
        }}
    ]
}}

Identify milestones:"""

    # 演化阶段分析 Prompt
    PHASE_PROMPT = """You are an expert in analyzing research field evolution.

Topic: {topic}

Timeline of milestones:
{milestones_info}

Paper distribution by year:
{year_distribution}

Identify the major phases in the evolution of this research field.

For each phase, provide:
1. Phase name
2. Start and end year
3. Description of the phase
4. Key characteristics
5. Representative works

Output format (JSON):
{{
    "phases": [
        {{
            "name": "Early Exploration Phase",
            "start_year": 2018,
            "end_year": 2020,
            "description": "Initial exploration of the concept...",
            "key_characteristics": ["characteristic1", "characteristic2"],
            "representative_works": ["Paper A", "Paper B"]
        }}
    ]
}}

Identify phases:"""

    # 趋势预测 Prompt
    TREND_PROMPT = """You are an expert in predicting research trends.

Topic: {topic}

Recent developments (last 2 years):
{recent_papers}

Evolution phases:
{phases_info}

Based on the historical evolution and recent developments, predict future trends.

For each trend, provide:
1. Trend name
2. Confidence level (0-1)
3. Description
4. Supporting evidence
5. Potential impact (high/medium/low)

Output format (JSON):
{{
    "trends": [
        {{
            "trend_name": "Multimodal Integration",
            "confidence": 0.85,
            "description": "Integration of multiple modalities...",
            "supporting_evidence": ["Evidence 1", "Evidence 2"],
            "potential_impact": "high"
        }}
    ]
}}

Predict trends:"""

    # 演化叙事生成 Prompt
    NARRATIVE_PROMPT = """You are an expert academic writer creating an evolutionary narrative for a survey paper.

Topic: {topic}

Evolution Phases:
{phases_info}

Key Milestones:
{milestones_info}

Future Trends:
{trends_info}

Write a coherent narrative (2-3 paragraphs) describing the evolution of this research field.

The narrative should:
1. Start with the origins and early developments
2. Describe the major transitions and breakthroughs
3. Highlight the current state of the field
4. Briefly mention future directions

Write in academic style, suitable for a survey paper's introduction or background section.

Narrative:"""

    def __init__(
        self,
        chat_agent: Optional[ChatAgent] = None,
        min_papers_for_analysis: int = 10
    ):
        """
        初始化演化分析器
        
        Args:
            chat_agent: ChatAgent 实例
            min_papers_for_analysis: 进行分析所需的最小论文数
        """
        self.chat_agent = chat_agent or ChatAgent()
        self.min_papers_for_analysis = min_papers_for_analysis
    
    def analyze(
        self,
        topic: str,
        papers: List[Dict[str, Any]],
        relations: Optional[List[Dict[str, Any]]] = None
    ) -> EvolutionaryAnalysis:
        """
        执行演化分析
        
        Args:
            topic: 研究主题
            papers: 论文列表 (需包含 year, title, abstract 等字段)
            relations: 论文关系列表 (可选，来自 MEKG)
            
        Returns:
            EvolutionaryAnalysis 对象
        """
        logger.info(f"开始演化分析: {topic}, 论文数: {len(papers)}")
        
        if len(papers) < self.min_papers_for_analysis:
            logger.warning(f"论文数量不足 ({len(papers)} < {self.min_papers_for_analysis})，返回基础分析")
            return self._create_basic_analysis(topic, papers)
        
        # 按年份排序论文
        sorted_papers = sorted(papers, key=lambda p: p.get("year", 0))
        
        # Step 1: 计算基础统计
        logger.info("Step 1: 计算基础统计...")
        statistics = self._compute_statistics(sorted_papers)
        
        # Step 2: 识别里程碑
        logger.info("Step 2: 识别研究里程碑...")
        milestones = self._identify_milestones(topic, sorted_papers)
        
        # Step 3: 分析演化阶段
        logger.info("Step 3: 分析演化阶段...")
        phases = self._analyze_phases(topic, milestones, statistics)
        
        # Step 4: 预测趋势
        logger.info("Step 4: 预测未来趋势...")
        trends = self._predict_trends(topic, sorted_papers, phases)
        
        # Step 5: 生成演化叙事
        logger.info("Step 5: 生成演化叙事...")
        narrative = self._generate_narrative(topic, phases, milestones, trends)
        
        result = EvolutionaryAnalysis(
            topic=topic,
            timeline=milestones,
            phases=phases,
            trends=trends,
            narrative=narrative,
            statistics=statistics
        )
        
        logger.info(
            f"演化分析完成: {len(milestones)} 个里程碑, "
            f"{len(phases)} 个阶段, {len(trends)} 个趋势"
        )
        
        return result
    
    def _compute_statistics(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算基础统计"""
        year_counts = defaultdict(int)
        category_counts = defaultdict(int)
        
        for paper in papers:
            year = paper.get("year")
            if year:
                year_counts[year] += 1
            
            category = paper.get("category", "unknown")
            category_counts[category] += 1
        
        # 计算年份范围
        years = [p.get("year") for p in papers if p.get("year")]
        min_year = min(years) if years else 0
        max_year = max(years) if years else 0
        
        # 计算增长趋势
        sorted_years = sorted(year_counts.keys())
        growth_rate = 0
        if len(sorted_years) >= 2:
            recent_years = sorted_years[-3:] if len(sorted_years) >= 3 else sorted_years
            early_years = sorted_years[:3] if len(sorted_years) >= 3 else sorted_years
            recent_avg = sum(year_counts[y] for y in recent_years) / len(recent_years)
            early_avg = sum(year_counts[y] for y in early_years) / len(early_years)
            if early_avg > 0:
                growth_rate = (recent_avg - early_avg) / early_avg
        
        return {
            "total_papers": len(papers),
            "year_range": {"min": min_year, "max": max_year},
            "year_distribution": dict(year_counts),
            "category_distribution": dict(category_counts),
            "growth_rate": growth_rate,
            "peak_year": max(year_counts.keys(), key=lambda y: year_counts[y]) if year_counts else None
        }
    
    def _identify_milestones(
        self,
        topic: str,
        papers: List[Dict[str, Any]]
    ) -> List[Milestone]:
        """识别研究里程碑"""
        # 准备论文信息
        papers_info = ""
        for i, paper in enumerate(papers[:50]):  # 限制数量
            title = paper.get("title", "")
            year = paper.get("year", "")
            abstract = paper.get("abstract", "")[:200]
            citations = paper.get("citations", 0)
            papers_info += f"\n[{i}] ({year}) {title}\n    Citations: {citations}\n    {abstract}...\n"
        
        prompt = self.MILESTONE_PROMPT.format(
            topic=topic,
            papers_info=papers_info
        )
        
        response = self.chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        milestones = []
        try:
            result_data = self._parse_json_response(response)
            
            for m_data in result_data.get("milestones", []):
                # 获取相关论文 ID
                paper_indices = m_data.get("paper_indices", [])
                paper_ids = []
                for idx in paper_indices:
                    if 0 <= idx < len(papers):
                        paper_id = papers[idx].get("id", "")
                        if paper_id:
                            paper_ids.append(paper_id)
                
                milestone = Milestone(
                    year=m_data.get("year", 0),
                    title=m_data.get("title", ""),
                    description=m_data.get("description", ""),
                    papers=paper_ids,
                    impact=m_data.get("impact", "medium"),
                    category=m_data.get("category", "method")
                )
                milestones.append(milestone)
        except Exception as e:
            logger.error(f"解析里程碑失败: {e}")
        
        # 按年份排序
        milestones.sort(key=lambda m: m.year)
        return milestones
    
    def _analyze_phases(
        self,
        topic: str,
        milestones: List[Milestone],
        statistics: Dict[str, Any]
    ) -> List[EvolutionPhase]:
        """分析演化阶段"""
        # 准备里程碑信息
        milestones_info = json.dumps([m.to_dict() for m in milestones], indent=2)
        
        # 准备年份分布
        year_distribution = json.dumps(statistics.get("year_distribution", {}), indent=2)
        
        prompt = self.PHASE_PROMPT.format(
            topic=topic,
            milestones_info=milestones_info,
            year_distribution=year_distribution
        )
        
        response = self.chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        phases = []
        try:
            result_data = self._parse_json_response(response)
            
            for p_data in result_data.get("phases", []):
                phase = EvolutionPhase(
                    name=p_data.get("name", ""),
                    start_year=p_data.get("start_year", 0),
                    end_year=p_data.get("end_year", 0),
                    description=p_data.get("description", ""),
                    key_characteristics=p_data.get("key_characteristics", []),
                    representative_works=p_data.get("representative_works", [])
                )
                phases.append(phase)
        except Exception as e:
            logger.error(f"解析演化阶段失败: {e}")
        
        # 按开始年份排序
        phases.sort(key=lambda p: p.start_year)
        return phases
    
    def _predict_trends(
        self,
        topic: str,
        papers: List[Dict[str, Any]],
        phases: List[EvolutionPhase]
    ) -> List[TrendPrediction]:
        """预测未来趋势"""
        # 获取最近两年的论文
        current_year = datetime.now().year
        recent_papers = [p for p in papers if p.get("year", 0) >= current_year - 2]
        
        # 准备最近论文信息
        recent_info = ""
        for i, paper in enumerate(recent_papers[:30]):
            title = paper.get("title", "")
            year = paper.get("year", "")
            abstract = paper.get("abstract", "")[:150]
            recent_info += f"\n[{i}] ({year}) {title}\n    {abstract}...\n"
        
        # 准备阶段信息
        phases_info = json.dumps([p.to_dict() for p in phases], indent=2)
        
        prompt = self.TREND_PROMPT.format(
            topic=topic,
            recent_papers=recent_info,
            phases_info=phases_info
        )
        
        response = self.chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        trends = []
        try:
            result_data = self._parse_json_response(response)
            
            for t_data in result_data.get("trends", []):
                trend = TrendPrediction(
                    trend_name=t_data.get("trend_name", ""),
                    confidence=t_data.get("confidence", 0.5),
                    description=t_data.get("description", ""),
                    supporting_evidence=t_data.get("supporting_evidence", []),
                    potential_impact=t_data.get("potential_impact", "medium")
                )
                trends.append(trend)
        except Exception as e:
            logger.error(f"解析趋势预测失败: {e}")
        
        # 按置信度排序
        trends.sort(key=lambda t: t.confidence, reverse=True)
        return trends
    
    def _generate_narrative(
        self,
        topic: str,
        phases: List[EvolutionPhase],
        milestones: List[Milestone],
        trends: List[TrendPrediction]
    ) -> str:
        """生成演化叙事"""
        phases_info = json.dumps([p.to_dict() for p in phases], indent=2)
        milestones_info = json.dumps([m.to_dict() for m in milestones[:10]], indent=2)
        trends_info = json.dumps([t.to_dict() for t in trends[:5]], indent=2)
        
        prompt = self.NARRATIVE_PROMPT.format(
            topic=topic,
            phases_info=phases_info,
            milestones_info=milestones_info,
            trends_info=trends_info
        )
        
        response = self.chat_agent.remote_chat(prompt, model=ADVANCED_CHATAGENT_MODEL)
        
        # 清理响应
        narrative = response.strip()
        # 移除可能的 markdown 标记
        narrative = re.sub(r'^```.*\n?', '', narrative)
        narrative = re.sub(r'\n?```$', '', narrative)
        
        return narrative
    
    def _create_basic_analysis(
        self,
        topic: str,
        papers: List[Dict[str, Any]]
    ) -> EvolutionaryAnalysis:
        """创建基础分析 (论文数量不足时)"""
        statistics = self._compute_statistics(papers)
        
        return EvolutionaryAnalysis(
            topic=topic,
            timeline=[],
            phases=[],
            trends=[],
            narrative=f"The field of {topic} is still emerging with limited published research.",
            statistics=statistics
        )
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析 JSON 响应"""
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response
        
        return json.loads(json_str)
    
    def generate_timeline_latex(self, analysis: EvolutionaryAnalysis) -> str:
        """
        生成时间线的 LaTeX 代码
        
        Args:
            analysis: 演化分析结果
            
        Returns:
            LaTeX 代码字符串
        """
        if not analysis.timeline:
            return ""
        
        latex = r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[scale=0.8]
% Timeline
\draw[thick,->] (0,0) -- (14,0) node[right] {Year};
"""
        
        # 计算年份范围
        years = [m.year for m in analysis.timeline]
        min_year = min(years)
        max_year = max(years)
        year_range = max_year - min_year + 1
        
        # 添加里程碑
        for i, milestone in enumerate(analysis.timeline[:8]):  # 限制数量
            x_pos = (milestone.year - min_year) / year_range * 12 + 1
            y_pos = 0.5 if i % 2 == 0 else -0.5
            
            latex += f"""
\\node[circle,fill=blue!50,minimum size=8pt] at ({x_pos:.1f},0) {{}};
\\node[above] at ({x_pos:.1f},{y_pos:.1f}) {{\\tiny {milestone.year}}};
\\node[below] at ({x_pos:.1f},{-y_pos:.1f}) {{\\tiny {milestone.title[:20]}}};
"""
        
        latex += r"""
\end{tikzpicture}
\caption{Evolution timeline of """ + analysis.topic + r"""}
\label{fig:timeline}
\end{figure}
"""
        
        return latex


# 便捷函数
def analyze_evolution(
    topic: str,
    papers: List[Dict[str, Any]],
    chat_agent: Optional[ChatAgent] = None
) -> EvolutionaryAnalysis:
    """
    执行演化分析的便捷函数
    
    Args:
        topic: 研究主题
        papers: 论文列表
        chat_agent: ChatAgent 实例
        
    Returns:
        EvolutionaryAnalysis 对象
    """
    analyzer = EvolutionaryAnalyzer(chat_agent=chat_agent)
    return analyzer.analyze(topic, papers)


if __name__ == "__main__":
    # 测试代码
    topic = "Large Language Model Agents"
    papers = [
        {"id": "1", "title": "Paper 1", "year": 2020, "abstract": "..."},
        {"id": "2", "title": "Paper 2", "year": 2021, "abstract": "..."},
        {"id": "3", "title": "Paper 3", "year": 2022, "abstract": "..."},
    ]
    
    analyzer = EvolutionaryAnalyzer()
    # 由于论文数量不足，会返回基础分析
    result = analyzer.analyze(topic, papers)
    
    print(f"主题: {result.topic}")
    print(f"里程碑数: {len(result.timeline)}")
    print(f"阶段数: {len(result.phases)}")