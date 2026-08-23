"""
MEKG V2 集成测试脚本

测试所有新组件的协同工作：
1. PersistentGraphDB - 持久化图数据库
2. GraphMerger - 图融合器
3. DualSearchOrchestrator - 双重搜索协调器
4. SurveyTemplateLibrary - Survey模板库
5. TemplateExtractor - 模板提取器
6. EnhancedRelationDiscoverer - 增强关系发现器
"""

import asyncio
import tempfile
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger


def test_persistent_graph_db():
    """测试持久化图数据库"""
    print("\n" + "="*60)
    print("测试 1: PersistentGraphDB 持久化图数据库")
    print("="*60)
    
    from src.modules.mekg.persistent_graph_db import PersistentGraphDB
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = PersistentGraphDB(db_path)
        
        # 添加论文
        papers = [
            {
                "paper_id": "W001",
                "title": "Attention Is All You Need",
                "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
                "year": 2017,
                "citation_count": 50000,
                "method_entities": ["transformer", "attention", "self-attention"]
            },
            {
                "paper_id": "W002",
                "title": "BERT: Pre-training of Deep Bidirectional Transformers",
                "abstract": "We introduce a new language representation model called BERT...",
                "year": 2018,
                "citation_count": 40000,
                "method_entities": ["transformer", "attention", "pre-training", "BERT"]
            },
            {
                "paper_id": "W003",
                "title": "GPT-3: Language Models are Few-Shot Learners",
                "abstract": "Recent work has demonstrated substantial gains on many NLP tasks...",
                "year": 2020,
                "citation_count": 30000,
                "method_entities": ["transformer", "GPT", "few-shot", "in-context learning"]
            }
        ]
        
        added = db.add_papers_batch(papers)
        print(f"✓ 添加论文: {added} 篇")
        
        # 添加引用关系
        db.add_citation("W002", "W001")  # BERT cites Transformer
        db.add_citation("W003", "W001")  # GPT-3 cites Transformer
        db.add_citation("W003", "W002")  # GPT-3 cites BERT
        print("✓ 添加引用关系: 3 条")
        
        # 添加语义关系
        db.add_relation("W002", "W001", "evolved_from", 0.9, evidence="BERT builds on Transformer")
        db.add_relation("W003", "W002", "evolved_from", 0.85, evidence="GPT-3 follows BERT paradigm")
        print("✓ 添加语义关系: 2 条")
        
        # 添加Topic
        db.add_topic("transformer", ["attention", "self-attention", "neural network"])
        db.link_paper_to_topic("W001", "transformer", is_core=True)
        db.link_paper_to_topic("W002", "transformer")
        db.link_paper_to_topic("W003", "transformer")
        print("✓ 添加Topic并关联论文")
        
        # 提取子图
        subgraph = db.extract_subgraph_by_topic("transformer")
        print(f"✓ 提取子图: {len(subgraph.nodes)} 节点, {len(subgraph.edges)} 边")
        
        # 统计信息
        stats = db.get_statistics()
        print(f"✓ 数据库统计: {stats}")
        
        print("\n✅ PersistentGraphDB 测试通过!")
        return True


def test_graph_merger():
    """测试图融合器"""
    print("\n" + "="*60)
    print("测试 2: GraphMerger 图融合器")
    print("="*60)
    
    from src.modules.mekg.persistent_graph_db import PersistentGraphDB
    from src.modules.mekg.graph_merger import GraphMerger
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = PersistentGraphDB(db_path)
        merger = GraphMerger(db)
        
        # 融合论文
        papers = [
            {
                "paper_id": "W001",
                "title": "Paper A",
                "year": 2023,
                "references": []
            },
            {
                "paper_id": "W002",
                "title": "Paper B",
                "year": 2024,
                "references": ["W001"]
            }
        ]
        
        result = merger.merge_papers(papers, topic="test_topic")
        print(f"✓ 融合结果: {result}")
        
        # 验证
        assert result.added_papers == 2, "应该添加2篇论文"
        assert result.added_citations == 1, "应该添加1条引用"
        
        print("\n✅ GraphMerger 测试通过!")
        return True


async def test_dual_search_orchestrator():
    """测试双重搜索协调器"""
    print("\n" + "="*60)
    print("测试 3: DualSearchOrchestrator 双重搜索协调器")
    print("="*60)
    
    from src.modules.mekg.persistent_graph_db import PersistentGraphDB
    from src.modules.mekg.dual_search_orchestrator import DualSearchOrchestrator, MockPaperCollector
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = PersistentGraphDB(db_path)
        
        # 预先添加一些数据
        db.add_paper({
            "paper_id": "W001",
            "title": "Existing Paper on Transformers",
            "year": 2023
        })
        db.add_topic("transformer")
        db.link_paper_to_topic("W001", "transformer")
        
        # 创建协调器
        orchestrator = DualSearchOrchestrator(
            db,
            paper_collector=MockPaperCollector()
        )
        
        # 执行双重搜索
        result = await orchestrator.search_and_merge(
            topic="transformer",
            keywords=["attention", "neural network"]
        )
        
        print(f"✓ 搜索结果: {result}")
        print(f"  - 图数据库: {result.from_graph_db} 篇")
        print(f"  - 网络搜索: {result.from_network} 篇")
        print(f"  - 去重后: {result.total_unique} 篇")
        print(f"  - 新增: {result.newly_added} 篇")
        
        assert result.from_graph_db >= 1, "应该从图数据库找到至少1篇"
        assert result.subgraph is not None, "应该返回子图"
        
        print("\n✅ DualSearchOrchestrator 测试通过!")
        return True


def test_survey_template_library():
    """测试Survey模板库"""
    print("\n" + "="*60)
    print("测试 4: SurveyTemplateLibrary Survey模板库")
    print("="*60)
    
    from src.modules.mekg.survey_template_library import (
        SurveyTemplateLibrary,
        SurveyTemplate,
        OutlineSection,
        TemplateType,
        initialize_default_templates
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        library = SurveyTemplateLibrary(tmpdir)
        
        # 初始化默认模板
        initialize_default_templates(library)
        
        count = library.get_template_count()
        print(f"✓ 模板数量: {count}")
        
        # 搜索模板
        results = library.search_templates("LLM tool use agents")
        print(f"✓ 搜索 'LLM tool use agents': {len(results)} 个匹配")
        for template, score in results:
            print(f"  - {template.topic} (score={score:.2f})")
        
        # 获取Few-shot示例
        examples = library.get_fewshot_examples("transformer", top_k=2)
        print(f"✓ Few-shot示例长度: {len(examples)} 字符")
        
        assert count >= 3, "应该有至少3个默认模板"
        assert len(results) > 0, "应该找到匹配的模板"
        
        print("\n✅ SurveyTemplateLibrary 测试通过!")
        return True


async def test_template_extractor():
    """测试模板提取器"""
    print("\n" + "="*60)
    print("测试 5: TemplateExtractor 模板提取器")
    print("="*60)
    
    from src.modules.mekg.template_extractor import TemplateExtractor, MockChatAgent
    
    extractor = TemplateExtractor(chat_agent=MockChatAgent())
    
    # 测试LLM提取
    result = await extractor.extract_from_text(
        title="A Survey on Deep Learning Methods",
        content="This survey covers various deep learning methods including CNNs, RNNs, and Transformers...",
        year=2024
    )
    
    print(f"✓ LLM提取成功: {result.success}")
    if result.template:
        print(f"  - 模板ID: {result.template.template_id}")
        print(f"  - Topic: {result.template.topic}")
        print(f"  - 类型: {result.template.template_type.value}")
        print(f"  - 章节数: {len(result.template.sections)}")
    
    # 测试Markdown解析
    md_content = """
# A Survey on Neural Networks

## Introduction
Background and motivation.

## Methods
### Convolutional Neural Networks
CNN description.

### Recurrent Neural Networks
RNN description.

## Applications
Real-world applications.

## Conclusion
Summary.
"""
    
    template = extractor.extract_outline_from_markdown_sync(md_content)
    print(f"✓ Markdown解析: {len(template.sections) if template else 0} 个顶级章节")
    
    assert result.success, "LLM提取应该成功"
    assert template is not None, "Markdown解析应该成功"
    
    print("\n✅ TemplateExtractor 测试通过!")
    return True


async def test_enhanced_relation_discoverer():
    """测试增强关系发现器"""
    print("\n" + "="*60)
    print("测试 6: EnhancedRelationDiscoverer 增强关系发现器")
    print("="*60)
    
    from src.modules.mekg.enhanced_relation_discoverer import (
        EnhancedRelationDiscoverer,
        MockRelationChatAgent
    )
    
    # 测试规则发现
    discoverer = EnhancedRelationDiscoverer(use_llm=False)
    
    paper_a = {
        "paper_id": "W001",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "year": 2018,
        "references": ["W002"],
        "method_entities": ["transformer", "attention", "pre-training"],
        "research_domains": ["NLP", "language model"]
    }
    
    paper_b = {
        "paper_id": "W002",
        "title": "Attention Is All You Need",
        "year": 2017,
        "references": [],
        "method_entities": ["transformer", "attention", "self-attention"],
        "research_domains": ["NLP", "machine translation"]
    }
    
    relations = await discoverer.discover_relations(paper_a, paper_b)
    print(f"✓ 规则发现关系数: {len(relations)}")
    for rel in relations:
        print(f"  - {rel.source_id} --[{rel.relation_type}]--> {rel.target_id} (conf={rel.confidence:.2f})")
    
    # 测试LLM发现
    discoverer_llm = EnhancedRelationDiscoverer(
        chat_agent=MockRelationChatAgent(),
        use_llm=True,
        use_rules=True
    )
    
    relations_llm = await discoverer_llm.discover_relations(paper_a, paper_b)
    print(f"✓ 规则+LLM发现关系数: {len(relations_llm)}")
    
    assert len(relations) >= 2, "规则应该发现至少2个关系"
    assert len(relations_llm) >= len(relations), "LLM应该发现更多关系"
    
    print("\n✅ EnhancedRelationDiscoverer 测试通过!")
    return True


async def test_full_integration():
    """完整集成测试"""
    print("\n" + "="*60)
    print("测试 7: 完整集成测试")
    print("="*60)
    
    from src.modules.mekg.persistent_graph_db import PersistentGraphDB
    from src.modules.mekg.graph_merger import GraphMerger
    from src.modules.mekg.dual_search_orchestrator import DualSearchOrchestrator, MockPaperCollector
    from src.modules.mekg.survey_template_library import SurveyTemplateLibrary, initialize_default_templates
    from src.modules.mekg.enhanced_relation_discoverer import EnhancedRelationDiscoverer
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 初始化组件
        db_path = os.path.join(tmpdir, "mekg_v2.db")
        template_path = os.path.join(tmpdir, "templates")
        
        db = PersistentGraphDB(db_path)
        merger = GraphMerger(db)
        orchestrator = DualSearchOrchestrator(db, paper_collector=MockPaperCollector())
        template_library = SurveyTemplateLibrary(template_path)
        relation_discoverer = EnhancedRelationDiscoverer(db, use_llm=False)
        
        print("✓ 所有组件初始化完成")
        
        # 2. 初始化模板库
        initialize_default_templates(template_library)
        print(f"✓ 模板库初始化: {template_library.get_template_count()} 个模板")
        
        # 3. 添加初始论文
        initial_papers = [
            {
                "paper_id": "W001",
                "title": "Attention Is All You Need",
                "year": 2017,
                "method_entities": ["transformer", "attention"]
            },
            {
                "paper_id": "W002",
                "title": "BERT",
                "year": 2018,
                "references": ["W001"],
                "method_entities": ["transformer", "BERT"]
            }
        ]
        
        result = merger.merge_papers(initial_papers, topic="transformer")
        print(f"✓ 初始论文融合: {result}")
        
        # 4. 执行双重搜索
        search_result = await orchestrator.search_and_merge(
            topic="transformer",
            keywords=["attention", "neural network"]
        )
        print(f"✓ 双重搜索: {search_result}")
        
        # 5. 发现关系
        paper_a = db.get_paper("W001")
        paper_b = db.get_paper("W002")
        if paper_a and paper_b:
            relations = await relation_discoverer.discover_relations(paper_a, paper_b)
            print(f"✓ 关系发现: {len(relations)} 个关系")
        
        # 6. 匹配模板
        templates = template_library.search_templates("transformer attention", top_k=2)
        print(f"✓ 模板匹配: {len(templates)} 个匹配")
        
        # 7. 最终统计
        stats = db.get_statistics()
        print(f"\n最终数据库统计:")
        print(f"  - 论文数: {stats['paper_count']}")
        print(f"  - 关系数: {stats['relation_count']}")
        print(f"  - 引用数: {stats['citation_count']}")
        print(f"  - Topic数: {stats['topic_count']}")
        
        print("\n✅ 完整集成测试通过!")
        return True


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("MEKG V2 集成测试")
    print("="*60)
    
    all_passed = True
    
    try:
        # 同步测试
        all_passed &= test_persistent_graph_db()
        all_passed &= test_graph_merger()
        all_passed &= test_survey_template_library()
        
        # 异步测试
        all_passed &= await test_dual_search_orchestrator()
        all_passed &= await test_template_extractor()
        all_passed &= await test_enhanced_relation_discoverer()
        all_passed &= await test_full_integration()
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 所有测试通过!")
    else:
        print("❌ 部分测试失败")
    print("="*60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)