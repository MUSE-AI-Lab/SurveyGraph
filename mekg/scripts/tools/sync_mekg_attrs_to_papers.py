import json
import os
from pathlib import Path

TASK_ID = "mekg_Large_Language_Model_Tool_Call_20251119_160117"
MEKG_PATH = Path(f"outputs/{TASK_ID}/mekg/mekg.json")
PAPERS_DIR = Path(f"outputs/{TASK_ID}/papers")

def sync():
    if not MEKG_PATH.exists():
        print(f"MEKG file not found: {MEKG_PATH}")
        return

    print(f"Loading MEKG from {MEKG_PATH}...")
    with open(MEKG_PATH, 'r', encoding='utf-8') as f:
        mekg = json.load(f)
    
    nodes = mekg.get('nodes', [])
    print(f"Loaded {len(nodes)} nodes from MEKG.")
    
    # Debug: Print first node
    if nodes:
        print(f"Sample node: {json.dumps(nodes[0], indent=2)}")

    count = 0
    matched_files = 0
    for node in nodes:
        paper_id = node.get('paper_id') or node.get('id')
        if not paper_id: continue
        
        # 查找对应的论文文件
        paper_path = PAPERS_DIR / f"{paper_id}.json"
        if not paper_path.exists():
            # 尝试不带后缀的ID
            paper_path = PAPERS_DIR / f"{paper_id.split('.')[0]}.json"
            if not paper_path.exists():
                # print(f"File not found for {paper_id}")
                continue
        
        matched_files += 1
            
        # 读取论文文件
        try:
            with open(paper_path, 'r', encoding='utf-8') as f:
                paper_data = json.load(f)
        except Exception as e:
            print(f"Error reading {paper_path}: {e}")
            continue
        
        updated = False
        
        # Extract attributes from node or metadata
        attributes = node.get('attri') or node.get('metadata', {}).get('attributes')
        
        # 同步属性
        if attributes:
            paper_data['attri'] = attributes
            updated = True
        
        # 同步 paper_type (如果 MEKG 中有)
        if 'paper_type' in node:
            paper_data['paper_type'] = node['paper_type']
            updated = True
        # 如果 MEKG 没有 paper_type，尝试从 attri 推断
        elif attributes:
            if 'dataset' in attributes and 'metrics' in attributes:
                paper_data['paper_type'] = 'benchmark'
                updated = True
            elif 'method' in attributes:
                paper_data['paper_type'] = 'method'
                updated = True

        # 同步 bib_name
        if 'bib_name' in node:
            paper_data['bib_name'] = node['bib_name']
            updated = True
        elif paper_id and 'bib_name' not in paper_data: # Fallback bib_name
             paper_data['bib_name'] = paper_id
             updated = True

        if updated:
            with open(paper_path, 'w', encoding='utf-8') as f:
                json.dump(paper_data, f, indent=4, ensure_ascii=False)
            count += 1
    
    print(f"Matched {matched_files} files. Synced attributes to {count} paper files.")

if __name__ == "__main__":
    sync()