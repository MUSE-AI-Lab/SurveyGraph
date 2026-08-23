"""
测试全局图谱管理器
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parents[3]))

from mekg.src.automation.global_graph_manager import GlobalGraphManager

def test_merge():
    # 使用测试数据库
    db_path = "data/graph_db/test_global_graph.db"
    
    # 如果存在则删除，确保干净的测试环境
    if os.path.exists(db_path):
        os.remove(db_path)
        
    manager = GlobalGraphManager(db_path)
    
    # 查找一个存在的mekg_data.json
    # 这里使用之前ls看到的路径
    mekg_file = "outputs/20251224_194022_2baaf796/mekg/mekg_data.json"
    
    if not os.path.exists(mekg_file):
        print(f"Warning: Test file {mekg_file} not found. Skipping test.")
        return
        
    print(f"Merging {mekg_file}...")
    stats = manager.merge_task_graph(mekg_file)
    
    print("\nMerge Result:")
    print(stats)
    
    # 验证数据库内容
    db_stats = manager.get_graph_statistics()
    print("\nDatabase Statistics:")
    print(db_stats)
    
    assert db_stats["papers"] > 0
    print("\nTest Passed!")

if __name__ == "__main__":
    test_merge()