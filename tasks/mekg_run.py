"""
MEKG Run - MEKG驱动的综述生成入口
=================================

支持从头开始生成综述，直到生成PDF。
步步留痕：所有中间结果都会保存到 outputs/{task_id}/ 目录下。

断点续传功能：
- 每个步骤完成后自动保存检查点
- 支持从任意检查点恢复执行
- 72小时内的检查点有效

使用方法:
    # 从头开始
    python tasks/mekg_run.py --topic "Large Language Model Agents" --max_papers 200
    
    # 从断点恢复（指定已有的task_id）
    python tasks/mekg_run.py --resume --task_id "2025-12-15-1933_Large_Language_Model"

    可选参数:
    --max_papers: 最大搜索论文数
    --year_start: 起始年份
    --year_end: 结束年份
    --enable_critic: 启用大纲批判循环
    --enable_refine: 启用内容自动优化
    --enable-reflection/--no-reflection: 启用/关闭章节级反思机制 (默认开启)
    --reflection-max-iter: 反思最大迭代次数 (默认3)
    --reflection-threshold: 反思质量阈值 (默认3.5)
    --use-hybrid-outline/--no-hybrid-outline: 启用/关闭混合大纲生成 (默认开启)
    --use-global-reflector/--no-global-reflector: 启用/关闭全局一致性检查 (默认开启)
    --use-evolutionary-analyzer/--no-evolutionary-analyzer: 启用/关闭演化叙事分析 (默认开启)
    --run-evaluation/--no-evaluation: 运行/关闭 evaluation/ 的综合评估（默认开启）
    --eval-use-llm: evaluation 是否启用 LLM（默认开启，且强制启用）
    --eval-api-key: evaluation 的 API KEY（可选，默认从 src/configs/config.py 读取，可覆盖）
    --resume: 从断点恢复
    --task_id: 指定要恢复的任务ID
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))

# 配置 loguru，将输出重定向到 stdout 而不是 stderr
# 这样可以避免 PowerShell 将 loguru 的 INFO 日志显示为红色错误
from loguru import logger as loguru_logger
loguru_logger.remove()  # 移除默认的 stderr handler
loguru_logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    colorize=True
)

from src.configs.logger import get_logger
from mekg.src.survey.pipeline import MEKGSurveyPipeline, PipelineConfig, PipelineStep
from src.models.generator.latex_generator import LatexGenerator

# 配置日志
logger = get_logger("tasks.mekg_run")

# ==========================================
# 默认配置
# ==========================================
DEFAULT_CONFIG = {
    "topic": "Large Language Model Function Calling",  # 综述主题
    "max_papers": 200,                       # 最大论文数
    "year_start": 2020,                      # 起始年份
    "year_end": 2026,                        # 结束年份
    "enable_critic": True,                   # 启用大纲批判循环
    "enable_refine": True,                   # 启用内容自动优化
    "use_memgraph": True,                    # 启用Memgraph图数据库
    "use_enhanced_collector": True,          # 使用增强版论文收集器
    "use_survey_strategy": False,            # 使用Survey优先策略（默认关闭，因为参考文献获取不稳定）
    "survey_count": 10,                      # Survey数量
    "max_refs_per_survey": 50,               # 每篇Survey最大参考文献数
    "use_embedding_filter": True,            # 使用Embedding筛选
    "embedding_threshold": 0.3,              # Embedding阈值
    # 反思机制配置 (P0 优化功能 - 默认开启)
    "enable_reflection": True,               # 启用章节级反思机制
    "reflection_max_iterations": 3,          # 反思最大迭代次数
    "reflection_quality_threshold": 3.5,     # 反思质量阈值 (1-5 分制)
    "enable_global_evaluation": True,        # 启用全局评分细则评估
    # 新模块配置 (P1/P2 优化功能 - 默认开启)
    "use_hybrid_outline": True,              # 启用混合大纲生成
    "use_global_reflector": True,            # 启用全局一致性检查
    "use_evolutionary_analyzer": True        # 启用演化叙事分析
}

def setup_task_directories(task_id: str, output_dir: str = "outputs") -> Path:
    """设置任务目录"""
    task_dir = Path(BASE_DIR) / output_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建子目录
    (task_dir / "mekg").mkdir(exist_ok=True)
    (task_dir / "papers").mkdir(exist_ok=True)
    (task_dir / "latex").mkdir(exist_ok=True)
    (task_dir / "tmp").mkdir(exist_ok=True)
    (task_dir / "logs").mkdir(exist_ok=True)
    
    return task_dir

def save_task_config(task_dir: Path, args: argparse.Namespace):
    """保存任务配置"""
    config = vars(args)
    config["created_at"] = datetime.now().isoformat()
    
    with open(task_dir / "task_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Task config saved to {task_dir / 'task_config.json'}")

def find_latest_task_for_topic(topic: str, output_dir: str = "outputs") -> str:
    """查找指定主题的最新任务ID"""
    output_path = Path(BASE_DIR) / output_dir
    if not output_path.exists():
        return None
    
    topic_slug = topic.replace(" ", "_")[:20]
    matching_tasks = []
    
    for task_dir in output_path.iterdir():
        if task_dir.is_dir() and topic_slug in task_dir.name:
            # 检查是否有检查点文件
            checkpoint_path = task_dir / "checkpoint.json"
            if checkpoint_path.exists():
                matching_tasks.append(task_dir.name)
    
    if not matching_tasks:
        return None
    
    # 按时间排序，返回最新的
    matching_tasks.sort(reverse=True)
    return matching_tasks[0]


def list_resumable_tasks(output_dir: str = "outputs") -> list:
    """列出所有可恢复的任务"""
    output_path = Path(BASE_DIR) / output_dir
    if not output_path.exists():
        return []
    
    resumable = []
    for task_dir in output_path.iterdir():
        if task_dir.is_dir():
            checkpoint_path = task_dir / "checkpoint.json"
            if checkpoint_path.exists():
                try:
                    import json
                    with open(checkpoint_path, 'r', encoding='utf-8') as f:
                        checkpoint = json.load(f)
                    
                    # 检查有效期（72小时）
                    from datetime import datetime
                    checkpoint_time = datetime.fromisoformat(checkpoint.get("timestamp", ""))
                    hours_diff = (datetime.now() - checkpoint_time).total_seconds() / 3600
                    
                    if hours_diff <= 72:
                        resumable.append({
                            "task_id": task_dir.name,
                            "topic": checkpoint.get("topic", "Unknown"),
                            "step": checkpoint.get("step_name", "Unknown"),
                            "timestamp": checkpoint.get("timestamp", ""),
                            "hours_ago": round(hours_diff, 1)
                        })
                except:
                    pass
    
    # 按时间排序
    resumable.sort(key=lambda x: x["timestamp"], reverse=True)
    return resumable


async def run_mekg_pipeline(args):
    """运行MEKG流水线"""
    resume_mode = getattr(args, 'resume', False)
    specified_task_id = getattr(args, 'task_id', None)
    
    # 确定任务ID
    if resume_mode:
        if specified_task_id:
            task_id = specified_task_id
        else:
            # 尝试查找该主题的最新任务
            task_id = find_latest_task_for_topic(args.topic)
            if not task_id:
                print("❌ 未找到可恢复的任务。请指定 --task_id 或从头开始。")
                print("\n可恢复的任务列表:")
                resumable = list_resumable_tasks()
                if resumable:
                    for task in resumable[:10]:
                        print(f"  - {task['task_id']}")
                        print(f"    主题: {task['topic']}")
                        print(f"    进度: {task['step']}")
                        print(f"    时间: {task['hours_ago']} 小时前")
                else:
                    print("  (无可恢复的任务)")
                return
        
        # 检查任务目录是否存在
        task_dir = Path(BASE_DIR) / "outputs" / task_id
        if not task_dir.exists():
            print(f"❌ 任务目录不存在: {task_dir}")
            return
        
        print(f"🔄 恢复任务: {task_id}")
    else:
        # 如果指定了 task_id，使用指定的（来自前端）
        # 否则生成新任务ID
        if specified_task_id:
            task_id = specified_task_id
            logger.info(f"使用指定的 task_id: {task_id}")
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
            topic_slug = args.topic.replace(" ", "_")[:20]
            task_id = f"{timestamp}_{topic_slug}"
        
        # 设置目录
        task_dir = setup_task_directories(task_id)
        save_task_config(task_dir, args)
    
    # 注意：logger 已经由 src.configs.logger 配置了控制台输出
    # 我们只需要确保它能输出到任务目录的日志文件
    file_handler = logging.FileHandler(task_dir / "logs" / "run.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    
    logger.info("=" * 60)
    logger.info(f"🚀 Starting MEKG Survey Generation")
    logger.info(f"   Topic: {args.topic}")
    logger.info(f"   Task ID: {task_id}")
    logger.info(f"   Output Dir: {task_dir}")
    logger.info("=" * 60)
    
    # 配置流水线
    config = PipelineConfig(
        topic=args.topic,
        output_dir=Path(BASE_DIR) / "outputs",
        task_id=task_id,
        max_papers=args.max_papers,
        year_start=args.year_start,
        year_end=args.year_end,
        use_llm_relations=True,
        enable_critic_loop=args.enable_critic,
        enable_auto_refine=args.enable_refine,
        use_memgraph=args.use_memgraph,
        use_enhanced_collector=args.use_enhanced_collector,
        use_survey_strategy=args.use_survey_strategy,
        survey_count=args.survey_count,
        max_refs_per_survey=args.max_refs_per_survey,
        use_embedding_filter=args.use_embedding_filter,
        embedding_threshold=args.embedding_threshold,
        generate_latex=True,
        generate_visualization=True,
        # 反思机制配置
        enable_reflection=getattr(args, 'enable_reflection', True),
        reflection_max_iterations=getattr(args, 'reflection_max_iterations', 3),
        reflection_quality_threshold=getattr(args, 'reflection_quality_threshold', 3.5),
        enable_global_evaluation=getattr(args, 'enable_global_evaluation', True),
        # 新模块配置
        use_hybrid_outline=getattr(args, 'use_hybrid_outline', True),
        use_global_reflector=getattr(args, 'use_global_reflector', True),
        use_evolutionary_analyzer=getattr(args, 'use_evolutionary_analyzer', True),
        # 自定义上传文件配置
        uploaded_files=getattr(args, 'uploaded_files', []),
        enable_arxiv=getattr(args, 'enable_arxiv', True)
    )
    
    # 打印反思机制配置
    if config.enable_reflection:
        logger.info(f"   🔄 反思机制: 已启用")
        logger.info(f"      - 最大迭代次数: {config.reflection_max_iterations}")
        logger.info(f"      - 质量阈值: {config.reflection_quality_threshold}")
        logger.info(f"      - 全局评估: {'启用' if config.enable_global_evaluation else '禁用'}")
    else:
        logger.info(f"   🔄 反思机制: 已禁用")

    # 打印新模块配置
    logger.info(f"   🚀 增强功能:")
    logger.info(f"      - 混合大纲生成: {'启用' if config.use_hybrid_outline else '禁用'}")
    logger.info(f"      - 全局一致性检查: {'启用' if config.use_global_reflector else '禁用'}")
    logger.info(f"      - 演化叙事分析: {'启用' if config.use_evolutionary_analyzer else '禁用'}")
    
    pipeline = MEKGSurveyPipeline(config)
    
    try:
        # 运行流水线
        if resume_mode:
            logger.info("🔄 从断点恢复执行...")
            result = await pipeline.run(resume=True)
        else:
            logger.info("Step 1-4: Running MEKG Pipeline (Collection -> Graph -> Outline -> Content)")
            result = await pipeline.run()
        
        if not result.success:
            logger.error(f"Pipeline failed: {result.error}")
            return
        
        # Step 5: 编译PDF
        logger.info("\n📄 Step 5: Compiling PDF...")
        try:
            latex_gen = LatexGenerator(task_id=task_id)
            
            # 重新生成 survey.tex，确保使用最新的增强内容（包含图片和表格）
            # 这一步很重要，因为 mainbody_enhanced_multimodal.tex 可能在 Step 8 之后才生成
            logger.info("   📝 Regenerating survey.tex with enhanced content...")
            latex_gen.generate_full_survey()
            
            # 编译 PDF
            latex_gen.compile_single_survey()
            
            pdf_path = task_dir / "survey.pdf"
            if pdf_path.exists():
                logger.info(f"✅ PDF generated successfully: {pdf_path}")
                print(f"\n✨ PDF生成成功: {pdf_path}")
            else:
                logger.error("❌ PDF generation failed (file not found)")

            # 强制启用 evaluation/ 的综合评估（写入 outputs/{task_id}/evaluation/）
            if getattr(args, "run_evaluation", True):
                from evaluation.main import evaluate_survey
                from evaluation.config import EvaluationConfig

                mekg_data_path = task_dir / "mekg" / "mekg_data.json"
                survey_tex_path = task_dir / "latex" / "survey.tex"
                outline_path = task_dir / "outline.json"
                eval_dir = task_dir / "evaluation"

                api_key = getattr(args, "eval_api_key", None)

                # 按用户要求：evaluation 必须启用 LLM
                eval_config = EvaluationConfig(use_llm=True)
                if api_key:
                    eval_config.api_key = api_key

                # 提前 validate，避免跑到一半才报错
                eval_config.validate()

                logger.info(f"🧪 Running evaluation module (use_llm=True) -> {eval_dir}")
                logger.info(f"   - Eval LLM model: {eval_config.advanced_model}")
                logger.info(f"   - Eval API URL: {eval_config.api_url}")
                evaluate_survey(
                    mekg_data_path=mekg_data_path,
                    survey_path=survey_tex_path,
                    outline_path=outline_path if outline_path.exists() else None,
                    output_dir=eval_dir,
                    config=eval_config,
                )
                logger.info(f"✅ Evaluation done: {eval_dir}")

        except Exception as e:
            logger.error(f"❌ PDF compilation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        # 自动更新全局图谱
        try:
            from mekg.src.automation.global_graph_manager import GlobalGraphManager
            logger.info("\n🌐 Updating Global Academic Graph...")
            
            mekg_path = task_dir / "mekg" / "mekg_data.json"
            if mekg_path.exists():
                manager = GlobalGraphManager()
                stats = manager.merge_task_graph(str(mekg_path), args.topic)
                logger.info(f"✅ Global graph updated: {stats}")
            else:
                logger.warning(f"⚠️ MEKG data not found at {mekg_path}, skipping global update")
                
        except Exception as e:
            logger.error(f"❌ Global graph update failed: {e}")
            
        logger.info("=" * 60)
        logger.info("🎉 All steps completed!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    # 检查是否通过命令行运行（是否有参数）
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description="MEKG Survey Generator")
        parser.add_argument("--topic", type=str, help="Survey topic (required for new tasks)")
        parser.add_argument("--max_papers", type=int, default=200, help="Max papers to collect")
        parser.add_argument("--year_start", type=int, default=2020, help="Start year")
        parser.add_argument("--year_end", type=int, default=2026, help="End year")
        parser.add_argument("--enable_critic", action="store_true", default=True, help="Enable outline critic loop")
        parser.add_argument("--enable_refine", action="store_true", default=True, help="Enable content auto-refine")
        parser.add_argument("--no_critic", action="store_false", dest="enable_critic", help="Disable outline critic loop")
        parser.add_argument("--no_refine", action="store_false", dest="enable_refine", help="Disable content auto-refine")
        parser.add_argument("--use-memgraph", action="store_true", help="Use Memgraph as graph database")
        parser.add_argument("--no-memgraph", action="store_false", dest="use_memgraph", help="Disable Memgraph graph database")
        
        # arXiv 搜索控制
        parser.add_argument("--no-arxiv", action="store_false", dest="enable_arxiv", help="Disable arXiv search (use only uploaded files)")
        
        # 增强版收集器参数
        parser.add_argument("--no-enhanced-collector", action="store_false", dest="use_enhanced_collector", help="Disable enhanced paper collector")
        parser.add_argument("--no-survey-strategy", action="store_false", dest="use_survey_strategy", help="Disable survey-first strategy")
        parser.add_argument("--survey-count", type=int, default=10, help="Number of surveys to search")
        parser.add_argument("--max-refs-per-survey", type=int, default=50, help="Max references per survey")
        parser.add_argument("--no-embedding-filter", action="store_false", dest="use_embedding_filter", help="Disable embedding filter")
        parser.add_argument("--embedding-threshold", type=float, default=0.3, help="Embedding similarity threshold")
        
        # 反思机制参数 (P0 优化功能)
        parser.add_argument("--enable-reflection", action="store_true", dest="enable_reflection", help="Enable section-level reflection (default: enabled)")
        parser.add_argument("--no-reflection", action="store_false", dest="enable_reflection", help="Disable section-level reflection")
        parser.add_argument("--reflection-max-iter", type=int, default=3, dest="reflection_max_iterations", help="Max reflection iterations (default: 3)")
        parser.add_argument("--reflection-threshold", type=float, default=3.5, dest="reflection_quality_threshold", help="Reflection quality threshold 1-5 (default: 3.5)")
        parser.add_argument("--no-global-evaluation", action="store_false", dest="enable_global_evaluation", help="Disable global rubric evaluation")
        
        # 新模块参数 (P1/P2 优化功能)
        parser.add_argument("--use-hybrid-outline", action="store_true", dest="use_hybrid_outline", help="Enable hybrid outline generation (default: enabled)")
        parser.add_argument("--no-hybrid-outline", action="store_false", dest="use_hybrid_outline", help="Disable hybrid outline generation")
        parser.add_argument("--use-global-reflector", action="store_true", dest="use_global_reflector", help="Enable global consistency check (default: enabled)")
        parser.add_argument("--no-global-reflector", action="store_false", dest="use_global_reflector", help="Disable global consistency check")
        parser.add_argument("--use-evolutionary-analyzer", action="store_true", dest="use_evolutionary_analyzer", help="Enable evolutionary narrative analysis (default: enabled)")
        parser.add_argument("--no-evolutionary-analyzer", action="store_false", dest="use_evolutionary_analyzer", help="Disable evolutionary narrative analysis")
        
        # 设置默认值
        parser.set_defaults(
            use_memgraph=True,
            use_enhanced_collector=True,
            use_survey_strategy=False,  # 默认关闭 Survey 策略，因为参考文献获取不稳定
            use_embedding_filter=True,
            enable_reflection=True,      # 默认启用反思机制
            enable_global_evaluation=True,  # 默认启用全局评估
            use_hybrid_outline=True,     # 默认启用混合大纲
            use_global_reflector=True,   # 默认启用全局一致性检查
            use_evolutionary_analyzer=True, # 默认启用演化分析
            run_evaluation=True,         # 默认启用 evaluation/
            eval_use_llm=True,           # 默认启用 LLM（且强制启用）
            enable_arxiv=True            # 默认启用 arXiv 搜索
        )
        
        # evaluation/ 综合评估（可选）
        parser.add_argument("--run-evaluation", action="store_true", dest="run_evaluation", help="Run evaluation module after generating LaTeX (default: enabled)")
        parser.add_argument("--no-evaluation", action="store_false", dest="run_evaluation", help="Disable evaluation module")
        parser.add_argument("--eval-use-llm", action="store_true", dest="eval_use_llm", help="Enable LLM in evaluation module (default: enabled, enforced)")
        parser.add_argument("--eval-api-key", type=str, dest="eval_api_key", default=None, help="API key for evaluation module (overrides src/configs/config.py TOKEN / env)")
        
        # 自定义上传文件参数
        parser.add_argument("--uploaded-files", type=str, dest="uploaded_files_json", default=None, help="JSON array of uploaded file paths")
        
        # 断点续传相关参数
        parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
        parser.add_argument("--task_id", type=str, help="Task ID to resume (optional, will find latest if not specified)")
        parser.add_argument("--list-tasks", action="store_true", help="List all resumable tasks")
        
        args = parser.parse_args()
        
        # 解析上传的文件列表
        if args.uploaded_files_json:
            try:
                args.uploaded_files = json.loads(args.uploaded_files_json)
                print(f"📂 收到 {len(args.uploaded_files)} 个上传的文件")
            except json.JSONDecodeError as e:
                print(f"⚠️ 解析上传文件列表失败: {e}")
                args.uploaded_files = []
        else:
            args.uploaded_files = []
        
        # 列出可恢复的任务
        if args.list_tasks:
            print("\n📋 可恢复的任务列表 (72小时内):\n")
            resumable = list_resumable_tasks()
            if resumable:
                for i, task in enumerate(resumable[:20], 1):
                    print(f"  {i}. {task['task_id']}")
                    print(f"     主题: {task['topic']}")
                    print(f"     进度: {task['step']}")
                    print(f"     时间: {task['hours_ago']} 小时前")
                    print()
            else:
                print("  (无可恢复的任务)")
            return
        
        # 恢复模式下，如果指定了task_id，从配置文件读取topic
        if args.resume and args.task_id and not args.topic:
            config_path = Path(BASE_DIR) / "outputs" / args.task_id / "task_config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                args.topic = config.get("topic", "")
        
        # 验证必要参数
        if not args.topic and not args.resume:
            parser.error("--topic is required for new tasks")
    else:
        # 直接运行模式：使用默认配置
        # 创建一个简单的对象来模拟 args
        class Args:
            pass
        args = Args()
        args.topic = DEFAULT_CONFIG["topic"]
        args.max_papers = DEFAULT_CONFIG["max_papers"]
        args.year_start = DEFAULT_CONFIG["year_start"]
        args.year_end = DEFAULT_CONFIG["year_end"]
        args.enable_critic = DEFAULT_CONFIG["enable_critic"]
        args.enable_refine = DEFAULT_CONFIG["enable_refine"]
        args.use_memgraph = DEFAULT_CONFIG["use_memgraph"]
        args.use_enhanced_collector = DEFAULT_CONFIG["use_enhanced_collector"]
        args.use_survey_strategy = DEFAULT_CONFIG["use_survey_strategy"]
        args.survey_count = DEFAULT_CONFIG["survey_count"]
        args.max_refs_per_survey = DEFAULT_CONFIG["max_refs_per_survey"]
        args.use_embedding_filter = DEFAULT_CONFIG["use_embedding_filter"]
        args.embedding_threshold = DEFAULT_CONFIG["embedding_threshold"]
        args.enable_reflection = DEFAULT_CONFIG["enable_reflection"]
        args.reflection_max_iterations = DEFAULT_CONFIG["reflection_max_iterations"]
        args.reflection_quality_threshold = DEFAULT_CONFIG["reflection_quality_threshold"]
        args.enable_global_evaluation = DEFAULT_CONFIG["enable_global_evaluation"]
        args.use_hybrid_outline = DEFAULT_CONFIG["use_hybrid_outline"]
        args.use_global_reflector = DEFAULT_CONFIG["use_global_reflector"]
        args.use_evolutionary_analyzer = DEFAULT_CONFIG["use_evolutionary_analyzer"]
        args.task_id = None
        args.run_evaluation = True
        args.eval_use_llm = True
        args.eval_api_key = None
        args.uploaded_files = []
        args.enable_arxiv = True
        
        # 自动检测是否有可恢复的任务
        latest_task = find_latest_task_for_topic(args.topic)
        if latest_task:
            # 检查该任务是否已完成
            checkpoint_path = Path(BASE_DIR) / "outputs" / latest_task / "checkpoint.json"
            if checkpoint_path.exists():
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    checkpoint = json.load(f)
                
                step_value = checkpoint.get("step", 0)
                step_name = checkpoint.get("step_name", "Unknown")
                
                # 如果任务未完成（step < COMPLETED），自动恢复
                if step_value < PipelineStep.COMPLETED.value:
                    print(f"🔄 检测到未完成的任务: {latest_task}")
                    print(f"   当前进度: {step_name}")
                    print(f"   自动从断点恢复...")
                    args.resume = True
                    args.task_id = latest_task
                else:
                    print("⚠️ 未检测到命令行参数，使用默认配置运行...")
                    print(f"   Topic: {DEFAULT_CONFIG['topic']}")
                    print(f"   Max Papers: {DEFAULT_CONFIG['max_papers']}")
                    args.resume = False
            else:
                print("⚠️ 未检测到命令行参数，使用默认配置运行...")
                print(f"   Topic: {DEFAULT_CONFIG['topic']}")
                print(f"   Max Papers: {DEFAULT_CONFIG['max_papers']}")
                args.resume = False
        else:
            print("⚠️ 未检测到命令行参数，使用默认配置运行...")
            print(f"   Topic: {DEFAULT_CONFIG['topic']}")
            print(f"   Max Papers: {DEFAULT_CONFIG['max_papers']}")
            args.resume = False
    
    import asyncio
    asyncio.run(run_mekg_pipeline(args))

if __name__ == "__main__":
    main()
