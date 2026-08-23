/**
 * SurveyGraph 主应用逻辑
 */

// 设置当前年份
document.addEventListener('DOMContentLoaded', () => {
    const yearSpan = document.getElementById('currentYear');
    if (yearSpan) {
        yearSpan.textContent = new Date().getFullYear();
    }

    // 移动端菜单逻辑
    const toggle = document.getElementById('mobileMenuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');

    if (toggle && sidebar && overlay) {
        toggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
        });
    }
});

// ==================== 应用状态 ====================

const AppState = {
    user: null,
    isAdmin: false,
    currentPage: null,
};

// ==================== 路由管理 ====================

class Router {
    constructor() {
        this.routes = {};
        this.currentRoute = null;
        window.addEventListener('popstate', () => this.handleRoute());
    }

    register(path, handler) {
        this.routes[path] = handler;
    }

    navigate(path, replace = false) {
        if (replace) {
            history.replaceState(null, '', path);
        } else {
            history.pushState(null, '', path);
        }
        this.handleRoute();
    }

    handleRoute() {
        const path = window.location.pathname;
        const handler = this.findHandler(path);
        
        if (handler) {
            this.currentRoute = path;
            handler.callback(handler.params);
        } else {
            this.navigate('/dashboard', true);
        }
    }

    findHandler(path) {
        if (this.routes[path]) {
            return { callback: this.routes[path], params: {} };
        }
        
        for (const [pattern, callback] of Object.entries(this.routes)) {
            const regex = this.pathToRegex(pattern);
            const match = path.match(regex);
            if (match) {
                const params = this.extractParams(pattern, match);
                return { callback, params };
            }
        }
        return null;
    }

    pathToRegex(path) {
        const pattern = path.replace(/\//g, '\\/').replace(/:(\w+)/g, '([^/]+)');
        return new RegExp(`^${pattern}$`);
    }

    extractParams(pattern, match) {
        const params = {};
        const paramNames = pattern.match(/:(\w+)/g) || [];
        paramNames.forEach((name, index) => {
            params[name.slice(1)] = match[index + 1];
        });
        return params;
    }
}

const router = new Router();

// ==================== 认证管理 ====================

async function checkAuth() {
    if (!api.isAuthenticated()) return null;
    
    try {
        const user = await api.getCurrentUser();
        AppState.user = user;
        AppState.isAdmin = user.is_admin;
        updateNavbar();
        return user;  // 返回用户对象而不是 true
    } catch (e) {
        api.clearTokens();
        return null;
    }
}

function requireAuth(callback) {
    return async (params) => {
        const isAuth = await checkAuth();
        if (!isAuth) {
            router.navigate('/login');
            return;
        }
        callback(params);
    };
}

function requireAdmin(callback) {
    return async (params) => {
        const isAuth = await checkAuth();
        if (!isAuth) {
            router.navigate('/login');
            return;
        }
        if (!AppState.isAdmin) {
            Toast.error('需要管理员权限');
            router.navigate('/dashboard');
            return;
        }
        callback(params);
    };
}

// ==================== 导航栏 ====================

function updateNavbar() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    
    const userProfile = sidebar.querySelector('.user-profile');
    if (!userProfile) return;
    
    if (AppState.user) {
        const avatar = document.getElementById('userAvatar');
        const name = document.getElementById('userName');
        const quota = document.getElementById('userQuota');
        
        if (avatar) avatar.textContent = AppState.user.username.charAt(0).toUpperCase();
        if (name) name.textContent = AppState.user.username;
        if (quota) {
            const total = AppState.user.daily_quota + AppState.user.bonus_quota;
            quota.textContent = `配额: ${total}次/天`;
        }
        
        userProfile.style.display = 'flex';
    } else {
        userProfile.style.display = 'none';
    }
    
    // 更新激活状态
    const currentPath = window.location.pathname;
    sidebar.querySelectorAll('.sidebar-link').forEach(link => {
        const href = link.getAttribute('href');
        if (currentPath === href || (href !== '/' && currentPath.startsWith(href))) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

function logout() {
    api.logout();
    AppState.user = null;
    AppState.isAdmin = false;
    Toast.success('已退出登录');
    router.navigate('/login');
}

// ==================== 页面渲染 ====================

function renderPage(content, title = 'SurveyGraph') {
    document.title = title + ' - SurveyGraph';
    const main = document.querySelector('main') || document.querySelector('.main-content');
    if (main) main.innerHTML = content;
}

// ==================== 登录页面 ====================

function renderLoginPage() {
    renderPage(`
        <div class="auth-container">
            <div class="auth-card">
                <div class="auth-header">
                    <div class="auth-logo">
                        <i class="fas fa-chart-line"></i>
                    </div>
                    <div class="auth-brand">
                        <span class="auth-brand-text">SurveyGraph</span>
                    </div>
                    <h1>欢迎回来</h1>
                    <p>登录您的账户，继续探索学术综述生成</p>
                </div>
                <form id="login-form" class="auth-form">
                    <div class="form-group">
                        <label for="username"><i class="fas fa-user"></i> 用户名</label>
                        <div class="input-with-icon">
                            <input type="text" id="username" name="username" required placeholder="请输入用户名">
                            <i class="fas fa-user"></i>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="password"><i class="fas fa-lock"></i> 密码</label>
                        <div class="input-with-icon">
                            <input type="password" id="password" name="password" required placeholder="请输入密码">
                            <i class="fas fa-lock"></i>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary btn-block">
                        <i class="fas fa-sign-in-alt"></i> 登录
                    </button>
                </form>
                <div class="auth-footer">
                    <p>还没有账户？<a href="/register">立即注册</a></p>
                </div>
            </div>
        </div>
    `, '登录');
    
    document.getElementById('login-form').addEventListener('submit', handleLogin);
}

async function handleLogin(e) {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector('button[type="submit"]');
    const username = form.username.value.trim();
    const password = form.password.value;
    
    if (!username || !password) {
        Toast.error('请填写用户名和密码');
        return;
    }
    
    Loading.button(btn, true);
    try {
        await api.login(username, password);
        Toast.success('登录成功');
        // 使用完整页面跳转而不是 SPA 路由，确保加载带有 navbar 的完整页面
        window.location.href = '/dashboard';
    } catch (e) {
        Toast.error(e.message || '登录失败');
    } finally {
        Loading.button(btn, false);
    }
}

// ==================== 注册页面 ====================

function renderRegisterPage() {
    const urlParams = new URLSearchParams(window.location.search);
    const inviteCode = urlParams.get('invite') || '';
    
    renderPage(`
        <div class="auth-container">
            <div class="auth-card">
                <div class="auth-header">
                    <div class="auth-logo">
                        <i class="fas fa-chart-line"></i>
                    </div>
                    <div class="auth-brand">
                        <span class="auth-brand-text">SurveyGraph</span>
                    </div>
                    <h1>创建账户</h1>
                    <p>开启 AI 驱动的学术综述生成之旅</p>
                </div>
                <form id="register-form" class="auth-form">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="username"><i class="fas fa-user"></i> 用户名</label>
                            <input type="text" id="username" name="username" required placeholder="3-20个字符" minlength="3" maxlength="20">
                        </div>
                        <div class="form-group">
                            <label for="email"><i class="fas fa-envelope"></i> 邮箱</label>
                            <input type="email" id="email" name="email" required placeholder="请输入邮箱">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="password"><i class="fas fa-lock"></i> 密码</label>
                            <input type="password" id="password" name="password" required placeholder="至少6个字符" minlength="6">
                        </div>
                        <div class="form-group">
                            <label for="confirm-password"><i class="fas fa-shield-alt"></i> 确认密码</label>
                            <input type="password" id="confirm-password" name="confirm_password" required placeholder="再次输入">
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="invite-code"><i class="fas fa-gift"></i> 邀请码 <span class="optional">(可选)</span></label>
                        <input type="text" id="invite-code" name="invite_code" placeholder="输入邀请码可获得额外配额" value="${escapeHtml(inviteCode)}">
                    </div>
                    <button type="submit" class="btn btn-primary btn-block">
                        <i class="fas fa-user-plus"></i> 创建账户
                    </button>
                </form>
                <div class="auth-footer">
                    <p>已有账户？<a href="/login">立即登录</a></p>
                </div>
            </div>
        </div>
    `, '注册');
    
    document.getElementById('register-form').addEventListener('submit', handleRegister);
}

async function handleRegister(e) {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector('button[type="submit"]');
    
    const username = form.username.value.trim();
    const email = form.email.value.trim();
    const password = form.password.value;
    const confirmPassword = form.confirm_password.value;
    const inviteCode = form.invite_code.value.trim();
    
    if (password !== confirmPassword) {
        Toast.error('两次输入的密码不一致');
        return;
    }
    
    Loading.button(btn, true);
    try {
        await api.register(username, email, password, inviteCode || null);
        Toast.success('注册成功，请登录');
        // 使用完整页面跳转确保页面结构正确
        window.location.href = '/login';
    } catch (e) {
        Toast.error(e.message || '注册失败');
    } finally {
        Loading.button(btn, false);
    }
}

// ==================== 仪表盘页面 ====================

async function renderDashboardPage() {
    renderPage(`
        <div class="dashboard">
            <div class="dashboard-header">
                <div class="dashboard-title">
                    <h1>我的任务</h1>
                    <p class="dashboard-subtitle">管理和监控您的综述生成任务</p>
                </div>
                <a href="/task/new" class="btn btn-primary">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="8" y1="3" x2="8" y2="13"></line>
                        <line x1="3" y1="8" x2="13" y2="8"></line>
                    </svg>
                    创建综述
                </a>
            </div>
            <div class="dashboard-stats" id="stats-container">
                <div class="stat-card">
                    <div class="stat-icon stat-icon-primary">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path>
                        </svg>
                    </div>
                    <div class="stat-info">
                        <div class="stat-value" id="stat-total">-</div>
                        <div class="stat-label">总任务数</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon stat-icon-success">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 11.08V12a10 10 0 11-5.93-9.14"></path>
                            <polyline points="22 4 12 14.01 9 11.01"></polyline>
                        </svg>
                    </div>
                    <div class="stat-info">
                        <div class="stat-value" id="stat-completed">-</div>
                        <div class="stat-label">已完成</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon stat-icon-warning">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                    </div>
                    <div class="stat-info">
                        <div class="stat-value" id="stat-running">-</div>
                        <div class="stat-label">进行中</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon stat-icon-info">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                            <line x1="16" y1="2" x2="16" y2="6"></line>
                            <line x1="8" y1="2" x2="8" y2="6"></line>
                            <line x1="3" y1="10" x2="21" y2="10"></line>
                        </svg>
                    </div>
                    <div class="stat-info">
                        <div class="stat-value" id="stat-quota">-</div>
                        <div class="stat-label">剩余配额</div>
                    </div>
                </div>
            </div>
            <div class="dashboard-content">
                <div class="content-header">
                    <h2 class="content-title">任务列表</h2>
                    <div class="task-filters">
                        <select id="status-filter" class="form-select">
                            <option value="">全部状态</option>
                            <option value="pending">等待中</option>
                            <option value="running">运行中</option>
                            <option value="completed">已完成</option>
                            <option value="failed">失败</option>
                            <option value="cancelled">已取消</option>
                        </select>
                    </div>
                </div>
                <div id="task-list" class="task-list"><div class="loading-placeholder">加载中...</div></div>
                <div id="pagination" class="pagination-container"></div>
            </div>
        </div>
    `, '我的任务');
    
    await loadDashboardData();
    document.getElementById('status-filter').addEventListener('change', () => loadTaskList(1));
}

async function loadDashboardData() {
    try {
        const [stats, quota] = await Promise.all([api.getUserStats(), api.getQuota()]);
        document.getElementById('stat-total').textContent = stats.total_tasks || 0;
        document.getElementById('stat-completed').textContent = stats.completed_tasks || 0;
        document.getElementById('stat-running').textContent = stats.running_tasks || 0;
        document.getElementById('stat-quota').textContent = `${quota.remaining_today}/${quota.daily_quota} + ${quota.bonus_quota}`;
        await loadTaskList(1);
    } catch (e) {
        Toast.error('加载数据失败');
    }
}

async function loadTaskList(page = 1) {
    const container = document.getElementById('task-list');
    const status = document.getElementById('status-filter').value;
    
    try {
        const result = await api.getTasks(page, 10, status || null);
        const tasks = result.tasks || result.items || [];
        
        if (tasks.length === 0) {
            container.innerHTML = `<div class="empty-state"><div class="empty-icon"><i class="fas fa-file-alt"></i></div><h3>暂无任务</h3><p>点击"创建综述"开始您的第一个任务</p><a href="/task/new" class="btn btn-primary">创建综述</a></div>`;
            document.getElementById('pagination').innerHTML = '';
            return;
        }
        
        container.innerHTML = tasks.map(task => `
            <div class="task-card" onclick="window.location.href='/task/${task.task_id}'">
                <div class="task-header"><h3 class="task-title">${escapeHtml(task.topic)}</h3>${renderStatusBadge(task.status)}</div>
                <div class="task-meta"><span class="task-step">${task.current_step_name ? getStepName(task.current_step_name) : '等待开始'}</span><span class="task-time">${formatRelativeTime(task.created_at)}</span></div>
                ${task.status === 'running' ? `<div class="task-progress"><div class="progress-bar"><div class="progress-fill" style="width: ${task.progress_percent || 0}%"></div></div></div>` : ''}
            </div>
        `).join('');
        
        new Pagination(document.getElementById('pagination'), {
            total: result.total, pageSize: result.page_size, currentPage: result.page, onChange: loadTaskList
        });
    } catch (e) {
        container.innerHTML = '<div class="error-state">加载失败，请刷新重试</div>';
    }
}

function getProgressPercent(step) {
    const index = getStepIndex(step);
    const total = Object.keys(STEP_NAMES).length;
    return Math.round((index + 1) / total * 100);
}

// ==================== 创建任务页面 ====================

// 注意：/task/new 页面现在使用服务端模板渲染 (task_new.html)
// 这个函数不再动态渲染页面，只做认证检查
async function renderNewTaskPage() {
    // 页面已经由模板渲染，这里只需要确保用户已登录
    // 认证检查已经在 requireAuth 中完成
    // 页面初始化逻辑在模板的 script 块中处理
    console.log('New task page loaded via template');
}

async function handleCreateTask(form, fileUpload) {
    const btn = form.querySelector('button[type="submit"]');
    const formHelper = new Form(form);
    const data = formHelper.getData();
    
    if (!data.topic.trim()) { Toast.error('请输入研究主题'); return; }
    
    const enableArxiv = form.enable_arxiv.checked;
    const files = fileUpload.getFiles();
    
    // 验证：如果不启用 arXiv 搜索，必须上传文件
    if (!enableArxiv && files.length === 0) { Toast.error('请启用 arXiv 搜索或上传至少一个文档'); return; }
    
    // 验证：最多上传 50 篇自定义论文
    if (files.length > 50) { Toast.error('最多只能上传 50 篇自定义论文'); return; }
    
    Loading.button(btn, true);
    try {
        // 1. 先创建任务（获取 task_id）
        const taskData = {
            topic: data.topic.trim(),
            keywords: data.keywords ? data.keywords.split(',').map(k => k.trim()).filter(k => k).join(', ') : null,
            enable_arxiv_search: enableArxiv,
            config: {
                max_papers: parseInt(data.max_papers) || 50,
                year_start: parseInt(data.year_start) || 2020,
                year_end: parseInt(data.year_end) || 2025,
                language: data.language || 'en',
                outline_depth: parseInt(data.outline_depth) || 3,
                enable_figures: form.enable_figures.checked,
                enable_evaluation: form.enable_evaluation.checked,
            },
        };
        
        const task = await api.createTask(taskData);
        const taskId = task.task_id;
        
        // 2. 上传文件到该任务（如果有）
        if (files.length > 0) {
            Toast.info(`正在上传 ${files.length} 个文件...`);
            for (const file of files) {
                try {
                    await api.uploadDocument(taskId, file);
                } catch (uploadError) {
                    console.error('文件上传失败:', file.name, uploadError);
                    Toast.warning(`文件 ${file.name} 上传失败: ${uploadError.message}`);
                }
            }
            Toast.success('文件上传完成');
        }
        
        Toast.success('任务创建成功');
        router.navigate(`/task/${taskId}`);
    } catch (e) {
        Toast.error(e.message || '创建任务失败');
    } finally {
        Loading.button(btn, false);
    }
}

// ==================== 任务详情页面 ====================

let currentTaskWS = null;
let currentTaskPollingInterval = null;
let currentTaskId = null;

async function renderTaskDetailPage(params) {
    const taskId = params.id;
    currentTaskId = taskId;
    renderPage(`<div class="task-detail"><div class="page-header"><a href="/dashboard" class="back-link">← 返回</a><h1 id="task-title">加载中...</h1></div><div id="task-content" class="task-content"><div class="loading-placeholder">加载中...</div></div></div>`, '任务详情');
    await loadTaskDetail(taskId);
}

async function loadTaskDetail(taskId) {
    try {
        const task = await api.getTask(taskId);
        renderTaskContent(task);
        if (task.status === 'running' || task.status === 'pending') {
            // 同时启动 WebSocket 和轮询，确保实时更新
            connectTaskWebSocket(taskId);
            startTaskPolling(taskId);
        } else {
            // 任务已完成或失败，停止轮询
            stopTaskPolling();
        }
    } catch (e) {
        document.getElementById('task-content').innerHTML = `<div class="error-state"><h3>加载失败</h3><p>${escapeHtml(e.message)}</p><button class="btn btn-primary" onclick="loadTaskDetail('${taskId}')">重试</button></div>`;
    }
}

// 轮询机制 - 作为 WebSocket 的备份
let logRefreshInterval = null;

function startTaskPolling(taskId) {
    stopTaskPolling(); // 先停止之前的轮询
    
    console.log('Starting task polling for:', taskId);
    
    currentTaskPollingInterval = setInterval(async () => {
        if (currentTaskId !== taskId) {
            stopTaskPolling();
            return;
        }
        
        try {
            // 使用专门的进度 API，更轻量
            const progress = await api.getTaskProgress(taskId);
            console.log('Polling progress:', progress);
            
            updateTaskProgressFromPolling(progress);
            
            // 如果任务已完成或失败，停止轮询并刷新页面
            if (progress.status === 'completed' || progress.status === 'failed' || progress.status === 'cancelled') {
                console.log('Task ended, stopping polling');
                stopTaskPolling();
                if (currentTaskWS) {
                    currentTaskWS.close();
                    currentTaskWS = null;
                }
                // 延迟刷新，让用户看到最终状态
                setTimeout(() => loadTaskDetail(taskId), 500);
            }
        } catch (e) {
            console.error('Polling error:', e);
        }
    }, 2000); // 每 2 秒轮询一次
    
    // 同时启动日志刷新（每 3 秒刷新一次）
    startLogRefresh(taskId);
}

// 日志刷新机制
function startLogRefresh(taskId) {
    stopLogRefresh();
    
    // 只有管理员才需要定时刷新详细日志
    if (!AppState.isAdmin) return;
    
    logRefreshInterval = setInterval(async () => {
        if (currentTaskId !== taskId) {
            stopLogRefresh();
            return;
        }
        
        try {
            await loadTaskLogs(taskId);
        } catch (e) {
            console.error('Log refresh error:', e);
        }
    }, 3000); // 每 3 秒刷新一次日志
}

function stopLogRefresh() {
    if (logRefreshInterval) {
        clearInterval(logRefreshInterval);
        logRefreshInterval = null;
    }
}

function stopTaskPolling() {
    if (currentTaskPollingInterval) {
        clearInterval(currentTaskPollingInterval);
        currentTaskPollingInterval = null;
    }
    stopLogRefresh();
}

// 更新任务进度（不重新渲染整个页面）- 用于轮询
function updateTaskProgressFromPolling(progress) {
    // 更新进度条
    const progressContainer = document.getElementById('progress-container');
    if (progressContainer) {
        const steps = [];
        for (let i = 0; i <= 11; i++) {
            steps.push({
                label: STEP_NAMES[i] || `步骤 ${i}`,
                key: STEP_NUMBER_TO_NAME[i] || `STEP_${i}`
            });
        }
        const currentIndex = progress.current_step || 0;
        new Progress(progressContainer, { steps, currentStep: currentIndex });
    }
    
    // 更新当前步骤显示
    const stepEl = document.querySelector('.meta-value[data-field="current_step"]');
    if (stepEl) {
        stepEl.textContent = getStepName(progress.current_step) || progress.current_step_name || '-';
    }
    
    // 更新进度百分比
    const progressEl = document.querySelector('.meta-value[data-field="progress"]');
    if (progressEl) {
        progressEl.textContent = `${progress.progress_percent || 0}%`;
    }
    
    // 更新论文数
    const papersEl = document.querySelector('.meta-value[data-field="papers_count"]');
    if (papersEl && progress.papers_count !== undefined && progress.papers_count !== null) {
        papersEl.textContent = progress.papers_count;
    }
    
    // 更新章节数
    const sectionsEl = document.querySelector('.meta-value[data-field="sections_count"]');
    if (sectionsEl && progress.sections_count !== undefined && progress.sections_count !== null) {
        sectionsEl.textContent = progress.sections_count;
    }
    
    // 更新状态徽章
    const statusBadge = document.querySelector('.task-status-header .badge');
    if (statusBadge && progress.status) {
        const statusMap = {
            pending: { label: '等待中', class: 'badge-secondary' },
            running: { label: '运行中', class: 'badge-primary' },
            completed: { label: '已完成', class: 'badge-success' },
            failed: { label: '失败', class: 'badge-danger' },
            cancelled: { label: '已取消', class: 'badge-warning' },
        };
        const info = statusMap[progress.status] || { label: progress.status, class: 'badge-secondary' };
        statusBadge.className = `badge ${info.class}`;
        statusBadge.textContent = info.label;
    }
    
    // 如果有错误信息，显示错误提示
    if (progress.error_message && progress.status === 'failed') {
        const errorAlert = document.querySelector('.alert-danger');
        if (!errorAlert) {
            const taskInfoCard = document.querySelector('.task-info-card');
            if (taskInfoCard) {
                const alertHtml = `<div class="alert alert-danger"><strong>任务失败</strong><p>${escapeHtml(progress.error_message)}</p></div>`;
                const actionsDiv = taskInfoCard.querySelector('.task-actions');
                if (actionsDiv) {
                    actionsDiv.insertAdjacentHTML('beforebegin', alertHtml);
                }
            }
        }
    }
}

// 更新任务进度（旧版本，保留兼容性）
function updateTaskProgress(task) {
    updateTaskProgressFromPolling({
        current_step: task.current_step,
        current_step_name: task.current_step_name,
        progress_percent: task.progress_percent,
        papers_count: task.papers_count,
        sections_count: task.sections_count,
        status: task.status,
        error_message: task.error_message
    });
    
    // 更新关键词显示
    const keywordsEl = document.querySelector('.meta-value[data-field="keywords"]');
    if (keywordsEl && task.keywords) {
        keywordsEl.textContent = task.keywords;
    }
}

function renderTaskContent(task) {
    document.getElementById('task-title').textContent = task.topic;
    const content = document.getElementById('task-content');
    
    // 使用 task_id（字符串格式）而不是 id（数据库整数 ID）
    const taskId = task.task_id;
    
    // 检查当前用户是否是管理员
    const isAdmin = AppState.isAdmin;
    
    // 构建操作按钮
    let actionButtons = '';
    if (task.status === 'pending') {
        actionButtons += `<button class="btn btn-primary" onclick="startTask('${taskId}')"><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><polygon points="4,2 14,8 4,14"/></svg> 开始任务</button>`;
        actionButtons += `<button class="btn btn-danger btn-outline" onclick="deleteTask('${taskId}')">删除任务</button>`;
    }
    if (task.status === 'running') {
        actionButtons += `<button class="btn btn-warning" onclick="pauseTask('${taskId}')">暂停任务</button>`;
        actionButtons += `<button class="btn btn-danger" onclick="cancelTask('${taskId}')">取消任务</button>`;
    }
    if (task.status === 'paused') {
        actionButtons += `<button class="btn btn-primary" onclick="resumeTask('${taskId}')">继续任务</button>`;
        actionButtons += `<button class="btn btn-danger" onclick="cancelTask('${taskId}')">取消任务</button>`;
    }
    if (task.status === 'failed' || task.status === 'cancelled') {
        actionButtons += `<button class="btn btn-primary" onclick="showRetryModal('${taskId}')">重试任务</button>`;
        actionButtons += `<button class="btn btn-danger btn-outline" onclick="deleteTask('${taskId}')">删除任务</button>`;
    }
    if (task.status === 'completed') {
        actionButtons += `<a href="/task/${taskId}/results" class="btn btn-primary">查看结果</a>`;
        actionButtons += `<button class="btn btn-secondary" onclick="showRetryModal('${taskId}')">重新生成</button>`;
    }
    
    // 管理员专用：强制从头开始
    if (isAdmin) {
        actionButtons += `<button class="btn btn-warning btn-outline" onclick="forceRetryTask('${taskId}')" style="margin-left: 8px;">从头开始(Admin)</button>`;
    }

    // 大纲编辑按钮（当大纲已生成且任务未运行时）
    if (task.current_step >= 2 && task.status !== 'running') {
        actionButtons += `<button class="btn btn-secondary" onclick="showOutlineEditor('${taskId}')">编辑大纲</button>`;
    }
    
    // 获取当前步骤的中文名称
    const currentStepLabel = getStepName(task.current_step) || getStepName(task.current_step_name) || '未开始';
    
    // 普通用户只显示简化的任务信息，管理员显示完整日志
    const logsSection = isAdmin ? `
        <div class="task-logs-section">
            <h3>任务日志</h3>
            <div id="logs-container" class="logs-container">
                <div class="loading-placeholder">加载日志中...</div>
            </div>
        </div>
    ` : `
        <div class="task-logs-section task-logs-simple">
            <h3>执行状态</h3>
            <div id="logs-container" class="logs-container-simple">
                <div class="simple-status">
                    <div class="status-icon ${task.status === 'running' ? 'status-running' : ''}">
                        ${task.status === 'running' ? '<div class="spinner-small"></div>' :
                          task.status === 'completed' ? '<i class="fas fa-check-circle"></i>' :
                          task.status === 'failed' ? '<i class="fas fa-times-circle"></i>' :
                          '<i class="fas fa-clock"></i>'}
                    </div>
                    <div class="status-text">
                        <span class="status-step" data-field="current_step_simple">${currentStepLabel}</span>
                        <span class="status-progress" data-field="progress_simple">${task.progress_percent || 0}% 完成</span>
                    </div>
                </div>
                <p class="status-hint">任务正在后台执行，您可以关闭此页面，稍后回来查看结果。</p>
            </div>
        </div>
    `;
    
    content.innerHTML = `
        <div class="task-info-card">
            <div class="task-status-header">${renderStatusBadge(task.status)}<span class="task-time">创建于 ${formatDate(task.created_at)}</span></div>
            <div class="task-meta-info">
                <div class="meta-item"><span class="meta-label">任务ID:</span><span class="meta-value">${escapeHtml(taskId)}</span></div>
                <div class="meta-item"><span class="meta-label">关键词:</span><span class="meta-value" data-field="keywords">${escapeHtml(task.keywords || '自动生成')}</span></div>
                <div class="meta-item"><span class="meta-label">当前步骤:</span><span class="meta-value" data-field="current_step">${currentStepLabel}</span></div>
                <div class="meta-item"><span class="meta-label">进度:</span><span class="meta-value" data-field="progress">${task.progress_percent || 0}%</span></div>
                <div class="meta-item"><span class="meta-label">论文数:</span><span class="meta-value" data-field="papers_count">${task.papers_count || '-'}</span></div>
                <div class="meta-item"><span class="meta-label">章节数:</span><span class="meta-value" data-field="sections_count">${task.sections_count || '-'}</span></div>
            </div>
            <div class="task-progress-section"><h3>任务进度</h3><div id="progress-container"></div></div>
            ${task.status === 'failed' ? `<div class="alert alert-danger"><strong>任务失败</strong><p>${escapeHtml(task.error_message || '未知错误')}</p></div>` : ''}
            <div class="task-actions">${actionButtons}</div>
        </div>
        ${logsSection}
    `;
    
    // 构建步骤列表 - 使用数字索引
    const steps = [];
    for (let i = 0; i <= 11; i++) {
        steps.push({
            label: STEP_NAMES[i] || `步骤 ${i}`,
            key: STEP_NUMBER_TO_NAME[i] || `STEP_${i}`
        });
    }
    const currentIndex = typeof task.current_step === 'number' ? task.current_step : getStepIndex(task.current_step_name);
    new Progress(document.getElementById('progress-container'), { steps, currentStep: currentIndex >= 0 ? currentIndex : 0 });
    
    // 只有管理员才加载详细日志
    if (isAdmin) {
        loadTaskLogs(taskId);
    }
}

async function loadTaskLogs(taskId) {
    const container = document.getElementById('logs-container');
    try {
        const result = await api.getTaskLogs(taskId);
        // 后端返回格式: {"total": ..., "logs": [...]}
        const logs = result.logs || result || [];
        if (logs.length === 0) { container.innerHTML = '<div class="empty-logs">暂无日志</div>'; return; }
        container.innerHTML = logs.map(log => `<div class="log-item log-${log.level}"><span class="log-time">${formatDate(log.created_at)}</span><span class="log-step">${getStepName(log.step) || '-'}</span><span class="log-message">${escapeHtml(log.message)}</span></div>`).join('');
        container.scrollTop = container.scrollHeight;
    } catch (e) {
        container.innerHTML = '<div class="error-logs">加载日志失败</div>';
    }
}

function connectTaskWebSocket(taskId) {
    if (currentTaskWS) {
        currentTaskWS.close();
        currentTaskWS = null;
    }
    
    currentTaskWS = new WSClient(taskId);
    
    currentTaskWS.on('progress', (data) => {
        console.log('WebSocket progress:', data);
        
        // 更新进度条
        const progressContainer = document.getElementById('progress-container');
        if (progressContainer) {
            const steps = [];
            for (let i = 0; i <= 11; i++) {
                steps.push({
                    label: STEP_NAMES[i] || `步骤 ${i}`,
                    key: STEP_NUMBER_TO_NAME[i] || `STEP_${i}`
                });
            }
            const currentIndex = typeof data.step === 'number' ? data.step : getStepIndex(data.step);
            new Progress(progressContainer, { steps, currentStep: currentIndex >= 0 ? currentIndex : 0 });
        }
        
        // 更新当前步骤显示
        const stepEl = document.querySelector('.meta-value[data-field="current_step"]');
        if (stepEl) {
            stepEl.textContent = getStepName(data.step) || data.step_name || '-';
        }
        
        // 更新进度百分比
        const progressEl = document.querySelector('.meta-value[data-field="progress"]');
        if (progressEl && data.progress_percent !== undefined) {
            progressEl.textContent = `${data.progress_percent}%`;
        }
        
        // 如果有消息，添加到日志 (仅限管理员)
        if (data.message && AppState.isAdmin) {
            const container = document.getElementById('logs-container');
            if (container) {
                // 移除加载占位符
                const placeholder = container.querySelector('.loading-placeholder');
                if (placeholder) placeholder.remove();
                
                container.insertAdjacentHTML('beforeend', `<div class="log-item log-info"><span class="log-time">${formatDate(new Date().toISOString())}</span><span class="log-step">${getStepName(data.step) || '-'}</span><span class="log-message">${escapeHtml(data.message)}</span></div>`);
                container.scrollTop = container.scrollHeight;
            }
        }
        
        // 更新简化版状态显示 (普通用户)
        if (!AppState.isAdmin) {
            const simpleStepEl = document.querySelector('[data-field="current_step_simple"]');
            const simpleProgressEl = document.querySelector('[data-field="progress_simple"]');
            if (simpleStepEl) simpleStepEl.textContent = getStepName(data.step) || data.step_name || '-';
            if (simpleProgressEl && data.progress_percent !== undefined) simpleProgressEl.textContent = `${data.progress_percent}% 完成`;
        }
    });
    
    currentTaskWS.on('log', (data) => {
        console.log('WebSocket log:', data);
        // 普通用户不处理详细日志事件
        if (!AppState.isAdmin) return;
        
        const container = document.getElementById('logs-container');
        if (container) {
            // 移除加载占位符
            const placeholder = container.querySelector('.loading-placeholder');
            if (placeholder) placeholder.remove();
            
            container.insertAdjacentHTML('beforeend', `<div class="log-item log-${data.level || 'info'}"><span class="log-time">${formatDate(data.created_at || new Date().toISOString())}</span><span class="log-step">${getStepName(data.step) || '-'}</span><span class="log-message">${escapeHtml(data.message)}</span></div>`);
            container.scrollTop = container.scrollHeight;
        }
    });
    
    currentTaskWS.on('status', (data) => {
        console.log('WebSocket status:', data);
        
        // 更新状态徽章
        const statusBadge = document.querySelector('.task-status-header .badge');
        if (statusBadge && data.status) {
            const statusMap = {
                pending: { label: '等待中', class: 'badge-secondary' },
                running: { label: '运行中', class: 'badge-primary' },
                completed: { label: '已完成', class: 'badge-success' },
                failed: { label: '失败', class: 'badge-danger' },
                cancelled: { label: '已取消', class: 'badge-warning' },
            };
            const info = statusMap[data.status] || { label: data.status, class: 'badge-secondary' };
            statusBadge.className = `badge ${info.class}`;
            statusBadge.textContent = info.label;
        }
        
        // 更新进度信息
        if (data.current_step !== undefined) {
            const stepEl = document.querySelector('.meta-value[data-field="current_step"]');
            if (stepEl) {
                stepEl.textContent = getStepName(data.current_step) || data.current_step_name || '-';
            }
        }
        
        if (data.progress_percent !== undefined) {
            const progressEl = document.querySelector('.meta-value[data-field="progress"]');
            if (progressEl) {
                progressEl.textContent = `${data.progress_percent}%`;
            }
        }
        
        if (data.papers_count !== undefined) {
            const papersEl = document.querySelector('.meta-value[data-field="papers_count"]');
            if (papersEl) {
                papersEl.textContent = data.papers_count;
            }
        }
    });
    
    currentTaskWS.on('status_change', (data) => {
        console.log('WebSocket status_change:', data);
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
            stopTaskPolling();
            if (currentTaskWS) {
                currentTaskWS.close();
                currentTaskWS = null;
            }
            // 延迟刷新，让用户看到最终状态
            setTimeout(() => loadTaskDetail(taskId), 1000);
        }
    });
    
    currentTaskWS.on('completion', (data) => {
        console.log('WebSocket completion:', data);
        stopTaskPolling();
        if (currentTaskWS) {
            currentTaskWS.close();
            currentTaskWS = null;
        }
        
        if (data.success) {
            Toast.success('任务完成！');
        } else {
            Toast.error('任务失败');
        }
        
        // 延迟刷新页面
        setTimeout(() => loadTaskDetail(taskId), 1000);
    });
    
    currentTaskWS.on('error', (error) => {
        console.error('WebSocket error:', error);
        // WebSocket 出错时，轮询会继续工作
    });
    
    currentTaskWS.on('close', () => {
        console.log('WebSocket closed');
        // WebSocket 关闭时，轮询会继续工作
    });
    
    currentTaskWS.connect();
}

async function startTask(taskId) {
    try {
        await api.startTask(taskId);
        Toast.success('任务已启动');
        loadTaskDetail(taskId);
    } catch (e) {
        Toast.error(e.message || '启动失败');
    }
}

async function pauseTask(taskId) {
    try {
        await api.pauseTask(taskId);
        Toast.success('任务已暂停');
        loadTaskDetail(taskId);
    } catch (e) {
        Toast.error(e.message || '暂停失败');
    }
}

async function resumeTask(taskId) {
    try {
        await api.startTask(taskId);
        Toast.success('任务已继续');
        loadTaskDetail(taskId);
    } catch (e) {
        Toast.error(e.message || '继续失败');
    }
}

async function cancelTask(taskId) {
    if (!await Modal.confirm('确定要取消此任务吗？')) return;
    try {
        await api.cancelTask(taskId);
        Toast.success('任务已取消');
        loadTaskDetail(taskId);
    } catch (e) {
        Toast.error(e.message || '取消失败');
    }
}

async function deleteTask(taskId) {
    if (!await Modal.confirm('确定要删除此任务吗？此操作不可恢复。')) return;
    try {
        await api.deleteTask(taskId);
        Toast.success('任务已删除');
        router.navigate('/dashboard');
    } catch (e) {
        Toast.error(e.message || '删除失败');
    }
}

async function forceRetryTask(taskId) {
    if (!await Modal.confirm('确定要强制从头开始此任务吗？这将清除当前进度。')) return;
    try {
        await api.adminForceRetryTask(taskId, 0);
        Toast.success('任务已强制从头开始');
        loadTaskDetail(taskId);
    } catch (e) {
        Toast.error(e.message || '操作失败');
    }
}

async function showRetryModal(taskId) {
    let task;
    try { task = await api.getTask(taskId); } catch (e) { Toast.error('获取任务信息失败'); return; }
    
    const steps = Object.entries(STEP_NAMES);
    const currentIndex = getStepIndex(task.current_step);
    
    const modal = new Modal({
        title: '重试任务',
        content: `<div class="retry-modal"><p>选择从哪个步骤开始重试：</p><div class="form-group"><select id="retry-step" class="form-select"><option value="">从头开始</option>${steps.slice(0, currentIndex + 1).map(([key, label]) => `<option value="${key}">${label}</option>`).join('')}</select></div><p class="form-hint">今日剩余重试次数：${5 - (task.retry_count || 0)}</p></div>`,
        onConfirm: async (m) => {
            const fromStep = document.getElementById('retry-step').value || null;
            try {
                await api.retryTask(taskId, fromStep);
                Toast.success('任务已重新开始');
                m.close();
                loadTaskDetail(taskId);
            } catch (e) { Toast.error(e.message || '重试失败'); }
        },
    });
    modal.show();
}

async function showOutlineEditor(taskId) {
    let outline;
    try { outline = await api.getTaskOutline(taskId); } catch (e) { Toast.error('获取大纲失败'); return; }
    
    const modal = new Modal({
        title: '编辑大纲',
        size: 'large',
        content: `<div class="outline-editor"><p class="form-hint">您可以修改大纲结构，修改后点击确认继续生成。</p><textarea id="outline-content" class="form-textarea" rows="20">${escapeHtml(JSON.stringify(outline, null, 2))}</textarea></div>`,
        confirmText: '保存并继续',
        onConfirm: async (m) => {
            const content = document.getElementById('outline-content').value;
            try {
                const parsed = JSON.parse(content);
                await api.updateTaskOutline(taskId, parsed);
                Toast.success('大纲已更新');
                m.close();
                loadTaskDetail(taskId);
            } catch (e) {
                if (e instanceof SyntaxError) Toast.error('JSON 格式错误');
                else Toast.error(e.message || '保存失败');
            }
        },
    });
    modal.show();
}

// ==================== 任务结果页面 ====================

async function renderTaskResultsPage(params) {
    const taskId = params.id;
    renderPage(`<div class="task-results"><div class="page-header"><a href="/task/${taskId}" class="back-link">← 返回任务</a><h1>任务结果</h1></div><div id="results-content" class="results-content"><div class="loading-placeholder">加载中...</div></div></div>`, '任务结果');
    await loadTaskResults(taskId);
}

async function loadTaskResults(taskId) {
    const container = document.getElementById('results-content');
    try {
        const results = await api.getTaskResults(taskId);
        container.innerHTML = `<div class="results-tabs" id="results-tabs"></div>`;
        
        const tabs = [];
        
        if (results.mekg_data) {
            tabs.push({ label: '知识图谱', icon: '<i class="fas fa-project-diagram"></i>', content: `<div class="mekg-viewer"><div id="mekg-graph" class="graph-container"></div></div>` });
        }
        
        if (results.pdf_url) {
            tabs.push({ label: 'PDF 论文', icon: '<i class="fas fa-file-pdf"></i>', content: `<div class="pdf-viewer"><div class="pdf-actions"><a href="${results.pdf_url}" download class="btn btn-primary"><i class="fas fa-download"></i> 下载 PDF</a></div><iframe src="${results.pdf_url}" class="pdf-frame"></iframe></div>` });
        }
        
        if (results.markdown_content) {
            tabs.push({ label: 'Markdown', icon: '<i class="fab fa-markdown"></i>', content: `<div class="markdown-viewer"><div class="markdown-actions"><button class="btn btn-primary" onclick="downloadMarkdown('${taskId}')"><i class="fas fa-download"></i> 下载</button><button class="btn btn-secondary" onclick="copyMarkdown()"><i class="fas fa-copy"></i> 复制</button></div><div id="markdown-content" class="markdown-content">${typeof marked !== 'undefined' ? marked.parse(results.markdown_content) : results.markdown_content}</div><textarea id="markdown-raw" style="display:none">${escapeHtml(results.markdown_content)}</textarea></div>` });
        }
        
        if (results.evaluation_report) {
            tabs.push({ label: '评估报告', icon: '<i class="fas fa-chart-bar"></i>', content: `<div class="evaluation-viewer"><div class="evaluation-content">${typeof marked !== 'undefined' ? marked.parse(results.evaluation_report) : results.evaluation_report}</div></div>` });
        }
        
        if (tabs.length === 0) { container.innerHTML = '<div class="empty-state">暂无结果</div>'; return; }
        
        new Tabs(document.getElementById('results-tabs'), {
            tabs,
            onChange: (index) => {
                if (tabs[index].label === '知识图谱' && results.mekg_data) setTimeout(() => initMekgGraph(results.mekg_data), 100);
            },
        });
        
        if (tabs[0].label === '知识图谱' && results.mekg_data) setTimeout(() => initMekgGraph(results.mekg_data), 100);
    } catch (e) {
        container.innerHTML = `<div class="error-state"><h3>加载失败</h3><p>${escapeHtml(e.message)}</p></div>`;
    }
}

function initMekgGraph(data) {
    const container = document.getElementById('mekg-graph');
    if (!container || !window.echarts) return;
    
    const chart = echarts.init(container);
    const nodes = data.nodes || [];
    const links = data.edges || [];
    
    chart.setOption({
        tooltip: { trigger: 'item' },
        series: [{
            type: 'graph', layout: 'force',
            data: nodes.map(n => ({ name: n.name || n.id, category: n.category, symbolSize: Math.min(50, 10 + (n.weight || 1) * 5) })),
            links: links.map(l => ({ source: l.source, target: l.target })),
            roam: true, label: { show: true, position: 'right', fontSize: 10 },
            force: { repulsion: 100, edgeLength: [50, 200] },
            lineStyle: { color: 'source', curveness: 0.3 },
        }],
    });
    window.addEventListener('resize', () => chart.resize());
}

function downloadMarkdown(taskId) {
    const content = document.getElementById('markdown-raw').value;
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `survey_${taskId}.md`; a.click();
    URL.revokeObjectURL(url);
}

function copyMarkdown() {
    const content = document.getElementById('markdown-raw').value;
    navigator.clipboard.writeText(content).then(() => Toast.success('已复制')).catch(() => Toast.error('复制失败'));
}

// ==================== 个人设置页面 ====================

async function renderProfilePage() {
    renderPage(`
        <div class="page-container">
            <div class="page-header">
                <a href="/dashboard" class="back-link">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M10 12L6 8L10 4"></path>
                    </svg>
                    返回任务列表
                </a>
                <div class="page-title-section">
                    <h1>个人设置</h1>
                    <p class="page-subtitle">管理您的账户信息和配额</p>
                </div>
            </div>
            
            <div class="profile-grid">
                <div class="profile-main">
                    <div class="card profile-section">
                        <div class="section-header">
                            <h2>账户信息</h2>
                        </div>
                        <div class="info-grid">
                            <div class="info-item">
                                <label>用户名</label>
                                <span id="profile-username" class="info-value">-</span>
                            </div>
                            <div class="info-item">
                                <label>邮箱</label>
                                <span id="profile-email" class="info-value">-</span>
                            </div>
                            <div class="info-item">
                                <label>注册时间</label>
                                <span id="profile-created" class="info-value">-</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card profile-section">
                        <div class="section-header">
                            <h2>配额信息</h2>
                        </div>
                        <div class="quota-cards">
                            <div class="quota-card">
                                <div class="quota-value" id="profile-daily-quota">-</div>
                                <div class="quota-label">每日配额</div>
                            </div>
                            <div class="quota-card">
                                <div class="quota-value" id="profile-daily-remaining">-</div>
                                <div class="quota-label">今日剩余</div>
                            </div>
                            <div class="quota-card quota-card-bonus">
                                <div class="quota-value" id="profile-bonus-quota">-</div>
                                <div class="quota-label">额外配额</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card profile-section">
                        <div class="section-header">
                            <h2>修改密码</h2>
                        </div>
                        <form id="password-form" class="password-form">
                            <div class="form-group">
                                <label>当前密码</label>
                                <input type="password" name="current_password" class="form-input" required placeholder="请输入当前密码">
                            </div>
                            <div class="form-group">
                                <label>新密码</label>
                                <input type="password" name="new_password" class="form-input" required minlength="6" placeholder="至少6个字符">
                            </div>
                            <div class="form-group">
                                <label>确认新密码</label>
                                <input type="password" name="confirm_new_password" class="form-input" required placeholder="再次输入新密码">
                            </div>
                            <button type="submit" class="btn btn-primary">修改密码</button>
                        </form>
                    </div>
                </div>
                
                <div class="profile-sidebar">
                    <div class="card invite-card">
                        <div class="invite-header">
                            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M22 11V7a2 2 0 00-2-2H6a2 2 0 00-2 2v14a2 2 0 002 2h4"></path>
                                <rect x="10" y="11" width="18" height="16" rx="2"></rect>
                                <path d="M19 19h-4m2-2v4"></path>
                            </svg>
                            <h3>邀请好友</h3>
                        </div>
                        <p class="invite-desc">邀请好友注册，双方各得 <strong>1 次</strong> 额外生成配额！</p>
                        <div class="invite-code-box">
                            <label>您的邀请码</label>
                            <div class="invite-code" id="invite-code">加载中...</div>
                        </div>
                        <button class="btn btn-primary btn-block" onclick="copyInviteLink()">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="5" y="5" width="8" height="10" rx="1"></rect>
                                <path d="M3 11V3a1 1 0 011-1h6"></path>
                            </svg>
                            复制邀请链接
                        </button>
                        <div class="invite-stats">
                            <span>已成功邀请 <strong id="invite-count">0</strong> 人</span>
                        </div>
                    </div>
                    
                    <div class="card" style="margin-top: 24px; padding: 24px;">
                        <h3 style="margin: 0 0 16px 0; font-size: 16px;">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle; margin-right: 8px;">
                                <rect x="2" y="2" width="12" height="12" rx="1"></rect>
                                <path d="M2 6h12M6 2v12"></path>
                            </svg>
                            使用统计
                        </h3>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: var(--text-muted);">总任务数</span>
                                <span id="stat-total-tasks" style="font-weight: 600;">-</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: var(--text-muted);">已完成</span>
                                <span id="stat-completed-tasks" style="font-weight: 600; color: var(--accent-success);">-</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: var(--text-muted);">进行中</span>
                                <span id="stat-running-tasks" style="font-weight: 600; color: var(--accent-primary);">-</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `, '个人设置');
    await loadProfileData();
    document.getElementById('password-form').addEventListener('submit', handleChangePassword);
}

async function loadProfileData() {
    try {
        const [user, quota, inviteCode, invitations, stats] = await Promise.all([
            api.getCurrentUser(),
            api.getQuota(),
            api.getInviteCode(),
            api.getInvitations(),
            api.getUserStats()
        ]);
        document.getElementById('profile-username').textContent = user.username;
        document.getElementById('profile-email').textContent = user.email;
        document.getElementById('profile-created').textContent = formatDate(user.created_at);
        document.getElementById('profile-daily-quota').textContent = quota.daily_quota;
        document.getElementById('profile-daily-remaining').textContent = quota.remaining_today;
        document.getElementById('profile-bonus-quota').textContent = quota.bonus_quota;
        document.getElementById('invite-code').textContent = inviteCode.invite_code;
        document.getElementById('invite-count').textContent = invitations.total || 0;
        
        // 使用统计
        const statTotalEl = document.getElementById('stat-total-tasks');
        const statCompletedEl = document.getElementById('stat-completed-tasks');
        const statRunningEl = document.getElementById('stat-running-tasks');
        if (statTotalEl) statTotalEl.textContent = stats.total_tasks || 0;
        if (statCompletedEl) statCompletedEl.textContent = stats.completed_tasks || 0;
        if (statRunningEl) statRunningEl.textContent = stats.running_tasks || 0;
    } catch (e) { Toast.error('加载数据失败: ' + e.message); }
}

function copyInviteLink() {
    const code = document.getElementById('invite-code').textContent;
    const link = `${window.location.origin}/register?invite=${code}`;
    navigator.clipboard.writeText(link).then(() => Toast.success('邀请链接已复制')).catch(() => Toast.error('复制失败'));
}

async function handleChangePassword(e) {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector('button[type="submit"]');
    const currentPassword = form.current_password.value;
    const newPassword = form.new_password.value;
    const confirmPassword = form.confirm_new_password.value;
    
    if (newPassword !== confirmPassword) { Toast.error('两次输入的新密码不一致'); return; }
    
    Loading.button(btn, true);
    try {
        await api.changePassword(currentPassword, newPassword);
        Toast.success('密码修改成功');
        form.reset();
    } catch (e) { Toast.error(e.message || '修改失败'); }
    finally { Loading.button(btn, false); }
}

// ==================== 管理员页面 ====================

async function renderAdminDashboardPage() {
    renderPage(`
        <div class="admin-dashboard">
            <h1>管理后台</h1>
            <div class="admin-nav"><a href="/admin" class="admin-nav-item active">概览</a><a href="/admin/users" class="admin-nav-item">用户管理</a><a href="/admin/tasks" class="admin-nav-item">任务管理</a></div>
            <div class="admin-stats" id="admin-stats">
                <div class="stat-card"><div class="stat-icon"><i class="fas fa-users"></i></div><div class="stat-info"><div class="stat-value" id="admin-stat-users">-</div><div class="stat-label">总用户数</div></div></div>
                <div class="stat-card"><div class="stat-icon"><i class="fas fa-file-alt"></i></div><div class="stat-info"><div class="stat-value" id="admin-stat-tasks">-</div><div class="stat-label">总任务数</div></div></div>
                <div class="stat-card"><div class="stat-icon"><i class="fas fa-spinner"></i></div><div class="stat-info"><div class="stat-value" id="admin-stat-running">-</div><div class="stat-label">运行中</div></div></div>
                <div class="stat-card"><div class="stat-icon"><i class="fas fa-check-circle"></i></div><div class="stat-info"><div class="stat-value" id="admin-stat-completed">-</div><div class="stat-label">已完成</div></div></div>
            </div>
            <div class="admin-recent"><h2>最近任务</h2><div id="recent-tasks" class="recent-tasks"><div class="loading-placeholder">加载中...</div></div></div>
        </div>
    `, '管理后台');
    await loadAdminDashboard();
}

async function loadAdminDashboard() {
    try {
        const stats = await api.adminGetStats();
        document.getElementById('admin-stat-users').textContent = stats.total_users || 0;
        document.getElementById('admin-stat-tasks').textContent = stats.total_tasks || 0;
        document.getElementById('admin-stat-running').textContent = stats.running_tasks || 0;
        document.getElementById('admin-stat-completed').textContent = stats.completed_tasks || 0;
        
        const tasks = await api.adminGetTasks(1, 10);
        const container = document.getElementById('recent-tasks');
        if (tasks.items.length === 0) { container.innerHTML = '<div class="empty-state">暂无任务</div>'; return; }
        
        container.innerHTML = `<table class="data-table"><thead><tr><th>ID</th><th>用户</th><th>主题</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody>${tasks.items.map(task => `<tr><td>${task.id.slice(0, 8)}...</td><td>${escapeHtml(task.username || '-')}</td><td>${escapeHtml(task.topic)}</td><td>${renderStatusBadge(task.status)}</td><td>${formatDate(task.created_at)}</td><td><a href="/admin/tasks/${task.id}" class="btn btn-sm btn-outline">详情</a></td></tr>`).join('')}</tbody></table>`;
    } catch (e) { Toast.error('加载数据失败'); }
}

async function renderAdminUsersPage() {
    renderPage(`
        <div class="admin-users">
            <h1>用户管理</h1>
            <div class="admin-nav"><a href="/admin" class="admin-nav-item">概览</a><a href="/admin/users" class="admin-nav-item active">用户管理</a><a href="/admin/tasks" class="admin-nav-item">任务管理</a></div>
            <div class="admin-toolbar"><input type="text" id="user-search" class="form-input" placeholder="搜索用户名或邮箱..."><button class="btn btn-primary" onclick="searchUsers()">搜索</button></div>
            <div id="users-table" class="users-table"><div class="loading-placeholder">加载中...</div></div>
            <div id="users-pagination" class="pagination-container"></div>
        </div>
    `, '用户管理');
    await loadAdminUsers(1);
    document.getElementById('user-search').addEventListener('keypress', (e) => { if (e.key === 'Enter') searchUsers(); });
}

async function loadAdminUsers(page = 1) {
    const container = document.getElementById('users-table');
    const search = document.getElementById('user-search')?.value || '';
    try {
        const result = await api.adminGetUsers(page, 20, search || null);
        container.innerHTML = `<table class="data-table"><thead><tr><th>用户名</th><th>邮箱</th><th>角色</th><th>配额</th><th>任务数</th><th>注册时间</th><th>操作</th></tr></thead><tbody>${result.items.map(user => `<tr><td>${escapeHtml(user.username)}</td><td>${escapeHtml(user.email)}</td><td>${user.is_admin ? '<span class="badge badge-primary">管理员</span>' : '<span class="badge badge-secondary">用户</span>'}</td><td>${user.daily_quota} + ${user.bonus_quota}</td><td>${user.task_count || 0}</td><td>${formatDate(user.created_at)}</td><td><button class="btn btn-sm btn-outline" onclick="editUser('${user.id}')">编辑</button></td></tr>`).join('')}</tbody></table>`;
        new Pagination(document.getElementById('users-pagination'), { total: result.total, pageSize: result.page_size, currentPage: result.page, onChange: loadAdminUsers });
    } catch (e) { container.innerHTML = '<div class="error-state">加载失败</div>'; }
}

function searchUsers() { loadAdminUsers(1); }

async function editUser(userId) {
    let user;
    try { user = await api.adminGetUser(userId); } catch (e) { Toast.error('获取用户信息失败'); return; }
    
    const modal = new Modal({
        title: '编辑用户',
        content: `<form id="edit-user-form"><div class="form-group"><label>用户名</label><input type="text" name="username" value="${escapeHtml(user.username)}" disabled></div><div class="form-group"><label>每日配额</label><input type="number" name="daily_quota" value="${user.daily_quota}" min="0"></div><div class="form-group"><label>额外配额</label><input type="number" name="bonus_quota" value="${user.bonus_quota}" min="0"></div><div class="form-group"><label class="checkbox-label"><input type="checkbox" name="is_admin" ${user.is_admin ? 'checked' : ''}><span>管理员权限</span></label></div><div class="form-group"><label class="checkbox-label"><input type="checkbox" name="is_active" ${user.is_active ? 'checked' : ''}><span>账户启用</span></label></div></form>`,
        onConfirm: async (m) => {
            const form = document.getElementById('edit-user-form');
            const data = { daily_quota: parseInt(form.daily_quota.value), bonus_quota: parseInt(form.bonus_quota.value), is_admin: form.is_admin.checked, is_active: form.is_active.checked };
            try { await api.adminUpdateUser(userId, data); Toast.success('用户已更新'); m.close(); loadAdminUsers(); } catch (e) { Toast.error(e.message || '更新失败'); }
        },
    });
    modal.show();
}

async function renderAdminTasksPage() {
    renderPage(`
        <div class="admin-tasks">
            <h1>任务管理</h1>
            <div class="admin-nav"><a href="/admin" class="admin-nav-item">概览</a><a href="/admin/users" class="admin-nav-item">用户管理</a><a href="/admin/tasks" class="admin-nav-item active">任务管理</a></div>
            <div class="admin-toolbar"><select id="task-status-filter" class="form-select"><option value="">全部状态</option><option value="pending">等待中</option><option value="running">运行中</option><option value="completed">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option></select><button class="btn btn-primary" onclick="loadAdminTasks(1)">筛选</button></div>
            <div id="tasks-table" class="tasks-table"><div class="loading-placeholder">加载中...</div></div>
            <div id="tasks-pagination" class="pagination-container"></div>
        </div>
    `, '任务管理');
    await loadAdminTasks(1);
}

async function loadAdminTasks(page = 1) {
    const container = document.getElementById('tasks-table');
    const status = document.getElementById('task-status-filter')?.value || '';
    try {
        const result = await api.adminGetTasks(page, 20, status || null);
        container.innerHTML = `<table class="data-table"><thead><tr><th>ID</th><th>用户</th><th>主题</th><th>状态</th><th>当前步骤</th><th>创建时间</th><th>操作</th></tr></thead><tbody>${result.items.map(task => `<tr><td>${task.id.slice(0, 8)}...</td><td>${escapeHtml(task.username || '-')}</td><td>${escapeHtml(task.topic)}</td><td>${renderStatusBadge(task.status)}</td><td>${getStepName(task.current_step) || '-'}</td><td>${formatDate(task.created_at)}</td><td><a href="/admin/tasks/${task.id}" class="btn btn-sm btn-outline">详情</a></td></tr>`).join('')}</tbody></table>`;
        new Pagination(document.getElementById('tasks-pagination'), { total: result.total, pageSize: result.page_size, currentPage: result.page, onChange: loadAdminTasks });
    } catch (e) { container.innerHTML = '<div class="error-state">加载失败</div>'; }
}

async function renderAdminTaskDetailPage(params) {
    const taskId = params.id;
    renderPage(`<div class="admin-task-detail"><div class="page-header"><a href="/admin/tasks" class="back-link">← 返回</a><h1 id="admin-task-title">加载中...</h1></div><div id="admin-task-content"><div class="loading-placeholder">加载中...</div></div></div>`, '任务详情');
    
    try {
        const task = await api.getTask(taskId);
        document.getElementById('admin-task-title').textContent = task.topic;
        
        const logs = await api.adminGetTaskLogs(taskId);
        
        document.getElementById('admin-task-content').innerHTML = `
            <div class="task-info-card">
                <div class="info-grid">
                    <div class="info-item"><label>任务ID</label><span>${task.id}</span></div>
                    <div class="info-item"><label>用户</label><span>${escapeHtml(task.username || '-')}</span></div>
                    <div class="info-item"><label>状态</label><span>${renderStatusBadge(task.status)}</span></div>
                    <div class="info-item"><label>当前步骤</label><span>${getStepName(task.current_step) || '-'}</span></div>
                    <div class="info-item"><label>创建时间</label><span>${formatDate(task.created_at)}</span></div>
                    <div class="info-item"><label>更新时间</label><span>${formatDate(task.updated_at)}</span></div>
                </div>
                ${task.error_message ? `<div class="alert alert-danger"><strong>错误信息</strong><p>${escapeHtml(task.error_message)}</p></div>` : ''}
            </div>
            <div class="task-logs-section">
                <h3>详细日志</h3>
                <div class="logs-container admin-logs">${logs.map(log => `<div class="log-item log-${log.level}"><span class="log-time">${formatDate(log.created_at)}</span><span class="log-level">${log.level}</span><span class="log-step">${getStepName(log.step) || '-'}</span><span class="log-message">${escapeHtml(log.message)}</span>${log.details ? `<pre class="log-details">${escapeHtml(JSON.stringify(log.details, null, 2))}</pre>` : ''}</div>`).join('')}</div>
            </div>
        `;
    } catch (e) {
        document.getElementById('admin-task-content').innerHTML = `<div class="error-state"><h3>加载失败</h3><p>${escapeHtml(e.message)}</p></div>`;
    }
}

// ==================== 路由注册 ====================

router.register('/login', renderLoginPage);
router.register('/register', renderRegisterPage);
router.register('/dashboard', requireAuth(renderDashboardPage));
router.register('/task/new', requireAuth(renderNewTaskPage));
router.register('/task/:id', requireAuth(renderTaskDetailPage));
router.register('/task/:id/results', requireAuth(renderTaskResultsPage));
router.register('/profile', requireAuth(renderProfilePage));
router.register('/admin', requireAdmin(renderAdminDashboardPage));
router.register('/admin/users', requireAdmin(renderAdminUsersPage));
router.register('/admin/tasks', requireAdmin(renderAdminTasksPage));
router.register('/admin/tasks/:id', requireAdmin(renderAdminTaskDetailPage));
// 首页由服务端渲染，不需要注册路由
// router.register('/', () => router.navigate('/dashboard'));

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    // 检查当前页面是否是服务端模板渲染的页面
    // 这些页面不需要通过路由系统动态渲染
    const currentPath = window.location.pathname;
    
    // 公开页面（不需要登录）
    const publicPages = ['/login', '/register', '/'];
    
    // 如果是登录或注册页面，检查是否已登录，已登录则跳转到 dashboard
    if (currentPath === '/login' || currentPath === '/register') {
        if (api.isAuthenticated()) {
            // 尝试验证 token 是否有效
            try {
                const user = await api.getCurrentUser();
                if (user) {
                    // 已登录，跳转到 dashboard
                    window.location.href = '/dashboard';
                    return;
                }
            } catch (e) {
                // token 无效，清除并继续显示登录页面
                api.clearTokens();
            }
        }
        // 未登录，继续渲染登录/注册页面
        router.handleRoute();
        return;
    }
    
    // 服务端渲染的页面列表（精确匹配）
    const serverRenderedExactPages = ['/', '/dashboard', '/task/new', '/knowledge-base', '/profile'];
    
    // 服务端渲染的页面前缀（前缀匹配）
    // /task/:id 和 /task/:id/results 都是服务端渲染的
    const serverRenderedPrefixes = ['/task/'];
    
    // 检查是否是服务端渲染的页面
    const isServerRendered = serverRenderedExactPages.includes(currentPath) ||
        serverRenderedPrefixes.some(prefix => {
            // 排除 /task/new，因为它已经在精确匹配列表中
            if (currentPath === '/task/new') return false;
            return currentPath.startsWith(prefix);
        });
    
    if (!isServerRendered) {
        router.handleRoute();
    } else {
        // 对于服务端渲染的页面，只需要执行认证检查
        checkAuth();
    }
    
    // 设置当前年份
    const yearSpan = document.getElementById('currentYear');
    if (yearSpan) {
        yearSpan.textContent = new Date().getFullYear();
    }

    // 移动端菜单逻辑
    const toggle = document.getElementById('mobileMenuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');

    if (toggle && sidebar && overlay) {
        toggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
        });
    }
});

// 导出全局函数
window.router = router;
window.logout = logout;
window.startTask = startTask;
window.pauseTask = pauseTask;
window.resumeTask = resumeTask;
window.cancelTask = cancelTask;
window.deleteTask = deleteTask;
window.forceRetryTask = forceRetryTask;
window.showRetryModal = showRetryModal;
window.showOutlineEditor = showOutlineEditor;
window.downloadMarkdown = downloadMarkdown;
window.copyMarkdown = copyMarkdown;
window.copyInviteLink = copyInviteLink;
window.searchUsers = searchUsers;
window.editUser = editUser;
window.loadAdminUsers = loadAdminUsers;
window.loadAdminTasks = loadAdminTasks;