"""
MEKG V2 小图谱提取脚本

功能：
1. 从持久化大图谱中提取指定topic的小图谱
2. 匹配Survey模板
3. 生成综述写作所需的结构化数据
4. 导出为多种格式（JSON、Markdown、可视化）

使用方法：
    python scripts/extract_survey_subgraph.py --topic "LLM Tool Calling" --output outputs/tool_calling_survey
    
    或搜索新topic：
    python scripts/extract_survey_subgraph.py --topic "Code Generation" --search-network --output outputs/code_gen_survey
"""

import asyncio
import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from src.modules.mekg.persistent_graph_db import PersistentGraphDB, SubGraph
from src.modules.mekg.dual_search_orchestrator import DualSearchOrchestrator
from src.modules.mekg.survey_template_library import SurveyTemplateLibrary, initialize_default_templates
from src.modules.mekg.paper_pool_collector import PaperPoolCollector
from src.modules.mekg.enhanced_relation_discoverer import EnhancedRelationDiscoverer


class SurveySubgraphExtractor:
    """
    综述子图提取器
    
    从大图谱中提取指定topic的小图谱，用于综述写作
    """
    
    def __init__(
        self,
        db_path: str = "data/graph_db/mekg_v2.db",
        template_path: str = "data/templates"
    ):
        """
        初始化提取器
        
        Args:
            db_path: 数据库路径
            template_path: 模板库路径
        """
        self.db_path = db_path
        self.template_path = template_path
        
        # 初始化组件
        self.db = PersistentGraphDB(db_path)
        self.template_library = SurveyTemplateLibrary(template_path)
        
        # 初始化默认模板（如果模板库为空）
        if self.template_library.get_template_count() == 0:
            initialize_default_templates(self.template_library)
        
        logger.info(f"综述子图提取器初始化完成")
        logger.info(f"  数据库: {db_path}")
        logger.info(f"  模板库: {template_path}")
        logger.info(f"  数据库统计: {self.db.get_statistics()}")
    
    async def extract_for_survey(
        self,
        topic: str,
        keywords: List[str] = None,
        search_network: bool = False,
        max_papers: int = 200,
        expand_hops: int = 2,
        output_dir: str = None
    ) -> Dict[str, Any]:
        """
        为综述写作提取子图
        
        Args:
            topic: 主题名称
            keywords: 关键词列表
            search_network: 是否搜索网络补充
            max_papers: 最大论文数
            expand_hops: 扩展跳数
            output_dir: 输出目录
        
        Returns:
            提取结果
        """
        start_time = datetime.now()
        
        result = {
            "topic": topic,
            "keywords": keywords or [topic],
            "extraction_time": start_time.isoformat(),
            "subgraph": None,
            "templates": [],
            "statistics": {},
            "papers": [],
            "relations": [],
            "outline_suggestion": None
        }
        
        logger.info("=" * 60)
        logger.info(f"提取综述子图: {topic}")
        logger.info("=" * 60)
        
        # 1. 提取子图
        logger.info("\n[步骤1] 提取子图...")
        
        if search_network:
            # 使用双重搜索
            subgraph = await self._dual_search_extract(
                topic=topic,
                keywords=keywords or [topic],
                max_papers=max_papers,
                expand_hops=expand_hops
            )
        else:
            # 仅从图数据库提取
            subgraph = self._extract_from_db(
                topic=topic,
                keywords=keywords or [topic],
                max_papers=max_papers,
                expand_hops=expand_hops
            )
        
        if not subgraph or not subgraph.nodes:
            logger.warning("未找到相关论文，尝试网络搜索...")
            subgraph = await self._dual_search_extract(
                topic=topic,
                keywords=keywords or [topic],
                max_papers=max_papers,
                expand_hops=expand_hops
            )
        
        result["subgraph"] = subgraph.to_dict() if subgraph else None
        
        if subgraph:
            logger.info(f"  子图: {len(subgraph.nodes)} 节点, {len(subgraph.edges)} 边")
        
        # 2. 获取论文详情
        logger.info("\n[步骤2] 获取论文详情...")
        papers = self._get_papers_details(subgraph)
        result["papers"] = papers
        logger.info(f"  获取 {len(papers)} 篇论文详情")
        
        # 3. 分析关系
        logger.info("\n[步骤3] 分析论文关系...")
        relations = self._analyze_relations(subgraph)
        result["relations"] = relations
        logger.info(f"  分析 {len(relations)} 个关系")
        
        # 4. 匹配模板
        logger.info("\n[步骤4] 匹配Survey模板...")
        templates = self._match_templates(topic, keywords)
        result["templates"] = templates
        logger.info(f"  匹配 {len(templates)} 个模板")
        
        # 5. 生成大纲建议
        logger.info("\n[步骤5] 生成大纲建议...")
        outline = self._generate_outline_suggestion(topic, papers, templates)
        result["outline_suggestion"] = outline
        
        # 6. 统计信息
        result["statistics"] = self._compute_statistics(papers, relations)
        
        # 7. 保存结果
        if output_dir:
            self._save_results(result, output_dir)
        
        end_time = datetime.now()
        result["elapsed_time"] = str(end_time - start_time)
        
        logger.info("\n" + "=" * 60)
        logger.info("子图提取完成!")
        logger.info(f"  论文数: {len(papers)}")
        logger.info(f"  关系数: {len(relations)}")
        logger.info(f"  匹配模板数: {len(templates)}")
        logger.info(f"  耗时: {result['elapsed_time']}")
        logger.info("=" * 60)
        
        return result
    
    def _extract_from_db(
        self,
        topic: str,
        keywords: List[str],
        max_papers: int,
        expand_hops: int
    ) -> Optional[SubGraph]:
        """从数据库提取子图"""
        # 先尝试按Topic提取
        topic_papers = self.db.get_topic_papers(topic)
        
        if topic_papers:
            logger.info(f"  Topic '{topic}' 已有 {len(topic_papers)} 篇论文")
            return self.db.extract_subgraph_by_topic(
                topic=topic,
                expand_hops=expand_hops,
                max_nodes=max_papers
            )
        
        # 否则按关键词提取
        logger.info(f"  使用关键词搜索: {keywords}")
        return self.db.extract_subgraph_by_keywords(
            keywords=keywords,
            expand_hops=expand_hops,
            max_nodes=max_papers
        )
    
    async def _dual_search_extract(
        self,
        topic: str,
        keywords: List[str],
        max_papers: int,
        expand_hops: int
    ) -> Optional[SubGraph]:
        """使用双重搜索提取子图"""
        from src.modules.mekg.graph_merger import GraphMerger
        
        # 创建论文收集器
        collector = PaperPoolCollector()
        merger = GraphMerger(self.db)
        
        # 1. 先从图数据库搜索
        db_subgraph = self._extract_from_db(topic, keywords, max_papers, expand_hops)
        db_paper_ids = set(db_subgraph.nodes) if db_subgraph else set()
        
        logger.info(f"  图数据库找到: {len(db_paper_ids)} 篇论文")
        
        # 2. 从网络搜索补充
        remaining = max_papers - len(db_paper_ids)
        if remaining > 0:
            logger.info(f"  从网络搜索补充 {remaining} 篇论文...")
            
            try:
                # 使用PaperPoolCollector直接搜索
                network_papers = await collector.search_papers_by_keywords(
                    keywords=keywords,
                    target_count=remaining,
                    year_start=2020,
                    year_end=2024
                )
                
                logger.info(f"  网络搜索到: {len(network_papers)} 篇论文")
                
                if network_papers:
                    # 转换格式
                    for paper in network_papers:
                        paper['references'] = paper.get('referenced_works', [])
                    
                    # 确保Topic存在
                    self.db.add_topic(topic, keywords)
                    
                    # 融合到数据库
                    merge_result = merger.merge_papers(network_papers, topic=topic)
                    logger.info(f"  融合: 新增 {merge_result.added_papers} 篇, 引用 {merge_result.added_citations} 条")
                    
                    # 重新提取子图
                    return self.db.extract_subgraph_by_topic(
                        topic=topic,
                        expand_hops=expand_hops,
                        max_nodes=max_papers
                    )
            
            except Exception as e:
                logger.error(f"  网络搜索失败: {e}")
                import traceback
                traceback.print_exc()
        
        return db_subgraph
    
    def _get_papers_details(self, subgraph: Optional[SubGraph]) -> List[Dict[str, Any]]:
        """获取论文详情"""
        if not subgraph:
            return []
        
        papers = []
        for paper_id in subgraph.nodes:
            paper = self.db.get_paper(paper_id)
            if paper:
                # 添加图结构信息
                paper["in_degree"] = sum(1 for e in subgraph.edges if e[1] == paper_id)
                paper["out_degree"] = sum(1 for e in subgraph.edges if e[0] == paper_id)
                papers.append(paper)
        
        # 按PageRank排序
        papers.sort(key=lambda p: p.get("pagerank", 0), reverse=True)
        
        return papers
    
    def _analyze_relations(self, subgraph: Optional[SubGraph]) -> List[Dict[str, Any]]:
        """分析关系"""
        if not subgraph:
            return []
        
        relations = []
        
        # 统计关系类型
        relation_types = {}
        for source, target, rel_type, confidence in subgraph.edges:
            if rel_type not in relation_types:
                relation_types[rel_type] = []
            
            # 获取论文标题
            source_paper = self.db.get_paper(source)
            target_paper = self.db.get_paper(target)
            
            relation = {
                "source_id": source,
                "source_title": source_paper.get("title", "") if source_paper else "",
                "target_id": target,
                "target_title": target_paper.get("title", "") if target_paper else "",
                "relation_type": rel_type,
                "confidence": confidence
            }
            
            relations.append(relation)
            relation_types[rel_type].append(relation)
        
        return relations
    
    def _match_templates(
        self,
        topic: str,
        keywords: List[str] = None
    ) -> List[Dict[str, Any]]:
        """匹配Survey模板"""
        query = topic
        if keywords:
            query = f"{topic} {' '.join(keywords)}"
        
        matches = self.template_library.search_templates(query, top_k=3)
        
        templates = []
        for template, score in matches:
            templates.append({
                "template_id": template.template_id,
                "source_paper_title": template.source_paper_title,
                "topic": template.topic,
                "template_type": template.template_type.value,
                "similarity_score": score,
                "sections": [s.to_dict() for s in template.sections]
            })
        
        return templates
    
    def _generate_outline_suggestion(
        self,
        topic: str,
        papers: List[Dict[str, Any]],
        templates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """生成大纲建议"""
        outline = {
            "topic": topic,
            "suggested_structure": [],
            "key_papers": [],
            "methodology_groups": {},
            "timeline": {}
        }
        
        # 基于模板生成结构建议
        if templates:
            best_template = templates[0]
            outline["suggested_structure"] = best_template.get("sections", [])
            outline["template_source"] = best_template.get("source_paper_title", "")
        else:
            # 默认结构
            outline["suggested_structure"] = [
                {"level": 1, "title": "Introduction", "description": "Background and motivation"},
                {"level": 1, "title": "Background", "description": "Preliminaries and definitions"},
                {"level": 1, "title": "Methods", "description": "Main approaches and techniques"},
                {"level": 1, "title": "Applications", "description": "Real-world applications"},
                {"level": 1, "title": "Challenges and Future Directions", "description": "Open problems"},
                {"level": 1, "title": "Conclusion", "description": "Summary"}
            ]
        
        # 识别关键论文（高PageRank）
        key_papers = papers[:10] if papers else []
        outline["key_papers"] = [
            {
                "paper_id": p.get("paper_id"),
                "title": p.get("title"),
                "year": p.get("year"),
                "citations": p.get("citation_count", 0),
                "pagerank": p.get("pagerank", 0)
            }
            for p in key_papers
        ]
        
        # 按方法分组
        method_groups = {}
        for paper in papers:
            methods = paper.get("method_entities", [])
            for method in methods[:3]:  # 取前3个方法
                if method not in method_groups:
                    method_groups[method] = []
                method_groups[method].append(paper.get("paper_id"))
        
        # 只保留有多篇论文的方法
        outline["methodology_groups"] = {
            k: v for k, v in method_groups.items() if len(v) >= 2
        }
        
        # 按年份分组
        year_groups = {}
        for paper in papers:
            year = paper.get("year", 0)
            if year > 0:
                if year not in year_groups:
                    year_groups[year] = 0
                year_groups[year] += 1
        
        outline["timeline"] = dict(sorted(year_groups.items()))
        
        return outline
    
    def _compute_statistics(
        self,
        papers: List[Dict[str, Any]],
        relations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """计算统计信息"""
        if not papers:
            return {}
        
        # 基本统计
        years = [p.get("year", 0) for p in papers if p.get("year", 0) > 0]
        citations = [p.get("citation_count", 0) for p in papers]
        
        stats = {
            "paper_count": len(papers),
            "relation_count": len(relations),
            "year_range": (min(years), max(years)) if years else (0, 0),
            "avg_citations": sum(citations) / len(citations) if citations else 0,
            "max_citations": max(citations) if citations else 0,
            "total_citations": sum(citations)
        }
        
        # 关系类型分布
        relation_types = {}
        for rel in relations:
            rel_type = rel.get("relation_type", "unknown")
            relation_types[rel_type] = relation_types.get(rel_type, 0) + 1
        stats["relation_type_distribution"] = relation_types
        
        # 年份分布
        year_dist = {}
        for year in years:
            year_dist[year] = year_dist.get(year, 0) + 1
        stats["year_distribution"] = dict(sorted(year_dist.items()))
        
        # 社区分布
        communities = {}
        for paper in papers:
            comm_id = paper.get("community_id")
            if comm_id is not None:
                communities[comm_id] = communities.get(comm_id, 0) + 1
        stats["community_distribution"] = communities
        
        return stats
    
    def _save_results(self, result: Dict[str, Any], output_dir: str):
        """保存结果"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 1. 保存完整JSON
        json_path = output_path / "survey_data.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"  保存JSON: {json_path}")
        
        # 2. 保存论文列表
        papers_path = output_path / "papers.json"
        with open(papers_path, "w", encoding="utf-8") as f:
            json.dump(result.get("papers", []), f, ensure_ascii=False, indent=2)
        logger.info(f"  保存论文列表: {papers_path}")
        
        # 3. 生成Markdown报告
        md_path = output_path / "survey_report.md"
        self._generate_markdown_report(result, md_path)
        logger.info(f"  保存Markdown报告: {md_path}")
        
        # 4. 保存大纲建议
        outline_path = output_path / "outline_suggestion.json"
        with open(outline_path, "w", encoding="utf-8") as f:
            json.dump(result.get("outline_suggestion", {}), f, ensure_ascii=False, indent=2)
        logger.info(f"  保存大纲建议: {outline_path}")
    
    def _generate_markdown_report(self, result: Dict[str, Any], output_path: Path):
        """生成Markdown报告"""
        topic = result.get("topic", "Unknown")
        papers = result.get("papers", [])
        relations = result.get("relations", [])
        stats = result.get("statistics", {})
        outline = result.get("outline_suggestion", {})
        templates = result.get("templates", [])
        
        lines = [
            f"# Survey子图报告: {topic}",
            f"\n生成时间: {result.get('extraction_time', '')}",
            f"\n## 统计概览",
            f"\n| 指标 | 值 |",
            f"|------|-----|",
            f"| 论文数 | {stats.get('paper_count', 0)} |",
            f"| 关系数 | {stats.get('relation_count', 0)} |",
            f"| 年份范围 | {stats.get('year_range', (0, 0))} |",
            f"| 平均引用 | {stats.get('avg_citations', 0):.1f} |",
            f"| 最高引用 | {stats.get('max_citations', 0)} |",
        ]
        
        # 大纲建议
        lines.append("\n## 建议大纲结构")
        if outline.get("template_source"):
            lines.append(f"\n*参考模板: {outline['template_source']}*\n")
        
        for section in outline.get("suggested_structure", []):
            level = section.get("level", 1)
            title = section.get("title", "")
            desc = section.get("description", "")
            prefix = "#" * (level + 1)
            lines.append(f"{prefix} {title}")
            if desc:
                lines.append(f"\n*{desc}*\n")
        
        # 关键论文
        lines.append("\n## 关键论文 (Top 10)")
        lines.append("\n| 排名 | 标题 | 年份 | 引用数 |")
        lines.append("|------|------|------|--------|")
        
        for i, paper in enumerate(outline.get("key_papers", [])[:10], 1):
            title = paper.get("title", "")[:50] + "..." if len(paper.get("title", "")) > 50 else paper.get("title", "")
            lines.append(f"| {i} | {title} | {paper.get('year', '')} | {paper.get('citations', 0)} |")
        
        # 方法分组
        if outline.get("methodology_groups"):
            lines.append("\n## 方法论分组")
            for method, paper_ids in list(outline["methodology_groups"].items())[:10]:
                lines.append(f"\n### {method}")
                lines.append(f"相关论文数: {len(paper_ids)}")
        
        # 时间线
        if outline.get("timeline"):
            lines.append("\n## 年份分布")
            lines.append("\n| 年份 | 论文数 |")
            lines.append("|------|--------|")
            for year, count in outline["timeline"].items():
                lines.append(f"| {year} | {count} |")
        
        # 关系分布
        if stats.get("relation_type_distribution"):
            lines.append("\n## 关系类型分布")
            lines.append("\n| 关系类型 | 数量 |")
            lines.append("|----------|------|")
            for rel_type, count in stats["relation_type_distribution"].items():
                lines.append(f"| {rel_type} | {count} |")
        
        # 匹配的模板
        if templates:
            lines.append("\n## 匹配的Survey模板")
            for tpl in templates:
                lines.append(f"\n### {tpl.get('topic', '')}")
                lines.append(f"- 来源: {tpl.get('source_paper_title', '')}")
                lines.append(f"- 类型: {tpl.get('template_type', '')}")
                lines.append(f"- 相似度: {tpl.get('similarity_score', 0):.2f}")
        
        # 写入文件
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="提取MEKG V2综述子图")
    
    parser.add_argument(
        "--topic",
        type=str,
        required=True,
        help="要提取的topic名称"
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        help="额外的关键词"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/graph_db/mekg_v2.db",
        help="数据库路径"
    )
    parser.add_argument(
        "--template-path",
        type=str,
        default="data/templates",
        help="模板库路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出目录"
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=200,
        help="最大论文数"
    )
    parser.add_argument(
        "--expand-hops",
        type=int,
        default=2,
        help="扩展跳数"
    )
    parser.add_argument(
        "--search-network",
        action="store_true",
        help="搜索网络补充论文"
    )
    
    args = parser.parse_args()
    
    # 设置默认输出目录
    if not args.output:
        safe_topic = args.topic.replace(" ", "_").replace("/", "_")[:30]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"outputs/survey_{safe_topic}_{timestamp}"
    
    # 创建提取器
    extractor = SurveySubgraphExtractor(
        db_path=args.db_path,
        template_path=args.template_path
    )
    
    # 执行提取
    result = await extractor.extract_for_survey(
        topic=args.topic,
        keywords=args.keywords,
        search_network=args.search_network,
        max_papers=args.max_papers,
        expand_hops=args.expand_hops,
        output_dir=args.output
    )
    
    logger.info(f"\n结果已保存到: {args.output}")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())