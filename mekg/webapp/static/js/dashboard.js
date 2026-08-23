// State
let network = null;
let ws = null;
let isConnected = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    initGraph();
    refreshGraph();
});

// WebSocket Handling
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/stream`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        isConnected = true;
        updateConnectionStatus('系统在线', 'success');
    };
    
    ws.onclose = () => {
        isConnected = false;
        updateConnectionStatus('离线 - 尝试重连...', 'danger');
        // Reconnect after 3s
        setTimeout(initWebSocket, 3000);
    };
    
    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'log') {
            appendLog(msg.data);
        } else if (msg.type === 'status') {
            updateStatus(msg.data);
        }
    };
}

function updateConnectionStatus(text, type) {
    const el = document.getElementById('connection-status');
    el.textContent = text;
    el.className = `badge bg-${type}`;
}

function appendLog(logText) {
    const terminal = document.getElementById('terminal');
    // Clear initial placeholder
    if (terminal.querySelector('.text-muted')) {
        terminal.innerHTML = '';
    }
    
    // Parse timestamp [HH:MM:SS]
    const match = logText.match(/^\[(.*?)\] (.*)/);
    let html = '';
    if (match) {
        html = `<div class="log-entry"><span class="log-time">${match[1]}</span>${match[2]}</div>`;
    } else {
        html = `<div class="log-entry">${logText}</div>`;
    }
    
    terminal.insertAdjacentHTML('beforeend', html);
    // Auto scroll (强制滚动到底部)
    requestAnimationFrame(() => {
        terminal.scrollTop = terminal.scrollHeight;
    });
    
    // Update count
    const countEl = document.getElementById('log-count');
    countEl.textContent = terminal.children.length;
}

function updateStatus(data) {
    // Update buttons
    document.getElementById('btn-start').disabled = data.is_running;
    document.getElementById('btn-stop').disabled = !data.is_running;
    
    // Update badges
    const statusEl = document.getElementById('crawler-status');
    statusEl.textContent = data.is_running ? '全速运行中' : '待机';
    statusEl.className = `badge bg-${data.is_running ? 'success' : 'secondary'}`;
    
    // Update stats
    if (data.stats) {
        document.getElementById('stat-papers').textContent = data.stats.papers_crawled || 0;
        document.getElementById('stat-communities').textContent = data.stats.communities_detected || 0;
    }
    
    // Update task
    document.getElementById('current-task').textContent = data.current_task || '系统待机中...';
}

// Control Actions
async function startCrawler() {
    try {
        await fetch('/start', { method: 'POST' });
    } catch (e) {
        console.error(e);
    }
}

async function stopCrawler() {
    try {
        await fetch('/stop', { method: 'POST' });
    } catch (e) {
        console.error(e);
    }
}

// 智能获取子图谱
async function fetchSubgraph() {
    const topicInput = document.getElementById('topic-input');
    const topic = topicInput.value.trim();
    
    if (!topic) {
        alert('请输入 Topic');
        return;
    }
    
    const btn = document.querySelector('button[onclick="fetchSubgraph()"]');
    const originalIcon = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
    btn.disabled = true;
    
    appendLog(`[SYSTEM] 正在智能获取 Topic: ${topic}...`);
    
    try {
        // 调用智能接口
        const res = await fetch(`/subgraph/${encodeURIComponent(topic)}`);
        const data = await res.json();
        
        if (data.error) {
            appendLog(`[ERROR] 获取失败: ${data.error}`);
            alert(`获取失败: ${data.error}`);
        } else {
            const status = data.status;
            appendLog(`[SUCCESS] 获取成功! 状态: ${status.reason}`);
            
            // 如果有数据，刷新图谱
            if (data.subgraph && data.subgraph.papers && data.subgraph.papers.length > 0) {
                appendLog(`[GRAPH] 加载 ${data.subgraph.papers.length} 篇论文到视图...`);
                // 这里我们简单地刷新整个图谱，或者可以只显示子图谱
                // 为了演示效果，我们刷新全图，因为新数据已经入库
                refreshGraph();
            } else {
                appendLog(`[WARN] 未找到相关论文数据`);
            }
        }
    } catch (e) {
        console.error(e);
        appendLog(`[ERROR] 网络请求失败: ${e.message}`);
    } finally {
        btn.innerHTML = originalIcon;
        btn.disabled = false;
    }
}

// 社区颜色调色板 - 鲜艳且易区分
const COMMUNITY_COLORS = [
    '#FF6B6B', // 红色
    '#4ECDC4', // 青色
    '#45B7D1', // 蓝色
    '#96CEB4', // 绿色
    '#FFEAA7', // 黄色
    '#DDA0DD', // 紫色
    '#98D8C8', // 薄荷绿
    '#F7DC6F', // 金色
    '#BB8FCE', // 淡紫
    '#85C1E9', // 天蓝
    '#F8B500', // 橙色
    '#00CED1', // 深青
    '#FF69B4', // 粉色
    '#32CD32', // 酸橙绿
    '#FF7F50', // 珊瑚色
];

// 关系类型颜色
const RELATION_COLORS = {
    'CITES': '#00d2ff',
    'PROPOSES': '#ff6b6b',
    'BELONGS_TO': '#4ecdc4',
    'USES': '#ffeaa7',
    'EXTENDS': '#dda0dd',
    'COMPARES': '#98d8c8',
    'default': '#888888'
};

// Graph Visualization
function initGraph() {
    const container = document.getElementById('mynetwork');
    const data = { nodes: [], edges: [] };
    const options = {
        nodes: {
            shape: 'dot',
            size: 16,
            font: {
                color: '#ffffff',
                size: 14,
                face: 'Inter',
                strokeWidth: 3,
                strokeColor: '#000000'
            },
            borderWidth: 3,
            shadow: {
                enabled: true,
                color: 'rgba(0,0,0,0.5)',
                size: 10,
                x: 3,
                y: 3
            }
        },
        edges: {
            color: {
                color: '#00d2ff',
                highlight: '#ff6b6b',
                hover: '#ffeaa7',
                opacity: 0.9
            },
            smooth: {
                type: 'curvedCW',
                roundness: 0.2
            },
            width: 2,
            arrows: {
                to: {
                    enabled: true,
                    scaleFactor: 0.8,
                    type: 'arrow'
                }
            },
            font: {
                color: '#ffffff',
                size: 10,
                face: 'Inter',
                strokeWidth: 2,
                strokeColor: '#000000',
                align: 'middle'
            },
            shadow: {
                enabled: true,
                color: 'rgba(0,210,255,0.3)',
                size: 5
            }
        },
        physics: {
            forceAtlas2Based: {
                gravitationalConstant: -50,
                centralGravity: 0.005,
                springLength: 150,
                springConstant: 0.1,
                damping: 0.4
            },
            maxVelocity: 50,
            solver: 'forceAtlas2Based',
            timestep: 0.35,
            stabilization: {
                enabled: true,
                iterations: 500,
                updateInterval: 25
            }
        },
        interaction: {
            hover: true,
            tooltipDelay: 100,
            hideEdgesOnDrag: false,
            navigationButtons: true,
            keyboard: true,
            zoomView: true
        },
        groups: {
            paper: {
                shape: 'dot',
                size: 18
            },
            topic: {
                shape: 'diamond',
                size: 25
            },
            method: {
                shape: 'triangle',
                size: 22
            },
            semanticentity: {
                shape: 'star',
                size: 20
            }
        }
    };
    
    network = new vis.Network(container, data, options);
    
    network.on("click", function (params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            showNodeDetails(nodeId);
        } else {
            closeDetails();
        }
    });
    
    // 双击聚焦节点
    network.on("doubleClick", function (params) {
        if (params.nodes.length > 0) {
            network.focus(params.nodes[0], {
                scale: 1.5,
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }
            });
        }
    });
}

async function refreshGraph() {
    const loading = document.getElementById('graph-loading');
    loading.classList.remove('d-none');
    
    try {
        const res = await fetch('/graph/data?limit=500');
        const data = await res.json();
        
        if (data.nodes) {
            // 收集社区信息
            const communitySet = new Set();
            data.nodes.forEach(n => {
                if (n.community_id !== undefined && n.community_id !== null) {
                    communitySet.add(n.community_id);
                }
            });
            const communities = Array.from(communitySet).sort((a, b) => a - b);
            
            // Transform for vis.js
            const nodes = new vis.DataSet(data.nodes.map(n => {
                const group = (n.group || 'paper').toLowerCase();
                let color, size, shape;
                
                if (group === 'paper') {
                    // 论文节点 - 根据社区分配颜色
                    const commId = n.community_id !== undefined ? n.community_id : -1;
                    color = commId >= 0 ? COMMUNITY_COLORS[commId % COMMUNITY_COLORS.length] : '#007bff';
                    size = 18;
                    shape = 'dot';
                } else if (group === 'topic') {
                    color = '#a855f7';
                    size = 30;
                    shape = 'diamond';
                } else if (group === 'method' || group === 'semanticentity') {
                    color = '#ff6b6b';
                    size = 22;
                    shape = 'triangle';
                } else {
                    color = '#4ecdc4';
                    size = 16;
                    shape = 'dot';
                }
                
                return {
                    id: n.id,
                    label: truncateLabel(n.label || n.id, 25),
                    title: buildTooltip(n), // 丰富的 Tooltip
                    group: group,
                    color: {
                        background: color,
                        border: shadeColor(color, -20),
                        highlight: {
                            background: shadeColor(color, 20),
                            border: '#ffffff'
                        },
                        hover: {
                            background: shadeColor(color, 10),
                            border: '#ffffff'
                        }
                    },
                    size: size,
                    shape: shape,
                    community_id: n.community_id
                };
            }));
            
            // 处理边 - 添加颜色和标签
            const edges = new vis.DataSet(data.edges.map(e => {
                const relType = e.label || 'CITES';
                const edgeColor = RELATION_COLORS[relType] || RELATION_COLORS['default'];
                
                return {
                    from: e.from,
                    to: e.to,
                    label: relType,
                    title: `${relType}${e.reasoning ? '\n' + e.reasoning : ''}`,
                    color: {
                        color: edgeColor,
                        highlight: '#ffffff',
                        hover: '#ffeaa7',
                        opacity: 0.85
                    },
                    width: relType === 'CITES' ? 2 : 3,
                    dashes: relType === 'BELONGS_TO' ? [5, 5] : false
                };
            }));
            
            network.setData({ nodes, edges });
            
            // 更新统计和图例
            updateGraphStats(nodes.length, edges.length, communities.length);
            updateLegend(communities);
        }
    } catch (e) {
        console.error("Graph refresh failed", e);
    } finally {
        loading.classList.add('d-none');
    }
}

// 截断标签
function truncateLabel(label, maxLen) {
    if (!label) return '';
    return label.length > maxLen ? label.substring(0, maxLen) + '...' : label;
}

// 构建丰富的 Tooltip
function buildTooltip(node) {
    let html = `<div style="max-width: 300px; padding: 8px;">`;
    html += `<strong>${node.title || node.label || node.id}</strong><br>`;
    if (node.group) html += `<span style="color: #888;">类型: ${node.group}</span><br>`;
    if (node.community_id !== undefined) html += `<span style="color: #4ecdc4;">社区: #${node.community_id}</span><br>`;
    if (node.year) html += `<span style="color: #ffeaa7;">年份: ${node.year}</span>`;
    html += `</div>`;
    return html;
}

// 颜色加深/变浅
function shadeColor(color, percent) {
    const num = parseInt(color.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = (num >> 16) + amt;
    const G = (num >> 8 & 0x00FF) + amt;
    const B = (num & 0x0000FF) + amt;
    return '#' + (0x1000000 +
        (R < 255 ? (R < 1 ? 0 : R) : 255) * 0x10000 +
        (G < 255 ? (G < 1 ? 0 : G) : 255) * 0x100 +
        (B < 255 ? (B < 1 ? 0 : B) : 255)
    ).toString(16).slice(1);
}

// 更新统计信息
function updateGraphStats(nodeCount, edgeCount, communityCount) {
    document.getElementById('graph-stats').innerHTML = `
        <span class="me-2">节点: <strong>${nodeCount}</strong></span>
        <span class="me-2">关系: <strong>${edgeCount}</strong></span>
        <span>社区: <strong style="color: #4ecdc4;">${communityCount}</strong></span>
    `;
}

// 更新图例
function updateLegend(communities) {
    let legendEl = document.getElementById('graph-legend');
    if (!legendEl) {
        // 创建图例容器
        const container = document.getElementById('mynetwork').parentElement;
        legendEl = document.createElement('div');
        legendEl.id = 'graph-legend';
        legendEl.className = 'graph-legend';
        container.appendChild(legendEl);
    }
    
    let html = '<div class="legend-title">图例</div>';
    
    // 节点类型
    html += '<div class="legend-section">节点类型</div>';
    html += '<div class="legend-item"><span class="legend-dot" style="background: #007bff;"></span> 论文</div>';
    html += '<div class="legend-item"><span class="legend-diamond" style="background: #a855f7;"></span> Topic</div>';
    html += '<div class="legend-item"><span class="legend-triangle" style="background: #ff6b6b;"></span> 方法/实体</div>';
    
    // 社区颜色
    if (communities.length > 0) {
        html += '<div class="legend-section">社区</div>';
        communities.slice(0, 8).forEach(commId => {
            const color = COMMUNITY_COLORS[commId % COMMUNITY_COLORS.length];
            html += `<div class="legend-item"><span class="legend-dot" style="background: ${color};"></span> 社区 #${commId}</div>`;
        });
        if (communities.length > 8) {
            html += `<div class="legend-item text-muted">... 还有 ${communities.length - 8} 个社区</div>`;
        }
    }
    
    // 关系类型
    html += '<div class="legend-section">关系类型</div>';
    html += '<div class="legend-item"><span class="legend-line" style="background: #00d2ff;"></span> CITES (引用)</div>';
    html += '<div class="legend-item"><span class="legend-line" style="background: #ff6b6b;"></span> PROPOSES (提出)</div>';
    html += '<div class="legend-item"><span class="legend-line-dashed" style="background: #4ecdc4;"></span> BELONGS_TO (属于)</div>';
    
    legendEl.innerHTML = html;
}

async function showNodeDetails(nodeId) {
    const panel = document.getElementById('node-details');
    const titleEl = document.getElementById('detail-title');
    const contentEl = document.getElementById('detail-content');
    
    // 获取节点数据 (从 network dataset 中查找)
    const nodeData = network.body.data.nodes.get(nodeId);
    const title = nodeData ? (nodeData.title || nodeId) : nodeId;
    
    titleEl.textContent = title.split('\n')[0]; // 只显示第一行标题
    contentEl.innerHTML = `<div class="spinner-border spinner-border-sm text-info" role="status"></div> 加载中...`;
    panel.classList.remove('d-none');
    
    // 模拟获取详情 (实际应调用后端 /api/paper/{id})
    // 这里我们展示更多元数据
    let html = `
        <div class="mb-3">
            <label class="text-muted small">ID</label>
            <div class="font-monospace small text-break">${nodeId}</div>
        </div>
    `;
    
    if (nodeData && nodeData.group === 'paper') {
        html += `
            <div class="mb-3">
                <label class="text-muted small">类型</label>
                <div><span class="badge bg-primary">论文</span></div>
            </div>
            <div class="d-grid gap-2">
                <a href="https://openalex.org/${nodeId}" target="_blank" class="btn btn-sm btn-outline-light">
                    <i class="bi bi-box-arrow-up-right"></i> OpenAlex
                </a>
                <button class="btn btn-sm btn-outline-info">
                    <i class="bi bi-file-earmark-pdf"></i> 下载 PDF
                </button>
            </div>
        `;
    } else {
        html += `
            <div class="mb-3">
                <label class="text-muted small">类型</label>
                <div><span class="badge bg-purple" style="background-color: #a855f7">社区/Topic</span></div>
            </div>
        `;
    }
    
    contentEl.innerHTML = html;
}

function closeDetails() {
    document.getElementById('node-details').classList.add('d-none');
}