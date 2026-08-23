"""
SurveyGraph Frontend - 配置文件
================================

包含所有配置项，支持环境变量覆盖。
"""

import os
import secrets
from pathlib import Path
from typing import Optional

# 基础路径
BASE_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = BASE_DIR.parent  # SurveyGraph 根目录

# ==========================================
# 数据库配置
# ==========================================
class DatabaseConfig:
    """MySQL 数据库配置"""
    HOST: str = os.getenv("DB_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("DB_PORT", "3306"))
    USER: str = os.getenv("DB_USER", "surveygraph")
    PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DATABASE: str = os.getenv("DB_NAME", "surveygraph")
    
    # 连接池配置
    POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN", "5"))
    POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX", "20"))
    
    @classmethod
    def get_dsn(cls) -> str:
        """获取数据库连接字符串"""
        return f"mysql://{cls.USER}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.DATABASE}"


# ==========================================
# JWT 认证配置
# ==========================================
class JWTConfig:
    """JWT 认证配置"""
    # A process-local fallback keeps development imports usable without publishing a shared secret.
    SECRET_KEY: str = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "43200"))  # 30天 (30*24*60=43200分钟)
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_DAYS", "30"))  # 30天


# ==========================================
# 应用配置
# ==========================================
class AppConfig:
    """应用配置"""
    # 基本信息
    APP_NAME: str = "SurveyGraph"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # 服务器配置
    HOST: str = os.getenv("APP_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("APP_PORT", "8065"))
    
    # CORS 配置
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")
    
    # 文件上传配置
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: set = {"pdf", "md", "markdown", "txt"}
    
    # 输出目录 (mekg_run.py 的输出)
    OUTPUT_DIR: Path = PROJECT_ROOT / "outputs"
    
    # 共享 PDF 库目录
    # 默认为 D:/SurveyGraphPdfs，如果不存在则使用项目内的 shared_pdfs
    SHARED_PDF_DIR: Path = Path(os.getenv("SHARED_PDF_DIR", "D:/SurveyGraphPdfs"))
    
    @classmethod
    def ensure_dirs(cls):
        """确保必要的目录存在"""
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # 尝试创建共享 PDF 目录
        try:
            cls.SHARED_PDF_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # 如果无法创建（例如权限问题），回退到项目内目录
            print(f"Warning: Failed to create shared PDF dir {cls.SHARED_PDF_DIR}: {e}")
            cls.SHARED_PDF_DIR = PROJECT_ROOT / "shared_pdfs"
            cls.SHARED_PDF_DIR.mkdir(parents=True, exist_ok=True)
            print(f"Using fallback shared PDF dir: {cls.SHARED_PDF_DIR}")


# ==========================================
# 任务配置
# ==========================================
class TaskConfig:
    """任务相关配置"""
    # 用户配额
    DEFAULT_DAILY_QUOTA: int = int(os.getenv("DEFAULT_DAILY_QUOTA", "3"))  # 每日默认生成次数
    MAX_RETRY_PER_DAY: int = int(os.getenv("MAX_RETRY_PER_DAY", "5"))    # 每篇综述每日最多重试次数
    INVITE_BONUS_QUOTA: int = int(os.getenv("INVITE_BONUS_QUOTA", "1"))   # 邀请奖励的永久次数
    
    # 检查点有效期 (小时)
    CHECKPOINT_VALIDITY_HOURS: int = 72
    
    # Pipeline 步骤定义 (与 mekg/src/survey/pipeline.py 保持一致)
    PIPELINE_STEPS = {
        0: {"name": "NOT_STARTED", "label": "未开始", "description": "任务尚未开始"},
        1: {"name": "MEKG_BUILT", "label": "MEKG构建", "description": "论文采集与图谱构建"},
        2: {"name": "OUTLINE_GENERATED", "label": "大纲生成", "description": "生成综述大纲"},
        3: {"name": "CONTENT_GENERATED", "label": "内容生成", "description": "生成Survey主体内容"},
        4: {"name": "POST_REFINED", "label": "文本优化", "description": "PostRefiner文本优化"},
        5: {"name": "TABLES_GENERATED", "label": "表格生成", "description": "生成表格"},
        6: {"name": "VISUALS_GENERATED", "label": "视觉元素", "description": "生成动态视觉元素"},
        7: {"name": "EVALUATED", "label": "质量评估", "description": "质量评估与全局反思"},
        8: {"name": "CRITICAL_ANALYZED", "label": "批判分析", "description": "批判性分析增强"},
        9: {"name": "LATEX_GENERATED", "label": "LaTeX生成", "description": "生成LaTeX文档"},
        10: {"name": "VISUALIZATION_DONE", "label": "可视化导出", "description": "导出可视化数据"},
        11: {"name": "COMPLETED", "label": "已完成", "description": "任务完成"},
    }
    
    # 默认 Pipeline 参数
    DEFAULT_PIPELINE_CONFIG = {
        # 论文采集配置
        "max_papers": 200,
        "year_start": 2020,
        "year_end": 2026,
        "use_enhanced_collector": True,
        "use_survey_strategy": False,
        "survey_count": 10,
        "max_refs_per_survey": 50,
        "use_embedding_filter": True,
        "embedding_threshold": 0.3,
        "use_openalex": False,
        "download_pdf": True,
        "extract_paper_attri": True,
        
        # 图谱构建配置
        "use_llm_relations": True,
        "max_relation_pairs": 500,
        "use_memgraph": True,
        
        # 相关性过滤配置
        "enable_relevance_filter": True,
        "relevance_threshold": 0.2,
        "use_llm_relevance": True,
        "llm_relevance_threshold": 0.5,
        
        # 内容生成配置
        "enable_critic": True,
        "enable_refine": True,
        "enable_reflection": True,
        "reflection_max_iterations": 3,
        "reflection_quality_threshold": 3.5,
        "enable_global_evaluation": True,
        
        # 新模块配置
        "use_hybrid_outline": True,
        "use_global_reflector": True,
        "use_evolutionary_analyzer": True,
        
        # 批判性分析配置
        "enable_critical_analysis": True,
        "critical_analysis_auto_enhance": True,
        
        # 输出配置
        "generate_latex": True,
        "generate_visualization": True,
        "run_evaluation": True,
    }


# ==========================================
# Section Rewriter 配置
# ==========================================
class SectionRewriterConfig:
    """Section Rewriter 压缩配置"""
    # 压缩比例阈值
    MIN_COMPRESSION_RATIO: float = float(os.getenv("COMPRESSION_MIN_RATIO", "0.50"))  # 压缩后至少保留50%的内容
    TARGET_COMPRESSION_RATIO: float = float(os.getenv("COMPRESSION_TARGET_RATIO", "0.70"))  # 目标压缩比例：保留70%的内容
    MAX_RETRY_ATTEMPTS: int = int(os.getenv("COMPRESSION_MAX_RETRY", "2"))  # 最大重试次数
    
    # 内容长度阈值：超过此长度的内容需要分块处理
    MAX_SECTION_WORDS: int = int(os.getenv("COMPRESSION_MAX_SECTION_WORDS", "15000"))  # 单个 section 最大词数


# ==========================================
# 日志配置
# ==========================================
class LogConfig:
    """日志配置"""
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DIR: Path = BASE_DIR / "logs"
    
    @classmethod
    def ensure_dirs(cls):
        """确保日志目录存在"""
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 初始化
# ==========================================
def init_config():
    """初始化配置，确保必要的目录存在"""
    AppConfig.ensure_dirs()
    LogConfig.ensure_dirs()


# 导出配置类
__all__ = [
    "BASE_DIR",
    "PROJECT_ROOT",
    "DatabaseConfig",
    "JWTConfig",
    "AppConfig",
    "TaskConfig",
    "SectionRewriterConfig",
    "LogConfig",
    "init_config",
]
