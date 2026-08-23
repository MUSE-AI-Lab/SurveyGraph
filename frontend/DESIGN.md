# SurveyGraph 前端系统设计文档

## 项目概述

为 `mekg_run.py` 设计一个现代化的 Web 前端系统，提供简洁、轻快、人性化的用户体验。

### 核心特点
- **白色背景 + 简洁设计**：类似 ChatGPT 的现代 UI 风格
- **全面的参数自定义**：支持 mekg_run.py 的所有参数配置
- **任意断点重试**：用户可从任意 checkpoint 处重新开始
- **大纲编辑**：用户可自行修改生成的大纲结构
- **进度可视化**：实时显示任务进度，区分用户/管理员视图
- **结果展示**：知识图谱、PDF、Markdown、评测报告一站式查看

---

## 技术选型

### 后端
- **框架**: FastAPI (异步支持，与现有 mekg 代码兼容)
- **数据库**: MySQL (aiomysql 异步驱动)
- **认证**: JWT Token
- **任务队列**: 内置异步任务管理 (基于 asyncio)
- **WebSocket**: 实时进度推送

### 前端
- **框架**: 原生 HTML/CSS/JavaScript (保持轻量)
- **UI 风格**: 白色背景、圆角卡片、柔和阴影
- **图表**: ECharts (知识图谱可视化)
- **PDF 渲染**: PDF.js
- **Markdown 渲染**: marked.js + highlight.js

---

## 数据库设计

### 用户表 (users)
```sql
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('user', 'admin') DEFAULT 'user',
    daily_quota INT DEFAULT 1,           -- 每日生成次数
    bonus_quota INT DEFAULT 0,           -- 邀请获得的永久次数
    invite_code VARCHAR(20) UNIQUE,      -- 用户的邀请码
    invited_by INT,                       -- 邀请人ID
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (invited_by) REFERENCES users(id)
);
```

### 任务表 (tasks)
```sql
CREATE TABLE tasks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    task_id VARCHAR(100) UNIQUE NOT NULL,  -- 如 "2025-12-17-2206_Large_Language_Model"
    user_id INT NOT NULL,
    topic VARCHAR(500) NOT NULL,
    keywords TEXT,                          -- JSON 格式的关键词列表
    status ENUM('pending', 'running', 'paused', 'completed', 'failed') DEFAULT 'pending',
    current_step INT DEFAULT 0,             -- 当前步骤 (PipelineStep 枚举值)
    current_step_name VARCHAR(50),          -- 当前步骤名称
    progress_percent INT DEFAULT 0,         -- 进度百分比
    
    -- 配置参数 (JSON 格式存储所有参数)
    config JSON,
    
    -- 用户上传的文档
    uploaded_files JSON,                    -- [{filename, path, type}]
    enable_arxiv_search BOOLEAN DEFAULT TRUE,
    
    -- 结果路径
    output_dir VARCHAR(500),
    mekg_data_path VARCHAR(500),
    outline_path VARCHAR(500),
    pdf_path VARCHAR(500),
    evaluation_path VARCHAR(500),
    visualization_path VARCHAR(500),
    
    -- 统计信息
    papers_count INT DEFAULT 0,
    relations_count INT DEFAULT 0,
    sections_count INT DEFAULT 0,
    
    -- 重试信息
    retry_count INT DEFAULT 0,              -- 当日重试次数
    last_retry_date DATE,                   -- 最后重试日期
    
    -- 错误信息
    error_message TEXT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at DATETIME,
    
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 任务日志表 (task_logs)
```sql
CREATE TABLE task_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    task_id INT NOT NULL,
    step INT NOT NULL,                      -- PipelineStep 枚举值
    step_name VARCHAR(50),
    level ENUM('info', 'warning', 'error', 'debug') DEFAULT 'info',
    message TEXT,
    details JSON,                           -- 详细信息 (仅管理员可见)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
```

### 邀请记录表 (invitations)
```sql
CREATE TABLE invitations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    inviter_id INT NOT NULL,
    invitee_id INT NOT NULL,
    invite_code VARCHAR(20) NOT NULL,
    bonus_granted BOOLEAN DEFAULT FALSE,    -- 是否已发放奖励
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inviter_id) REFERENCES users(id),
    FOREIGN KEY (invitee_id) REFERENCES users(id)
);
```

---

## API 设计

### 认证相关
```
POST /api/auth/register          - 用户注册
POST /api/auth/login             - 用户登录
POST /api/auth/logout            - 用户登出
GET  /api/auth/me                - 获取当前用户信息
POST /api/auth/refresh           - 刷新 Token
```

### 用户相关
```
GET  /api/user/quota             - 获取用户配额信息
GET  /api/user/invite-code       - 获取邀请码
POST /api/user/apply-invite      - 使用邀请码
```

### 任务相关
```
POST /api/tasks                  - 创建新任务
GET  /api/tasks                  - 获取任务列表
GET  /api/tasks/{task_id}        - 获取任务详情
DELETE /api/tasks/{task_id}      - 删除任务

POST /api/tasks/{task_id}/start  - 启动任务
POST /api/tasks/{task_id}/pause  - 暂停任务
POST /api/tasks/{task_id}/retry  - 重试任务 (可指定从哪个步骤开始)
POST /api/tasks/{task_id}/cancel - 取消任务

GET  /api/tasks/{task_id}/logs   - 获取任务日志 (用户看简化版，管理员看详细版)
GET  /api/tasks/{task_id}/progress - 获取任务进度

PUT  /api/tasks/{task_id}/outline - 更新大纲
GET  /api/tasks/{task_id}/outline - 获取大纲
```

### 结果相关
```
GET  /api/tasks/{task_id}/mekg           - 获取知识图谱数据
GET  /api/tasks/{task_id}/pdf            - 下载 PDF
GET  /api/tasks/{task_id}/markdown       - 获取 Markdown 内容
GET  /api/tasks/{task_id}/evaluation     - 获取评测报告
GET  /api/tasks/{task_id}/visualization  - 获取可视化数据
```

### 文件上传
```
POST /api/upload                 - 上传文档 (PDF/MD)
DELETE /api/upload/{file_id}     - 删除已上传文件
```

### 管理员相关
```
GET  /api/admin/users            - 获取所有用户
GET  /api/admin/tasks            - 获取所有任务
GET  /api/admin/tasks/{task_id}/logs - 获取详细日志
PUT  /api/admin/users/{user_id}  - 修改用户信息
```

### WebSocket
```
WS /ws/tasks/{task_id}           - 实时任务进度推送
```

---

## 页面设计

### 1. 登录/注册页面 (`/login`, `/register`)
- 简洁的白色卡片居中布局
- 支持邀请码注册
- 记住登录状态

### 2. 用户仪表盘 (`/dashboard`)
- 顶部：用户信息、配额显示、邀请码
- 主体：任务列表卡片
  - 每个任务显示：主题、状态、进度条、创建时间
  - 快捷操作：查看、重试、删除
- 右侧/底部：快速创建新任务入口

### 3. 创建任务页面 (`/tasks/new`)
**分步骤表单设计：**

#### Step 1: 基本信息
- Topic (主题) - 必填
- Keywords (关键词) - 可选，逗号分隔

#### Step 2: 文档来源
- 上传自己的文档 (PDF/MD) - 拖拽上传
- 是否开启 arXiv 搜索补充
- 提示：如果不开启 arXiv 搜索，必须上传文档

#### Step 3: 高级参数 (可折叠)
```
论文采集配置:
├── max_papers: 最大论文数 (默认 200)
├── year_start: 起始年份 (默认 2020)
├── year_end: 结束年份 (默认 2026)
├── use_enhanced_collector: 使用增强收集器 (默认开启)
├── use_survey_strategy: Survey优先策略 (默认关闭)
├── use_embedding_filter: Embedding筛选 (默认开启)
├── embedding_threshold: Embedding阈值 (默认 0.3)
├── download_pdf: 下载PDF解析 (默认开启)
└── extract_paper_attri: LLM提取论文属性 (默认开启)

内容生成配置:
├── enable_critic: 大纲批判循环 (默认开启)
├── enable_refine: 内容自动优化 (默认开启)
├── enable_reflection: 章节级反思 (默认开启)
├── reflection_max_iterations: 反思最大迭代 (默认 3)
├── reflection_quality_threshold: 反思质量阈值 (默认 3.5)
├── use_hybrid_outline: 混合大纲生成 (默认开启)
├── use_global_reflector: 全局一致性检查 (默认开启)
├── use_evolutionary_analyzer: 演化叙事分析 (默认开启)
└── enable_critical_analysis: 批判性分析增强 (默认开启)

图谱配置:
├── use_llm_relations: LLM关系发现 (默认开启)
├── max_relation_pairs: 最大关系对数 (默认 500)
└── use_memgraph: 使用Memgraph (默认开启)

输出配置:
├── generate_latex: 生成LaTeX (默认开启)
├── generate_visualization: 生成可视化 (默认开启)
└── run_evaluation: 运行评测 (默认开启)
```

#### Step 4: 确认并提交
- 显示配置摘要
- 提交按钮

### 4. 任务详情页面 (`/tasks/{task_id}`)

#### 4.1 进度面板
- 步骤进度条 (11个步骤)
```
1. MEKG构建 → 2. 大纲生成 → 3. 内容生成 → 4. 文本优化 → 
5. 表格生成 → 6. 视觉元素 → 7. 质量评估 → 7.5. 批判分析 → 
8. LaTeX生成 → 9. 可视化导出 → 10. 完成
```
- 当前步骤高亮
- 每个步骤可点击查看详情

#### 4.2 日志面板
- **用户视图**：简化日志
  - 只显示主要步骤的开始/完成信息
  - 隐藏详细的技术日志
- **管理员视图**：完整日志
  - 显示所有级别的日志
  - 可按级别筛选 (info/warning/error/debug)

#### 4.3 操作面板
- 暂停/继续按钮
- 重试按钮 (可选择从哪个步骤开始)
- 取消按钮
- 重试次数显示 (每日最多5次)

#### 4.4 大纲编辑面板 (任务完成大纲生成后可用)
- 树形结构展示大纲
- 支持拖拽调整顺序
- 支持编辑标题和描述
- 保存后可从大纲生成步骤重新开始

### 5. 结果查看页面 (`/tasks/{task_id}/results`)

#### Tab 1: 知识图谱
- 复用 `mekg/src/visualization` 的可视化组件
- 交互式图谱浏览
- 节点详情面板

#### Tab 2: 论文预览
- PDF 在线预览 (PDF.js)
- 一键下载按钮
- Markdown 渲染预览
- 一键下载 Markdown

#### Tab 3: 评测报告
- 评测分数雷达图
- 各维度详细评分
- 改进建议列表

### 6. 管理员后台 (`/admin`)

#### 6.1 用户管理
- 用户列表表格
- 搜索/筛选
- 编辑用户配额
- 查看用户任务

#### 6.2 任务管理
- 所有任务列表
- 按状态筛选
- 查看任务详细日志
- 强制重试/取消任务

#### 6.3 系统监控
- 活跃任务数
- 今日生成数
- 系统资源使用

---

## 文件结构

```
frontend/
├── DESIGN.md                    # 本设计文档
├── requirements.txt             # Python 依赖
├── main.py                      # FastAPI 入口
├── config.py                    # 配置文件
│
├── api/                         # API 路由
│   ├── __init__.py
│   ├── auth.py                  # 认证相关
│   ├── users.py                 # 用户相关
│   ├── tasks.py                 # 任务相关
│   ├── admin.py                 # 管理员相关
│   └── websocket.py             # WebSocket
│
├── core/                        # 核心模块
│   ├── __init__.py
│   ├── database.py              # 数据库连接
│   ├── models.py                # 数据模型
│   ├── security.py              # 安全相关
│   └── task_manager.py          # 任务管理器
│
├── services/                    # 业务服务
│   ├── __init__.py
│   ├── user_service.py
│   ├── task_service.py
│   └── pipeline_service.py      # 调用 mekg_run.py
│
├── static/                      # 静态文件
│   ├── css/
│   │   └── style.css            # 主样式文件
│   ├── js/
│   │   ├── app.js               # 主应用逻辑
│   │   ├── api.js               # API 调用封装
│   │   ├── components.js        # UI 组件
│   │   └── visualization.js     # 可视化相关
│   └── images/
│       └── logo.svg
│
├── templates/                   # HTML 模板
│   ├── base.html                # 基础模板
│   ├── login.html               # 登录页
│   ├── register.html            # 注册页
│   ├── dashboard.html           # 仪表盘
│   ├── task_new.html            # 创建任务
│   ├── task_detail.html         # 任务详情
│   ├── task_results.html        # 结果查看
│   └── admin/
│       ├── dashboard.html       # 管理员仪表盘
│       ├── users.html           # 用户管理
│       └── tasks.html           # 任务管理
│
└── utils/                       # 工具函数
    ├── __init__.py
    └── helpers.py
```

---

## UI 设计规范

### 颜色系统
```css
:root {
    /* 主色调 - 白色背景 */
    --bg-primary: #ffffff;
    --bg-secondary: #f9fafb;
    --bg-tertiary: #f3f4f6;
    
    /* 文字颜色 */
    --text-primary: #111827;
    --text-secondary: #4b5563;
    --text-muted: #9ca3af;
    
    /* 强调色 */
    --accent-primary: #2563eb;      /* 蓝色 - 主要操作 */
    --accent-success: #10b981;      /* 绿色 - 成功 */
    --accent-warning: #f59e0b;      /* 橙色 - 警告 */
    --accent-error: #ef4444;        /* 红色 - 错误 */
    
    /* 边框和阴影 */
    --border-color: #e5e7eb;
    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
    --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.07);
    --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);
    
    /* 圆角 */
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 16px;
}
```

### 组件样式
- **卡片**: 白色背景 + 细边框 + 柔和阴影
- **按钮**: 圆角 + 渐变/纯色 + hover 效果
- **输入框**: 简洁边框 + focus 高亮
- **进度条**: 渐变色 + 动画效果

---

## 实现优先级

### Phase 1: 核心功能 (MVP)
1. 用户注册/登录
2. 创建任务 (基本参数)
3. 任务列表和进度查看
4. 结果下载 (PDF)

### Phase 2: 增强功能
1. 完整参数配置
2. 大纲编辑
3. 断点重试
4. 知识图谱可视化
5. 评测报告展示

### Phase 3: 高级功能
1. 管理员后台
2. 邀请系统
3. 文档上传
4. WebSocket 实时进度
5. Markdown 预览

---

## 安全考虑

1. **密码安全**: bcrypt 加密存储
2. **JWT Token**: 短期有效 + 刷新机制
3. **CORS**: 限制允许的来源
4. **输入验证**: 所有用户输入进行验证
5. **文件上传**: 限制类型和大小
6. **SQL 注入**: 使用参数化查询
7. **XSS 防护**: 输出转义

---

## 部署说明

### 开发环境
```bash
cd frontend
pip install -r requirements.txt
python main.py
```

### 生产环境
```bash
# 使用 uvicorn + gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### 数据库初始化
```bash
python -c "from core.database import init_db; import asyncio; asyncio.run(init_db())"