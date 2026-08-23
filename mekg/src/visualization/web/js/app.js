/**
 * MEKG 可视化主逻辑 (Pro Version)
 */

class MEKGViewer {
    constructor() {
        this.chart = null;
        this.graphData = null;
        this.option = null;
        this.layoutFrozen = false; // 冻结布局以避免缩放后乱位
        this.init();
    }

    init() {
        // 初始化 ECharts 实例
        const container = document.getElementById('graph-container');
        this.chart = echarts.init(container);

        // 监听窗口大小变化
        window.addEventListener('resize', () => {
            this.chart.resize();
        });

        // 绑定交互事件
        this.bindEvents();

        // 初始化数据源列表
        this.initDataSourceList();
    }

    async initDataSourceList() {
        const select = document.getElementById('data-source-select');
        try {
            const response = await fetch('/api/dirs');
            const dirs = await response.json();
            
            if (dirs.length === 0) {
                const option = document.createElement('option');
                option.text = "No data found";
                select.add(option);
                return;
            }

            dirs.forEach(dir => {
                const option = document.createElement('option');
                option.value = dir.name;
                option.text = `${dir.name} (${new Date(dir.mtime * 1000).toLocaleString()})`;
                select.add(option);
            });

            // 默认选择最新的
            select.selectedIndex = 0;
            this.loadData(dirs[0].name);

        } catch (error) {
            console.error('Failed to fetch data sources:', error);
        }
    }

    async loadData(dirName) {
        this.showLoading(true);
        try {
            const response = await fetch(`/api/data/${dirName}`);
            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            this.graphData = data;
            this.renderGraph(data);
        } catch (error) {
            console.error('Failed to load graph data:', error);
            alert('Failed to load data. Check console for details.');
        } finally {
            this.showLoading(false);
        }
    }

    renderGraph(data) {
        // 基础配置
        this.option = {
            backgroundColor: 'transparent',
            tooltip: {
                trigger: 'item',
                formatter: (params) => {
                    if (params.dataType === 'node') {
                        return `<strong>${params.data.full_name}</strong><br>
                                Citations: ${params.data.attributes.Citations}<br>
                                PageRank: ${params.data.attributes.PageRank}`;
                    }
                    const rel = (params.data && params.data.label && params.data.label.formatter)
                        ? params.data.label.formatter
                        : (params.data && params.data.name ? params.data.name : '');
                    return `${params.data.source} → ${params.data.target}<br>${rel}`;
                },
                backgroundColor: 'rgba(30, 41, 59, 0.9)',
                borderColor: '#38bdf8',
                textStyle: { color: '#f8fafc' }
            },
            legend: {
                data: data.categories.map(c => c.name),
                textStyle: { color: '#94a3b8' },
                bottom: 20,
                type: 'scroll'
            },
            series: [
                {
                    type: 'graph',
                    layout: 'force',
                    data: data.nodes.map(node => ({
                        ...node,
                        symbolSize: node.symbolSize || 10,
                        label: {
                            show: (node.value && node.value > 0.01) || false,
                            color: '#fff',
                            position: 'right'
                        }
                    })),
                    links: data.links,
                    categories: data.categories,
                    roam: true,
                    // 开启有向图箭头
                    edgeSymbol: ['none', 'arrow'],
                    edgeSymbolSize: [0, 8],
                    label: {
                        position: 'right',
                        formatter: '{b}'
                    },
                    edgeLabel: {
                        show: false,
                        fontSize: 10,
                        color: '#94a3b8',
                        formatter: (params) => {
                            return (params.data && params.data.label && params.data.label.formatter)
                                ? params.data.label.formatter
                                : (params.data && params.data.name ? params.data.name : '');
                        }
                    },
                    lineStyle: {
                        color: 'source',
                        curveness: 0.2,
                        opacity: 0.6
                    },
                    // 性能优化：渐进渲染与动画降级
                    progressive: 3000,
                    progressiveThreshold: 5000,
                    animationDuration: 300,
                    animationDurationUpdate: 0,
                    // 性能优化：根据节点数量动态调整布局参数
                    force: {
                        initLayout: 'circular',
                        repulsion: 800,
                        edgeLength: [50, 200],
                        gravity: 0.05,
                        layoutAnimation: data.nodes.length < 800 // 节点多时关闭动画以提升性能
                    },
                    emphasis: {
                        focus: 'adjacency',
                        lineStyle: {
                            width: 4,
                            opacity: 1
                        }
                    },
                    autoCurveness: true
                }
            ]
        };

        this.chart.setOption(this.option);
        this.applyControls(); // 应用当前控制面板设置
        this.setupFreezeAfterLayout(); // 冻结首次力导向布局，缩放不乱位
    }

    bindEvents() {
        // 数据源切换
        document.getElementById('data-source-select').addEventListener('change', (e) => {
            if (e.target.value) this.loadData(e.target.value);
        });

        // 刷新按钮
        document.getElementById('refresh-btn').addEventListener('click', () => {
            const select = document.getElementById('data-source-select');
            select.innerHTML = '<option value="" disabled selected>Loading...</option>';
            this.initDataSourceList();
        });

        // 搜索功能
        document.getElementById('search-btn').addEventListener('click', () => this.handleSearch());
        document.getElementById('search-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleSearch();
        });

        // 显示控制
        document.getElementById('show-labels-check').addEventListener('change', (e) => {
            this.chart.setOption({
                series: [{
                    label: { show: e.target.checked }
                }]
            });
        });

        document.getElementById('show-edges-check').addEventListener('change', (e) => {
            this.chart.setOption({
                series: [{
                    edgeLabel: {
                        show: e.target.checked
                    }
                }]
            });
        });

        // 力导向控制
        const repulsionRange = document.getElementById('repulsion-range');
        const rangeValue = document.querySelector('.range-value');
        
        // 拖动时只更新数值显示，不触发计算，避免卡顿
        repulsionRange.addEventListener('input', (e) => {
            rangeValue.textContent = e.target.value;
        });

        // 松开鼠标时才触发重排
        repulsionRange.addEventListener('change', (e) => {
            const val = parseInt(e.target.value);
            // 1. 解冻布局，允许重排
            this.unfreezeLayout();
            // 2. 应用新参数
            this.chart.setOption({
                series: [{
                    force: { repulsion: val }
                }]
            });
            // 3. 等待稳定后再次冻结
            this.setupFreezeAfterLayout();
        });

        // 节点点击
        this.chart.on('click', (params) => {
            if (params.dataType === 'node') {
                this.showNodeDetails(params.data);
            }
        });

        // 空白点击关闭侧边栏
        this.chart.getZr().on('click', (params) => {
            if (!params.target) {
                this.hideSidebar();
                // 取消高亮
                this.chart.dispatchAction({
                    type: 'downplay'
                });
            }
        });

        document.getElementById('close-sidebar').addEventListener('click', () => this.hideSidebar());
    }

    handleSearch() {
        const query = document.getElementById('search-input').value.toLowerCase();
        if (!query || !this.graphData) return;

        const targetNode = this.graphData.nodes.find(n => 
            n.name.toLowerCase().includes(query) || 
            n.full_name.toLowerCase().includes(query)
        );

        if (targetNode) {
            // 高亮节点
            this.chart.dispatchAction({
                type: 'highlight',
                seriesIndex: 0,
                name: targetNode.name
            });
            
            // 居中显示
            this.chart.dispatchAction({
                type: 'focusNodeAdjacency',
                seriesIndex: 0,
                dataIndex: this.graphData.nodes.indexOf(targetNode)
            });

            this.showNodeDetails(targetNode);
        } else {
            alert('Node not found');
        }
    }

    showNodeDetails(nodeData) {
        const sidebar = document.getElementById('sidebar');
        const title = document.getElementById('node-title');
        const basicInfo = document.getElementById('node-basic-info');
        const attributes = document.getElementById('node-attributes');
        const openBtn = document.getElementById('open-paper-btn');
        
        title.textContent = nodeData.full_name;

        const categoryName = this.graphData.categories[nodeData.category] 
            ? this.graphData.categories[nodeData.category].name 
            : 'Unknown';

        basicInfo.innerHTML = `
            <p><strong>ID:</strong> ${nodeData.id}</p>
            <p><strong>Category:</strong> <span style="color:var(--accent-color)">${categoryName}</span></p>
            <p><strong>Importance:</strong> ${parseFloat(nodeData.value).toFixed(4)}</p>
        `;

        if (nodeData.attributes) {
            let attrHtml = '<ul style="list-style: none;">';
            for (const [key, value] of Object.entries(nodeData.attributes)) {
                if (key === 'Abstract' && value.length > 200) {
                    attrHtml += `<li><strong style="color:var(--text-secondary)">${key}:</strong><br>${value}</li>`;
                } else {
                    attrHtml += `<li><strong style="color:var(--text-secondary)">${key}:</strong> ${value}</li>`;
                }
            }
            attrHtml += '</ul>';
            attributes.innerHTML = attrHtml;
        }

        // 链接处理
        if (nodeData.id.startsWith('W') || nodeData.id.startsWith('http')) {
            openBtn.href = nodeData.id.startsWith('http') ? nodeData.id : `https://openalex.org/${nodeData.id}`;
            openBtn.classList.remove('hidden');
        } else {
            openBtn.classList.add('hidden');
        }

        sidebar.classList.remove('hidden');
    }

    hideSidebar() {
        document.getElementById('sidebar').classList.add('hidden');
    }

    showLoading(show) {
        const mask = document.getElementById('loading-mask');
        if (show) mask.classList.remove('hidden');
        else mask.classList.add('hidden');
    }

    applyControls() {
        // 应用初始设置
        const showLabels = document.getElementById('show-labels-check').checked;
        const showEdges = document.getElementById('show-edges-check').checked;
        const repulsion = document.getElementById('repulsion-range').value;

        this.chart.setOption({
            series: [{
                label: { show: showLabels },
                edgeLabel: { show: showEdges },
                force: { repulsion: parseInt(repulsion) }
            }]
        });
    }

    // 解冻布局：清除固定坐标，恢复力导向计算
    unfreezeLayout() {
        this.layoutFrozen = false;
        // 恢复原始节点数据（不带 x, y 坐标）
        const nodes = this.graphData.nodes.map(node => {
            const { x, y, fixed, ...rest } = node;
            return rest;
        });

        this.chart.setOption({
            series: [{
                layout: 'force',
                data: nodes,
                force: {
                    initLayout: 'circular', // 重排时使用环形初始布局有助于打散
                    layoutAnimation: true
                }
            }]
        });
    }

    // 冻结布局：力导向收敛后，将坐标固化为静态
    setupFreezeAfterLayout() {
        // 先解绑之前的事件，防止重复
        this.chart.off('finished');
        
        // 绑定一次性 finished 事件
        const onFinished = () => {
            if (this.layoutFrozen) return;
            
            try {
                const model = this.chart.getModel();
                const seriesModel = model.getSeriesByIndex(0);
                const dataList = seriesModel.getData();
                
                if (!dataList || !dataList.getItemLayout) return;

                // 获取当前的计算坐标
                const frozenData = this.graphData.nodes.map((n, i) => {
                    const layout = dataList.getItemLayout(i);
                    // 只有当布局有效时才固化
                    if (Array.isArray(layout) && !isNaN(layout[0]) && !isNaN(layout[1])) {
                        return { ...n, x: layout[0], y: layout[1], fixed: true };
                    }
                    return n;
                });

                this.layoutFrozen = true;
                
                // 切换为静态布局
                this.chart.setOption({
                    series: [{
                        layout: 'none',
                        data: frozenData
                    }]
                });
                
                // 完成后解绑，避免后续干扰
                this.chart.off('finished', onFinished);
                
            } catch (e) {
                console.warn('Freeze layout failed:', e);
            }
        };

        this.chart.on('finished', onFinished);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new MEKGViewer();
});