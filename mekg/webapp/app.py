import asyncio
import json
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from src.modules.mekg.automation.crawler_manager import CrawlerManager
from src.modules.mekg.storage.memgraph_graph_db import MemgraphGraphDB

app = FastAPI(title="MEKG Enterprise Control Center")

# 挂载静态文件
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

crawler = CrawlerManager()
# DB 用于只读查询接口 - Memgraph 支持并发访问，无需担心锁冲突
db_reader = MemgraphGraphDB(read_only=True)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # 移除已断开的连接
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(message)
            except:
                self.active_connections.remove(connection)

manager = ConnectionManager()

# 将 manager 注入到 crawler 中，以便 crawler 主动推送日志
crawler.set_log_callback(lambda log: asyncio.create_task(manager.broadcast(json.dumps({"type": "log", "data": log}))))

@app.get("/")
async def index(request: Request):
    """主页"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/status")
async def get_status():
    """获取爬虫状态"""
    return crawler.get_status()

@app.post("/config/update")
async def update_config(config: dict):
    """动态更新配置"""
    # 示例：更新最大并发数
    if "max_workers" in config:
        crawler.update_config("max_workers", config["max_workers"])
    return {"status": "updated"}

@app.post("/start")
async def start_crawler():
    """启动爬虫"""
    success = crawler.start_crawler()
    return {"success": success, "message": "Crawler started" if success else "Already running"}

@app.post("/stop")
async def stop_crawler():
    """停止爬虫"""
    success = crawler.stop_crawler()
    return {"success": success, "message": "Stopping crawler..."}

@app.get("/graph/stats")
async def get_graph_stats():
    """获取图谱统计 (只读)"""
    try:
        # Memgraph 使用 execute_cypher 方法
        paper_result = db_reader.execute_cypher("MATCH (p:Paper) RETURN count(p) AS cnt")
        topic_result = db_reader.execute_cypher("MATCH (t:Topic) RETURN count(t) AS cnt")
        
        paper_count = paper_result[0]['cnt'] if paper_result else 0
        topic_count = topic_result[0]['cnt'] if topic_result else 0
        
        return {"papers": paper_count, "topics": topic_count}
    except Exception as e:
        return {"error": str(e)}

@app.get("/graph/data")
async def get_graph_data(limit: int = 100):
    """获取图谱可视化数据 - 包含社区信息"""
    try:
        nodes = []
        edges = []
        seen_nodes = set()

        # 1. 获取论文节点 (包含社区 ID 和更多属性)
        paper_query = f"""
        MATCH (p:Paper)
        RETURN p.id AS id, p.title AS title, p.year AS year,
               p.community_id AS community_id, p.citations AS citations
        LIMIT {limit}
        """
        paper_results = db_reader.execute_cypher(paper_query)
        for record in paper_results:
            p_id = record['id']
            p_title = record['title'] or ''
            if p_id not in seen_nodes:
                nodes.append({
                    "id": p_id,
                    "label": p_title[:30] + "..." if len(p_title) > 30 else p_title,
                    "group": "paper",
                    "title": p_title,
                    "year": record.get('year'),
                    "community_id": record.get('community_id'),
                    "citations": record.get('citations', 0)
                })
                seen_nodes.add(p_id)

        # 2. 获取 Paper -> SemanticEntity 关系
        entity_query = f"""
        MATCH (p:Paper)-[r]->(e:SemanticEntity)
        RETURN p.id AS p_id, e.id AS e_id, e.name AS e_name, e.type AS e_type, type(r) AS r_type
        LIMIT {limit * 2}
        """
        entity_results = db_reader.execute_cypher(entity_query)
        for record in entity_results:
            p_id = record['p_id']
            e_id = record['e_id']
            e_name = record['e_name'] or e_id
            e_type = record['e_type'] or 'entity'
            r_type = record['r_type']
            
            # 添加实体节点
            if e_id not in seen_nodes:
                nodes.append({
                    "id": e_id,
                    "label": e_name[:25] + "..." if len(e_name) > 25 else e_name,
                    "group": e_type.lower() if e_type else "semanticentity",
                    "title": f"{e_type}: {e_name}"
                })
                seen_nodes.add(e_id)
            
            # 添加边
            edges.append({
                "from": p_id,
                "to": e_id,
                "label": r_type
            })

        # 3. 获取 Paper -> Topic 关系
        topic_query = f"""
        MATCH (p:Paper)-[r:BELONGS_TO]->(t:Topic)
        RETURN p.id AS p_id, t.name AS t_name, r.relevance_score AS score
        LIMIT {limit}
        """
        topic_results = db_reader.execute_cypher(topic_query)
        for record in topic_results:
            p_id = record['p_id']
            t_name = record['t_name']
            t_id = f"Topic:{t_name}"
            
            # 添加 Topic 节点
            if t_id not in seen_nodes:
                nodes.append({
                    "id": t_id,
                    "label": t_name,
                    "group": "topic",
                    "title": f"Topic: {t_name}"
                })
                seen_nodes.add(t_id)
            
            # 添加边
            edges.append({
                "from": p_id,
                "to": t_id,
                "label": "BELONGS_TO"
            })

        # 4. 获取 Paper -> Paper 引用关系 (增强版)
        # 只要有一端在当前显示的节点中，就尝试把另一端也加进来
        # 这样能展示更多引用关系
        current_ids = list(seen_nodes)
        if current_ids:
            # 使用参数化查询，避免字符串拼接导致的转义问题
            cite_query = """
            MATCH (a:Paper)-[r:CITES]->(b:Paper)
            WHERE a.id IN $ids OR b.id IN $ids
            RETURN a.id AS src, a.title AS src_title,
                   b.id AS dst, b.title AS dst_title,
                   r.type AS cite_type, r.reasoning AS reasoning
            LIMIT $limit
            """
            
            cite_results = db_reader.execute_cypher(cite_query, {"ids": current_ids, "limit": limit * 2})
            for record in cite_results:
                src = record['src']
                dst = record['dst']
                
                # 补充缺失的节点 (Stub Nodes)
                if src not in seen_nodes:
                    nodes.append({
                        "id": src, "label": record['src_title'][:20]+"..." if record['src_title'] else src,
                        "group": "paper", "title": record['src_title']
                    })
                    seen_nodes.add(src)
                
                if dst not in seen_nodes:
                    nodes.append({
                        "id": dst, "label": record['dst_title'][:20]+"..." if record['dst_title'] else dst,
                        "group": "paper", "title": record['dst_title']
                    })
                    seen_nodes.add(dst)
                
                # 添加有向边
                edges.append({
                    "from": src,
                    "to": dst,
                    "label": record.get('cite_type', 'CITES'),
                    "arrows": "to", # 强制前端显示箭头
                    "reasoning": record.get('reasoning', '')
                })
            
        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # 发送初始状态
        await websocket.send_json({"type": "status", "data": crawler.get_status()})
        
        while True:
            # 心跳/状态推送 (每秒)
            status = crawler.get_status()
            await websocket.send_json({"type": "status", "data": status})
            await asyncio.sleep(1)
            # 日志通过 callback 实时推送，不在这里轮询
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8770)