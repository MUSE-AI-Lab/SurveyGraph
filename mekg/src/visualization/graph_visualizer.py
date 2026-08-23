from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Tuple

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import networkx as nx
import numpy as np

from mekg.src.core.data_structures import MEKGEdge, MEKGGraph, MEKGNode, RelationType

PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]


def _assign_colors(unique_keys: Iterable[int]) -> Dict[int, str]:
    colors: Dict[int, str] = {}
    keys = list(sorted(k for k in unique_keys if k is not None))
    for idx, key in enumerate(keys):
        colors[key] = PALETTE[idx % len(PALETTE)]
    return colors


def render_hierarchical_tree(
    mekg: MEKGGraph,
    output_path: Path,
    highlight_nodes: Optional[Set[str]] = None,
) -> None:
    """
    Render a top-down tree focusing on evolutionary (evolved_from) relations.
    Communities become colored sub-branches and core nodes appear larger.
    """

    dag = nx.DiGraph()
    for node_id, data in mekg.graph.nodes(data=True):
        dag.add_node(node_id, **data)

    has_evolution = False
    for edge in mekg.edges:
        if edge.relation_type == RelationType.EVOLVED_FROM:
            has_evolution = True
            # Draw from ancestor -> descendant
            dag.add_edge(edge.target, edge.source, weight=edge.confidence or 0.5)

    if not has_evolution:
        # Fallback: connect high pagerank nodes in sequence to keep layout meaningful
        sorted_nodes = sorted(
            dag.nodes(),
            key=lambda n: dag.nodes[n].get("pagerank", 0.0),
            reverse=True,
        )
        for idx in range(len(sorted_nodes) - 1):
            dag.add_edge(sorted_nodes[idx], sorted_nodes[idx + 1], weight=0.1)

    # Determine hierarchical levels via BFS from root nodes
    roots = [n for n, deg in dag.in_degree() if deg == 0]
    if not roots:
        roots = list(dag.nodes())[:1]

    levels: Dict[str, int] = {}
    queue: List[str] = list(roots)
    for root in roots:
        levels[root] = 0

    while queue:
        current = queue.pop(0)
        for child in dag.successors(current):
            if child not in levels:
                levels[child] = levels[current] + 1
                queue.append(child)

    # Any isolated nodes not discovered
    for node in dag.nodes():
        if node not in levels:
            levels[node] = max(levels.values(), default=0) + 1

    # Layout nodes level by level
    level_groups: Dict[int, list] = {}
    for node, level in levels.items():
        level_groups.setdefault(level, []).append(node)

    pos: Dict[str, Tuple[float, float]] = {}
    for level in sorted(level_groups.keys()):
        group = level_groups[level]
        group.sort(key=lambda n: dag.nodes[n].get("pagerank", 0.0), reverse=True)
        span = max(len(group) - 1, 1)
        for idx, node in enumerate(group):
            x = (idx - span / 2) * 1.5
            y = -level * 2.0
            pos[node] = (x, y)

    communities = [data.get("community_id") for _, data in dag.nodes(data=True)]
    community_colors = _assign_colors(set(communities))

    node_list = list(dag.nodes())
    node_colors = [
        community_colors.get(dag.nodes[n].get("community_id"), "#cccccc")
        for n in node_list
    ]
    node_sizes = [
        400 + (dag.nodes[n].get("pagerank", 0.0) or 0.0) * 3000 for n in node_list
    ]

    plt.figure(figsize=(18, 12))
    nx.draw_networkx_edges(
        dag,
        pos,
        edge_color="#bbbbbb",
        arrows=True,
        arrowstyle="-|>",
        arrowsize=12,
        alpha=0.6,
        width=1.2,
    )
    nx.draw_networkx_nodes(
        dag,
        pos,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.95,
    )

    labels = {
        n: dag.nodes[n].get("title", "")[:28] + ("…" if len(dag.nodes[n].get("title", "")) > 28 else "")
        for n in dag.nodes()
    }
    nx.draw_networkx_labels(
        dag,
        pos,
        labels=labels,
        font_size=8,
        font_color="#1d1d1d",
    )

    if highlight_nodes:
        highlight = [n for n in node_list if n in highlight_nodes]
        if highlight:
            nx.draw_networkx_nodes(
                dag,
                pos,
                nodelist=highlight,
                node_color="none",
                edgecolors="#111111",
                linewidths=1.8,
                node_size=[
                    node_sizes[node_list.index(n)] * 1.1 for n in highlight
                ],
            )

    plt.title("MEKG Evolution Tree (Top-Down)", fontsize=16)
    plt.axis("off")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def render_community_map(
    mekg: MEKGGraph,
    output_path: Path,
    highlight_nodes: Optional[Set[str]] = None,
) -> None:
    """
    Render a map-like visualization with spring layout, dashed community boundaries,
    and color-coded nodes.
    """

    G = mekg.graph.copy()
    if G.number_of_nodes() == 0:
        return

    pos = nx.spring_layout(G, weight="weight", seed=42, k=1.5 / math.sqrt(G.number_of_nodes()))

    communities: Dict[int, list] = {}
    for node, data in G.nodes(data=True):
        cid = data.get("community_id")
        communities.setdefault(cid, []).append(node)

    community_colors = _assign_colors(communities.keys())
    node_list = list(G.nodes())
    node_colors = [
        community_colors.get(G.nodes[n].get("community_id"), "#a0a0a0") for n in G.nodes()
    ]
    node_sizes = [
        200 + (G.nodes[n].get("pagerank", 0.0) or 0.0) * 2500 for n in node_list
    ]

    plt.figure(figsize=(20, 14))
    ax = plt.gca()

    nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        width=0.8,
        alpha=0.25,
        edge_color="#999999",
    )

    nx.draw_networkx_nodes(
        G,
        pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.9,
    )

    if highlight_nodes:
        highlight = [n for n in node_list if n in highlight_nodes]
        if highlight:
            nx.draw_networkx_nodes(
                G,
                pos,
                nodelist=highlight,
                ax=ax,
                node_color="none",
                edgecolors="#000000",
                linewidths=1.5,
                node_size=[node_sizes[node_list.index(n)] * 1.15 for n in highlight],
            )

    # Draw dashed borders per community
    for cid, nodes in communities.items():
        if cid is None or len(nodes) < 2:
            continue
        xs = np.array([pos[n][0] for n in nodes])
        ys = np.array([pos[n][1] for n in nodes])
        center_x, center_y = xs.mean(), ys.mean()
        width = xs.max() - xs.min()
        height = ys.max() - ys.min()
        pad = 0.2
        ellipse = patches.Ellipse(
            (center_x, center_y),
            width + pad,
            height + pad,
            linewidth=1.5,
            edgecolor=community_colors.get(cid, "#333333"),
            facecolor="none",
            linestyle="--",
            alpha=0.9,
        )
        ax.add_patch(ellipse)
        ax.text(
            center_x,
            center_y + (height + pad) / 2 + 0.03,
            f"Community {cid}",
            fontsize=10,
            ha="center",
            color=community_colors.get(cid, "#333333"),
        )

    ax.set_title("MEKG Community Map", fontsize=18)
    ax.axis("off")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=320, bbox_inches="tight")
    plt.close()


class GraphVisualizer:
    """
    MEKG 图谱可视化器

    - 输入: pipeline 产出的 `mekg_data` 字典（含 papers/relations）
    - 输出: 静态图（community map / evolution tree），用于论文插图或快速检查
    """

    def __init__(self, max_nodes: int = 300):
        self.max_nodes = max_nodes

    def build_graph_from_mekg_data(self, mekg_data: Dict[str, Any]) -> MEKGGraph:
        """将 pipeline 的 mekg_data 转为可视化使用的 MEKGGraph。"""
        mekg = MEKGGraph()

        papers = mekg_data.get("papers", []) or []
        for paper in papers:
            paper_id = paper.get("id") or paper.get("paper_id") or ""
            if not paper_id:
                continue

            authors = paper.get("authors", "")
            if isinstance(authors, list):
                if authors and isinstance(authors[0], dict):
                    authors = ", ".join([a.get("name", "") for a in authors if a.get("name")])
                else:
                    authors = ", ".join([str(a) for a in authors if a])
            authors = str(authors or "")

            year = paper.get("year") or 0
            if isinstance(year, str) and year.isdigit():
                year = int(year)
            if not isinstance(year, int):
                year = 0

            citations = paper.get("citations", paper.get("citation_count", 0)) or 0
            try:
                citations = int(citations)
            except Exception:
                citations = 0

            node = MEKGNode(
                paper_id=paper_id,
                title=paper.get("title", "") or paper_id,
                abstract=paper.get("abstract", "") or "",
                authors=authors,
                year=year,
                venue=paper.get("venue", "") or "",
                citation_count=citations,
                metadata=paper,
            )
            mekg.add_node(node)

        # 将所有关系写入 NetworkX 图（用于布局/中心性），并尽可能保留 evolved_from 到 edges 列表
        relations = mekg_data.get("relations", []) or []
        for rel in relations:
            src = rel.get("source") or ""
            tgt = rel.get("target") or ""
            if not src or not tgt:
                continue

            conf = rel.get("confidence", 0.5)
            try:
                conf = float(conf)
            except Exception:
                conf = 0.5

            rel_type = rel.get("type") or rel.get("relation_type") or ""

            # 可能存在 paper 未进入 papers 列表但被关系引用的情况：补一个轻量节点
            if src not in mekg.graph:
                mekg.graph.add_node(src, title=src)
            if tgt not in mekg.graph:
                mekg.graph.add_node(tgt, title=tgt)

            mekg.graph.add_edge(
                src,
                tgt,
                weight=conf,
                confidence=conf,
                relation_type=rel_type,
            )

            if str(rel_type).lower() == RelationType.EVOLVED_FROM.value:
                try:
                    mekg.edges.append(
                        MEKGEdge(
                            source=src,
                            target=tgt,
                            relation_type=RelationType.EVOLVED_FROM,
                            confidence=conf,
                        )
                    )
                except Exception:
                    # 只影响层级树，不影响 community map
                    pass

        # 如果节点太多，裁剪到 top-N（按 citation_count / pagerank ）
        if self.max_nodes and mekg.graph.number_of_nodes() > self.max_nodes:
            nodes_sorted = sorted(
                mekg.graph.nodes(),
                key=lambda n: float(mekg.graph.nodes[n].get("citation_count", 0) or 0),
                reverse=True,
            )
            keep = set(nodes_sorted[: self.max_nodes])
            mekg.graph = mekg.graph.subgraph(keep).copy()
            # edges 列表也裁剪
            mekg.edges = [e for e in mekg.edges if e.source in keep and e.target in keep]

        # PageRank（用于 size）
        try:
            pr = nx.pagerank(mekg.graph, weight="weight")
        except Exception:
            pr = {n: 0.0 for n in mekg.graph.nodes()}
        max_pr = max(pr.values()) if pr else 1.0
        for node, score in pr.items():
            norm = (score / max_pr) if max_pr > 0 else 0.0
            mekg.graph.nodes[node]["pagerank"] = norm

        # 社区划分（用于颜色）
        try:
            undirected = mekg.graph.to_undirected()
            communities = list(nx.algorithms.community.greedy_modularity_communities(undirected))
            for cid, members in enumerate(communities):
                for node in members:
                    mekg.graph.nodes[node]["community_id"] = cid
        except Exception:
            # 保持 community_id 缺失即可
            pass

        return mekg

    def render(
        self,
        mekg_data: Dict[str, Any],
        output_dir: Path,
        *,
        highlight_topk: int = 12,
    ) -> Dict[str, Path]:
        """生成核心静态图（PNG），返回产物路径。"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        mekg = self.build_graph_from_mekg_data(mekg_data)

        # 默认高亮 top-k PageRank 节点
        highlight_nodes: Set[str] = set()
        try:
            ranked = sorted(
                mekg.graph.nodes(),
                key=lambda n: float(mekg.graph.nodes[n].get("pagerank", 0.0) or 0.0),
                reverse=True,
            )
            highlight_nodes = set(ranked[:highlight_topk])
        except Exception:
            pass

        community_map_path = output_dir / "mekg_community_map.png"
        evolution_tree_path = output_dir / "mekg_evolution_tree.png"

        render_community_map(mekg, community_map_path, highlight_nodes=highlight_nodes)
        render_hierarchical_tree(mekg, evolution_tree_path, highlight_nodes=highlight_nodes)

        return {
            "community_map": community_map_path,
            "evolution_tree": evolution_tree_path,
        }
