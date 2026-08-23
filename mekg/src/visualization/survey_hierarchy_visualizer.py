"""
MEKG Survey Hierarchy Visualizer
================================

基于综述结构的2D层级可视化器，类似公司组织架构图。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class HierarchyNode:
    """层级节点"""
    id: str
    title: str
    level: int  # 0=Topic, 1=Category, 2=SubCategory, 3=Paper
    node_type: str  # 'topic', 'category', 'subcategory', 'paper'
    children: List['HierarchyNode'] = field(default_factory=list)
    parent: Optional['HierarchyNode'] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 0.5


@dataclass
class HierarchyEdge:
    """层级边"""
    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 1.0
    evidence: str = ""


class SurveyHierarchyBuilder:
    """从MEKG图谱构建综述层级结构"""
    
    def __init__(self):
        self.nodes: Dict[str, HierarchyNode] = {}
        self.edges: List[HierarchyEdge] = []
        self.root: Optional[HierarchyNode] = None
    
    def build_from_survey_structure(
        self,
        topic: str,
        categories: List[Dict[str, Any]],
        papers: List[Dict[str, Any]],
        relations: List[Dict[str, Any]]
    ) -> HierarchyNode:
        """从综述结构构建层级"""
        self.root = HierarchyNode(
            id=f"topic_{topic.replace(' ', '_')}",
            title=topic,
            level=0,
            node_type='topic'
        )
        self.nodes[self.root.id] = self.root
        
        paper_map = {p['id']: p for p in papers}
        
        for cat in categories:
            cat_node = HierarchyNode(
                id=f"cat_{cat['name'].replace(' ', '_')}",
                title=cat['name'],
                level=1,
                node_type='category',
                parent=self.root
            )
            self.nodes[cat_node.id] = cat_node
            self.root.children.append(cat_node)
            
            if 'subcategories' in cat and cat['subcategories']:
                for subcat in cat['subcategories']:
                    subcat_node = HierarchyNode(
                        id=f"subcat_{subcat['name'].replace(' ', '_')}",
                        title=subcat['name'],
                        level=2,
                        node_type='subcategory',
                        parent=cat_node
                    )
                    self.nodes[subcat_node.id] = subcat_node
                    cat_node.children.append(subcat_node)
                    
                    for paper_id in subcat.get('paper_ids', []):
                        if paper_id in paper_map:
                            paper = paper_map[paper_id]
                            paper_node = self._create_paper_node(paper, subcat_node)
                            subcat_node.children.append(paper_node)
            
            for paper_id in cat.get('paper_ids', []):
                if paper_id in paper_map:
                    paper = paper_map[paper_id]
                    paper_node = self._create_paper_node(paper, cat_node)
                    cat_node.children.append(paper_node)
        
        for rel in relations:
            self.edges.append(HierarchyEdge(
                source_id=rel['source'],
                target_id=rel['target'],
                relation_type=rel['type'],
                confidence=rel.get('confidence', 1.0),
                evidence=rel.get('evidence', '')
            ))
        
        return self.root
    
    def _create_paper_node(self, paper: Dict, parent: HierarchyNode) -> HierarchyNode:
        """创建论文节点"""
        node = HierarchyNode(
            id=paper['id'],
            title=paper.get('title', paper['id'])[:50],
            level=parent.level + 1,
            node_type='paper',
            parent=parent,
            metadata={
                'year': paper.get('year'),
                'citations': paper.get('citations', 0),
                'authors': paper.get('authors', []),
                'venue': paper.get('venue', ''),
                'full_title': paper.get('title', '')
            }
        )
        self.nodes[node.id] = node
        return node
    
    def build_from_example(self) -> HierarchyNode:
        """构建示例数据：Deep Learning on Graphs"""
        topic = "Deep Learning on Graphs"
        
        categories = [
            {
                'name': 'Graph Recurrent Neural Networks',
                'subcategories': [],
                'paper_ids': ['ggnn_2016', 'graphrnn_2018', 'gated_graph_2015']
            },
            {
                'name': 'Graph Convolutional Networks',
                'subcategories': [
                    {'name': 'Spectral Methods', 'paper_ids': ['spectral_cnn_2014', 'chebnet_2016', 'gcn_2017']},
                    {'name': 'Spatial Methods', 'paper_ids': ['graphsage_2017', 'gat_2018', 'gin_2019']}
                ],
                'paper_ids': []
            },
            {
                'name': 'Graph Autoencoders',
                'subcategories': [],
                'paper_ids': ['vgae_2016', 'graphvae_2018', 'arga_2018']
            },
            {
                'name': 'Graph Reinforcement Learning',
                'subcategories': [],
                'paper_ids': ['gcpn_2018', 'graphopt_2019']
            },
            {
                'name': 'Graph Adversarial Methods',
                'subcategories': [],
                'paper_ids': ['netgan_2018', 'graphgan_2018']
            }
        ]
        
        papers = [
            {'id': 'ggnn_2016', 'title': 'Gated Graph Sequence Neural Networks', 'year': 2016, 'citations': 3500},
            {'id': 'graphrnn_2018', 'title': 'GraphRNN: Generating Realistic Graphs', 'year': 2018, 'citations': 1200},
            {'id': 'gated_graph_2015', 'title': 'Gated Graph Neural Networks', 'year': 2015, 'citations': 2800},
            {'id': 'spectral_cnn_2014', 'title': 'Spectral Networks and Deep Locally Connected Networks', 'year': 2014, 'citations': 4200},
            {'id': 'chebnet_2016', 'title': 'Convolutional Neural Networks on Graphs with Fast Localized Spectral Filtering', 'year': 2016, 'citations': 5100},
            {'id': 'gcn_2017', 'title': 'Semi-Supervised Classification with Graph Convolutional Networks', 'year': 2017, 'citations': 18000},
            {'id': 'graphsage_2017', 'title': 'Inductive Representation Learning on Large Graphs', 'year': 2017, 'citations': 9500},
            {'id': 'gat_2018', 'title': 'Graph Attention Networks', 'year': 2018, 'citations': 12000},
            {'id': 'gin_2019', 'title': 'How Powerful are Graph Neural Networks?', 'year': 2019, 'citations': 4500},
            {'id': 'vgae_2016', 'title': 'Variational Graph Auto-Encoders', 'year': 2016, 'citations': 3200},
            {'id': 'graphvae_2018', 'title': 'GraphVAE: Towards Generation of Small Graphs', 'year': 2018, 'citations': 800},
            {'id': 'arga_2018', 'title': 'Adversarially Regularized Graph Autoencoder', 'year': 2018, 'citations': 950},
            {'id': 'gcpn_2018', 'title': 'Graph Convolutional Policy Network for Goal-Directed Molecular Graph Generation', 'year': 2018, 'citations': 1100},
            {'id': 'graphopt_2019', 'title': 'Graph Optimization with Reinforcement Learning', 'year': 2019, 'citations': 450},
            {'id': 'netgan_2018', 'title': 'NetGAN: Generating Graphs via Random Walks', 'year': 2018, 'citations': 680},
            {'id': 'graphgan_2018', 'title': 'GraphGAN: Graph Representation Learning with Generative Adversarial Nets', 'year': 2018, 'citations': 720},
        ]
        
        relations = [
            {'source': 'gcn_2017', 'target': 'chebnet_2016', 'type': 'improves', 'confidence': 0.95},
            {'source': 'gcn_2017', 'target': 'spectral_cnn_2014', 'type': 'extends', 'confidence': 0.9},
            {'source': 'gat_2018', 'target': 'gcn_2017', 'type': 'improves', 'confidence': 0.92},
            {'source': 'graphsage_2017', 'target': 'gcn_2017', 'type': 'extends', 'confidence': 0.88},
            {'source': 'gin_2019', 'target': 'gcn_2017', 'type': 'extends', 'confidence': 0.85},
            {'source': 'gin_2019', 'target': 'graphsage_2017', 'type': 'compares', 'confidence': 0.9},
            {'source': 'gat_2018', 'target': 'graphsage_2017', 'type': 'cites', 'confidence': 1.0},
            {'source': 'vgae_2016', 'target': 'gcn_2017', 'type': 'applies', 'confidence': 0.85},
            {'source': 'arga_2018', 'target': 'vgae_2016', 'type': 'improves', 'confidence': 0.9},
            {'source': 'gcn_2017', 'target': 'graphsage_2017', 'type': 'shares_task', 'confidence': 0.95},
            {'source': 'gat_2018', 'target': 'gin_2019', 'type': 'shares_dataset', 'confidence': 0.9},
        ]
        
        return self.build_from_survey_structure(topic, categories, papers, relations)


class HierarchyLayoutEngine:
    """层级布局引擎 - 优化的树形布局算法"""
    
    # 不同层级的垂直间距配置
    LEVEL_HEIGHTS = {
        0: 3.0,  # Topic -> Category 间距较大
        1: 2.8,  # Category -> SubCategory
        2: 2.5,  # SubCategory -> Paper
        3: 2.0,  # Paper 之间（如果有更深层级）
    }
    
    # 不同层级的水平间距配置
    LEVEL_SPACINGS = {
        0: 3.0,  # Category 之间间距较大
        1: 2.5,  # SubCategory 之间
        2: 1.8,  # Paper 之间间距较小
        3: 1.5,
    }
    
    def __init__(self, base_level_height: float = 2.5, base_node_spacing: float = 2.0,
                 min_node_width: float = 2.0, max_node_width: float = 6.0,
                 compact_mode: bool = False):
        """
        初始化布局引擎
        
        Args:
            base_level_height: 基础层级垂直间距
            base_node_spacing: 基础节点水平间距
            min_node_width: 节点最小宽度
            max_node_width: 节点最大宽度
            compact_mode: 紧凑模式，减少间距
        """
        self.base_level_height = base_level_height
        self.base_node_spacing = base_node_spacing
        self.min_node_width = min_node_width
        self.max_node_width = max_node_width
        self.compact_mode = compact_mode
        
        # 紧凑模式下减少间距
        if compact_mode:
            self.LEVEL_HEIGHTS = {k: v * 0.7 for k, v in self.LEVEL_HEIGHTS.items()}
            self.LEVEL_SPACINGS = {k: v * 0.7 for k, v in self.LEVEL_SPACINGS.items()}
    
    def _get_level_height(self, level: int) -> float:
        """获取指定层级的垂直间距"""
        return self.LEVEL_HEIGHTS.get(level, self.base_level_height)
    
    def _get_level_spacing(self, level: int) -> float:
        """获取指定层级的水平间距"""
        return self.LEVEL_SPACINGS.get(level, self.base_node_spacing)
    
    def layout(self, root: HierarchyNode) -> Dict[str, Tuple[float, float, float, float]]:
        """计算所有节点的布局位置"""
        positions = {}
        subtree_widths = self._calculate_subtree_widths(root)
        self._assign_positions(root, 0, 0, subtree_widths, positions)
        return positions
    
    def _calculate_subtree_widths(self, node: HierarchyNode) -> Dict[str, float]:
        """计算每个节点子树的宽度"""
        widths = {}
        
        def calc_width(n: HierarchyNode) -> float:
            if not n.children:
                width = self._get_node_width(n)
            else:
                # 获取当前层级的间距
                spacing = self._get_level_spacing(n.level)
                children_width = sum(calc_width(c) for c in n.children)
                children_width += spacing * (len(n.children) - 1)
                width = max(children_width, self._get_node_width(n))
            widths[n.id] = width
            return width
        
        calc_width(root)
        return widths
    
    def _get_node_width(self, node: HierarchyNode) -> float:
        """根据节点类型和标题长度计算节点宽度"""
        # 基于标题长度计算基础宽度
        base_width = len(node.title) * 0.12
        
        if node.node_type == 'topic':
            # 主题节点最宽
            return max(self.max_node_width * 1.2, base_width)
        elif node.node_type == 'category':
            # 分类节点较宽
            return max(self.min_node_width * 1.8, min(base_width, self.max_node_width))
        elif node.node_type == 'subcategory':
            # 子分类节点中等宽度
            return max(self.min_node_width * 1.4, min(base_width, self.max_node_width * 0.85))
        else:
            # 论文节点较窄但保证可读性
            return max(self.min_node_width * 1.2, min(base_width, self.max_node_width * 0.75))
    
    def _get_node_height(self, node: HierarchyNode) -> float:
        """根据节点类型计算节点高度"""
        if node.node_type == 'topic':
            return 1.0
        elif node.node_type == 'category':
            return 0.85
        elif node.node_type == 'subcategory':
            return 0.7
        else:
            return 0.6
    
    def _assign_positions(self, node: HierarchyNode, x_offset: float, y_offset: float,
                          subtree_widths: Dict[str, float],
                          positions: Dict[str, Tuple[float, float, float, float]]):
        """递归分配节点位置"""
        width = self._get_node_width(node)
        height = self._get_node_height(node)
        
        subtree_width = subtree_widths[node.id]
        x = x_offset + subtree_width / 2
        y = y_offset
        
        positions[node.id] = (x, y, width, height)
        node.x = x
        node.y = y
        node.width = width
        node.height = height
        
        if node.children:
            # 获取当前层级的间距
            spacing = self._get_level_spacing(node.level)
            level_height = self._get_level_height(node.level)
            
            # 计算子节点的起始位置
            child_x = x_offset
            child_y = y_offset - level_height
            
            for child in node.children:
                child_width = subtree_widths[child.id]
                self._assign_positions(child, child_x, child_y, subtree_widths, positions)
                child_x += child_width + spacing


class SurveyHierarchyRenderer:
    """综述层级可视化渲染器"""
    
    NODE_COLORS = {
        'topic': '#6366f1',
        'category': '#3b82f6',
        'subcategory': '#10b981',
        'paper': '#f59e0b'
    }
    
    def __init__(self):
        self.template_path = Path(__file__).parent / 'templates' / 'hierarchy_template.html'
    
    def render_html(self, root: HierarchyNode, edges: List[HierarchyEdge],
                    positions: Dict[str, Tuple[float, float, float, float]],
                    output_path: Path, title: str = "Survey Knowledge Graph Hierarchy") -> str:
        """生成交互式HTML可视化"""
        all_nodes = self._collect_all_nodes(root)
        
        nodes_data = []
        for node in all_nodes:
            pos = positions[node.id]
            nodes_data.append({
                'id': node.id,
                'title': node.title,
                'fullTitle': node.metadata.get('full_title', node.title) if node.metadata else node.title,
                'type': node.node_type,
                'level': node.level,
                'x': pos[0] * 100,
                'y': -pos[1] * 100,
                'width': pos[2] * 100,
                'height': pos[3] * 100,
                'year': node.metadata.get('year') if node.metadata else None,
                'citations': node.metadata.get('citations', 0) if node.metadata else 0,
                'parentId': node.parent.id if node.parent else None
            })
        
        edges_data = []
        for edge in edges:
            if edge.source_id in positions and edge.target_id in positions:
                edges_data.append({
                    'source': edge.source_id,
                    'target': edge.target_id,
                    'type': edge.relation_type,
                    'confidence': edge.confidence,
                    'evidence': edge.evidence
                })
        
        hierarchy_edges = []
        for node in all_nodes:
            if node.parent:
                hierarchy_edges.append({
                    'source': node.parent.id,
                    'target': node.id,
                    'type': 'hierarchy'
                })
        
        # 读取模板并替换数据
        template = self._load_template()
        html_content = template.replace('{{TITLE}}', title)
        html_content = html_content.replace('{{NODES_DATA}}', json.dumps(nodes_data, ensure_ascii=False, indent=2))
        html_content = html_content.replace('{{EDGES_DATA}}', json.dumps(edges_data, ensure_ascii=False, indent=2))
        html_content = html_content.replace('{{HIERARCHY_DATA}}', json.dumps(hierarchy_edges, ensure_ascii=False, indent=2))
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ 交互式HTML已保存到: {output_path}")
        return str(output_path)
    
    def _collect_all_nodes(self, root: HierarchyNode) -> List[HierarchyNode]:
        nodes = [root]
        for child in root.children:
            nodes.extend(self._collect_all_nodes(child))
        return nodes
    
    def _load_template(self) -> str:
        """加载HTML模板"""
        if self.template_path.exists():
            with open(self.template_path, 'r', encoding='utf-8') as f:
                return f.read()
        raise FileNotFoundError(f"模板文件不存在: {self.template_path}")


def generate_example_visualization(output_dir: Path = None):
    """生成示例可视化"""
    if output_dir is None:
        output_dir = Path(__file__).parent.parent.parent.parent / 'outputs' / 'visualization'
    
    # 构建示例数据
    builder = SurveyHierarchyBuilder()
    root = builder.build_from_example()
    
    # 计算布局
    layout_engine = HierarchyLayoutEngine()
    positions = layout_engine.layout(root)
    
    # 渲染HTML
    renderer = SurveyHierarchyRenderer()
    output_path = output_dir / 'deep_learning_on_graphs_hierarchy.html'
    renderer.render_html(root, builder.edges, positions, output_path, 
                        title="Deep Learning on Graphs - Survey Structure")
    
    return output_path


if __name__ == '__main__':
    output = generate_example_visualization()
    print(f"示例可视化已生成: {output}")