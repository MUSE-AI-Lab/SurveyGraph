"""
SurveyGraph Frontend - FastAPI 主入口
======================================

启动命令:
    python main.py
    
或使用 uvicorn:
    uvicorn main:app --host 0.0.0.0 --port 8080 --reload
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

sys.path.insert(0, str(Path(__file__).parent))

from config import AppConfig, LogConfig, init_config


# ==========================================
# Windows ConnectionResetError 日志过滤器
# ==========================================
class ConnectionResetFilter(logging.Filter):
    """
    过滤 Windows 上的 ConnectionResetError 日志。
    
    这个错误在 Windows + asyncio ProactorEventLoop 上是常见的,
    当客户端(浏览器)在服务器关闭连接之前就断开时会发生。
    这是无害的,不影响应用程序功能。
    """
    def filter(self, record: logging.LogRecord) -> bool:
        # 过滤掉包含 ConnectionResetError 和 WinError 10054 的日志
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type and issubclass(exc_type, ConnectionResetError):
                return False
        
        # 也过滤掉消息中包含这些关键词的日志
        msg = str(record.getMessage()) if record.msg else ""
        if "ConnectionResetError" in msg or "WinError 10054" in msg:
            return False
        if "_ProactorBasePipeTransport" in msg and "connection_lost" in msg:
            return False
            
        return True


# 在 Windows 上应用过滤器
if sys.platform == "win32":
    # 为 asyncio 日志器添加过滤器
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.addFilter(ConnectionResetFilter())
from core.database import init_db, close_db
from api import api_router
from api.websocket import router as websocket_router

# 确保日志目录存在（在配置日志之前）
LogConfig.LOG_DIR.mkdir(parents=True, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=getattr(logging, LogConfig.LOG_LEVEL),
    format=LogConfig.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LogConfig.LOG_DIR / "app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("=" * 60)
    logger.info(f"[START] Starting {AppConfig.APP_NAME} v{AppConfig.APP_VERSION}")
    logger.info("=" * 60)
    
    # 初始化配置
    init_config()
    
    # 初始化数据库
    await init_db()
    logger.info("[OK] Database initialized")
    
    # 恢复运行中任务的监控
    try:
        from services.pipeline_service import recover_running_tasks
        await recover_running_tasks()
        logger.info("[OK] Running task monitors recovered")
    except Exception as e:
        logger.error(f"[WARN] Failed to recover task monitors: {e}")
    
    yield
    
    # 关闭时
    logger.info("Shutting down...")
    await close_db()
    logger.info("[OK] Database connection closed")


# 创建 FastAPI 应用
app = FastAPI(
    title=AppConfig.APP_NAME,
    version=AppConfig.APP_VERSION,
    description="SurveyGraph - AI 驱动的学术综述自动生成系统",
    lifespan=lifespan,
    docs_url="/api/docs" if AppConfig.DEBUG else None,
    redoc_url="/api/redoc" if AppConfig.DEBUG else None,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=AppConfig.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 模板
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# 注册 API 路由
app.include_router(api_router, prefix="/api")

# 注册 WebSocket 路由（添加 /api 前缀以匹配前端请求）
app.include_router(websocket_router, prefix="/api")


# ==========================================
# 页面路由
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页 - 官网宣传页"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, invite: str = None):
    """注册页面"""
    return templates.TemplateResponse("register.html", {
        "request": request,
        "invite_code": invite
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """用户仪表盘"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/task/new", response_class=HTMLResponse)
async def new_task_page(request: Request):
    """创建任务页面"""
    return templates.TemplateResponse("task_new.html", {"request": request})


@app.get("/tasks/new", response_class=HTMLResponse)
async def new_task_page_alt(request: Request):
    """创建任务页面（兼容路由）"""
    return templates.TemplateResponse("task_new.html", {"request": request})


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """个人设置页面"""
    return templates.TemplateResponse("profile.html", {"request": request})


@app.get("/knowledge-base", response_class=HTMLResponse)
async def knowledge_base_page(request: Request):
    """个人知识库页面"""
    return templates.TemplateResponse("knowledge_base.html", {"request": request})


@app.get("/task/{task_id}", response_class=HTMLResponse)
async def task_detail_page(request: Request, task_id: str):
    """任务详情页面"""
    return templates.TemplateResponse("task_detail.html", {
        "request": request,
        "task_id": task_id
    })


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail_page_alt(request: Request, task_id: str):
    """任务详情页面（兼容路由）"""
    return templates.TemplateResponse("task_detail.html", {
        "request": request,
        "task_id": task_id
    })


@app.get("/task/{task_id}/results", response_class=HTMLResponse)
async def task_results_page(request: Request, task_id: str):
    """任务结果页面"""
    return templates.TemplateResponse("task_results.html", {
        "request": request,
        "task_id": task_id
    })


@app.get("/tasks/{task_id}/results", response_class=HTMLResponse)
async def task_results_page_alt(request: Request, task_id: str):
    """任务结果页面（兼容路由）"""
    return templates.TemplateResponse("task_results.html", {
        "request": request,
        "task_id": task_id
    })


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request):
    """管理员仪表盘"""
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    """管理员 - 用户管理"""
    return templates.TemplateResponse("admin/users.html", {"request": request})


@app.get("/admin/tasks", response_class=HTMLResponse)
async def admin_tasks_page(request: Request):
    """管理员 - 任务管理"""
    return templates.TemplateResponse("admin/tasks.html", {"request": request})


# ==========================================
# 健康检查
# ==========================================

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "app": AppConfig.APP_NAME,
        "version": AppConfig.APP_VERSION
    }


# ==========================================
# 启动入口
# ==========================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=AppConfig.HOST,
        port=AppConfig.PORT,
        reload=AppConfig.DEBUG,
        log_level="info"
    )
