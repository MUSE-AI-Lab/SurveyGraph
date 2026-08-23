import os
import json
import glob
import sys
from pathlib import Path
from datetime import datetime

# 添加 src 到 pythonpath 以便导入模块 (如果需要)
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def find_latest_output_dir(base_path):
    """找到 src/outputs 下最新的任务目录 (必须包含 supplemented_papers)"""
    dirs = [d for d in glob.glob(os.path.join(base_path, "*")) if os.path.isdir(d)]
    
    # 过滤掉没有 supplemented_papers 的目录
    valid_dirs = []
    for d in dirs:
        if os.path.exists(os.path.join(d, "supplemented_papers")):
            valid_dirs.append(d)
            
    if not valid_dirs:
        return None
        
    # 按修改时间排序
    return max(valid_dirs, key=os.path.getmtime)

def load_papers_from_dir(output_dir):
    """读取 supplemented_papers 下的 JSON 文件"""
    papers_dir = os.path.join(output_dir, "supplemented_papers")
    if not os.path.exists(papers_dir):
        print(f"Warning: {papers_dir} does not exist.")
        return []

    papers = []
    for json_file in glob.glob(os.path.join(papers_dir, "*.json")):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 添加文件路径作为 ID 的一部分，防止 ID 冲突
                data['_filename'] = os.path.basename(json_file)
                papers.append(data)
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
    
    return papers

def generate_mekg_data(papers):
    """将论文数据转换为 ECharts 格式"""
    nodes = []
    links = []
    categories = []
    
    category_map = {}  # name -> index
    
    # 1. 处理分类 (基于 section_for)
    sections = set()
    for p in papers:
        section = p.get('section_for', 'Uncategorized')
        sections.add(section)
    
    sorted_sections = sorted(list(sections))
    for idx, section in enumerate(sorted_sections):
        categories.append({"name": section})
        category_map[section] = idx
        
        # 可选：为每个 Section 创建一个中心节点，让图谱更好看
        # section_node_id = f"section_{idx}"
        # nodes.append({
        #     "id": section_node_id,
        #     "name": section,
        #     "value": 50,
        #     "symbolSize": 30,
        #     "category": idx,
        #     "attributes": {"type": "Section"}
        # })

    # 2. 处理节点
    for i, p in enumerate(papers):
        # 生成唯一 ID
        paper_id = p.get('doi') or p.get('title') or f"paper_{i}"
        
        # 获取分类索引
        section = p.get('section_for', 'Uncategorized')
        cat_idx = category_map.get(section, 0)
        
        # 构建属性
        attributes = {
            "Title": p.get('title', 'Unknown'),
            "Authors": p.get('authors', 'Unknown'),
            "Year": p.get('year', 'Unknown'),
            "Venue": p.get('venue', 'Unknown'),
            "Section": section,
            "Abstract": p.get('abstract', '')[:200] + "..." if p.get('abstract') else ""
        }
        
        # 添加 DOI 链接
        if p.get('doi'):
            attributes["DOI"] = p.get('doi')

        node = {
            "id": paper_id,
            "name": p.get('title', 'Unknown')[:20] + "...", # 缩短显示名称
            "full_name": p.get('title', 'Unknown'),
            "value": 10, # 默认权重
            "category": cat_idx,
            "attributes": attributes
        }
        nodes.append(node)
        
        # 如果启用了 Section 中心节点，可以在这里添加连线
        # section_node_id = f"section_{cat_idx}"
        # links.append({
        #     "source": section_node_id,
        #     "target": paper_id,
        #     "value": "belongs_to"
        # })

    # 3. 尝试构建引用关系 (如果有)
    # 目前 JSON 中没有明确的引用列表，所以暂时留空
    # 如果未来有 references 字段，可以在这里遍历添加 links
    
    return {
        "nodes": nodes,
        "links": links,
        "categories": categories
    }

def export_to_js(data, output_path):
    """写入 JS 文件"""
    js_content = f"""/**
 * MEKG 数据文件
 * Generated at {datetime.now().isoformat()}
 */

window.MEKG_DATA = {json.dumps(data, ensure_ascii=False, indent=2)};
"""
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)
    print(f"Successfully exported data to {output_path}")

def main():
    base_output_dir = "src/outputs"
    target_js_path = "src/visualization/mekg_viewer/js/data.js"
    
    # 支持通过命令行参数指定目录
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
        if os.path.exists(target_dir):
            latest_dir = target_dir
        else:
            # 尝试在 base_output_dir 中查找
            potential_path = os.path.join(base_output_dir, target_dir)
            if os.path.exists(potential_path):
                latest_dir = potential_path
            else:
                print(f"Error: Directory {target_dir} not found.")
                return
    else:
        print(f"Searching for latest output in {base_output_dir}...")
        latest_dir = find_latest_output_dir(base_output_dir)
    
    if not latest_dir:
        print("No output directories found.")
        return
    
    print(f"Using directory: {latest_dir}")
    
    print("Loading papers...")
    papers = load_papers_from_dir(latest_dir)
    print(f"Loaded {len(papers)} papers.")
    
    if not papers:
        print("No papers found to export.")
        return
    
    print("Generating graph data...")
    graph_data = generate_mekg_data(papers)
    
    print(f"Generated {len(graph_data['nodes'])} nodes and {len(graph_data['links'])} links.")
    
    print("Exporting to JS...")
    export_to_js(graph_data, target_js_path)

if __name__ == "__main__":
    main()