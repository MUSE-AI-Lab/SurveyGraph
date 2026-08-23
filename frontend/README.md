# SurveyGraph Frontend

AI 综述生成平台前端系统

## 功能特性

### 用户功能
- 📝 **综述生成**: 输入研究主题和关键词，自动生成学术综述
- 📊 **知识图谱**: 可视化展示文献关系网络
- 📄 **多格式输出**: 支持 PDF、Markdown 格式下载
- 📈 **评估报告**: 自动生成综述质量评估报告
- 🔄 **断点续传**: 支持从任意步骤重试任务
- ✏️ **大纲编辑**: 可自定义修改生成的大纲结构

### 管理功能
- 👥 **用户管理**: 管理用户账户、配额、权限
- 📋 **任务管理**: 查看所有任务状态和详细日志
- 📊 **系统统计**: 实时监控系统运行状态

### 配额系统
- 每日配额: 每个用户每天可生成 1 篇综述
- 邀请奖励: 邀请好友注册，双方各得 1 次额外配额
- 重试限制: 每篇综述每天最多重试 5 次

## 技术栈

### 后端
- **FastAPI**: 高性能异步 Web 框架
- **aiomysql**: 异步 MySQL 驱动
- **JWT**: 用户认证
- **WebSocket**: 实时进度推送

### 前端
- **原生 JavaScript**: 无框架依赖，轻量快速
- **ECharts**: 知识图谱可视化
- **Marked.js**: Markdown 渲染

## 快速开始

### 1. 安装依赖

```bash
cd frontend
pip install -r requirements.txt
```

### 2. 配置数据库

数据库配置通过环境变量注入，仓库不提供共享数据库或默认密码：
- `DB_HOST`（默认 `127.0.0.1`）
- `DB_PORT`（默认 `3306`）
- `DB_NAME`、`DB_USER`、`DB_PASSWORD`
- `JWT_SECRET`（生产环境必须显式设置）

### 3. 启动服务

```bash
# 开发模式（自动重载）
python run.py --reload

# 生产模式
python run.py --host 0.0.0.0 --port 8080 --workers 4
```

### 4. 访问系统

打开浏览器访问: http://localhost:8080

## 项目结构

```
frontend/
├── __init__.py          # 包初始化
├── config.py            # 配置文件
├── main.py              # FastAPI 应用入口
├── run.py               # 启动脚本
├── requirements.txt     # Python 依赖
├── README.md            # 说明文档
├── DESIGN.md            # 设计文档
│
├── api/                 # API 路由
│   ├── __init__.py
│   ├── auth.py          # 认证 API
│   ├── users.py         # 用户 API
│   ├── tasks.py         # 任务 API
│   ├── admin.py         # 管理员 API
│   └── websocket.py     # WebSocket
│
├── core/                # 核心模块
│   ├── __init__.py
│   ├── database.py      # 数据库连接
│   ├── models.py        # 数据模型
│   └── security.py      # 安全认证
│
├── services/            # 业务服务
│   ├── __init__.py
│   ├── task_service.py  # 任务服务
│   └── pipeline_service.py  # Pipeline 服务
│
├── static/              # 静态资源
│   ├── css/
│   │   └── style.css    # 样式表
│   └── js/
│       ├── api.js       # API 客户端
│       ├── components.js # UI 组件
│       └── app.js       # 应用逻辑
│
└── templates/           # HTML 模板
    ├── index.html       # 主页面
    ├── base.html        # 基础模板
    └── login.html       # 登录页面
```

## API 文档

启动服务后访问:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## 主要 API 端点

### 认证
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/refresh` - 刷新令牌

### 用户
- `GET /api/users/me` - 获取当前用户信息
- `GET /api/users/quota` - 获取配额信息
- `GET /api/users/invite-code` - 获取邀请码

### 任务
- `GET /api/tasks` - 获取任务列表
- `POST /api/tasks` - 创建任务
- `GET /api/tasks/{id}` - 获取任务详情
- `POST /api/tasks/{id}/retry` - 重试任务
- `GET /api/tasks/{id}/results` - 获取任务结果

### 管理员
- `GET /api/admin/users` - 获取所有用户
- `GET /api/admin/tasks` - 获取所有任务
- `GET /api/admin/stats` - 获取系统统计

## 配置说明

### 数据库配置
```python
class DatabaseConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "surveygraph"
    password: str = ""
    database: str = "surveygraph"
```

### JWT 配置
```python
class JWTConfig:
    secret_key: str = "从 JWT_SECRET 环境变量读取"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
```

### 任务配置
```python
class TaskConfig:
    daily_quota: int = 1           # 每日配额
    max_retry_per_day: int = 5     # 每日最大重试次数
    checkpoint_expire_hours: int = 72  # 检查点过期时间
```

## 开发说明

### 添加新的 API 端点

1. 在 `api/` 目录下创建或修改路由文件
2. 在 `api/__init__.py` 中注册路由
3. 如需新的数据模型，在 `core/models.py` 中添加

### 添加新的前端页面

1. 在 `static/js/app.js` 中添加页面渲染函数
2. 在路由注册部分添加新路由
3. 如需新的 UI 组件，在 `static/js/components.js` 中添加

### 数据库迁移

首次运行时会自动创建所需的数据库表。如需修改表结构：

1. 修改 `core/database.py` 中的建表 SQL
2. 手动执行数据库迁移或删除重建表

## 注意事项

1. **安全性**: 生产环境请修改 JWT 密钥
2. **数据库**: 确保 MySQL 服务可访问
3. **文件上传**: 上传的文件存储在 `uploads/` 目录
4. **日志**: 任务日志存储在数据库中

## License

MIT License
