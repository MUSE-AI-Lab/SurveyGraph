#!/usr/bin/env python
"""
测试改进后的关系发现效果

验证:
1. 新的关系类型是否正确定义
2. LLM Prompt是否能识别多种关系
3. 共享实体策略是否生效
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.modules.mekg.data_structures import RelationType
from src.modules.mekg.attribute_based_relation_extractor import AttributeBasedRelationExtractor


def test_relation_types():
    """测试关系类型枚举"""
    print("=" * 60)
    print("测试1: 关系类型枚举")
    print("=" * 60)
    
    # 检查所有关系类型
    all_types = list(RelationType)
    print(f"\n总共 {len(all_types)} 种关系类型:")
    
    print("\n引用关系:")
    for rt in RelationType.citation_relations():
        print(f"  - {rt.value}")
    
    print("\n方法演进关系:")
    for rt in RelationType.method_relations():
        print(f"  - {rt.value}")
    
    print("\n共享实体关系:")
    for rt in RelationType.shared_entity_relations():
        print(f"  - {rt.value}")
    
    print("\n✓ 关系类型测试通过")
    return True


async def test_relation_extraction():
    """测试关系抽取"""
    print("\n" + "=" * 60)
    print("测试2: 关系抽取（需要LLM API）")
    print("=" * 60)
    
    extractor = AttributeBasedRelationExtractor()
    
    # 测试论文对1: GPT-3 vs GPT-2 (应该发现 evolved_from 关系)
    paper_a = {
        "paper_id": "gpt3",
        "title": "Language Models are Few-Shot Learners",
        "abstract": "We demonstrate that scaling up language models greatly improves task-agnostic, few-shot performance. GPT-3, an autoregressive language model with 175 billion parameters, achieves strong performance on many NLP datasets.",
        "year": 2020,
        "attributes": {
            "paper_type": "Methodology Paper",
            "method_info": {
                "has_method": True,
                "method_name": "GPT-3",
                "method_category": "Large Language Model"
            },
            "innovations": ["175B parameters", "Few-shot learning"],
            "research_domains": ["NLP", "Language Models"]
        },
        "semantic_entities": {
            "task": ["language modeling", "few-shot learning", "question answering"],
            "dataset": ["LAMBADA", "HellaSwag", "SuperGLUE"],
            "method": ["transformer", "autoregressive language model"],
            "model": ["GPT-3"]
        }
    }
    
    paper_b = {
        "paper_id": "gpt2",
        "title": "Language Models are Unsupervised Multitask Learners",
        "abstract": "We demonstrate that language models begin to learn NLP tasks without any explicit supervision when trained on a new dataset of millions of webpages called WebText. GPT-2, a 1.5B parameter Transformer, achieves state of the art results on 7 out of 8 tested language modeling datasets.",
        "year": 2019,
        "attributes": {
            "paper_type": "Methodology Paper",
            "method_info": {
                "has_method": True,
                "method_name": "GPT-2",
                "method_category": "Language Model"
            },
            "innovations": ["Zero-shot learning", "WebText dataset"],
            "research_domains": ["NLP", "Language Models"]
        },
        "semantic_entities": {
            "task": ["language modeling", "zero-shot learning"],
            "dataset": ["WebText", "LAMBADA"],
            "method": ["transformer", "autoregressive language model"],
            "model": ["GPT-2"]
        }
    }
    
    print("\n测试论文对: GPT-3 vs GPT-2")
    print(f"  Paper A: {paper_a['title']}")
    print(f"  Paper B: {paper_b['title']}")
    
    try:
        edges = await extractor.extract_all_relations_between_papers(paper_a, paper_b)
        
        if edges:
            print(f"\n发现 {len(edges)} 条关系:")
            for edge in edges:
                print(f"  - {edge.relation_type.value}: {edge.source} -> {edge.target}")
                print(f"    置信度: {edge.llm_confidence:.2f}")
                print(f"    证据: {edge.evidence[:100]}...")
        else:
            print("\n未发现关系")
        
        print("\n✓ 关系抽取测试完成")
        return True
        
    except Exception as e:
        print(f"\n✗ 关系抽取测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_candidate_generation():
    """测试候选对生成"""
    print("\n" + "=" * 60)
    print("测试3: 候选对生成（共享实体策略）")
    print("=" * 60)
    
    extractor = AttributeBasedRelationExtractor()
    
    # 创建测试论文集
    papers = [
        {
            "paper_id": "p1",
            "title": "BERT for Question Answering",
            "year": 2019,
            "citations": 100,
            "attributes": {"research_domains": ["NLP"]},
            "semantic_entities": {
                "task": ["question answering"],
                "dataset": ["SQuAD", "GLUE"],
                "method": ["BERT", "transformer"]
            }
        },
        {
            "paper_id": "p2",
            "title": "RoBERTa: A Robustly Optimized BERT",
            "year": 2019,
            "citations": 200,
            "attributes": {"research_domains": ["NLP"]},
            "semantic_entities": {
                "task": ["language understanding"],
                "dataset": ["SQuAD", "GLUE", "MNLI"],
                "method": ["BERT", "transformer"]
            }
        },
        {
            "paper_id": "p3",
            "title": "XLNet: Generalized Autoregressive Pretraining",
            "year": 2019,
            "citations": 150,
            "attributes": {"research_domains": ["NLP"]},
            "semantic_entities": {
                "task": ["language understanding", "question answering"],
                "dataset": ["SQuAD", "GLUE"],
                "method": ["transformer", "autoregressive"]
            }
        },
        {
            "paper_id": "p4",
            "title": "Image Classification with CNN",
            "year": 2020,
            "citations": 50,
            "attributes": {"research_domains": ["Computer Vision"]},
            "semantic_entities": {
                "task": ["image classification"],
                "dataset": ["ImageNet", "CIFAR-10"],
                "method": ["CNN", "ResNet"]
            }
        }
    ]
    
    # 测试共享实体配对
    shared_pairs = extractor._find_shared_entity_pairs(papers, max_pairs_per_entity=10)
    
    print(f"\n从 {len(papers)} 篇论文中找到 {len(shared_pairs)} 个共享实体配对:")
    for pair in shared_pairs:
        print(f"  - {pair[0]} <-> {pair[1]}")
    
    # 验证: p1, p2, p3 应该有配对（共享SQuAD, GLUE, transformer等）
    # p4 不应该与其他论文配对（不同领域）
    
    expected_pairs = {("p1", "p2"), ("p1", "p3"), ("p2", "p3")}
    actual_pairs = {tuple(sorted(p)) for p in shared_pairs}
    
    if expected_pairs.issubset(actual_pairs):
        print("\n✓ 共享实体配对测试通过")
        return True
    else:
        print(f"\n✗ 期望配对: {expected_pairs}")
        print(f"  实际配对: {actual_pairs}")
        return False


def test_similar_papers():
    """测试相似论文查找"""
    print("\n" + "=" * 60)
    print("测试4: 相似论文查找（语义实体增强）")
    print("=" * 60)
    
    extractor = AttributeBasedRelationExtractor()
    
    # 目标论文
    target = {
        "paper_id": "target",
        "title": "BERT for QA",
        "year": 2020,
        "citations": 100,
        "attributes": {"research_domains": ["NLP"]},
        "semantic_entities": {
            "task": ["question answering"],
            "dataset": ["SQuAD"],
            "method": ["BERT"]
        }
    }
    
    # 候选论文
    candidates = [
        {
            "paper_id": "c1",
            "title": "RoBERTa for QA",  # 共享task和dataset
            "year": 2020,
            "citations": 80,
            "attributes": {"research_domains": ["NLP"]},
            "semantic_entities": {
                "task": ["question answering"],
                "dataset": ["SQuAD"],
                "method": ["RoBERTa"]
            }
        },
        {
            "paper_id": "c2",
            "title": "Image Classification",  # 不相关
            "year": 2020,
            "citations": 100,
            "attributes": {"research_domains": ["CV"]},
            "semantic_entities": {
                "task": ["image classification"],
                "dataset": ["ImageNet"],
                "method": ["CNN"]
            }
        },
        {
            "paper_id": "c3",
            "title": "BERT for NER",  # 共享method
            "year": 2020,
            "citations": 60,
            "attributes": {"research_domains": ["NLP"]},
            "semantic_entities": {
                "task": ["named entity recognition"],
                "dataset": ["CoNLL"],
                "method": ["BERT"]
            }
        }
    ]
    
    similar = extractor._find_similar_papers(target, candidates, top_k=3)
    
    print(f"\n目标论文: {target['title']}")
    print(f"找到 {len(similar)} 篇相似论文:")
    for p in similar:
        print(f"  - {p['paper_id']}: {p['title']}")
    
    # 验证: c1应该排第一（共享task和dataset），c3第二（共享method），c2最后或不出现
    if similar and similar[0]['paper_id'] == 'c1':
        print("\n✓ 相似论文查找测试通过")
        return True
    else:
        print("\n✗ 相似论文查找测试失败")
        return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("MEKG 关系发现改进测试")
    print("借鉴 NLP-AKG 的设计")
    print("=" * 60)
    
    results = []
    
    # 测试1: 关系类型
    results.append(("关系类型枚举", test_relation_types()))
    
    # 测试2: 候选对生成
    results.append(("候选对生成", test_candidate_generation()))
    
    # 测试3: 相似论文查找
    results.append(("相似论文查找", test_similar_papers()))
    
    # 测试4: 关系抽取（需要LLM API）
    print("\n是否测试LLM关系抽取? (需要API配置) [y/N]: ", end="")
    try:
        answer = input().strip().lower()
        if answer == 'y':
            results.append(("关系抽取", await test_relation_extraction()))
        else:
            print("跳过LLM关系抽取测试")
    except EOFError:
        print("跳过LLM关系抽取测试（非交互模式）")
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 测试通过")
    
    return passed == len(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)