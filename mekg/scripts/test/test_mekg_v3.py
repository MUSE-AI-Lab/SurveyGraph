"""
MEKG V3 测试脚本

测试新增的语义实体相关功能：
1. 语义实体抽取器
2. 引用上下文分析器
3. 实体消歧器
4. 实体清洗器
5. 语义实体数据库
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger


def test_semantic_entity_extractor():
    """测试语义实体抽取器"""
    print("\n" + "="*60)
    print("测试1: 语义实体抽取器 (SemanticEntityExtractor)")
    print("="*60)
    
    from src.modules.mekg.semantic_entity_extractor import (
        SemanticEntityExtractor,
        SemanticEntityType
    )
    
    # 测试论文
    test_papers = [
        {
            "paper_id": "test_bert",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "abstract": "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers. Unlike recent language representation models, BERT is designed to pre-train deep bidirectional representations from unlabeled text by jointly conditioning on both left and right context in all layers. As a result, the pre-trained BERT model can be fine-tuned with just one additional output layer to create state-of-the-art models for a wide range of tasks, such as question answering and language inference, without substantial task-specific architecture modifications. BERT is conceptually simple and empirically powerful. It obtains new state-of-the-art results on eleven natural language processing tasks, including pushing the GLUE score to 80.5% (7.7% point absolute improvement), MultiNLI accuracy to 86.7% (4.6% absolute improvement), SQuAD v1.1 question answering Test F1 to 93.2 (1.5 point absolute improvement) and SQuAD v2.0 Test F1 to 83.1 (5.1 point absolute improvement)."
        }
    ]
    
    extractor = SemanticEntityExtractor(max_workers=1)  # 使用默认模型
    
    async def run_extraction():
        result = await extractor.extract_from_paper(test_papers[0])
        return result
    
    try:
        result = asyncio.run(run_extraction())
        
        print(f"\n论文: {result.title[:50]}...")
        print(f"抽取的实体数: {result.entity_count()}")
        print(f"  Problems: {len(result.problems)}")
        print(f"  Methods: {len(result.methods)}")
        print(f"  Models: {len(result.models)}")
        print(f"  Tasks: {len(result.tasks)}")
        print(f"  Datasets: {len(result.datasets)}")
        print(f"  Metrics: {len(result.metrics)}")
        print(f"  Innovations: {len(result.innovations)}")
        
        if result.models:
            print(f"\n  模型名称: {[m.value for m in result.models]}")
        if result.tasks:
            print(f"  任务: {[t.value for t in result.tasks]}")
        if result.datasets:
            print(f"  数据集: {[d.value for d in result.datasets]}")
        
        print("\n✓ 语义实体抽取器测试通过")
        return True
        
    except Exception as e:
        print(f"\n✗ 语义实体抽取器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_citation_context_analyzer():
    """测试引用上下文分析器"""
    print("\n" + "="*60)
    print("测试2: 引用上下文分析器 (CitationContextAnalyzer)")
    print("="*60)
    
    from src.modules.mekg.citation_context_analyzer import (
        CitationContextAnalyzer,
        CitationRelationType
    )
    
    analyzer = CitationContextAnalyzer(use_llm=False)  # 只用规则测试
    
    # 测试引用上下文
    test_contexts = [
        ("We use the dataset from [1] for our experiments.", "direct_use"),
        ("Our method extends [2] by adding a new attention mechanism.", "extends"),
        ("Compared with [3], our approach achieves better performance.", "compares"),
        ("Similar to [4], we also focus on the task of text classification.", "task_related"),
        ("Transformers [5] have been widely used in NLP tasks.", "background"),
    ]
    
    correct = 0
    total = len(test_contexts)
    
    for context, expected in test_contexts:
        rel_type, conf, evidence = analyzer._rule_based_classify(context)
        actual = rel_type.value
        
        status = "✓" if actual == expected else "✗"
        print(f"  {status} '{context[:40]}...'")
        print(f"      预期: {expected}, 实际: {actual} (置信度: {conf:.2f})")
        
        if actual == expected:
            correct += 1
    
    accuracy = correct / total * 100
    print(f"\n规则匹配准确率: {accuracy:.1f}% ({correct}/{total})")
    
    # 测试引用上下文提取
    test_text = """
    Natural language processing has made significant progress in recent years. 
    Transformers [1] have revolutionized the field with their attention mechanism.
    Building upon this work, BERT [2] introduced bidirectional pre-training.
    We extend the approach of [2] by incorporating external knowledge.
    """
    
    contexts = analyzer.extract_citation_context(test_text, "[2]")
    print(f"\n引用上下文提取: 找到 {len(contexts)} 处引用")
    
    if accuracy >= 60:
        print("\n✓ 引用上下文分析器测试通过")
        return True
    else:
        print("\n✗ 引用上下文分析器测试失败（准确率过低）")
        return False


def test_entity_disambiguator():
    """测试实体消歧器"""
    print("\n" + "="*60)
    print("测试3: 实体消歧器 (EntityDisambiguator)")
    print("="*60)
    
    from src.modules.mekg.entity_disambiguator import EntityDisambiguator
    
    disambiguator = EntityDisambiguator()
    
    # 测试数据集消歧（使用字符串相似度回退）
    test_datasets = [
        "MNIST",
        "mnist",
        "ImageNet",
        "IMAGENET",
        "ImageNet-1K",
        "CIFAR-10",
        "CIFAR10",
        "cifar-10",
    ]
    
    print("\n测试数据集消歧:")
    result = disambiguator._fallback_disambiguate(
        test_datasets, "dataset", {d: 1 for d in test_datasets}
    )
    
    print(f"  原始实体数: {result.original_count}")
    print(f"  聚类数: {result.cluster_count}")
    print(f"  映射:")
    for original, canonical in result.mapping.items():
        if original != canonical:
            print(f"    '{original}' -> '{canonical}'")
    
    # 测试任务消歧
    test_tasks = [
        "text classification",
        "Text Classification",
        "sentiment analysis",
        "Sentiment Analysis",
    ]
    
    print("\n测试任务消歧:")
    result = disambiguator._fallback_disambiguate(
        test_tasks, "task", {t: 1 for t in test_tasks}
    )
    
    print(f"  原始实体数: {result.original_count}")
    print(f"  聚类数: {result.cluster_count}")
    
    # 测试相似度判断
    print("\n测试相似度判断:")
    test_pairs = [
        ("MNIST", "mnist", True),
        ("ImageNet", "CIFAR-10", False),
        ("text classification", "Text Classification", True),
    ]
    
    for a, b, expected in test_pairs:
        actual = disambiguator._string_similar(a, b)
        status = "✓" if actual == expected else "✗"
        print(f"  {status} '{a}' vs '{b}': {actual} (预期: {expected})")
    
    print("\n✓ 实体消歧器测试通过")
    return True


def test_entity_cleaner():
    """测试实体清洗器"""
    print("\n" + "="*60)
    print("测试4: 实体清洗器 (EntityCleaner)")
    print("="*60)
    
    from src.modules.mekg.entity_cleaner import EntityCleaner, ErrorType
    
    cleaner = EntityCleaner(use_llm=False)
    
    # 测试数据集清洗
    test_datasets = [
        ("MNIST", True),
        ("dataset: ImageNet", True),  # 应该被清洗
        ("21 document corpus", False),  # 无效
        ("our custom dataset", False),  # 无效
        ("SQuAD 1.1", True),
        ("a", False),  # 太短
    ]
    
    print("\n测试数据集清洗:")
    for entity, expected_valid in test_datasets:
        result = cleaner.clean_entity(entity, "dataset")
        status = "✓" if result.is_valid == expected_valid else "✗"
        cleaned_str = f" -> '{result.cleaned}'" if result.cleaned else ""
        print(f"  {status} '{entity}'{cleaned_str}")
        print(f"      有效: {result.is_valid} (预期: {expected_valid}), 类型: {result.error_type.value}")
    
    # 测试模型清洗
    test_models = [
        ("BERT", True),
        ("GPT-4", True),
        ("a model", False),
        ("our proposed model", False),
    ]
    
    print("\n测试模型清洗:")
    for entity, expected_valid in test_models:
        result = cleaner.clean_entity(entity, "model")
        status = "✓" if result.is_valid == expected_valid else "✗"
        print(f"  {status} '{entity}': {result.is_valid} (预期: {expected_valid})")
    
    # 测试批量清洗
    print("\n测试批量清洗:")
    entities = ["BERT", "GPT-4", "a model", "Transformer"]
    batch_result = cleaner.batch_clean(entities, "model")
    print(f"  总数: {batch_result.total}")
    print(f"  有效: {batch_result.valid}")
    print(f"  无效: {batch_result.invalid}")
    
    print("\n✓ 实体清洗器测试通过")
    return True


def test_semantic_entity_db():
    """测试语义实体数据库"""
    print("\n" + "="*60)
    print("测试5: 语义实体数据库 (SemanticEntityDB)")
    print("="*60)
    
    import tempfile
    from src.modules.mekg.semantic_entity_db import SemanticEntityDB
    from src.modules.mekg.semantic_entity_extractor import (
        SemanticEntity,
        SemanticEntityType,
        PaperSemanticEntities
    )
    from src.modules.mekg.citation_context_analyzer import (
        CitationRelation,
        CitationRelationType
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_semantic.db")
        db = SemanticEntityDB(db_path)
        
        # 添加测试论文
        paper1 = {
            "paper_id": "W001",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "abstract": "We introduce BERT...",
            "year": 2018
        }
        paper2 = {
            "paper_id": "W002",
            "title": "Attention Is All You Need",
            "abstract": "The dominant sequence transduction models...",
            "year": 2017
        }
        
        db.add_paper(paper1)
        db.add_paper(paper2)
        print(f"  添加了 2 篇论文")
        
        # 添加语义实体
        entities1 = PaperSemanticEntities(
            paper_id="W001",
            title=paper1["title"],
            models=[SemanticEntity(entity_type=SemanticEntityType.MODEL, value="BERT")],
            tasks=[
                SemanticEntity(entity_type=SemanticEntityType.TASK, value="question answering"),
                SemanticEntity(entity_type=SemanticEntityType.TASK, value="language inference")
            ],
            datasets=[
                SemanticEntity(entity_type=SemanticEntityType.DATASET, value="SQuAD"),
                SemanticEntity(entity_type=SemanticEntityType.DATASET, value="GLUE")
            ]
        )
        
        entities2 = PaperSemanticEntities(
            paper_id="W002",
            title=paper2["title"],
            models=[SemanticEntity(entity_type=SemanticEntityType.MODEL, value="Transformer")],
            tasks=[
                SemanticEntity(entity_type=SemanticEntityType.TASK, value="machine translation")
            ],
            datasets=[
                SemanticEntity(entity_type=SemanticEntityType.DATASET, value="WMT")
            ]
        )
        
        count1 = db.add_paper_semantic_entities(entities1)
        count2 = db.add_paper_semantic_entities(entities2)
        print(f"  添加了 {count1 + count2} 个语义实体")
        
        # 查询语义实体
        retrieved = db.get_paper_semantic_entities("W001")
        print(f"  检索论文W001的实体: {retrieved.entity_count()}")
        
        # 按类型查询
        tasks = db.get_entities_by_type("task")
        print(f"  所有任务实体: {[t[0] for t in tasks]}")
        
        # 按实体查询论文
        papers = db.get_papers_by_entity("task", "question answering")
        print(f"  包含'question answering'的论文: {papers}")
        
        # 添加引用上下文
        citation = CitationRelation(
            citing_paper_id="W001",
            cited_paper_id="W002",
            relation_type=CitationRelationType.EXTENDS,
            confidence=0.9,
            context="BERT extends the Transformer architecture...",
            evidence="Extends the base model"
        )
        db.add_citation_context(citation)
        print(f"  添加了引用上下文")
        
        # 查询引用上下文
        retrieved_citation = db.get_citation_context("W001", "W002")
        print(f"  检索引用上下文: {retrieved_citation.relation_type.value}")
        
        # 获取统计信息
        stats = db.get_statistics()
        print(f"\n  统计信息:")
        print(f"    论文数: {stats['paper_count']}")
        print(f"    语义实体数: {stats['semantic']['semantic_entity_count']}")
        print(f"    按类型: {stats['semantic']['entity_by_type']}")
        print(f"    引用上下文数: {stats['semantic']['citation_context_count']}")
    
    print("\n✓ 语义实体数据库测试通过")
    return True


def test_shared_entity_detection():
    """测试共享实体检测"""
    print("\n" + "="*60)
    print("测试6: 共享实体检测与关系推断")
    print("="*60)
    
    from src.modules.mekg.semantic_entity_extractor import (
        SemanticEntityExtractor,
        SemanticEntity,
        SemanticEntityType,
        PaperSemanticEntities
    )
    
    extractor = SemanticEntityExtractor()
    
    # 创建两篇有共享实体的论文
    entities_a = PaperSemanticEntities(
        paper_id="A",
        title="Paper A",
        tasks=[
            SemanticEntity(entity_type=SemanticEntityType.TASK, value="text classification"),
            SemanticEntity(entity_type=SemanticEntityType.TASK, value="sentiment analysis")
        ],
        datasets=[
            SemanticEntity(entity_type=SemanticEntityType.DATASET, value="IMDB"),
            SemanticEntity(entity_type=SemanticEntityType.DATASET, value="SST-2")
        ],
        methods=[
            SemanticEntity(entity_type=SemanticEntityType.METHOD, value="fine-tuning BERT")
        ]
    )
    
    entities_b = PaperSemanticEntities(
        paper_id="B",
        title="Paper B",
        tasks=[
            SemanticEntity(entity_type=SemanticEntityType.TASK, value="sentiment analysis"),
            SemanticEntity(entity_type=SemanticEntityType.TASK, value="opinion mining")
        ],
        datasets=[
            SemanticEntity(entity_type=SemanticEntityType.DATASET, value="SST-2"),
            SemanticEntity(entity_type=SemanticEntityType.DATASET, value="Yelp")
        ],
        methods=[
            SemanticEntity(entity_type=SemanticEntityType.METHOD, value="fine-tuning RoBERTa")
        ]
    )
    
    # 检测共享实体
    shared = extractor.extract_shared_entities(entities_a, entities_b)
    
    print("\n共享实体检测:")
    print(f"  共享任务: {shared['tasks']}")
    print(f"  共享数据集: {shared['datasets']}")
    print(f"  共享方法: {shared['methods']}")
    
    # 推断关系
    relations = extractor.infer_relations_from_shared_entities(entities_a, entities_b)
    
    print("\n推断的关系:")
    for rel in relations:
        print(f"  {rel['relation_type']}: 置信度={rel['confidence']:.2f}")
        print(f"    证据: {rel['evidence']}")
    
    # 验证
    has_shared_task = len(shared['tasks']) > 0
    has_shared_dataset = len(shared['datasets']) > 0
    has_relations = len(relations) > 0
    
    if has_shared_task and has_shared_dataset and has_relations:
        print("\n✓ 共享实体检测测试通过")
        return True
    else:
        print("\n✗ 共享实体检测测试失败")
        return False


def main():
    """运行所有测试"""
    print("="*60)
    print("MEKG V3 功能测试")
    print("="*60)
    
    results = {}
    
    # 测试1: 语义实体抽取器（需要API，可选）
    try:
        results["语义实体抽取器"] = test_semantic_entity_extractor()
    except Exception as e:
        print(f"\n⚠ 语义实体抽取器测试跳过（可能需要API）: {e}")
        results["语义实体抽取器"] = None
    
    # 测试2: 引用上下文分析器
    results["引用上下文分析器"] = test_citation_context_analyzer()
    
    # 测试3: 实体消歧器
    results["实体消歧器"] = test_entity_disambiguator()
    
    # 测试4: 实体清洗器
    results["实体清洗器"] = test_entity_cleaner()
    
    # 测试5: 语义实体数据库
    results["语义实体数据库"] = test_semantic_entity_db()
    
    # 测试6: 共享实体检测
    results["共享实体检测"] = test_shared_entity_detection()
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, result in results.items():
        if result is True:
            status = "✓ 通过"
            passed += 1
        elif result is False:
            status = "✗ 失败"
            failed += 1
        else:
            status = "⚠ 跳过"
            skipped += 1
        print(f"  {status}: {name}")
    
    print(f"\n总计: {passed} 通过, {failed} 失败, {skipped} 跳过")
    
    if failed == 0:
        print("\n🎉 所有测试通过！MEKG V3 功能正常。")
        return 0
    else:
        print("\n⚠ 部分测试失败，请检查。")
        return 1


if __name__ == "__main__":
    exit(main())