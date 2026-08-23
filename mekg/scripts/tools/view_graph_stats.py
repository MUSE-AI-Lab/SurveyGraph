#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MEKG V2 图谱统计和可视化脚本

功能：
1. 显示图谱统计信息
2. 生成可视化图
3. 导出图谱数据
"""

import sys
sys.path.insert(0, '.')

import argparse
import json
from pathlib import Path
from datetime import datetime

from loguru import logger


def view_statistics(db_path: str):
    """查看图谱统计信息"""
    from src.modules.mekg.persistent_graph_db import PersistentGraphDB
    
    db = PersistentGraphDB(db_path)
    stats = db.get_statistics()
    
    print("\n" + "="*60)
    print("📊 MEKG V2 图谱统计信息")
    print("="*60)
    
    print(f"\n📁 数据库路径: {stats['db_path']}")
    print(f"💾 数据库大小: {stats['db_size_mb']:.2f} MB")
    
    print(f"\n📄 论文总数: {stats['paper_count']}")
    print(f"🔗 语义关系数: {stats['relation_count']}")
    print(f"📚 引用关系数: {stats['citation_count']}")
    print(f"🏷️ Topic数: {stats['topic_count']}")
    
    if stats['year_range'][0]:
        print(f"📅 年份范围: {stats['year_range'][0]} - {stats['year_range'][1]}")
    
    if stats['relation_types']:
        print("\n📈 关系类型分布:")
        for rel_type, count in sorted(stats['relation_types'].items(), key=lambda x: -x[1]):
            print(f"   {rel_type}: {count}")
    
    # 显示Topic列表
    topics = db.get_all_topics()
    if topics:
        print("\n🏷️ Topic列表:")
        for topic in topics:
            print(f"   - {topic['topic']}: {topic['paper_count']} 篇论文")
    
    print("\n" + "="*60)
    return stats


def visualize_graph(db_path: str, topic: str = None, output_path: str = None, max_nodes: int = 200):
    """生成图谱可视化"""
    from src.modules.mekg.persistent_graph_db import PersistentGraphDB
    
    db = PersistentGraphDB(db_path)
    
    # 获取论文
    if topic:
        paper_ids = db.get_topic_papers(topic)[:max_nodes]
        title = f"MEKG: {topic}"
    else:
        paper_ids = db.get_all_paper_ids()[:max_nodes]
        title = "MEKG V2 Knowledge Graph"
    
    if not paper_ids:
        print("❌ 没有找到论文")
        return
    
    print(f"\n🎨 生成可视化图 ({len(paper_ids)} 节点)...")
    
    # 尝试使用pyvis
    try:
        from pyvis.network import Network
        
        net = Network(height="800px", width="100%", bgcolor="#ffffff", font_color="black")
        net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=200)
        
        # 添加节点
        paper_set = set(paper_ids)
        for pid in paper_ids:
            paper = db.get_paper(pid)
            if paper:
                label = paper['title'][:30] + "..." if len(paper['title']) > 30 else paper['title']
                year = paper.get('year', 0)
                citations = paper.get('citation_count', 0)
                
                # 根据引用数设置节点大小
                size = min(10 + citations / 100, 50)
                
                # 根据年份设置颜色
                if year >= 2023:
                    color = "#e74c3c"  # 红色 - 最新
                elif year >= 2021:
                    color = "#f39c12"  # 橙色 - 较新
                elif year >= 2019:
                    color = "#3498db"  # 蓝色 - 中等
                else:
                    color = "#95a5a6"  # 灰色 - 较旧
                
                net.add_node(pid, label=label, title=f"{paper['title']}\n{year}\nCitations: {citations}", 
                           size=size, color=color)
        
        # 添加边
        with db._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join(["?" for _ in paper_ids])
            
            # 引用关系
            cursor.execute(f"""
                SELECT citing_id, cited_id FROM citations
                WHERE citing_id IN ({placeholders}) AND cited_id IN ({placeholders})
            """, paper_ids + paper_ids)
            
            for row in cursor.fetchall():
                if row[0] in paper_set and row[1] in paper_set:
                    net.add_edge(row[0], row[1], color="#cccccc", width=1)
            
            # 语义关系
            cursor.execute(f"""
                SELECT source_id, target_id, relation_type, confidence FROM relations
                WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})
            """, paper_ids + paper_ids)
            
            relation_colors = {
                "extends": "#27ae60",
                "improves": "#2ecc71",
                "applies": "#3498db",
                "compares": "#9b59b6",
                "combines": "#e67e22",
                "supports": "#1abc9c",
                "refutes": "#e74c3c",
            }
            
            for row in cursor.fetchall():
                if row[0] in paper_set and row[1] in paper_set:
                    color = relation_colors.get(row[2], "#7f8c8d")
                    width = max(1, row[3] * 3)
                    net.add_edge(row[0], row[1], color=color, width=width, title=row[2])
        
        # 保存
        if not output_path:
            output_path = f"data/visualizations/mekg_{'_'.join(topic.split()) if topic else 'full'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        net.save_graph(output_path)
        print(f"✅ 可视化已保存: {output_path}")
        
    except ImportError:
        print("⚠️ pyvis未安装，使用简单文本输出")
        print(f"   论文数: {len(paper_ids)}")
        print(f"   请安装: pip install pyvis")


def export_graph(db_path: str, topic: str = None, output_path: str = None, format: str = "json"):
    """导出图谱数据"""
    from src.modules.mekg.persistent_graph_db import PersistentGraphDB
    
    db = PersistentGraphDB(db_path)
    
    # 获取论文
    if topic:
        paper_ids = db.get_topic_papers(topic)
    else:
        paper_ids = db.get_all_paper_ids()
    
    print(f"\n📤 导出图谱数据 ({len(paper_ids)} 论文)...")
    
    # 收集数据
    nodes = []
    for pid in paper_ids:
        paper = db.get_paper(pid)
        if paper:
            nodes.append({
                "id": pid,
                "title": paper['title'],
                "year": paper.get('year'),
                "citation_count": paper.get('citation_count', 0),
                "abstract": paper.get('abstract', '')[:500],
                "method_entities": paper.get('method_entities', []),
            })
    
    # 收集边
    edges = []
    paper_set = set(paper_ids)
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join(["?" for _ in paper_ids])
        
        # 引用关系
        cursor.execute(f"""
            SELECT citing_id, cited_id FROM citations
            WHERE citing_id IN ({placeholders}) AND cited_id IN ({placeholders})
        """, paper_ids + paper_ids)
        
        for row in cursor.fetchall():
            edges.append({"source": row[0], "target": row[1], "type": "cites", "confidence": 1.0})
        
        # 语义关系
        cursor.execute(f"""
            SELECT source_id, target_id, relation_type, confidence FROM relations
            WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})
        """, paper_ids + paper_ids)
        
        for row in cursor.fetchall():
            edges.append({"source": row[0], "target": row[1], "type": row[2], "confidence": row[3]})
    
    data = {
        "topic": topic,
        "exported_at": datetime.now().isoformat(),
        "statistics": {
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "nodes": nodes,
        "edges": edges,
    }
    
    # 保存
    if not output_path:
        output_path = f"data/exports/mekg_{'_'.join(topic.split()) if topic else 'full'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 数据已导出: {output_path}")
    print(f"   节点数: {len(nodes)}")
    print(f"   边数: {len(edges)}")


def main():
    parser = argparse.ArgumentParser(description="MEKG V2 图谱统计和可视化")
    parser.add_argument("--db", default="data/graph_db/mekg_v2.db", help="数据库路径")
    parser.add_argument("--action", choices=["stats", "visualize", "export", "all"], default="stats",
                       help="操作类型")
    parser.add_argument("--topic", help="指定Topic")
    parser.add_argument("--output", help="输出路径")
    parser.add_argument("--max-nodes", type=int, default=200, help="可视化最大节点数")
    
    args = parser.parse_args()
    
    if args.action == "stats" or args.action == "all":
        view_statistics(args.db)
    
    if args.action == "visualize" or args.action == "all":
        visualize_graph(args.db, args.topic, args.output, args.max_nodes)
    
    if args.action == "export" or args.action == "all":
        export_graph(args.db, args.topic, args.output)


if __name__ == "__main__":
    main()