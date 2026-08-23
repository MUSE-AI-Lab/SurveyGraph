import streamlit as st
import requests
import pandas as pd
from pyvis.network import Network
import time
import tempfile
import os
import json
import threading
import websocket
from queue import Queue

# 配置
API_URL = "http://localhost:8770"
WS_URL = "ws://localhost:8770/ws/stream"

st.set_page_config(page_title="MEKG Pro Console", layout="wide", page_icon="🚀")

# 初始化 Session State
if "logs" not in st.session_state:
    st.session_state.logs = []
if "status" not in st.session_state:
    st.session_state.status = {}
if "ws_thread" not in st.session_state:
    st.session_state.ws_thread = None

# WebSocket 客户端线程
def ws_client_thread():
    def on_message(ws, message):
        data = json.loads(message)
        if data["type"] == "log":
            st.session_state.logs.append(data["data"])
            # 保持日志长度
            if len(st.session_state.logs) > 500:
                st.session_state.logs.pop(0)
        elif data["type"] == "status":
            st.session_state.status = data["data"]

    def on_error(ws, error):
        st.toast(f"WebSocket Error: {error}", icon="⚠️")

    ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_error=on_error)
    ws.run_forever()

# 启动 WebSocket 线程 (单例)
if st.session_state.ws_thread is None:
    t = threading.Thread(target=ws_client_thread, daemon=True)
    t.start()
    st.session_state.ws_thread = t

# 侧边栏：控制中心
with st.sidebar:
    st.title("🕹️ Mission Control")
    
    status = st.session_state.status
    is_running = status.get("is_running", False)
    
    # 状态指示灯
    if is_running:
        st.success("SYSTEM ONLINE", icon="🟢")
    else:
        st.error("SYSTEM OFFLINE", icon="🔴")
        
    st.divider()
    
    # 控制按钮
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 启动", disabled=is_running, use_container_width=True):
            requests.post(f"{API_URL}/start")
    with col2:
        if st.button("🛑 停止", disabled=not is_running, use_container_width=True):
            requests.post(f"{API_URL}/stop")
            
    st.divider()
    
    # 实时指标
    stats = status.get("stats", {})
    st.metric("📚 已爬取论文", stats.get("papers_crawled", 0))
    st.metric("🏷️ 发现社区", stats.get("communities_detected", 0))
    
    st.divider()
    
    # 配置热更新
    with st.expander("⚙️ 高级配置"):
        max_workers = st.slider("并发线程数", 1, 20, 5)
        if st.button("应用配置"):
            requests.post(f"{API_URL}/config/update", json={"max_workers": max_workers})
            st.toast("配置已更新", icon="✅")

# 主界面
st.title("🧠 MEKG 全局态势感知")

# 顶部状态栏
task_container = st.empty()
task_container.info(f"当前任务: {status.get('current_task', 'Idle')}")

tab1, tab2, tab3 = st.tabs(["📊 实时终端", "🕸️ 图谱透视", "🔍 深度搜索"])

with tab1:
    # 仿终端日志显示
    st.markdown("""
        <style>
        .terminal {
            background-color: #0e1117;
            color: #00ff00;
            font-family: 'Courier New', Courier, monospace;
            padding: 10px;
            border-radius: 5px;
            height: 500px;
            overflow-y: auto;
            border: 1px solid #333;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # 倒序显示日志
    logs_html = "<br>".join(reversed(st.session_state.logs))
    st.markdown(f'<div class="terminal">{logs_html}</div>', unsafe_allow_html=True)

with tab2:
    col1, col2 = st.columns([3, 1])
    with col1:
        # 图谱可视化
        try:
            graph_res = requests.get(f"{API_URL}/graph/data?limit=200")
            if graph_res.status_code == 200:
                data = graph_res.json()
                nodes = data.get("nodes", [])
                edges = data.get("edges", [])
                
                if nodes:
                    net = Network(height="600px", width="100%", bgcolor="#1E1E1E", font_color="white")
                    net.force_atlas_2based(gravity=-50)
                    
                    for node in nodes:
                        color = "#4da6ff" if node["group"] == "paper" else "#ff6666"
                        # 添加更多属性到 title 以便悬停显示
                        title = f"{node.get('title', '')}\nID: {node['id']}"
                        net.add_node(node["id"], label=node["label"], title=title, color=color, group=node["group"])
                        
                    for edge in edges:
                        net.add_edge(edge["from"], edge["to"], label=edge["label"])
                        
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
                        net.save_graph(tmp.name)
                        with open(tmp.name, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                        st.components.v1.html(html_content, height=600)
                    os.unlink(tmp.name)
                else:
                    st.info("暂无图谱数据，请启动爬虫")
        except Exception as e:
            st.error(f"图谱加载失败: {e}")
            
    with col2:
        st.subheader("图谱统计")
        try:
            stats_res = requests.get(f"{API_URL}/graph/stats")
            if stats_res.status_code == 200:
                g_stats = stats_res.json()
                st.write(f"**节点总数**: {g_stats.get('papers', 0) + g_stats.get('topics', 0)}")
                st.write(f"- 论文: {g_stats.get('papers', 0)}")
                st.write(f"- Topic: {g_stats.get('topics', 0)}")
        except:
            pass

with tab3:
    search_term = st.text_input("搜索论文/Topic", placeholder="输入关键词...")
    if search_term:
        # 这里可以调用后端搜索接口 (需实现)
        st.info("搜索功能开发中...")

# 自动刷新机制 (利用 st_autorefresh 或简单的 sleep)
# 为了让 WebSocket 数据能及时渲染到 UI，我们需要触发 rerun
time.sleep(1)
st.rerun()