
/**
 * SurveyGraph UI 组件库
 * 提供可复用的UI组件
 */

// ==================== 工具函数 ====================

// 格式化日期
function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

// 格式化相对时间
function formatRelativeTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    if (hours < 24) return `${hours}小时前`;
    if (days < 30) return `${days}天前`;
    return formatDate(dateStr);
}

// 转义HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 生成唯一ID
function generateId() {
    return 'id_' + Math.random().toString(36).substr(2, 9);
}

// ==================== Toast 通知 ====================

class Toast {
    static container = null;

    static init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    }

    static show(message, type = 'info', duration = 3000) {
        this.init();

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icons = {
            success: '<i class="fas fa-check"></i>',
            error: '<i class="fas fa-times"></i>',
            warning: '<i class="fas fa-exclamation-triangle"></i>',
            info: '<i class="fas fa-info-circle"></i>',
        };

        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${escapeHtml(message)}</span>
            <button class="toast-close" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>
        `;

        this.container.appendChild(toast);

        // 触发动画
        requestAnimationFrame(() => {
            toast.classList.add('toast-show');
        });

        // 自动移除
        if (duration > 0) {
            setTimeout(() => {
                toast.classList.remove('toast-show');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }

        return toast;
    }

    static success(message, duration) {
        return this.show(message, 'success', duration);
    }

    static error(message, duration) {
        return this.show(message, 'error', duration);
    }

    static warning(message, duration) {
        return this.show(message, 'warning', duration);
    }

    static info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// ==================== Modal 对话框 ====================

class Modal {
    constructor(options = {}) {
        this.options = {
            title: options.title || '',
            content: options.content || '',
            size: options.size || 'medium', // small, medium, large, full
            closable: options.closable !== false,
            onClose: options.onClose || null,
            onConfirm: options.onConfirm || null,
            confirmText: options.confirmText || '确定',
            cancelText: options.cancelText || '取消',
            showFooter: options.showFooter !== false,
            showCancel: options.showCancel !== false,
        };

        this.element = null;
        this.create();
    }

    create() {
        this.element = document.createElement('div');
        this.element.className = 'modal-overlay';
        this.element.innerHTML = `
            <div class="modal modal-${this.options.size}">
                <div class="modal-header">
                    <h3 class="modal-title">${escapeHtml(this.options.title)}</h3>
                    ${this.options.closable ? '<button class="modal-close" data-action="close">×</button>' : ''}
                </div>
                <div class="modal-body">
                    ${this.options.content}
                </div>
                ${this.options.showFooter ? `
                <div class="modal-footer">
                    ${this.options.showCancel ? `<button class="btn btn-secondary" data-action="cancel">${escapeHtml(this.options.cancelText)}</button>` : ''}
                    <button class="btn btn-primary" data-action="confirm">${escapeHtml(this.options.confirmText)}</button>
                </div>
                ` : ''}
            </div>
        `;

        // 绑定事件
        this.element.addEventListener('click', (e) => {
            const action = e.target.dataset.action;
            if (action === 'close' || action === 'cancel') {
                this.close();
            } else if (action === 'confirm') {
                if (this.options.onConfirm) {
                    this.options.onConfirm(this);
                } else {
                    this.close();
                }
            }
        });

        // 点击遮罩关闭
        if (this.options.closable) {
            this.element.addEventListener('click', (e) => {
                if (e.target === this.element) {
                    this.close();
                }
            });
        }
    }

    show() {
        document.body.appendChild(this.element);
        document.body.style.overflow = 'hidden';
        requestAnimationFrame(() => {
            this.element.classList.add('active');
        });
        return this;
    }

    close() {
        this.element.classList.remove('active');
        document.body.style.overflow = '';
        setTimeout(() => {
            this.element.remove();
            if (this.options.onClose) {
                this.options.onClose();
            }
        }, 300);
    }

    setContent(content) {
        const body = this.element.querySelector('.modal-body');
        if (body) {
            body.innerHTML = content;
        }
    }

    getBody() {
        return this.element.querySelector('.modal-body');
    }

    // 静态方法：确认对话框
    static confirm(message, options = {}) {
        return new Promise((resolve) => {
            const modal = new Modal({
                title: options.title || '确认',
                content: `<p>${escapeHtml(message)}</p>`,
                size: 'small',
                confirmText: options.confirmText || '确定',
                cancelText: options.cancelText || '取消',
                onConfirm: () => {
                    modal.close();
                    resolve(true);
                },
                onClose: () => resolve(false),
            });
            modal.show();
        });
    }

    // 静态方法：提示对话框
    static alert(message, options = {}) {
        return new Promise((resolve) => {
            const modal = new Modal({
                title: options.title || '提示',
                content: `<p>${escapeHtml(message)}</p>`,
                size: 'small',
                showCancel: false,
                onConfirm: () => {
                    modal.close();
                    resolve();
                },
            });
            modal.show();
        });
    }
}

// ==================== Loading 加载状态 ====================

class Loading {
    static overlay = null;

    static show(message = '加载中...') {
        if (!this.overlay) {
            this.overlay = document.createElement('div');
            this.overlay.className = 'loading-overlay';
            this.overlay.innerHTML = `
                <div class="loading-content">
                    <div class="loading-spinner"></div>
                    <p class="loading-message">${escapeHtml(message)}</p>
                </div>
            `;
            document.body.appendChild(this.overlay);
        } else {
            this.overlay.querySelector('.loading-message').textContent = message;
            this.overlay.style.display = 'flex';
        }
    }

    static hide() {
        if (this.overlay) {
            this.overlay.style.display = 'none';
        }
    }

    // 按钮加载状态
    static button(btn, loading = true) {
        if (loading) {
            btn.disabled = true;
            btn.dataset.originalText = btn.innerHTML;
            btn.innerHTML = '<span class="btn-spinner"></span> 处理中...';
        } else {
            btn.disabled = false;
            btn.innerHTML = btn.dataset.originalText || btn.innerHTML;
        }
    }
}

// ==================== Progress 进度条 ====================

class Progress {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' 
            ? document.querySelector(container) 
            : container;
        this.options = {
            steps: options.steps || [],
            currentStep: options.currentStep || 0,
            showLabels: options.showLabels !== false,
        };
        this.render();
    }

    render() {
        const { steps, currentStep, showLabels } = this.options;
        
        let html = '<div class="progress-steps">';
        
        steps.forEach((step, index) => {
            const status = index < currentStep ? 'completed' 
                : index === currentStep ? 'active' 
                : 'pending';
            
            html += `
                <div class="progress-step ${status}" data-step="${index}">
                    <div class="step-indicator">
                        ${status === 'completed' ? '<i class="fas fa-check"></i>' : index + 1}
                    </div>
                    ${showLabels ? `<div class="step-label">${escapeHtml(step.label || step)}</div>` : ''}
                </div>
            `;
            
            if (index < steps.length - 1) {
                html += `<div class="step-connector ${index < currentStep ? 'completed' : ''}"></div>`;
            }
        });
        
        html += '</div>';
        this.container.innerHTML = html;
    }

    setStep(step) {
        this.options.currentStep = step;
        this.render();
    }

    next() {
        if (this.options.currentStep < this.options.steps.length - 1) {
            this.options.currentStep++;
            this.render();
        }
    }

    prev() {
        if (this.options.currentStep > 0) {
            this.options.currentStep--;
            this.render();
        }
    }
}

// ==================== Tabs 标签页 ====================

class Tabs {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' 
            ? document.querySelector(container) 
            : container;
        this.options = {
            tabs: options.tabs || [],
            activeTab: options.activeTab || 0,
            onChange: options.onChange || null,
        };
        this.render();
        this.bindEvents();
    }

    render() {
        const { tabs, activeTab } = this.options;
        
        let html = '<div class="tabs-header">';
        tabs.forEach((tab, index) => {
            html += `
                <button class="tab-btn ${index === activeTab ? 'active' : ''}" 
                        data-tab="${index}">
                    ${tab.icon ? `<span class="tab-icon">${tab.icon}</span>` : ''}
                    ${escapeHtml(tab.label)}
                </button>
            `;
        });
        html += '</div>';
        
        html += '<div class="tabs-content">';
        tabs.forEach((tab, index) => {
            html += `
                <div class="tab-panel ${index === activeTab ? 'active' : ''}" 
                     data-panel="${index}">
                    ${tab.content || ''}
                </div>
            `;
        });
        html += '</div>';
        
        this.container.innerHTML = html;
    }

    bindEvents() {
        this.container.addEventListener('click', (e) => {
            const btn = e.target.closest('.tab-btn');
            if (btn) {
                const tabIndex = parseInt(btn.dataset.tab);
                this.setActive(tabIndex);
            }
        });
    }

    setActive(index) {
        this.options.activeTab = index;
        
        // 更新按钮状态
        this.container.querySelectorAll('.tab-btn').forEach((btn, i) => {
            btn.classList.toggle('active', i === index);
        });
        
        // 更新面板状态
        this.container.querySelectorAll('.tab-panel').forEach((panel, i) => {
            panel.classList.toggle('active', i === index);
        });
        
        if (this.options.onChange) {
            this.options.onChange(index, this.options.tabs[index]);
        }
    }

    getPanel(index) {
        return this.container.querySelector(`.tab-panel[data-panel="${index}"]`);
    }
}

// ==================== Pagination 分页 ====================

class Pagination {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' 
            ? document.querySelector(container) 
            : container;
        this.options = {
            total: options.total || 0,
            pageSize: options.pageSize || 10,
            currentPage: options.currentPage || 1,
            maxButtons: options.maxButtons || 7,
            onChange: options.onChange || null,
        };
        this.render();
        this.bindEvents();
    }

    get totalPages() {
        return Math.ceil(this.options.total / this.options.pageSize);
    }

    render() {
        const { currentPage, maxButtons } = this.options;
        const totalPages = this.totalPages;
        
        if (totalPages <= 1) {
            this.container.innerHTML = '';
            return;
        }
        
        let html = '<div class="pagination">';
        
        // 上一页
        html += `
            <button class="page-btn" data-page="prev" ${currentPage === 1 ? 'disabled' : ''}>
                ‹
            </button>
        `;
        
        // 页码按钮
        const pages = this.getPageNumbers();
        pages.forEach(page => {
            if (page === '...') {
                html += '<span class="page-ellipsis">...</span>';
            } else {
                html += `
                    <button class="page-btn ${page === currentPage ? 'active' : ''}" 
                            data-page="${page}">
                        ${page}
                    </button>
                `;
            }
        });
        
        // 下一页
        html += `
            <button class="page-btn" data-page="next" ${currentPage === totalPages ? 'disabled' : ''}>
                ›
            </button>
        `;
        
        html += '</div>';
        this.container.innerHTML = html;
    }

    getPageNumbers() {
        const { currentPage, maxButtons } = this.options;
        const totalPages = this.totalPages;
        const pages = [];
        
        if (totalPages <= maxButtons) {
            for (let i = 1; i <= totalPages; i++) {
                pages.push(i);
            }
        } else {
            const half = Math.floor(maxButtons / 2);
            let start = Math.max(1, currentPage - half);
            let end = Math.min(totalPages, start + maxButtons - 1);
            
            if (end - start < maxButtons - 1) {
                start = Math.max(1, end - maxButtons + 1);
            }
            
            if (start > 1) {
                pages.push(1);
                if (start > 2) pages.push('...');
            }
            
            for (let i = start; i <= end; i++) {
                if (i !== 1 && i !== totalPages) {
                    pages.push(i);
                }
            }
            
            if (end < totalPages) {
                if (end < totalPages - 1) pages.push('...');
                pages.push(totalPages);
            }
        }
        
        return pages;
    }

    bindEvents() {
        this.container.addEventListener('click', (e) => {
            const btn = e.target.closest('.page-btn');
            if (btn && !btn.disabled) {
                const page = btn.dataset.page;
                if (page === 'prev') {
                    this.setPage(this.options.currentPage - 1);
                } else if (page === 'next') {
                    this.setPage(this.options.currentPage + 1);
                } else {
                    this.setPage(parseInt(page));
                }
            }
        });
    }

    setPage(page) {
        page = Math.max(1, Math.min(page, this.totalPages));
        if (page !== this.options.currentPage) {
            this.options.currentPage = page;
            this.render();
            if (this.options.onChange) {
                this.options.onChange(page);
            }
        }
    }

    update(options) {
        Object.assign(this.options, options);
        this.render();
    }
}

// ==================== Table 表格 ====================

class DataTable {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' 
            ? document.querySelector(container) 
            : container;
        this.options = {
            columns: options.columns || [],
            data: options.data || [],
            emptyText: options.emptyText || '暂无数据',
            loading: false,
            selectable: options.selectable || false,
            onRowClick: options.onRowClick || null,
        };
        this.render();
    }

    render() {
        const { columns, data, emptyText, loading, selectable } = this.options;
        
        let html = '<div class="data-table-wrapper">';
        
        if (loading) {
            html += '<div class="table-loading"><div class="loading-spinner"></div></div>';
        }
        
        html += '<table class="data-table">';
        
        // 表头
        html += '<thead><tr>';
        if (selectable) {
            html += '<th class="col-checkbox"><input type="checkbox" class="select-all"></th>';
        }
        columns.forEach(col => {
            html += `<th class="${col.class || ''}" style="${col.width ? `width:${col.width}` : ''}">${escapeHtml(col.label)}</th>`;
        });
        html += '</tr></thead>';
        
        // 表体
        html += '<tbody>';
        if (data.length === 0) {
            html += `<tr class="empty-row"><td colspan="${columns.length + (selectable ? 1 : 0)}">${escapeHtml(emptyText)}</td></tr>`;
        } else {
            data.forEach((row, rowIndex) => {
                html += `<tr data-index="${rowIndex}">`;
                if (selectable) {
                    html += `<td class="col-checkbox"><input type="checkbox" class="row-select" data-index="${rowIndex}"></td>`;
                }
                columns.forEach(col => {
                    const value = col.render 
                        ? col.render(row[col.key], row, rowIndex) 
                        : escapeHtml(row[col.key] ?? '');
                    html += `<td class="${col.class || ''}">${value}</td>`;
                });
                html += '</tr>';
            });
        }
        html += '</tbody>';
        
        html += '</table></div>';
        this.container.innerHTML = html;
        
        this.bindEvents();
    }

    bindEvents() {
        // 行点击
        if (this.options.onRowClick) {
            this.container.querySelectorAll('tbody tr:not(.empty-row)').forEach(tr => {
                tr.style.cursor = 'pointer';
                tr.addEventListener('click', (e) => {
                    if (!e.target.closest('.row-select')) {
                        const index = parseInt(tr.dataset.index);
                        this.options.onRowClick(this.options.data[index], index);
                    }
                });
            });
        }
        
        // 全选
        const selectAll = this.container.querySelector('.select-all');
        if (selectAll) {
            selectAll.addEventListener('change', (e) => {
                this.container.querySelectorAll('.row-select').forEach(cb => {
                    cb.checked = e.target.checked;
                });
            });
        }
    }

    setData(data) {
        this.options.data = data;
        this.render();
    }

    setLoading(loading) {
        this.options.loading = loading;
        this.render();
    }

    getSelected() {
        const selected = [];
        this.container.querySelectorAll('.row-select:checked').forEach(cb => {
            const index = parseInt(cb.dataset.index);
            selected.push(this.options.data[index]);
        });
        return selected;
    }
}

// ==================== Form 表单工具 ====================

class Form {
    constructor(form) {
        this.form = typeof form === 'string' ? document.querySelector(form) : form;
    }

    // 获取表单数据
    getData() {
        const formData = new FormData(this.form);
        const data = {};
        formData.forEach((value, key) => {
            if (data[key]) {
                if (!Array.isArray(data[key])) {
                    data[key] = [data[key]];
                }
                data[key].push(value);
            } else {
                data[key] = value;
            }
        });
        return data;
    }

    // 设置表单数据
    setData(data) {
        Object.entries(data).forEach(([key, value]) => {
            const field = this.form.elements[key];
            if (field) {
                if (field.type === 'checkbox') {
                    field.checked = !!value;
                } else if (field.type === 'radio') {
                    const radio = this.form.querySelector(`input[name="${key}"][value="${value}"]`);
                    if (radio) radio.checked = true;
                } else {
                    field.value = value;
                }
            }
        });
    }

    // 验证表单
    validate() {
        const errors = [];
        this.form.querySelectorAll('[required]').forEach(field => {
            if (!field.value.trim()) {
                errors.push({
                    field: field.name,
                    message: `${field.dataset.label || field.name} 不能为空`,
                });
                field.classList.add('error');
            } else {
                field.classList.remove('error');
            }
        });
        
        // 邮箱验证
        this.form.querySelectorAll('[type="email"]').forEach(field => {
            if (field.value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(field.value)) {
                errors.push({
                    field: field.name,
                    message: '请输入有效的邮箱地址',
                });
                field.classList.add('error');
            }
        });
        
        return errors;
    }

    // 重置表单
    reset() {
        this.form.reset();
        this.form.querySelectorAll('.error').forEach(el => el.classList.remove('error'));
    }

    // 禁用/启用表单
    setDisabled(disabled) {
        this.form.querySelectorAll('input, select, textarea, button').forEach(el => {
            el.disabled = disabled;
        });
    }
}

// ==================== FileUpload 文件上传 ====================

class FileUpload {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' 
            ? document.querySelector(container) 
            : container;
        this.options = {
            accept: options.accept || '*',
            multiple: options.multiple || false,
            maxSize: options.maxSize || 10 * 1024 * 1024, // 10MB
            onSelect: options.onSelect || null,
            onUpload: options.onUpload || null,
            onError: options.onError || null,
        };
        this.files = [];
        this.render();
        this.bindEvents();
    }

    render() {
        this.container.innerHTML = `
            <div class="file-upload">
                <input type="file" class="file-input"
                       accept="${this.options.accept}"
                       ${this.options.multiple ? 'multiple' : ''}>
                <div class="file-dropzone">
                    <div class="dropzone-icon"><i class="fas fa-folder-open"></i></div>
                    <p class="dropzone-text">拖拽文件到此处，或 <span class="dropzone-link">点击上传</span></p>
                    <p class="dropzone-hint">支持 ${this.options.accept}，最大 ${this.formatSize(this.options.maxSize)}</p>
                </div>
                <div class="file-list"></div>
            </div>
        `;
    }

    bindEvents() {
        const input = this.container.querySelector('.file-input');
        const dropzone = this.container.querySelector('.file-dropzone');
        
        // 点击上传
        dropzone.addEventListener('click', () => input.click());
        
        // 文件选择
        input.addEventListener('change', (e) => {
            this.handleFiles(e.target.files);
        });
        
        // 拖拽
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        
        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });
        
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            this.handleFiles(e.dataTransfer.files);
        });
    }

    handleFiles(fileList) {
        const files = Array.from(fileList);
        const validFiles = [];
        
        files.forEach(file => {
            if (file.size > this.options.maxSize) {
                if (this.options.onError) {
                    this.options.onError(`文件 ${file.name} 超过大小限制`);
                }
                return;
            }
            validFiles.push(file);
        });
        
        if (this.options.multiple) {
            this.files = [...this.files, ...validFiles];
        } else {
            this.files = validFiles.slice(0, 1);
        }
        
        this.renderFileList();
        
        if (this.options.onSelect) {
            this.options.onSelect(this.files);
        }
    }

    renderFileList() {
        const list = this.container.querySelector('.file-list');
        
        if (this.files.length === 0) {
            list.innerHTML = '';
            return;
        }
        
        list.innerHTML = this.files.map((file, index) => `
            <div class="file-item" data-index="${index}">
                <span class="file-icon">${this.getFileIcon(file.type)}</span>
                <span class="file-name">${escapeHtml(file.name)}</span>
                <span class="file-size">${this.formatSize(file.size)}</span>
                <button class="file-remove" data-index="${index}"><i class="fas fa-times"></i></button>
            </div>
        `).join('');
        
        // 删除按钮
        list.querySelectorAll('.file-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const index = parseInt(btn.dataset.index);
                this.files.splice(index, 1);
                this.renderFileList();
            });
        });
    }

    getFileIcon(type) {
        if (type.includes('pdf')) return '<i class="fas fa-file-pdf"></i>';
        if (type.includes('image')) return '<i class="fas fa-file-image"></i>';
        if (type.includes('text') || type.includes('markdown')) return '<i class="fas fa-file-alt"></i>';
        return '<i class="fas fa-file"></i>';
    }

    formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    getFiles() {
        return this.files;
    }

    clear() {
        this.files = [];
        this.renderFileList();
        this.container.querySelector('.file-input').value = '';
    }
}

// ==================== 状态徽章 ====================

function renderStatusBadge(status) {
    const statusMap = {
        pending: { label: '等待中', class: 'badge-secondary' },
        running: { label: '运行中', class: 'badge-primary' },
        completed: { label: '已完成', class: 'badge-success' },
        failed: { label: '失败', class: 'badge-danger' },
        cancelled: { label: '已取消', class: 'badge-warning' },
    };
    
    const info = statusMap[status] || { label: status, class: 'badge-secondary' };
    return `<span class="badge ${info.class}">${info.label}</span>`;
}

// ==================== 步骤名称映射 ====================
// 与后端 frontend/config.py TaskConfig.PIPELINE_STEPS 保持一致

const STEP_NAMES = {
    0: '未开始',
    1: 'MEKG构建',
    2: '大纲生成',
    3: '内容生成',
    4: '文本优化',
    5: '表格生成',
    6: '视觉元素',
    7: '质量评估',
    8: '批判分析',
    9: 'LaTeX生成',
    10: '可视化导出',
    11: '已完成',
    // 兼容旧的字符串格式
    'NOT_STARTED': '未开始',
    'MEKG_BUILT': 'MEKG构建',
    'OUTLINE_GENERATED': '大纲生成',
    'CONTENT_GENERATED': '内容生成',
    'POST_REFINED': '文本优化',
    'TABLES_GENERATED': '表格生成',
    'VISUALS_GENERATED': '视觉元素',
    'EVALUATED': '质量评估',
    'CRITICAL_ANALYZED': '批判分析',
    'LATEX_GENERATED': 'LaTeX生成',
    'VISUALIZATION_DONE': '可视化导出',
    'COMPLETED': '已完成',
};

// 步骤数字到名称的映射
const STEP_NUMBER_TO_NAME = {
    0: 'NOT_STARTED',
    1: 'MEKG_BUILT',
    2: 'OUTLINE_GENERATED',
    3: 'CONTENT_GENERATED',
    4: 'POST_REFINED',
    5: 'TABLES_GENERATED',
    6: 'VISUALS_GENERATED',
    7: 'EVALUATED',
    8: 'CRITICAL_ANALYZED',
    9: 'LATEX_GENERATED',
    10: 'VISUALIZATION_DONE',
    11: 'COMPLETED',
};

function getStepName(step) {
    // 支持数字和字符串两种格式
    if (typeof step === 'number') {
        return STEP_NAMES[step] || `步骤 ${step}`;
    }
    return STEP_NAMES[step] || step || '-';
}

function getStepIndex(step) {
    // 如果是数字，直接返回
    if (typeof step === 'number') {
        return step;
    }
    // 如果是字符串，查找对应的数字
    for (const [num, name] of Object.entries(STEP_NUMBER_TO_NAME)) {
        if (name === step) {
            return parseInt(num);
        }
    }
    return -1;
}

// ==================== Skeleton 骨架屏 ====================

class Skeleton {
    /**
     * 创建骨架屏元素
     * @param {string} type - 骨架屏类型
     * @param {object} options - 配置选项
     * @returns {string} HTML字符串
     */
    static create(type, options = {}) {
        const templates = {
            // 文本行
            text: (opts) => {
                const width = opts.width || '100%';
                const size = opts.size || 'md';
                const sizeClass = size === 'sm' ? 'skeleton-text-sm' :
                                  size === 'lg' ? 'skeleton-text-lg' :
                                  size === 'xl' ? 'skeleton-text-xl' : '';
                return `<div class="skeleton-box skeleton-text ${sizeClass}" style="width: ${width}"></div>`;
            },
            
            // 标题
            title: (opts) => {
                const width = opts.width || '60%';
                return `<div class="skeleton-box skeleton-title" style="width: ${width}"></div>`;
            },
            
            // 头像
            avatar: (opts) => {
                const size = opts.size || 'md';
                const sizeClass = size === 'sm' ? 'skeleton-avatar-sm' :
                                  size === 'lg' ? 'skeleton-avatar-lg' : '';
                return `<div class="skeleton-box skeleton-avatar ${sizeClass}"></div>`;
            },
            
            // 图片
            image: (opts) => {
                const size = opts.size || 'md';
                const sizeClass = size === 'sm' ? 'skeleton-image-sm' :
                                  size === 'lg' ? 'skeleton-image-lg' : '';
                return `<div class="skeleton-box skeleton-image ${sizeClass}"></div>`;
            },
            
            // 按钮
            button: (opts) => {
                const size = opts.size || 'md';
                const sizeClass = size === 'sm' ? 'skeleton-button-sm' : '';
                const width = opts.width || (size === 'sm' ? '80px' : '120px');
                return `<div class="skeleton-box skeleton-button ${sizeClass}" style="width: ${width}"></div>`;
            },
            
            // 徽章
            badge: (opts) => {
                const width = opts.width || '80px';
                return `<div class="skeleton-box skeleton-badge" style="width: ${width}"></div>`;
            },
            
            // 任务卡片
            taskCard: (opts) => {
                return `
                    <div class="skeleton-task-card">
                        <div class="skeleton-header">
                            <div class="skeleton-title-group">
                                <div class="skeleton-box skeleton-title" style="width: 70%; margin-bottom: 8px;"></div>
                                <div class="skeleton-box skeleton-text skeleton-text-sm" style="width: 40%;"></div>
                            </div>
                            <div class="skeleton-box skeleton-badge"></div>
                        </div>
                        <div class="skeleton-box skeleton-progress"></div>
                        <div class="skeleton-footer">
                            <div class="skeleton-box skeleton-text skeleton-text-sm" style="width: 100px;"></div>
                            <div class="skeleton-box skeleton-text skeleton-text-sm" style="width: 80px;"></div>
                        </div>
                    </div>
                `;
            },
            
            // 统计卡片
            statCard: (opts) => {
                return `
                    <div class="skeleton-stat-card">
                        <div class="skeleton-box skeleton-icon"></div>
                        <div class="skeleton-info">
                            <div class="skeleton-box skeleton-text skeleton-text-xl" style="width: 60px; margin-bottom: 4px;"></div>
                            <div class="skeleton-box skeleton-text skeleton-text-sm" style="width: 80px;"></div>
                        </div>
                    </div>
                `;
            },
            
            // 列表项
            listItem: (opts) => {
                const showAvatar = opts.showAvatar !== false;
                return `
                    <div class="skeleton-list-item">
                        ${showAvatar ? '<div class="skeleton-box skeleton-avatar skeleton-avatar-sm"></div>' : ''}
                        <div class="skeleton-content" style="flex: 1;">
                            <div class="skeleton-box skeleton-text" style="width: 80%; margin-bottom: 6px;"></div>
                            <div class="skeleton-box skeleton-text skeleton-text-sm" style="width: 50%;"></div>
                        </div>
                    </div>
                `;
            },
            
            // 表单组
            formGroup: (opts) => {
                return `
                    <div class="skeleton-form-group">
                        <div class="skeleton-box skeleton-form-label"></div>
                        <div class="skeleton-box skeleton-form-input"></div>
                    </div>
                `;
            },
            
            // 表格行
            tableRow: (opts) => {
                const cols = opts.cols || 4;
                let cells = '';
                for (let i = 0; i < cols; i++) {
                    const width = i === 0 ? '70%' : '60%';
                    cells += `<div class="skeleton-box skeleton-text" style="width: ${width};"></div>`;
                }
                return `<div class="skeleton-table-row">${cells}</div>`;
            },
            
            // 段落（多行文本）
            paragraph: (opts) => {
                const lines = opts.lines || 3;
                let html = '';
                for (let i = 0; i < lines; i++) {
                    const width = i === lines - 1 ? '60%' : '100%';
                    html += `<div class="skeleton-box skeleton-text" style="width: ${width};"></div>`;
                }
                return `<div class="skeleton-paragraph">${html}</div>`;
            },
        };
        
        const template = templates[type];
        if (template) {
            return template(options);
        }
        
        console.warn(`Unknown skeleton type: ${type}`);
        return '';
    }
    
    /**
     * 创建多个骨架屏元素
     * @param {string} type - 骨架屏类型
     * @param {number} count - 数量
     * @param {object} options - 配置选项
     * @returns {string} HTML字符串
     */
    static createMultiple(type, count, options = {}) {
        let html = '';
        for (let i = 0; i < count; i++) {
            html += this.create(type, options);
        }
        return html;
    }
    
    /**
     * 创建仪表盘骨架屏
     * @param {object} options - 配置选项
     * @returns {string} HTML字符串
     */
    static dashboard(options = {}) {
        const statCount = options.statCount || 4;
        const taskCount = options.taskCount || 5;
        
        return `
            <div class="skeleton-dashboard">
                <div class="skeleton-page-header">
                    <div class="skeleton-box skeleton-page-title"></div>
                    <div class="skeleton-box skeleton-page-subtitle"></div>
                </div>
                <div class="skeleton-dashboard-stats">
                    ${this.createMultiple('statCard', statCount)}
                </div>
                <div class="skeleton-dashboard-content">
                    <div class="skeleton-content-area">
                        ${this.createMultiple('taskCard', taskCount)}
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * 创建任务列表骨架屏
     * @param {number} count - 任务卡片数量
     * @returns {string} HTML字符串
     */
    static taskList(count = 5) {
        return `
            <div class="skeleton-content-area">
                ${this.createMultiple('taskCard', count)}
            </div>
        `;
    }
    
    /**
     * 创建表单骨架屏
     * @param {number} fieldCount - 表单字段数量
     * @returns {string} HTML字符串
     */
    static form(fieldCount = 4) {
        return `
            <div class="skeleton-form">
                ${this.createMultiple('formGroup', fieldCount)}
                <div style="display: flex; gap: 16px; margin-top: 24px;">
                    <div class="skeleton-box skeleton-button" style="width: 100px;"></div>
                    <div class="skeleton-box skeleton-button" style="width: 80px;"></div>
                </div>
            </div>
        `;
    }
    
    /**
     * 创建表格骨架屏
     * @param {object} options - 配置选项
     * @returns {string} HTML字符串
     */
    static table(options = {}) {
        const rows = options.rows || 5;
        const cols = options.cols || 4;
        
        let headerCells = '';
        for (let i = 0; i < cols; i++) {
            headerCells += `<div class="skeleton-box skeleton-text skeleton-text-sm" style="width: 60%;"></div>`;
        }
        
        return `
            <div class="skeleton-table">
                <div class="skeleton-table-header">${headerCells}</div>
                ${this.createMultiple('tableRow', rows, { cols })}
            </div>
        `;
    }
    
    /**
     * 创建详情页骨架屏
     * @returns {string} HTML字符串
     */
    static detail() {
        return `
            <div class="skeleton-detail">
                <div class="skeleton-page-header" style="margin-bottom: 32px;">
                    <div class="skeleton-box skeleton-page-title" style="width: 300px;"></div>
                    <div class="skeleton-box skeleton-page-subtitle" style="width: 200px;"></div>
                </div>
                <div class="skeleton-card" style="margin-bottom: 24px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 24px;">
                        <div class="skeleton-box skeleton-badge"></div>
                        <div class="skeleton-box skeleton-text skeleton-text-sm" style="width: 150px;"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px;">
                        ${this.createMultiple('text', 6, { width: '80%' })}
                    </div>
                    <div class="skeleton-box skeleton-progress" style="height: 8px; margin-bottom: 24px;"></div>
                    <div style="display: flex; gap: 12px;">
                        ${this.createMultiple('button', 3)}
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * 在容器中显示骨架屏
     * @param {HTMLElement|string} container - 容器元素或选择器
     * @param {string} type - 骨架屏类型
     * @param {object} options - 配置选项
     */
    static show(container, type, options = {}) {
        const el = typeof container === 'string' ? document.querySelector(container) : container;
        if (!el) return;
        
        let html = '';
        switch (type) {
            case 'dashboard':
                html = this.dashboard(options);
                break;
            case 'taskList':
                html = this.taskList(options.count);
                break;
            case 'form':
                html = this.form(options.fieldCount);
                break;
            case 'table':
                html = this.table(options);
                break;
            case 'detail':
                html = this.detail();
                break;
            default:
                html = this.create(type, options);
        }
        
        el.innerHTML = html;
    }
    
    /**
     * 隐藏骨架屏并显示内容
     * @param {HTMLElement|string} container - 容器元素或选择器
     * @param {string} content - 要显示的内容
     * @param {boolean} animate - 是否使用动画
     */
    static hide(container, content, animate = true) {
        const el = typeof container === 'string' ? document.querySelector(container) : container;
        if (!el) return;
        
        if (animate) {
            el.classList.add('skeleton-to-content');
            setTimeout(() => {
                el.innerHTML = content;
                el.classList.remove('skeleton-to-content');
                el.classList.add('content-loaded');
                setTimeout(() => {
                    el.classList.remove('content-loaded');
                }, 400);
            }, 300);
        } else {
            el.innerHTML = content;
        }
    }
}

// ==================== 图片懒加载 ====================

class LazyImage {
    static observer = null;
    
    static init() {
        if (this.observer) return;
        
        this.observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    this.loadImage(img);
                    this.observer.unobserve(img);
                }
            });
        }, {
            rootMargin: '50px 0px',
            threshold: 0.01
        });
    }
    
    static observe(img) {
        this.init();
        
        // 设置占位符
        if (!img.dataset.src) {
            img.dataset.src = img.src;
        }
        
        // 显示占位符
        const placeholder = img.dataset.placeholder || '';
        if (placeholder) {
            img.src = placeholder;
        } else {
            img.style.background = 'var(--bg-tertiary)';
        }
        
        img.classList.add('lazy-image');
        this.observer.observe(img);
    }
    
    static loadImage(img) {
        const src = img.dataset.src;
        if (!src) return;
        
        const tempImg = new Image();
        tempImg.onload = () => {
            img.src = src;
            img.classList.remove('lazy-image');
            img.classList.add('image-loaded');
        };
        tempImg.onerror = () => {
            img.classList.add('image-error');
        };
        tempImg.src = src;
    }
    
    static observeAll(selector = 'img[data-src]') {
        document.querySelectorAll(selector).forEach(img => {
            this.observe(img);
        });
    }
}

// ==================== 内容加载动画 ====================

class ContentLoader {
    /**
     * 显示加载状态
     * @param {HTMLElement|string} container - 容器
     * @param {string} type - 加载类型 (spinner, skeleton, placeholder)
     * @param {object} options - 配置选项
     */
    static show(container, type = 'spinner', options = {}) {
        const el = typeof container === 'string' ? document.querySelector(container) : container;
        if (!el) return;
        
        el.dataset.originalContent = el.innerHTML;
        
        switch (type) {
            case 'spinner':
                el.innerHTML = `
                    <div class="loading-indicator">
                        <div class="spinner"></div>
                        <span class="loading-text">${options.message || '加载中...'}</span>
                    </div>
                `;
                break;
            case 'skeleton':
                Skeleton.show(el, options.skeletonType || 'paragraph', options);
                break;
            case 'placeholder':
                el.innerHTML = `
                    <div class="loading-placeholder">
                        <div class="spinner"></div>
                        <p>${options.message || '正在加载内容...'}</p>
                    </div>
                `;
                break;
        }
    }
    
    /**
     * 隐藏加载状态并显示内容
     * @param {HTMLElement|string} container - 容器
     * @param {string} content - 要显示的内容（可选，不传则恢复原内容）
     * @param {boolean} animate - 是否使用动画
     */
    static hide(container, content = null, animate = true) {
        const el = typeof container === 'string' ? document.querySelector(container) : container;
        if (!el) return;
        
        const newContent = content !== null ? content : (el.dataset.originalContent || '');
        
        if (animate) {
            el.style.opacity = '0';
            el.style.transform = 'translateY(8px)';
            
            setTimeout(() => {
                el.innerHTML = newContent;
                el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                el.style.opacity = '1';
                el.style.transform = 'translateY(0)';
                
                setTimeout(() => {
                    el.style.transition = '';
                    el.style.opacity = '';
                    el.style.transform = '';
                }, 300);
            }, 100);
        } else {
            el.innerHTML = newContent;
        }
        
        delete el.dataset.originalContent;
    }
    
    /**
     * 按钮加载状态
     * @param {HTMLElement|string} btn - 按钮元素
     * @param {boolean} loading - 是否加载中
     * @param {string} loadingText - 加载时显示的文本
     */
    static button(btn, loading = true, loadingText = '处理中...') {
        const el = typeof btn === 'string' ? document.querySelector(btn) : btn;
        if (!el) return;
        
        if (loading) {
            el.dataset.originalText = el.innerHTML;
            el.disabled = true;
            el.classList.add('btn-loading');
            if (loadingText) {
                el.innerHTML = `<span class="btn-spinner"></span> ${loadingText}`;
            }
        } else {
            el.disabled = false;
            el.classList.remove('btn-loading');
            if (el.dataset.originalText) {
                el.innerHTML = el.dataset.originalText;
                delete el.dataset.originalText;
            }
        }
    }
}

// ==================== 导出 ====================

window.Toast = Toast;
window.Modal = Modal;
window.Loading = Loading;
window.Progress = Progress;
window.Tabs = Tabs;
window.Pagination = Pagination;
window.DataTable = DataTable;
window.Form = Form;
window.FileUpload = FileUpload;
window.Skeleton = Skeleton;
window.LazyImage = LazyImage;
window.ContentLoader = ContentLoader;
window.renderStatusBadge = renderStatusBadge;
window.getStepName = getStepName;
window.getStepIndex = getStepIndex;
window.STEP_NAMES = STEP_NAMES;
window.STEP_NUMBER_TO_NAME = STEP_NUMBER_TO_NAME;
window.formatDate = formatDate;
window.formatRelativeTime = formatRelativeTime;
window.escapeHtml = escapeHtml;
window.generateId = generateId;