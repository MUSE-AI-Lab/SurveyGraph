"""
章节级反思模块 - 参考 SciSage 实现

该模块实现了章节级别的"写-评-改"迭代优化循环，通过多轮反思和改进
来提升综述章节的质量。

核心功能:
1. 多维度评估章节质量（覆盖度、连贯性、引用准确性、批判性分析、写作质量）
2. 基于评估反馈进行定向改进
3. 内容去重检测，避免无效迭代
4. 完整的反思历史追踪

Reference:
- SciSage: refer/SciSage-main/core/section_reflection_opt.py
"""

import asyncio
import hashlib
import json
import time
import traceback
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from pydantic import BaseModel, Field, validator

from src.configs.logger import get_logger
from src.models.LLM import ChatAgent

logger = get_logger("src.modules.post_refine.SectionReflector")


class SectionReflectionResult(BaseModel):
    """章节反思结果模型"""
    
    meets_requirements: bool = Field(
        description="是否满足质量要求"
    )
    feedback: str = Field(
        description="改进反馈，包含具体的问题描述和改进建议"
    )
    improvement_queries: List[str] = Field(
        default_factory=list,
        description="用于检索更多相关文献的改进查询"
    )
    scores: Dict[str, float] = Field(
        default_factory=dict,
        description="各维度评分 (1-5分)"
    )
    
    @validator("feedback")
    def validate_feedback(cls, v):
        """确保反馈不为空"""
        if not v or not v.strip():
            return "未提供具体反馈。"
        return v


class EvaluationDetail(BaseModel):
    """评估详情模型"""
    
    iteration: int = Field(description="迭代轮次")
    timestamp: float = Field(description="评估时间戳")
    scores: Dict[str, float] = Field(description="各维度评分")
    meets_requirements: bool = Field(description="是否满足要求")
    feedback: str = Field(description="评估反馈")
    improvement_queries: List[str] = Field(default_factory=list)
    content_hash: str = Field(description="内容哈希值")
    duration_seconds: float = Field(default=0.0, description="评估耗时")


class RegenerationDetail(BaseModel):
    """重生成详情模型"""
    
    iteration: int = Field(description="迭代轮次")
    timestamp: float = Field(description="重生成时间戳")
    feedback_used: str = Field(description="使用的反馈")
    queries_used: List[str] = Field(description="使用的查询")
    success: bool = Field(description="是否成功")
    duration_seconds: float = Field(default=0.0, description="重生成耗时")


class SectionReflector:
    """
    章节反思器 - 实现章节级别的迭代优化
    
    核心流程:
    1. 评估当前章节内容质量
    2. 如果不满足要求，基于反馈重新生成
    3. 重复直到满足要求或达到最大迭代次数
    4. 生成章节摘要
    
    Attributes:
        chat_agent: LLM 对话代理
        config: 配置参数
        quality_threshold: 质量阈值 (默认 3.5/5.0)
        max_iterations: 最大迭代次数 (默认 3)
    """
    
    # 评估维度及其权重
    EVALUATION_DIMENSIONS = {
        "coverage": {
            "weight": 0.25,
            "name": "内容覆盖度",
            "description": "是否覆盖了该主题的关键方面和重要工作"
        },
        "coherence": {
            "weight": 0.20,
            "name": "逻辑连贯性", 
            "description": "段落之间是否有清晰的逻辑关系和过渡"
        },
        "citation": {
            "weight": 0.20,
            "name": "引用准确性",
            "description": "引用是否准确、相关且格式正确"
        },
        "analysis": {
            "weight": 0.20,
            "name": "批判性分析",
            "description": "是否有对方法优缺点的深入分析"
        },
        "writing": {
            "weight": 0.15,
            "name": "写作质量",
            "description": "语言是否专业、清晰、学术化"
        }
    }
    
    def __init__(
        self,
        chat_agent: ChatAgent,
        config: Optional[Dict[str, Any]] = None,
        quality_threshold: float = 3.5,
        max_iterations: int = 3
    ):
        """
        初始化章节反思器
        
        Args:
            chat_agent: LLM 对话代理
            config: 配置参数
            quality_threshold: 质量阈值，低于此值需要改进 (1-5分制)
            max_iterations: 最大迭代次数
        """
        self.chat_agent = chat_agent
        self.config = config or {}
        self.quality_threshold = quality_threshold
        self.max_iterations = max_iterations
        
    async def reflect_section(
        self,
        section_name: str,
        section_content: str,
        paper_title: str,
        user_query: str,
        outline: Dict[str, Any],
        related_papers: Optional[List[Dict[str, Any]]] = None,
        max_iterations: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        对单个章节进行反思和优化
        
        Args:
            section_name: 章节名称
            section_content: 章节内容 (LaTeX 格式)
            paper_title: 论文标题
            user_query: 用户查询/主题
            outline: 大纲结构
            related_papers: 相关论文列表
            max_iterations: 最大迭代次数 (覆盖默认值)
            
        Returns:
            包含优化后内容和反思历史的字典:
            {
                "section_name": str,
                "final_content": str,
                "summary": str,
                "meets_requirements": bool,
                "final_score": float,
                "iterations": int,
                "evaluation_history": List[EvaluationDetail],
                "regeneration_history": List[RegenerationDetail],
                "content_versions": List[Dict],
                "performance": Dict
            }
        """
        if max_iterations is None:
            max_iterations = self.max_iterations
            
        start_time = time.time()
        iteration = 0
        meets_requirements = False
        
        # 历史追踪
        content_versions = []
        evaluation_history = []
        regeneration_history = []
        
        current_content = section_content
        
        logger.info(f"开始反思章节: {section_name}")
        
        # 记录初始内容
        content_versions.append({
            "iteration": 0,
            "content": current_content,
            "content_hash": self._content_hash(current_content),
            "timestamp": time.time()
        })
        
        while not meets_requirements and iteration < max_iterations:
            iteration_start = time.time()
            logger.info(f"章节 [{section_name}] 反思迭代 {iteration + 1}/{max_iterations}")
            
            try:
                # 1. 评估当前内容
                evaluation = await self._evaluate_section(
                    section_name=section_name,
                    content=current_content,
                    paper_title=paper_title,
                    user_query=user_query,
                    outline=outline
                )
                
                # 记录评估详情
                eval_detail = EvaluationDetail(
                    iteration=iteration + 1,
                    timestamp=time.time(),
                    scores=evaluation.scores,
                    meets_requirements=evaluation.meets_requirements,
                    feedback=evaluation.feedback,
                    improvement_queries=evaluation.improvement_queries,
                    content_hash=self._content_hash(current_content),
                    duration_seconds=time.time() - iteration_start
                )
                evaluation_history.append(eval_detail)
                
                meets_requirements = evaluation.meets_requirements
                
                if meets_requirements:
                    logger.info(f"章节 [{section_name}] 满足质量要求，评分: {self._calculate_weighted_score(evaluation.scores):.2f}")
                    break
                
                # 2. 检查内容是否重复（避免无效迭代）
                current_hash = self._content_hash(current_content)
                previous_hashes = [v["content_hash"] for v in content_versions[:-1]]
                
                if current_hash in previous_hashes:
                    logger.warning(f"章节 [{section_name}] 内容重复，终止迭代")
                    break
                
                # 3. 基于反馈重新生成
                logger.info(f"章节 [{section_name}] 需要改进: {evaluation.feedback[:100]}...")
                
                regen_start = time.time()
                new_content = await self._regenerate_section(
                    section_name=section_name,
                    current_content=current_content,
                    feedback=evaluation.feedback,
                    improvement_queries=evaluation.improvement_queries,
                    paper_title=paper_title,
                    user_query=user_query,
                    related_papers=related_papers
                )
                
                # 记录重生成详情
                regen_detail = RegenerationDetail(
                    iteration=iteration + 1,
                    timestamp=time.time(),
                    feedback_used=evaluation.feedback,
                    queries_used=evaluation.improvement_queries,
                    success=bool(new_content and new_content != current_content),
                    duration_seconds=time.time() - regen_start
                )
                regeneration_history.append(regen_detail)
                
                if new_content and new_content != current_content:
                    current_content = new_content
                    content_versions.append({
                        "iteration": iteration + 1,
                        "content": current_content,
                        "content_hash": self._content_hash(current_content),
                        "timestamp": time.time()
                    })
                else:
                    logger.warning(f"章节 [{section_name}] 重生成失败或内容未变化")
                    
            except Exception as e:
                logger.error(f"章节 [{section_name}] 反思迭代 {iteration + 1} 出错: {e}")
                logger.error(traceback.format_exc())
                break
                
            iteration += 1
        
        # 4. 生成章节摘要
        summary = await self._generate_summary(
            section_name=section_name,
            content=current_content,
            paper_title=paper_title
        )
        
        # 计算最终评分
        final_score = 0.0
        if evaluation_history:
            final_score = self._calculate_weighted_score(evaluation_history[-1].scores)
        
        total_duration = time.time() - start_time
        
        result = {
            "section_name": section_name,
            "final_content": current_content,
            "summary": summary,
            "meets_requirements": meets_requirements,
            "final_score": final_score,
            "iterations": len(evaluation_history),
            "evaluation_history": [e.dict() for e in evaluation_history],
            "regeneration_history": [r.dict() for r in regeneration_history],
            "content_versions": content_versions,
            "performance": {
                "total_duration_seconds": total_duration,
                "iterations_performed": iteration,
                "start_time": start_time,
                "end_time": time.time()
            }
        }
        
        logger.info(
            f"章节 [{section_name}] 反思完成: "
            f"满足要求={meets_requirements}, "
            f"最终评分={final_score:.2f}, "
            f"迭代次数={iteration}, "
            f"耗时={total_duration:.2f}s"
        )
        
        return result
    
    async def _evaluate_section(
        self,
        section_name: str,
        content: str,
        paper_title: str,
        user_query: str,
        outline: Dict[str, Any]
    ) -> SectionReflectionResult:
        """
        评估章节质量
        
        使用 LLM 对章节进行多维度评估，返回结构化的评估结果。
        """
        prompt = self._build_evaluation_prompt(
            section_name=section_name,
            content=content,
            paper_title=paper_title,
            user_query=user_query,
            outline=outline
        )
        
        try:
            response = self.chat_agent.remote_chat(prompt, temperature=0.3)
            result = self._parse_evaluation_response(response)
            return result
        except Exception as e:
            logger.error(f"评估章节 [{section_name}] 失败: {e}")
            # 返回默认的失败结果
            return SectionReflectionResult(
                meets_requirements=False,
                feedback=f"评估失败: {str(e)}",
                improvement_queries=[],
                scores={dim: 2.0 for dim in self.EVALUATION_DIMENSIONS}
            )
    
    async def _regenerate_section(
        self,
        section_name: str,
        current_content: str,
        feedback: str,
        improvement_queries: List[str],
        paper_title: str,
        user_query: str,
        related_papers: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        基于反馈重新生成章节内容
        """
        prompt = self._build_regeneration_prompt(
            section_name=section_name,
            current_content=current_content,
            feedback=feedback,
            improvement_queries=improvement_queries,
            paper_title=paper_title,
            user_query=user_query,
            related_papers=related_papers
        )
        
        try:
            response = self.chat_agent.remote_chat(prompt, temperature=0.5)
            # 提取改进后的内容
            improved_content = self._extract_improved_content(response)
            return improved_content
        except Exception as e:
            logger.error(f"重生成章节 [{section_name}] 失败: {e}")
            return current_content
    
    async def _generate_summary(
        self,
        section_name: str,
        content: str,
        paper_title: str
    ) -> str:
        """
        生成章节摘要
        """
        prompt = f"""请为以下学术综述章节生成一个简洁的摘要（2-3句话）。

论文标题: {paper_title}
章节名称: {section_name}

章节内容:
{content[:4000]}

要求:
1. 摘要应概括章节的主要内容和关键发现
2. 使用学术化的语言
3. 控制在 100 字以内

请直接输出摘要内容，不要添加任何前缀或标签。
"""
        
        try:
            response = self.chat_agent.remote_chat(prompt, temperature=0.3)
            return response.strip()
        except Exception as e:
            logger.error(f"生成章节 [{section_name}] 摘要失败: {e}")
            return f"本章节讨论了 {section_name} 的相关内容。"
    
    def _build_evaluation_prompt(
        self,
        section_name: str,
        content: str,
        paper_title: str,
        user_query: str,
        outline: Dict[str, Any]
    ) -> str:
        """构建评估提示词"""
        
        dimensions_desc = "\n".join([
            f"- {dim_info['name']} ({dim}): {dim_info['description']}"
            for dim, dim_info in self.EVALUATION_DIMENSIONS.items()
        ])
        
        outline_str = json.dumps(outline, ensure_ascii=False, indent=2) if outline else "无"
        
        prompt = f"""你是一位学术综述评审专家。请评估以下章节的质量。

## 论文信息
- 论文标题: {paper_title}
- 研究主题: {user_query}
- 章节名称: {section_name}

## 大纲结构
{outline_str}

## 章节内容
{content[:6000]}

## 评估维度
{dimensions_desc}

## 评估要求
请对每个维度进行 1-5 分的评分:
- 5分: 优秀，达到顶会发表标准
- 4分: 良好，有少量可改进之处
- 3分: 中等，存在明显问题需要改进
- 2分: 较差，存在严重问题
- 1分: 很差，需要重写

## 输出格式
请严格按照以下 JSON 格式输出:
```json
{{
    "scores": {{
        "coverage": <1-5>,
        "coherence": <1-5>,
        "citation": <1-5>,
        "analysis": <1-5>,
        "writing": <1-5>
    }},
    "meets_requirements": <true/false>,
    "feedback": "<具体的改进建议，指出存在的问题和改进方向>",
    "improvement_queries": ["<用于检索更多相关文献的查询1>", "<查询2>"]
}}
```

注意:
1. meets_requirements 为 true 当且仅当所有维度评分 >= 3.5 且加权平均分 >= {self.quality_threshold}
2. feedback 应该具体、可操作，指出具体的问题和改进方向
3. improvement_queries 应该是可用于学术搜索的具体查询词

请输出评估结果:
"""
        return prompt
    
    def _build_regeneration_prompt(
        self,
        section_name: str,
        current_content: str,
        feedback: str,
        improvement_queries: List[str],
        paper_title: str,
        user_query: str,
        related_papers: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """构建重生成提示词"""
        
        papers_info = ""
        if related_papers:
            papers_info = "\n\n## 可参考的相关论文\n"
            for i, paper in enumerate(related_papers[:5], 1):
                title = paper.get("title", "Unknown")
                abstract = paper.get("abstract", "")[:300]
                bib_name = paper.get("bib_name", f"paper{i}")
                papers_info += f"{i}. [{bib_name}] {title}\n   摘要: {abstract}...\n"
        
        queries_str = "\n".join([f"- {q}" for q in improvement_queries]) if improvement_queries else "无"
        
        prompt = f"""你是一位学术综述写作专家。请根据评审反馈改进以下章节。

## 论文信息
- 论文标题: {paper_title}
- 研究主题: {user_query}
- 章节名称: {section_name}

## 当前章节内容
{current_content}

## 评审反馈
{feedback}

## 建议的改进方向
{queries_str}
{papers_info}

## 改进要求
1. 针对评审反馈中指出的问题进行改进
2. 保持 LaTeX 格式，确保可以正确编译
3. 保持学术化的写作风格
4. 确保引用格式正确 (使用 \\cite{{bib_name}} 格式)
5. 不要改变章节的整体结构，只改进内容质量
6. 不要添加 \\section 或 \\subsection 命令，只输出章节正文内容
7. 严禁编造 citation key：只能使用“可参考的相关论文”中出现过的 bib_name（若未提供相关论文，则不要新增引用）

## 输出格式
请直接输出改进后的章节内容（LaTeX 格式），不要添加任何解释或标签。

改进后的内容:
"""
        return prompt
    
    def _parse_evaluation_response(self, response: str) -> SectionReflectionResult:
        """解析评估响应"""
        try:
            # 尝试提取 JSON
            json_match = response
            if "```json" in response:
                json_match = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_match = response.split("```")[1].split("```")[0]
            
            result = json.loads(json_match.strip())
            
            # 验证必要字段
            scores = result.get("scores", {})
            for dim in self.EVALUATION_DIMENSIONS:
                if dim not in scores:
                    scores[dim] = 3.0  # 默认中等分数
                else:
                    scores[dim] = float(scores[dim])
            
            # 计算加权平均分
            weighted_score = self._calculate_weighted_score(scores)
            
            # 判断是否满足要求
            meets_requirements = result.get("meets_requirements", False)
            if not meets_requirements:
                # 如果 LLM 没有正确判断，我们自己计算
                meets_requirements = (
                    weighted_score >= self.quality_threshold and
                    all(scores.get(dim, 0) >= 3.0 for dim in self.EVALUATION_DIMENSIONS)
                )
            
            return SectionReflectionResult(
                meets_requirements=meets_requirements,
                feedback=result.get("feedback", "未提供具体反馈"),
                improvement_queries=result.get("improvement_queries", []),
                scores=scores
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"解析评估响应失败: {e}, 响应: {response[:200]}...")
            # 返回默认结果
            return SectionReflectionResult(
                meets_requirements=False,
                feedback="评估响应解析失败，请重新评估",
                improvement_queries=[],
                scores={dim: 3.0 for dim in self.EVALUATION_DIMENSIONS}
            )
    
    def _extract_improved_content(self, response: str) -> str:
        """从响应中提取改进后的内容"""
        content = response.strip()
        
        # 移除可能的 markdown 代码块标记
        if content.startswith("```latex"):
            content = content[8:]
        elif content.startswith("```"):
            content = content[3:]
        
        if content.endswith("```"):
            content = content[:-3]
        
        return content.strip()
    
    def _calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """计算加权平均分"""
        total_weight = 0.0
        weighted_sum = 0.0
        
        for dim, dim_info in self.EVALUATION_DIMENSIONS.items():
            if dim in scores:
                weighted_sum += scores[dim] * dim_info["weight"]
                total_weight += dim_info["weight"]
        
        if total_weight == 0:
            return 0.0
        
        return weighted_sum / total_weight
    
    def _content_hash(self, content: str) -> str:
        """计算内容哈希值用于去重"""
        return hashlib.md5(content.encode()).hexdigest()


# 同步包装器，方便在非异步环境中使用
def reflect_section_sync(
    chat_agent: ChatAgent,
    section_name: str,
    section_content: str,
    paper_title: str,
    user_query: str,
    outline: Dict[str, Any],
    related_papers: Optional[List[Dict[str, Any]]] = None,
    max_iterations: int = 3,
    quality_threshold: float = 3.5
) -> Dict[str, Any]:
    """
    同步版本的章节反思函数
    
    Args:
        chat_agent: LLM 对话代理
        section_name: 章节名称
        section_content: 章节内容
        paper_title: 论文标题
        user_query: 用户查询
        outline: 大纲结构
        related_papers: 相关论文列表
        max_iterations: 最大迭代次数
        quality_threshold: 质量阈值
        
    Returns:
        反思结果字典
    """
    reflector = SectionReflector(
        chat_agent=chat_agent,
        quality_threshold=quality_threshold,
        max_iterations=max_iterations
    )
    
    # 运行异步函数，处理已存在事件循环的情况
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环，可以使用 asyncio.run()
        loop = None
    
    if loop is not None:
        # 已经在事件循环中，使用同步方式执行
        # 创建一个新的事件循环在单独的线程中运行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                reflector.reflect_section(
                    section_name=section_name,
                    section_content=section_content,
                    paper_title=paper_title,
                    user_query=user_query,
                    outline=outline,
                    related_papers=related_papers
                )
            )
            return future.result()
    else:
        # 没有运行中的事件循环，直接使用 asyncio.run()
        return asyncio.run(reflector.reflect_section(
            section_name=section_name,
            section_content=section_content,
            paper_title=paper_title,
            user_query=user_query,
            outline=outline,
            related_papers=related_papers
        ))


if __name__ == "__main__":
    # 测试代码
    from src.models.monitor.token_monitor import TokenMonitor
    
    # 创建测试用的 ChatAgent
    token_monitor = TokenMonitor("test", "section_reflection_test")
    chat_agent = ChatAgent(token_monitor)
    
    # 测试章节内容
    test_content = """
Large Language Models (LLMs) have revolutionized natural language processing in recent years. 
Models such as GPT-4 \\cite{openai2023gpt4} and LLaMA \\cite{touvron2023llama} have demonstrated 
remarkable capabilities in various tasks including text generation, question answering, and reasoning.

The development of LLMs can be traced back to the transformer architecture \\cite{vaswani2017attention}, 
which introduced the self-attention mechanism. This architecture has become the foundation for 
most modern language models.

Recent advances have focused on scaling model parameters and training data. Studies have shown 
that larger models generally exhibit better performance on downstream tasks, following scaling laws 
\\cite{kaplan2020scaling}.
"""
    
    # 测试大纲
    test_outline = {
        "title": "A Survey on Large Language Models",
        "sections": [
            {"title": "Introduction", "desc": "Overview of LLMs"},
            {"title": "Background", "desc": "Historical development"},
            {"title": "Methods", "desc": "Key techniques and architectures"}
        ]
    }
    
    # 运行测试
    result = reflect_section_sync(
        chat_agent=chat_agent,
        section_name="Introduction",
        section_content=test_content,
        paper_title="A Survey on Large Language Models",
        user_query="Large Language Models",
        outline=test_outline,
        max_iterations=2
    )
    
    print("反思结果:")
    print(f"满足要求: {result['meets_requirements']}")
    print(f"最终评分: {result['final_score']:.2f}")
    print(f"迭代次数: {result['iterations']}")
    print(f"摘要: {result['summary']}")
