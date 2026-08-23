"""
igraph vs NetworkX 性能对比测试

测试MEKG图谱在不同规模下的性能差异
"""

import sys
import time
import json
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from loguru import logger
from src.modules.mekg.data_structures import MEKGGraph
from src.modules.mekg.analyzer import MEKGAnalyzer

try:
    from src.modules.mekg.igraph_adapter import IGraphAdapter, IGRAPH_AVAILABLE
except ImportError:
    IGRAPH_AVAILABLE = False


def load_mekg_from_file(mekg_path: str) -> MEKGGraph:
    """从文件加载MEKG"""
    logger.info(f"加载MEKG: {mekg_path}")
    return MEKGGraph.load_from_file(mekg_path)


def benchmark_centrality(mekg: MEKGGraph, use_igraph: bool) -> Dict[str, Any]:
    """测试中心性计算性能"""
    analyzer = MEKGAnalyzer(mekg, use_igraph=use_igraph)
    
    start_time = time.time()
    metrics = analyzer.calculate_centrality_metrics()
    elapsed = time.time() - start_time
    
    return {
        "time": elapsed,
        "nodes": len(metrics),
        "engine": "igraph" if use_igraph else "NetworkX"
    }


def benchmark_community(mekg: MEKGGraph, use_igraph: bool) -> Dict[str, Any]:
    """测试社区发现性能"""
    analyzer = MEKGAnalyzer(mekg, use_igraph=use_igraph)
    
    start_time = time.time()
    communities = analyzer.detect_communities(algorithm="louvain")
    elapsed = time.time() - start_time
    
    num_communities = len(set(communities.values()))
    
    return {
        "time": elapsed,
        "communities": num_communities,
        "engine": "igraph" if use_igraph else "NetworkX"
    }


def benchmark_paths(mekg: MEKGGraph, use_igraph: bool) -> Dict[str, Any]:
    """测试路径追踪性能"""
    analyzer = MEKGAnalyzer(mekg, use_igraph=use_igraph)
    
    start_time = time.time()
    paths = analyzer.find_evolution_paths(max_depth=5)
    elapsed = time.time() - start_time
    
    return {
        "time": elapsed,
        "paths": len(paths),
        "engine": "igraph" if use_igraph else "NetworkX"
    }


def run_comprehensive_benchmark(mekg_path: str):
    """运行完整性能对比测试"""
    print("=" * 80)
    print("MEKG 图算法性能对比测试")
    print("=" * 80)
    
    # 检查igraph是否可用
    if not IGRAPH_AVAILABLE:
        print("\n❌ igraph未安装，无法进行对比测试")
        print("安装命令: pip install python-igraph")
        return
    
    # 加载MEKG
    mekg = load_mekg_from_file(mekg_path)
    
    print(f"\nMEKG规模:")
    print(f"  节点数: {mekg.node_count()}")
    print(f"  边数: {mekg.edge_count()}")
    print()
    
    results = {}
    
    # ==================== 测试1: 中心性计算 ====================
    print("[1] 中心性计算 (PageRank + Betweenness)")
    print("-" * 60)
    
    # NetworkX
    print("  测试 NetworkX...")
    nx_centrality = benchmark_centrality(mekg, use_igraph=False)
    print(f"    耗时: {nx_centrality['time']:.3f}秒")
    
    # igraph
    print("  测试 igraph...")
    ig_centrality = benchmark_centrality(mekg, use_igraph=True)
    print(f"    耗时: {ig_centrality['time']:.3f}秒")
    
    # 对比
    speedup = nx_centrality['time'] / ig_centrality['time']
    print(f"  ✅ 加速比: {speedup:.1f}x")
    print()
    
    results['centrality'] = {
        'networkx': nx_centrality,
        'igraph': ig_centrality,
        'speedup': speedup
    }
    
    # ==================== 测试2: 社区发现 ====================
    print("[2] 社区发现 (Louvain)")
    print("-" * 60)
    
    # NetworkX
    print("  测试 NetworkX...")
    nx_community = benchmark_community(mekg, use_igraph=False)
    print(f"    耗时: {nx_community['time']:.3f}秒")
    print(f"    社区数: {nx_community['communities']}")
    
    # igraph
    print("  测试 igraph...")
    ig_community = benchmark_community(mekg, use_igraph=True)
    print(f"    耗时: {ig_community['time']:.3f}秒")
    print(f"    社区数: {ig_community['communities']}")
    
    # 对比
    speedup = nx_community['time'] / ig_community['time']
    print(f"  ✅ 加速比: {speedup:.1f}x")
    print()
    
    results['community'] = {
        'networkx': nx_community,
        'igraph': ig_community,
        'speedup': speedup
    }
    
    # ==================== 测试3: 演进路径追踪 ====================
    print("[3] 演进路径追踪")
    print("-" * 60)
    
    # NetworkX
    print("  测试 NetworkX...")
    nx_paths = benchmark_paths(mekg, use_igraph=False)
    print(f"    耗时: {nx_paths['time']:.3f}秒")
    print(f"    路径数: {nx_paths['paths']}")
    
    # igraph
    print("  测试 igraph...")
    ig_paths = benchmark_paths(mekg, use_igraph=True)
    print(f"    耗时: {ig_paths['time']:.3f}秒")
    print(f"    路径数: {ig_paths['paths']}")
    
    # 对比
    speedup = nx_paths['time'] / ig_paths['time'] if ig_paths['time'] > 0 else float('inf')
    print(f"  ✅ 加速比: {speedup:.1f}x")
    print()
    
    results['paths'] = {
        'networkx': nx_paths,
        'igraph': ig_paths,
        'speedup': speedup
    }
    
    # ==================== 总结 ====================
    print("=" * 80)
    print("性能对比总结")
    print("=" * 80)
    
    total_nx_time = (
        nx_centrality['time'] + 
        nx_community['time'] + 
        nx_paths['time']
    )
    total_ig_time = (
        ig_centrality['time'] + 
        ig_community['time'] + 
        ig_paths['time']
    )
    overall_speedup = total_nx_time / total_ig_time
    
    print(f"\nNetworkX 总耗时: {total_nx_time:.3f}秒")
    print(f"igraph 总耗时:   {total_ig_time:.3f}秒")
    print(f"\n🚀 整体加速比: {overall_speedup:.1f}x")
    print(f"\n💡 建议: 使用igraph可节省 {(1 - total_ig_time/total_nx_time)*100:.1f}% 的计算时间")
    print()
    
    # 保存结果
    results['summary'] = {
        'total_networkx_time': total_nx_time,
        'total_igraph_time': total_ig_time,
        'overall_speedup': overall_speedup,
        'mekg_nodes': mekg.node_count(),
        'mekg_edges': mekg.edge_count()
    }
    
    output_path = Path(mekg_path).parent / "performance_benchmark.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"详细结果已保存到: {output_path}")
    print("=" * 80)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="MEKG性能对比测试")
    parser.add_argument(
        "--mekg",
        type=str,
        required=True,
        help="MEKG文件路径 (mekg.json)"
    )
    
    args = parser.parse_args()
    
    if not Path(args.mekg).exists():
        print(f"❌ 文件不存在: {args.mekg}")
        sys.exit(1)
    
    run_comprehensive_benchmark(args.mekg)


if __name__ == "__main__":
    # 示例用法
    # python scripts/test_igraph_performance.py --mekg outputs/mekg_xxx/mekg/mekg.json
    main()