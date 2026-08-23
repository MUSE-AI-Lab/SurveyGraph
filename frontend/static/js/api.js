/**
 * SurveyGraph API 客户端
 * 封装所有与后端的通信
 *
 * 认证方式：
 * 1. Cookie (access_token) - 主要方式，30天有效期
 * 2. localStorage - 向后兼容，用于 WebSocket 连接
 */

class APIClient {
    constructor() {
        this.baseURL = '/api';
        // 从 localStorage 读取 token（向后兼容）
        this.accessToken = localStorage.getItem('access_token');
        this.refreshToken = localStorage.getItem('refresh_token');
    }

    // 设置认证令牌（同时存储到 localStorage，用于 WebSocket）
    setTokens(accessToken, refreshToken) {
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
        // 存储到 localStorage（用于 WebSocket 连接）
        localStorage.setItem('access_token', accessToken);
        localStorage.setItem('refresh_token', refreshToken);
    }

    // 清除认证令牌
    clearTokens() {
        this.accessToken = null;
        this.refreshToken = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
    }

    // 检查是否已登录（检查 cookie 或 localStorage）
    isAuthenticated() {
        // 优先检查 cookie
        const cookieToken = this.getCookie('access_token');
        if (cookieToken) {
            this.accessToken = cookieToken;
            return true;
        }
        return !!this.accessToken;
    }

    // 从 cookie 获取值
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }

    // 获取请求头
    getHeaders(includeAuth = true, contentType = 'application/json') {
        const headers = {};
        if (contentType) {
            headers['Content-Type'] = contentType;
        }
        if (includeAuth && this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`;
        }
        return headers;
    }

    // 通用请求方法
    async request(method, endpoint, data = null, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            method,
            headers: this.getHeaders(options.auth !== false, options.contentType),
            credentials: 'same-origin',  // 确保发送 cookie
        };

        if (data) {
            if (options.contentType === null) {
                // FormData，不设置Content-Type
                config.body = data;
                delete config.headers['Content-Type'];
            } else {
                config.body = JSON.stringify(data);
            }
        }

        try {
            let response = await fetch(url, config);

            // 如果401且有refresh token，尝试刷新
            if (response.status === 401 && this.refreshToken && !options.isRetry) {
                const refreshed = await this.refreshAccessToken();
                if (refreshed) {
                    config.headers['Authorization'] = `Bearer ${this.accessToken}`;
                    response = await fetch(url, { ...config, isRetry: true });
                }
            }

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: '请求失败' }));
                throw new APIError(response.status, error.detail || '请求失败');
            }

            // 检查是否有内容返回
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            return null;
        } catch (error) {
            if (error instanceof APIError) {
                throw error;
            }
            throw new APIError(0, error.message || '网络错误');
        }
    }

    // 刷新访问令牌
    async refreshAccessToken() {
        try {
            const response = await fetch(`${this.baseURL}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: this.refreshToken }),
            });

            if (response.ok) {
                const data = await response.json();
                this.setTokens(data.access_token, data.refresh_token);
                return true;
            }
        } catch (e) {
            console.error('Token refresh failed:', e);
        }

        this.clearTokens();
        return false;
    }

    // GET 请求
    async get(endpoint, options = {}) {
        return this.request('GET', endpoint, null, options);
    }

    // POST 请求
    async post(endpoint, data, options = {}) {
        return this.request('POST', endpoint, data, options);
    }

    // PUT 请求
    async put(endpoint, data, options = {}) {
        return this.request('PUT', endpoint, data, options);
    }

    // DELETE 请求
    async delete(endpoint, options = {}) {
        return this.request('DELETE', endpoint, null, options);
    }

    // ==================== 认证 API ====================

    // 注册
    async register(username, email, password, inviteCode = null) {
        const data = { username, email, password };
        if (inviteCode) {
            data.invite_code = inviteCode;
        }
        return this.post('/auth/register', data, { auth: false });
    }

    // 登录
    async login(username, password) {
        const response = await fetch(`${this.baseURL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
            credentials: 'same-origin',  // 确保接收 cookie
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: '登录失败' }));
            throw new APIError(response.status, error.detail || '登录失败');
        }

        const data = await response.json();
        // 后端会自动设置 cookie，这里同时存储到 localStorage（用于 WebSocket）
        this.setTokens(data.access_token, data.refresh_token);
        return data;
    }

    // 登出
    async logout() {
        try {
            // 调用后端登出接口，清除 cookie
            await this.post('/auth/logout');
        } catch (e) {
            console.error('Logout API error:', e);
        }
        // 清除本地存储
        this.clearTokens();
    }

    // 修改密码
    async changePassword(currentPassword, newPassword) {
        return this.post('/auth/change-password', {
            current_password: currentPassword,
            new_password: newPassword,
        });
    }

    // ==================== 用户 API ====================

    // 获取当前用户信息
    async getCurrentUser() {
        return this.get('/auth/me');
    }

    // 获取配额信息
    async getQuota() {
        return this.get('/user/quota');
    }

    // 获取邀请码
    async getInviteCode() {
        return this.get('/user/invite-code');
    }

    // 获取邀请列表
    async getInvitations() {
        return this.get('/user/invitations');
    }

    // 获取用户统计
    async getUserStats() {
        return this.get('/user/stats');
    }

    // ==================== 任务 API ====================

    // 获取任务列表
    // all: 是否查看所有用户的任务（仅管理员有效）
    // search: 搜索主题关键词
    async getTasks(page = 1, pageSize = 10, status = null, all = false, search = null) {
        let endpoint = `/tasks?page=${page}&page_size=${pageSize}`;
        if (status) {
            endpoint += `&status=${status}`;
        }
        if (all) {
            endpoint += `&all=true`;
        }
        if (search) {
            endpoint += `&search=${encodeURIComponent(search)}`;
        }
        return this.get(endpoint);
    }

    // 获取任务详情
    async getTask(taskId) {
        return this.get(`/tasks/${taskId}`);
    }

    // 创建任务
    async createTask(taskData) {
        return this.post('/tasks', taskData);
    }

    // 启动任务
    async startTask(taskId) {
        return this.post(`/tasks/${taskId}/start`);
    }

    // 暂停任务
    async pauseTask(taskId) {
        return this.post(`/tasks/${taskId}/pause`);
    }

    // 取消任务
    async cancelTask(taskId) {
        return this.post(`/tasks/${taskId}/cancel`);
    }

    // 删除任务
    async deleteTask(taskId) {
        return this.delete(`/tasks/${taskId}`);
    }

    // 重试任务
    async retryTask(taskId, fromStep = null) {
        const data = {};
        if (fromStep) {
            data.from_step = fromStep;
        }
        return this.post(`/tasks/${taskId}/retry`, data);
    }

    // 获取任务日志
    async getTaskLogs(taskId, level = null) {
        let endpoint = `/tasks/${taskId}/logs`;
        if (level) {
            endpoint += `?level=${level}`;
        }
        return this.get(endpoint);
    }

    // 获取任务大纲
    async getTaskOutline(taskId) {
        return this.get(`/tasks/${taskId}/outline`);
    }

    // 更新任务大纲
    async updateTaskOutline(taskId, outline) {
        return this.put(`/tasks/${taskId}/outline`, { outline });
    }

    // 获取任务结果
    async getTaskResults(taskId) {
        return this.get(`/tasks/${taskId}/results`);
    }

    // 获取任务进度（用于轮询）
    async getTaskProgress(taskId) {
        return this.get(`/tasks/${taskId}/progress`);
    }

    // 上传文档到指定任务
    async uploadDocument(taskId, file) {
        const formData = new FormData();
        formData.append('file', file);
        return this.post(`/tasks/${taskId}/upload`, formData, { contentType: null });
    }

    // 获取可用步骤
    async getAvailableSteps() {
        return this.get('/tasks/steps');
    }

    // ==================== 独立文件上传 API ====================

    // 上传 PDF 文件到共享目录（不依赖 taskId）
    async uploadPdf(file) {
        const formData = new FormData();
        formData.append('file', file);
        return this.post('/upload', formData, { contentType: null });
    }

    // 批量上传 PDF 文件
    async uploadPdfBatch(files) {
        const formData = new FormData();
        files.forEach(file => {
            formData.append('files', file);
        });
        return this.post('/upload/batch', formData, { contentType: null });
    }

    // 获取已上传的 PDF 文件列表
    async getUploadedFiles() {
        return this.get('/upload/list');
    }

    // 删除已上传的 PDF 文件
    async deleteUploadedFile(filename) {
        return this.delete(`/upload/${encodeURIComponent(filename)}`);
    }

    // ==================== 个人知识库 API ====================

    // 获取知识库文件列表
    async getKnowledgeBaseFiles(page = 1, pageSize = 20, search = null, tags = null) {
        let endpoint = `/knowledge-base?page=${page}&page_size=${pageSize}`;
        if (search) {
            endpoint += `&search=${encodeURIComponent(search)}`;
        }
        if (tags) {
            endpoint += `&tags=${encodeURIComponent(tags)}`;
        }
        return this.get(endpoint);
    }

    // 添加文件到知识库
    async addToKnowledgeBase(fileInfo) {
        return this.post('/knowledge-base', fileInfo);
    }

    // 批量添加文件到知识库
    async batchAddToKnowledgeBase(files) {
        return this.post('/knowledge-base/batch', { files });
    }

    // 获取知识库文件详情
    async getKnowledgeBaseFile(fileId) {
        return this.get(`/knowledge-base/${fileId}`);
    }

    // 更新知识库文件信息
    async updateKnowledgeBaseFile(fileId, updateInfo) {
        return this.put(`/knowledge-base/${fileId}`, updateInfo);
    }

    // 从知识库移除文件
    async removeFromKnowledgeBase(fileId) {
        return this.delete(`/knowledge-base/${fileId}`);
    }

    // 批量从知识库移除文件
    async batchRemoveFromKnowledgeBase(fileIds) {
        return this.delete(`/knowledge-base?file_ids=${fileIds.join(',')}`);
    }

    // ==================== 管理员 API ====================

    // 获取所有用户
    async adminGetUsers(page = 1, pageSize = 20, search = null) {
        let endpoint = `/admin/users?page=${page}&page_size=${pageSize}`;
        if (search) {
            endpoint += `&search=${encodeURIComponent(search)}`;
        }
        return this.get(endpoint);
    }

    // 获取用户详情
    async adminGetUser(userId) {
        return this.get(`/admin/users/${userId}`);
    }

    // 更新用户
    async adminUpdateUser(userId, data) {
        return this.put(`/admin/users/${userId}`, data);
    }

    // 删除用户
    async adminDeleteUser(userId) {
        return this.delete(`/admin/users/${userId}`);
    }

    // 获取所有任务
    async adminGetTasks(page = 1, pageSize = 20, status = null, userId = null) {
        let endpoint = `/admin/tasks?page=${page}&page_size=${pageSize}`;
        if (status) {
            endpoint += `&status=${status}`;
        }
        if (userId) {
            endpoint += `&user_id=${userId}`;
        }
        return this.get(endpoint);
    }

    // 获取任务详细日志
    async adminGetTaskLogs(taskId) {
        return this.get(`/admin/tasks/${taskId}/logs`);
    }

    // 获取系统统计
    async adminGetStats() {
        return this.get('/admin/stats');
    }

    // 强制重试任务（管理员）
    async adminForceRetryTask(taskId, fromStep = 0) {
        return this.post(`/admin/tasks/${taskId}/force-retry?from_step=${fromStep}`);
    }
}

// API 错误类
class APIError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
        this.name = 'APIError';
    }
}

// WebSocket 客户端
class WSClient {
    constructor(taskId) {
        this.taskId = taskId;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.handlers = {
            progress: [],
            log: [],
            status: [],
            status_change: [],
            completion: [],
            heartbeat: [],
            pong: [],
            error: [],
            close: [],
        };
    }

    // 连接 WebSocket
    connect() {
        // 优先从 cookie 获取 token，其次从 localStorage
        let token = this.getCookie('access_token') || localStorage.getItem('access_token');
        if (!token) {
            console.error('No access token for WebSocket');
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws/${this.taskId}?token=${token}`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket closed:', event.code, event.reason);
            this.emit('close', event);

            // 尝试重连
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                setTimeout(() => this.connect(), this.reconnectDelay * this.reconnectAttempts);
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.emit('error', error);
        };
    }

    // 处理消息
    handleMessage(data) {
        const { type, data: payload } = data;
        // 如果消息有 data 字段，使用它；否则使用整个消息（去掉 type）
        const eventData = payload !== undefined ? payload : (() => {
            const { type: _, ...rest } = data;
            return rest;
        })();
        this.emit(type, eventData);
    }

    // 注册事件处理器
    on(event, handler) {
        if (this.handlers[event]) {
            this.handlers[event].push(handler);
        }
        return this;
    }

    // 移除事件处理器
    off(event, handler) {
        if (this.handlers[event]) {
            this.handlers[event] = this.handlers[event].filter(h => h !== handler);
        }
        return this;
    }

    // 触发事件
    emit(event, data) {
        if (this.handlers[event]) {
            this.handlers[event].forEach(handler => handler(data));
        }
    }

    // 关闭连接
    close() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    // 从 cookie 获取值
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }
}

// 创建全局 API 实例
const api = new APIClient();

// 导出
window.api = api;
window.APIError = APIError;
window.WSClient = WSClient;