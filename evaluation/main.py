"""
MEKG Survey Evaluation System - 主入口
======================================

基于MEKG知识图谱的综述质量评估系统。

支持多模型评测：
- 非可视化评测（内容、结构、伦理等）可使用多个 T2T 模型进行评测并融合结果
- 可视化评测（富媒体质量）使用单一多模态模型（advanced_model）

使用方法:
    # 命令行
    python -m evaluation.main --mekg-data path/to/mekg.json --survey-path path/to/survey.tex
    
    # Python API
    from evaluation import MEKGSurveyEvaluator, EvaluationConfig
    evaluator = MEKGSurveyEvaluator(mekg_data, survey_path, config)
    result = evaluator.evaluate_all()
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from evaluation.config import (
    EvaluationConfig, FAST_CONFIG, FULL_CONFIG, DEV_CONFIG,
    MULTI_MODEL_CONFIG, SINGLE_MODEL_CONFIG
)
from evaluation.core.result import EvaluationResult, DimensionResult
from evaluation.evaluators.reference_evaluator import ReferenceEvaluator
from evaluation.evaluators.structure_evaluator import StructureEvaluator
from evaluation.evaluators.content_evaluator import ContentEvaluator
from evaluation.evaluators.ethics_evaluator import EthicsEvaluator
from evaluation.evaluators.media_evaluator import MediaEvaluator
from evaluation.utils.latex_parser import resolve_latex_inputs
from evaluation.utils.llm_client import (
    set_default_client, LLMClient,
    set_multi_model_evaluator, MultiModelEvaluator
)


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class MEKGSurveyEvaluator:
    """
    MEKG综述评测主类
    
    整合所有评测模块，提供统一的评测接口。
    """
    
    def __init__(
        self,
        mekg_data: Dict[str, Any],
        survey_path: Path,
        config: Optional[EvaluationConfig] = None,
        outline_path: Optional[Path] = None,
        bibtex_path: Optional[Path] = None
    ):
        """
        初始化评测器
        
        Args:
            mekg_data: MEKG数据
            survey_path: 综述文件路径
            config: 评测配置
            outline_path: 大纲文件路径（可选）
            bibtex_path: BibTeX文件路径（可选）
        """
        self.mekg_data = mekg_data
        self.survey_path = Path(survey_path)
        self.config = config or EvaluationConfig()
        self.outline_path = Path(outline_path) if outline_path else None
        self.bibtex_path = Path(bibtex_path) if bibtex_path else None
        
        # 自动检测BibTeX文件
        if not self.bibtex_path:
            self.bibtex_path = self._find_bibtex_file()
        
        # 加载综述内容
        self.survey_content = self._load_survey_content()
        
        # 加载大纲
        self.survey_outline = self._load_outline()
        
        # 获取主题
        self.topic = mekg_data.get("topic", "")
        
        # 初始化LLM客户端
        if self.config.use_llm:
            self._init_llm_client()
        
        # 初始化评测器
        self._init_evaluators()
        
        logger.info(f"初始化MEKG综述评测器")
        logger.info(f"  综述路径: {self.survey_path}")
        logger.info(f"  MEKG论文数: {len(mekg_data.get('papers', []))}")
        logger.info(f"  使用LLM: {self.config.use_llm}")
    
    def _find_bibtex_file(self) -> Optional[Path]:
        """自动查找BibTeX文件"""
        survey_dir = self.survey_path.parent
        
        # 常见的BibTeX文件名
        bib_names = ["references.bib", "ref.bib", "bibliography.bib", "main.bib"]
        
        for name in bib_names:
            bib_path = survey_dir / name
            if bib_path.exists():
                return bib_path
        
        # 查找任意.bib文件
        bib_files = list(survey_dir.glob("*.bib"))
        if bib_files:
            return bib_files[0]
        
        return None
    
    def _load_survey_content(self) -> str:
        """加载综述内容"""
        if not self.survey_path.exists():
            raise FileNotFoundError(f"综述文件不存在: {self.survey_path}")
        
        # 解析LaTeX文件（处理\input等命令）
        content = resolve_latex_inputs(self.survey_path)
        logger.info(f"加载综述内容: {len(content)} 字符")
        
        return content
    
    def _load_outline(self) -> Optional[Dict]:
        """加载大纲"""
        if self.outline_path and self.outline_path.exists():
            with open(self.outline_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def _init_llm_client(self):
        """初始化LLM客户端和多模型评测器"""
        # 初始化默认 LLM 客户端（用于单模型评测和可视化评测）
        client = LLMClient(
            api_url=self.config.api_url,
            api_key=self.config.api_key,
            model=self.config.advanced_model,
            temperature=self.config.temperature,
            max_retries=self.config.max_retries,
            timeout=self.config.timeout
        )
        set_default_client(client)
        
        # 如果启用多模型评测，初始化多模型评测器
        if self.config.should_use_multi_model():
            multi_evaluator = MultiModelEvaluator(
                models=self.config.t2t_models,
                api_url=self.config.api_url,
                api_key=self.config.api_key,
                temperature=self.config.temperature,
                timeout=self.config.multi_model_timeout,
                model_weights=self.config.model_weights,
                fusion_strategy=self.config.fusion_strategy
            )
            set_multi_model_evaluator(multi_evaluator)
            logger.info(f"  多模型评测: 已启用")
            logger.info(f"    - T2T 模型: {', '.join(self.config.t2t_models)}")
            logger.info(f"    - 融合策略: {self.config.fusion_strategy}")
        else:
            logger.info(f"  多模型评测: 已禁用（使用单模型）")
    
    def _init_evaluators(self):
        """初始化各评测器"""
        self.evaluators = {
            "reference_quality": ReferenceEvaluator(self.config, self.mekg_data),
            "structural_soundness": StructureEvaluator(self.config, self.mekg_data),
            "content_integrity": ContentEvaluator(self.config, self.mekg_data),
            "ethics_integrity": EthicsEvaluator(self.config, self.mekg_data),
            "rich_media_quality": MediaEvaluator(self.config, self.mekg_data)
        }
    
    def evaluate_all(self) -> EvaluationResult:
        """
        执行完整评测流程（并行版本）
        
        所有5个维度的评测将并行执行，大幅提升评测速度。
        
        Returns:
            EvaluationResult对象
        """
        logger.info("=" * 60)
        logger.info("开始MEKG综述评测（并行模式）")
        logger.info("=" * 60)
        
        result = EvaluationResult(
            survey_path=str(self.survey_path),
            mekg_path="",
            timestamp=datetime.now().isoformat()
        )
        
        # 定义各维度的评测任务
        def evaluate_reference_quality() -> Dict[str, Any]:
            """评测引用质量"""
            return {
                "dimension": "reference_quality",
                "name": "Reference Quality",
                "result": self.evaluators["reference_quality"].evaluate(
                    self.survey_content,
                    self.survey_outline,
                    bibtex_path=self.bibtex_path
                )
            }
        
        def evaluate_structural_soundness() -> Dict[str, Any]:
            """评测结构完整性"""
            return {
                "dimension": "structural_soundness",
                "name": "Structural Soundness",
                "result": self.evaluators["structural_soundness"].evaluate(
                    self.survey_content,
                    self.survey_outline
                )
            }
        
        def evaluate_content_integrity() -> Dict[str, Any]:
            """评测内容完整性"""
            return {
                "dimension": "content_integrity",
                "name": "Content Integrity",
                "result": self.evaluators["content_integrity"].evaluate(
                    self.survey_content,
                    self.survey_outline,
                    topic=self.topic
                )
            }
        
        def evaluate_ethics_integrity() -> Dict[str, Any]:
            """评测伦理与完整性"""
            return {
                "dimension": "ethics_integrity",
                "name": "Ethics & Integrity",
                "result": self.evaluators["ethics_integrity"].evaluate(
                    self.survey_content,
                    self.survey_outline
                )
            }
        
        def evaluate_rich_media_quality() -> Dict[str, Any]:
            """评测富媒体质量"""
            return {
                "dimension": "rich_media_quality",
                "name": "Rich Media Quality",
                "result": self.evaluators["rich_media_quality"].evaluate(
                    self.survey_content,
                    self.survey_outline
                )
            }
        
        # 所有评测任务
        evaluation_tasks: List[Callable[[], Dict[str, Any]]] = [
            evaluate_reference_quality,
            evaluate_structural_soundness,
            evaluate_content_integrity,
            evaluate_ethics_integrity,
            evaluate_rich_media_quality
        ]
        
        # 并行执行所有评测任务
        logger.info(f"并行执行 {len(evaluation_tasks)} 个维度的评测...")
        
        with ThreadPoolExecutor(max_workers=len(evaluation_tasks)) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(task): task.__name__
                for task in evaluation_tasks
            }
            
            # 收集结果
            for future in as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    task_result = future.result()
                    dimension = task_result["dimension"]
                    name = task_result["name"]
                    eval_result = task_result["result"]
                    
                    # 创建 DimensionResult 并赋值给对应属性
                    dimension_result = DimensionResult(
                        name=name,
                        score=eval_result["score"],
                        weight=self.config.dimension_weights[dimension],
                        metrics=eval_result["metrics"],
                        details=eval_result.get("details", {})
                    )
                    
                    # 根据维度名称赋值
                    if dimension == "reference_quality":
                        result.reference_quality = dimension_result
                    elif dimension == "structural_soundness":
                        result.structural_soundness = dimension_result
                    elif dimension == "content_integrity":
                        result.content_integrity = dimension_result
                    elif dimension == "ethics_integrity":
                        result.ethics_integrity = dimension_result
                    elif dimension == "rich_media_quality":
                        result.rich_media_quality = dimension_result
                    
                    logger.info(f"✅ {name} 评测完成，得分: {eval_result['score']:.2f}")
                    
                except Exception as e:
                    logger.error(f"❌ {task_name} 评测失败: {e}")
                    # 从任务名称推断维度名称
                    dimension_map = {
                        "evaluate_reference_quality": "Reference Quality",
                        "evaluate_structural_soundness": "Structural Soundness",
                        "evaluate_content_integrity": "Content Integrity",
                        "evaluate_ethics_integrity": "Ethics & Integrity",
                        "evaluate_rich_media_quality": "Rich Media Quality"
                    }
                    error_name = dimension_map.get(task_name, task_name)
                    result.errors.append(f"{error_name}: {str(e)}")
        
        # 计算综合分数
        result.calculate_overall_score()
        result.collect_all_metrics()
        
        # 生成建议
        result.recommendations = self._generate_recommendations(result)
        
        logger.info("=" * 60)
        logger.info(f"评测完成！综合得分: {result.overall_score:.2f}/100")
        logger.info("=" * 60)
        
        return result
    
    def evaluate_dimension(self, dimension: str) -> DimensionResult:
        """
        评测单个维度
        
        Args:
            dimension: 维度名称
            
        Returns:
            DimensionResult对象
        """
        if dimension not in self.evaluators:
            raise ValueError(f"未知的评测维度: {dimension}")
        
        evaluator = self.evaluators[dimension]
        
        kwargs = {
            "survey_content": self.survey_content,
            "survey_outline": self.survey_outline
        }
        
        if dimension == "reference_quality":
            kwargs["bibtex_path"] = self.bibtex_path
        elif dimension == "content_integrity":
            kwargs["topic"] = self.topic
        
        result = evaluator.evaluate(**kwargs)
        
        return DimensionResult(
            name=evaluator.name,
            score=result["score"],
            weight=self.config.dimension_weights[dimension],
            metrics=result["metrics"],
            details=result.get("details", {})
        )
    
    def _generate_recommendations(self, result: EvaluationResult) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        # 引用质量建议
        if result.reference_quality and result.reference_quality.score < 0.7:
            wcr = result.reference_quality.metrics.get("wcr", 0)
            cc = result.reference_quality.metrics.get("cc", 0)
            
            if wcr < 0.7:
                recommendations.append(
                    "📚 提高核心论文覆盖率: 建议引用更多高影响力的核心论文"
                )
            if cc < 0.8:
                recommendations.append(
                    "🔍 扩展研究方向覆盖: 建议增加对更多研究社区的讨论"
                )
        
        # 结构建议
        if result.structural_soundness and result.structural_soundness.score < 0.7:
            recommendations.append(
                "📋 优化综述结构: 建议调整章节结构，确保包含完整的引言、背景、主体和结论"
            )
        
        # 内容建议
        if result.content_integrity and result.content_integrity.score < 0.7:
            recommendations.append(
                "✍️ 提升内容质量: 建议加强批判性分析和综合讨论"
            )
        
        # 伦理建议
        if result.ethics_integrity and result.ethics_integrity.score < 0.5:
            recommendations.append(
                "⚖️ 增加伦理讨论: 建议添加关于社会影响和潜在风险的讨论"
            )
        
        # 富媒体建议
        if result.rich_media_quality and result.rich_media_quality.score < 0.5:
            recommendations.append(
                "📊 改善图表质量: 建议添加更多有信息量的图表，并确保所有图表都有清晰的标题"
            )
        
        if not recommendations:
            recommendations.append("✅ 综述质量良好，各项指标均达到较高水平")
        
        return recommendations
    
    def generate_report(
        self,
        result: EvaluationResult,
        output_path: Optional[Path] = None
    ) -> str:
        """
        生成评测报告（基础版）
        
        Args:
            result: 评测结果
            output_path: 输出路径（可选）
            
        Returns:
            报告内容
        """
        from evaluation.report.generator import ReportGenerator
        
        generator = ReportGenerator(result)
        report = generator.generate()
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report, encoding='utf-8')
            logger.info(f"报告已保存到: {output_path}")
        
        return report
    
    def generate_enhanced_report(
        self,
        result: EvaluationResult,
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        生成增强版评测报告（多格式）
        
        Args:
            result: 评测结果
            output_dir: 输出目录
            
        Returns:
            生成的文件路径字典
        """
        from evaluation.report.enhanced_generator import (
            EnhancedReportGenerator,
            ReportConfig
        )
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建报告配置
        config = ReportConfig(
            generate_markdown=True,
            generate_json=True,
            generate_charts=True,
            generate_poster=True,
            generate_html=True,  # 生成 HTML 报告（中英文双语）
            language="zh"
        )
        
        # 生成所有格式的报告
        generator = EnhancedReportGenerator(result, config)
        generated_files = generator.generate_all(output_dir)
        
        logger.info(f"增强版报告已生成到: {output_dir}")
        logger.info(f"  - Markdown报告: {generated_files.get('markdown', 'N/A')}")
        logger.info(f"  - JSON数据: {generated_files.get('json', 'N/A')}")
        logger.info(f"  - 可视化图表: {generated_files.get('charts', 'N/A')}")
        logger.info(f"  - 报告海报: {generated_files.get('poster', 'N/A')}")
        logger.info(f"  - HTML报告: {generated_files.get('html', 'N/A')}")
        
        return generated_files


def evaluate_survey(
    mekg_data_path: Path,
    survey_path: Path,
    outline_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    config: Optional[EvaluationConfig] = None
) -> EvaluationResult:
    """
    评测综述的便捷函数
    
    Args:
        mekg_data_path: MEKG数据路径
        survey_path: 综述文件路径
        outline_path: 大纲路径（可选）
        output_dir: 输出目录（可选）
        config: 评测配置（可选）
        
    Returns:
        EvaluationResult对象
    """
    # 加载MEKG数据
    with open(mekg_data_path, 'r', encoding='utf-8') as f:
        mekg_data = json.load(f)
    
    # 创建评测器
    evaluator = MEKGSurveyEvaluator(
        mekg_data=mekg_data,
        survey_path=survey_path,
        config=config,
        outline_path=outline_path
    )
    
    # 执行评测
    result = evaluator.evaluate_all()
    
    # 保存结果
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存JSON结果（基础版）
        result.save(output_dir / "evaluation_results.json")
        
        # 生成增强版报告（多格式）
        evaluator.generate_enhanced_report(result, output_dir)
    
    return result


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="MEKG Survey Evaluation System",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--mekg-data",
        type=str,
        required=True,
        help="MEKG数据JSON文件路径"
    )
    
    parser.add_argument(
        "--survey-path",
        type=str,
        required=True,
        help="综述LaTeX文件路径"
    )
    
    parser.add_argument(
        "--outline",
        type=str,
        help="大纲JSON文件路径（可选）"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        help="输出目录（可选）"
    )
    
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="不使用LLM（更快但评估不够全面）"
    )
    
    parser.add_argument(
        "--fast",
        action="store_true",
        help="使用快速评测配置（不使用LLM）"
    )
    
    parser.add_argument(
        "--full",
        action="store_true",
        help="使用完整评测配置（启用多模型）"
    )
    
    parser.add_argument(
        "--multi-model",
        action="store_true",
        help="使用多模型评测配置"
    )
    
    parser.add_argument(
        "--single-model",
        action="store_true",
        help="使用单模型评测配置（禁用多模型融合）"
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        help="OpenAI API Key"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出"
    )
    
    args = parser.parse_args()
    
    # 选择配置
    if args.fast:
        config = FAST_CONFIG
    elif args.full:
        config = FULL_CONFIG
    elif getattr(args, 'multi_model', False):
        config = MULTI_MODEL_CONFIG
    elif getattr(args, 'single_model', False):
        config = SINGLE_MODEL_CONFIG
    else:
        config = EvaluationConfig()
    
    if args.no_llm:
        config.use_llm = False
    
    if args.api_key:
        config.api_key = args.api_key
    
    if args.verbose:
        config.verbose = True
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        result = evaluate_survey(
            mekg_data_path=Path(args.mekg_data),
            survey_path=Path(args.survey_path),
            outline_path=Path(args.outline) if args.outline else None,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            config=config
        )
        
        # 打印结果
        print(result)
        
    except Exception as e:
        logger.error(f"评测失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()