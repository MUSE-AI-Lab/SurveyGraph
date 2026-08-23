import os
import sys
import tempfile
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from pyvis.network import Network

# 设置页面配置
st.set_page_config(page_title="MEKG Live Dashboard", layout="wide")

st.title("🧠 MEKG 实时科研情报中心")

# 侧边栏配置
st.sidebar.header("控制面板")
memgraph_uri = st.sidebar.text_input("Memgraph URI", os.getenv("MEMGRAPH_URI", "bolt://localhost:7687"))
memgraph_user = st.sidebar.text_input("用户名 (可选)", "")
memgraph_password = st.sidebar.text_input("密码 (可选)", "", type="password")
node_limit = st.sidebar.slider("显示节点数量限制", 50, 500, 100)

# 连接数据库 - 使用 Memgraph
# Memgraph 支持并发访问，无需担心锁问题
@st.cache_resource
def get_db_connection():
    """获取 Memgraph 数据库连接"""
    try:
        from src.modules.mekg.storage.memgraph_graph_db import MemgraphGraphDB
        return MemgraphGraphDB(
            uri=memgraph_uri,
            user=memgraph_user if memgraph_user else None,
            password=memgraph_password if memgraph_password else None,
            read_only=True
        )
    except Exception as e:
        st.error(f"无法连接到 Memgraph: {e}")
        return None

def execute_query(query, params=None):
    """执行查询"""
    db = get_db_connection()
    if db is None:
        return None
    try:
        return db.execute_cypher(query, params or {})
    except Exception as e:
        st.error(f"查询错误: {e}")
        return None

# 1. 统计信息
col1, col2, col3 = st.columns(3)

try:
    # 分别查询
    res_paper = execute_query("MATCH (p:Paper) RETURN count(p) AS cnt")
    paper_count = res_paper[0]['cnt'] if res_paper else 0
    
    res_topic = execute_query("MATCH (t:Topic) RETURN count(t) AS cnt")
    topic_count = res_topic[0]['cnt'] if res_topic else 0
    
    res_rel = execute_query("MATCH ()-[r]->() RETURN count(r) AS cnt")
    rel_count = res_rel[0]['cnt'] if res_rel else 0
    
    col1.metric("📚 论文总数", paper_count)
    col2.metric("🏷️ Topic 总数", topic_count)
    col3.metric("🔗 关系总数", rel_count)
except Exception as e:
    st.warning(f"无法获取统计信息: {e}")

# 2. 图谱可视化
st.subheader("🕸️ 知识图谱概览")

# 获取数据 - Memgraph 使用 labels() 和 type() 函数
cypher = f"""
MATCH (p:Paper)-[r]->(t)
RETURN p.title AS p_title, p.id AS p_id, labels(t)[0] AS t_label, t.name AS t_name, type(r) AS r_label
LIMIT {node_limit}
"""

rows = execute_query(cypher)

if rows:
    try:
        # 构建 PyVis 网络
        net = Network(height="600px", width="100%", bgcolor="#222222", font_color="white")
        net.force_atlas_2based()
        
        for row in rows:
            p_title = row['p_title'] or ''
            p_id = row['p_id']
            t_label = row['t_label']
            t_name = row['t_name']
            r_label = row['r_label']
            
            # 添加论文节点
            net.add_node(p_id, label=p_title[:20]+"...", title=p_title, color="#4da6ff", shape="dot")
            
            # 添加目标节点
            target_id = f"{t_label}:{t_name}"
            color = "#ff6666" if t_label == "Topic" else "#66ff66"
            net.add_node(target_id, label=t_name, title=f"{t_label}: {t_name}", color=color)
            
            # 添加边
            net.add_edge(p_id, target_id, title=r_label)
            
        # 保存并显示
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            net.save_graph(tmp.name)
            with open(tmp.name, 'r', encoding='utf-8') as f:
                html_content = f.read()
            st.components.v1.html(html_content, height=600)
        os.unlink(tmp.name)
        
    except Exception as e:
        st.error(f"可视化失败: {e}")

# 3. 详细数据查询
st.subheader("🔍 论文深度解析")
search_term = st.text_input("搜索论文 (标题或ID)")

if search_term:
    search_cypher = """
    MATCH (p:Paper)
    WHERE p.title CONTAINS $term OR p.id = $term
    RETURN p
    LIMIT 1
    """
    res = execute_query(search_cypher, {"term": search_term})
    
    if res and len(res) > 0:
        paper = dict(res[0]['p'])  # Memgraph 返回节点对象
        
        # 解析 method_info JSON
        if 'method_info' in paper and isinstance(paper['method_info'], str):
            try:
                paper['method_info'] = json.loads(paper['method_info'])
            except:
                paper['method_info'] = {}
        
        st.write(f"### {paper.get('title', 'Unknown')}")
        st.write(f"**ID**: {paper.get('id', 'N/A')} | **Year**: {paper.get('year', 'N/A')}")
        st.info(f"**Abstract**: {paper.get('abstract', 'No abstract')}")
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.write("#### 🛠️ Method Info")
            method_info = paper.get('method_info')
            if method_info:
                st.json(method_info)
            else:
                st.write("无数据")
                
        with c2:
            st.write("#### ✨ Innovations")
            innovations = paper.get('innovations')
            if innovations:
                for i in innovations:
                    st.success(f"- {i}")
            else:
                st.write("无数据")
                
        st.write("#### 🎯 Research Domains")
        domains = paper.get('research_domains', [])
        st.write(", ".join(domains) if domains else "无数据")
        
    else:
        st.write("未找到相关论文")

else:
    st.info("💡 提示：Memgraph 支持并发访问，无需担心数据库锁问题！")