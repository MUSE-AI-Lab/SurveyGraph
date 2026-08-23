import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.modules.mekg.citation_context_analyzer import CitationContextAnalyzer

async def test():
    print("🧪 测试引用上下文分析器 (LLM版)...")
    
    analyzer = CitationContextAnalyzer()
    text = """
    Graph Neural Networks have achieved great success. 
    Kipf et al. [1] proposed GCN for semi-supervised classification.
    However, GCN fails to handle directed graphs.
    To address this, we extend the method of [1] by introducing a new attention mechanism.
    We also compare our model with GAT [2] on three datasets.
    We use the Cora dataset [3] for evaluation.
    """
    
    print("Analyzing text with LLM...")
    results = await analyzer.extract_contexts(text)
    
    print(f"\n📊 分析结果 ({len(results)} 个引用):")
    for res in results:
        print(f"\nMarker: {res.citation_marker}")
        print(f"Type: {res.relation_type} (conf={res.confidence})")
        print(f"Context: ...{res.context[:50]}...")
        
    # 验证关键关系
    types = [r.relation_type for r in results]
    if "extends" in types and "compares" in types and "uses" in types:
        print("\n✅ 测试通过！成功识别了 extends, compares, uses 关系。")
    else:
        print(f"\n⚠️ 警告: 未能识别所有预期关系类型。识别到的类型: {types}")

if __name__ == "__main__":
    asyncio.run(test())