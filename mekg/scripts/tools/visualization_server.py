#!/usr/bin/env python3
"""
MEKG 可视化服务器 - FastAPI 实时渲染

启动方式：
    python mekg/scripts/tools/visualization_server.py

访问地址：
    http://localhost:8765

支持两种分类模式：
    1. 基于大纲结构（推荐）：从 outline.json 读取章节结构
    2. 基于论文分类（旧版）：从 mekg_data.json 的 categories 字段读取
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="MEKG Survey Visualization", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据缓存
DATA_CACHE: Dict[str, Any] = {}
OUTLINE_CACHE: Dict[str, Any] = {}

# 配置：数据目录
DATA_DIR = project_root / 'outputs' / '2025-12-23-1426_Large_Language_Model'

# 是否使用新的 LLM 分类数据（如果存在）
USE_NEW_CLASSIFICATION = True

# 是否使用大纲结构作为分类（备用方案）
USE_OUTLINE_AS_CATEGORIES = False


def load_data():
    """加载 MEKG 数据和大纲"""
    global DATA_CACHE, OUTLINE_CACHE
    
    # 优先加载新的 LLM 分类数据
    new_data_path = DATA_DIR / 'mekg' / 'mekg_data_new.json'
    old_data_path = DATA_DIR / 'mekg' / 'mekg_data.json'
    
    if USE_NEW_CLASSIFICATION and new_data_path.exists():
        with open(new_data_path, 'r', encoding='utf-8') as f:
            DATA_CACHE = json.load(f)
            print(f"✅ 已加载新分类数据: {DATA_CACHE.get('papers_count', 0)} 篇论文, {DATA_CACHE.get('relations_count', 0)} 条关系")
            print(f"   📁 分类数: {len(DATA_CACHE.get('categories', {}))}")
    elif old_data_path.exists():
        with open(old_data_path, 'r', encoding='utf-8') as f:
            DATA_CACHE = json.load(f)
            print(f"✅ 已加载 MEKG 数据: {DATA_CACHE.get('papers_count', 0)} 篇论文, {DATA_CACHE.get('relations_count', 0)} 条关系")
    else:
        print(f"⚠️ MEKG 数据文件不存在")
    
    # 加载大纲
    outline_path = DATA_DIR / 'outline.json'
    if outline_path.exists():
        with open(outline_path, 'r', encoding='utf-8') as f:
            OUTLINE_CACHE = json.load(f)
            sections = OUTLINE_CACHE.get('sections', [])
            print(f"✅ 已加载大纲: {len(sections)} 个章节")
    else:
        print(f"⚠️ 大纲文件不存在: {outline_path}")


def get_outline_based_categories() -> Dict[str, Dict[str, int]]:
    """
    从大纲结构生成分类
    
    将大纲的章节（section）作为分类（category），
    子章节（subsection）作为子分类（subcategory）。
    
    Returns:
        Dict[str, Dict[str, int]]: {章节标题: {子章节标题: 论文数}}
    """
    categories = {}
    sections = OUTLINE_CACHE.get('sections', [])
    
    for section in sections:
        section_title = section.get('title', 'Unknown')
        subsections = section.get('subsections', [])
        
        if subsections:
            # 有子章节的情况
            categories[section_title] = {}
            for subsection in subsections:
                subsection_title = subsection.get('title', 'Unknown')
                # 统计挂载到该子章节的论文数
                paper_ids = subsection.get('paper_ids', [])
                categories[section_title][subsection_title] = len(paper_ids) if paper_ids else 0
        else:
            # 没有子章节的情况，使用章节本身
            paper_ids = section.get('paper_ids', [])
            categories[section_title] = {
                "General": len(paper_ids) if paper_ids else 0
            }
    
    return categories


def get_categories() -> Dict[str, Dict[str, int]]:
    """获取分类结构（根据配置选择来源）"""
    if USE_OUTLINE_AS_CATEGORIES and OUTLINE_CACHE:
        return get_outline_based_categories()
    else:
        return DATA_CACHE.get("categories", {})


def assign_papers_to_outline_sections(papers: List[Dict]) -> Dict[str, List[Dict]]:
    """
    将论文分配到大纲章节
    
    基于论文的 category/subcategory 字段，尝试匹配到大纲章节。
    如果无法匹配，则根据论文内容进行智能分配。
    
    Returns:
        Dict[str, List[Dict]]: {子章节ID: [论文列表]}
    """
    paper_by_section = {}
    sections = OUTLINE_CACHE.get('sections', [])
    
    # 构建章节关键词映射（用于智能匹配）
    section_keywords = {}
    for section in sections:
        section_title = section.get('title', '').lower()
        section_desc = section.get('description', '').lower()
        
        for subsection in section.get('subsections', []):
            subsection_title = subsection.get('title', '')
            subsection_desc = subsection.get('description', '').lower()
            
            # 提取关键词
            keywords = set()
            for text in [section_title, section_desc, subsection_title.lower(), subsection_desc]:
                words = text.replace('-', ' ').replace('_', ' ').split()
                keywords.update(w for w in words if len(w) > 3)
            
            section_id = f"subcat_{section.get('title', '')}_{subsection_title}".replace(' ', '_').replace('&', 'and')
            section_keywords[section_id] = {
                'section': section.get('title', ''),
                'subsection': subsection_title,
                'keywords': keywords
            }
    
    # 分配论文
    for paper in papers:
        paper_title = paper.get('title', '').lower()
        paper_abstract = paper.get('abstract', '').lower()
        paper_text = f"{paper_title} {paper_abstract}"
        
        # 计算每个章节的匹配分数
        best_match = None
        best_score = 0
        
        for section_id, info in section_keywords.items():
            score = sum(1 for kw in info['keywords'] if kw in paper_text)
            if score > best_score:
                best_score = score
                best_match = section_id
        
        # 如果找到匹配，分配到该章节
        if best_match and best_score > 0:
            if best_match not in paper_by_section:
                paper_by_section[best_match] = []
            paper_by_section[best_match].append(paper)
        else:
            # 默认分配到第一个章节
            if sections:
                first_section = sections[0]
                subsections = first_section.get('subsections', [])
                if subsections:
                    default_id = f"subcat_{first_section.get('title', '')}_{subsections[0].get('title', '')}".replace(' ', '_').replace('&', 'and')
                else:
                    default_id = f"subcat_{first_section.get('title', '')}_General".replace(' ', '_').replace('&', 'and')
                
                if default_id not in paper_by_section:
                    paper_by_section[default_id] = []
                paper_by_section[default_id].append(paper)
    
    return paper_by_section


load_data()


@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = project_root / 'mekg' / 'src' / 'visualization' / 'templates' / 'realtime_template.html'
    if template_path.exists():
        return template_path.read_text(encoding='utf-8')
    return "<h1>模板文件不存在</h1><p>请确保 realtime_template.html 存在</p>"


@app.get("/api/nodes")
async def get_nodes(use_outline: bool = Query(default=USE_OUTLINE_AS_CATEGORIES, description="是否使用大纲结构")):
    return JSONResponse(build_nodes(use_outline=use_outline))


@app.get("/api/edges")
async def get_edges():
    return JSONResponse(DATA_CACHE.get("relations", []))


@app.get("/api/hierarchy")
async def get_hierarchy(use_outline: bool = Query(default=USE_OUTLINE_AS_CATEGORIES, description="是否使用大纲结构")):
    return JSONResponse(build_hierarchy(use_outline=use_outline))


@app.get("/api/stats")
async def get_stats(use_outline: bool = Query(default=USE_OUTLINE_AS_CATEGORIES, description="是否使用大纲结构")):
    categories = get_outline_based_categories() if use_outline and OUTLINE_CACHE else DATA_CACHE.get("categories", {})
    subcategory_count = sum(len(subcats) for subcats in categories.values())
    nodes_count = DATA_CACHE.get("papers_count", 0) + len(categories) + subcategory_count + 1
    
    return JSONResponse({
        "topic": DATA_CACHE.get("topic", "Survey"),
        "papers_count": DATA_CACHE.get("papers_count", 0),
        "nodes_count": nodes_count,
        "relations_count": DATA_CACHE.get("relations_count", 0),
        "categories": categories,
        "relation_stats": DATA_CACHE.get("relation_stats", {}),
        "use_outline": use_outline and bool(OUTLINE_CACHE),
        "outline_title": OUTLINE_CACHE.get("title", "") if OUTLINE_CACHE else ""
    })


@app.get("/api/outline")
async def get_outline():
    """获取大纲结构"""
    return JSONResponse(OUTLINE_CACHE)


@app.post("/api/reload")
async def reload():
    load_data()
    return JSONResponse({"status": "ok", "message": "数据已重新加载"})


def build_nodes(use_outline: bool = True) -> List[Dict]:
    """
    构建可视化节点
    
    Args:
        use_outline: 是否使用大纲结构作为分类层级
    """
    nodes = []
    topic = DATA_CACHE.get("topic", "Survey")
    papers = DATA_CACHE.get("papers", [])
    
    # 布局参数
    CATEGORY_SPACING_X = 500  # 分类水平间距
    SUBCATEGORY_SPACING_Y = 150 # 子分类垂直间距
    PAPER_SPACING_Y = 60      # 论文垂直间距
    PAPER_OFFSET_X = 250      # 论文相对于子分类的水平偏移
    
    # 1. 根节点 (Topic)
    root_id = f"topic_{topic.replace(' ', '_')}"
    nodes.append({
        "id": root_id, "title": topic, "fullTitle": topic, "type": "topic",
        "level": 0, "x": 0, "y": 0, "width": 240, "height": 70, "parentId": None
    })
    
    # 选择分类来源
    if use_outline and OUTLINE_CACHE:
        # 使用大纲结构
        categories = get_outline_based_categories()
        paper_by_subcat = assign_papers_to_outline_sections(papers)
    else:
        # 使用原始分类
        categories = DATA_CACHE.get("categories", {})
        # 预处理论文数据（按原始分类）
        paper_by_subcat = {}
        for paper in papers:
            cat = paper.get("category", "Other")
            subcat = paper.get("subcategory", "Other")
            key = f"subcat_{cat}_{subcat}".replace(' ', '_').replace('&', 'and')
            if key not in paper_by_subcat:
                paper_by_subcat[key] = []
            paper_by_subcat[key].append(paper)

    # 计算每个分类的总高度
    cat_list = list(categories.items())
    total_width = len(cat_list) * CATEGORY_SPACING_X
    current_cat_x = -total_width / 2 + CATEGORY_SPACING_X / 2
    
    for cat_idx, (category, subcats) in enumerate(cat_list):
        cat_id = f"cat_{category.replace(' ', '_').replace('&', 'and')}"
        
        # 🔧 修复：先检查该分类下是否有任何论文
        # 如果所有子分类都没有论文，跳过整个分类
        has_papers_in_category = False
        for subcategory, count in subcats.items():
            subcat_id = f"subcat_{category}_{subcategory}".replace(' ', '_').replace('&', 'and')
            if paper_by_subcat.get(subcat_id, []):
                has_papers_in_category = True
                break
        
        if not has_papers_in_category:
            continue
        
        # 2. 分类节点 (Category / Section)
        nodes.append({
            "id": cat_id, "title": category[:30], "fullTitle": category, "type": "category",
            "level": 1, "x": current_cat_x, "y": 200, "width": 220, "height": 55, "parentId": root_id
        })
        
        # 计算该分类下所有子分类和论文的高度
        current_subcat_y = 350
        
        for subcat_idx, (subcategory, count) in enumerate(subcats.items()):
            subcat_id = f"subcat_{category}_{subcategory}".replace(' ', '_').replace('&', 'and')
            
            # 获取该子分类下的论文
            subcat_papers = paper_by_subcat.get(subcat_id, [])
            
            # 🔧 修复：跳过没有论文的子分类，避免显示空节点
            if not subcat_papers:
                continue
            
            # 按引用数排序，取前10篇
            sorted_papers = sorted(subcat_papers, key=lambda x: x.get("citations", 0), reverse=True)[:10]
            
            # 更新论文数（使用实际分配的论文数）
            actual_count = len(subcat_papers)
            
            # 计算子分类块的高度
            block_height = max(len(sorted_papers) * PAPER_SPACING_Y, 60)
            
            # 3. 子分类节点 (SubCategory / Subsection)
            nodes.append({
                "id": subcat_id, "title": subcategory[:25], "fullTitle": subcategory, "type": "subcategory",
                "level": 2, "x": current_cat_x, "y": current_subcat_y + block_height / 2 - 30, # 垂直居中
                "width": 180, "height": 48, "parentId": cat_id, "paperCount": actual_count
            })
            
            # 4. 论文节点 (Paper) - 垂直列表排列
            paper_start_y = current_subcat_y
            for paper_idx, paper in enumerate(sorted_papers):
                paper_id = paper.get("id", f"paper_{paper_idx}")
                
                nodes.append({
                    "id": paper_id, "title": paper.get("title", "")[:40], "fullTitle": paper.get("title", ""),
                    "type": "paper", "level": 3,
                    "x": current_cat_x + PAPER_OFFSET_X,
                    "y": paper_start_y + paper_idx * PAPER_SPACING_Y,
                    "width": 200, "height": 45, "parentId": subcat_id,
                    "year": paper.get("year"), "citations": paper.get("citations", 0)
                })
            
            current_subcat_y += block_height + 40 # 增加子分类间距
            
        current_cat_x += CATEGORY_SPACING_X

    return nodes


def build_hierarchy(use_outline: bool = True) -> List[Dict]:
    nodes = build_nodes(use_outline=use_outline)
    return [{"source": n["parentId"], "target": n["id"], "type": "hierarchy"} for n in nodes if n.get("parentId")]


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 MEKG Survey Visualization Server v2.0")
    print("=" * 60)
    print(f"\n📊 访问地址: http://localhost:8765")
    print(f"📁 数据目录: {DATA_DIR}")
    print(f"📋 分类模式: {'基于大纲结构' if USE_OUTLINE_AS_CATEGORIES else '基于论文分类'}")
    print("\n💡 API 端点:")
    print("   GET  /api/nodes?use_outline=true  - 获取节点（可切换分类模式）")
    print("   GET  /api/edges                   - 获取关系边")
    print("   GET  /api/hierarchy               - 获取层级结构")
    print("   GET  /api/stats                   - 获取统计信息")
    print("   GET  /api/outline                 - 获取大纲结构")
    print("   POST /api/reload                  - 重新加载数据")
    print("\n💡 提示: 按 Ctrl+C 停止服务器")
    print("=" * 60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8765)