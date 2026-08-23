import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.modules.mekg.entity_disambiguator import EntityDisambiguator

async def test():
    print("🧪 测试实体消歧器...")
    
    disambiguator = EntityDisambiguator()
    
    entities = [
        "Large Language Model",
        "LLM",
        "Large Language Models",
        "Graph Neural Network",
        "GNN",
        "Graph Neural Networks",
        "Transformer",
        "Transformers"
    ]
    
    print(f"输入实体: {entities}")
    print("正在消歧 (调用 EmbedAgent)...")
    
    try:
        mapping = await disambiguator.disambiguate(entities)
        
        print("\n📊 映射结果:")
        for original, canonical in mapping.items():
            print(f"'{original}' -> '{canonical}'")
            
        # 验证合并效果
        unique_canonical = set(mapping.values())
        print(f"\n消歧前: {len(entities)} -> 消歧后: {len(unique_canonical)}")
        
        if len(unique_canonical) < len(entities):
            print("✅ 测试通过！成功合并了相似实体。")
        else:
            print("⚠️ 警告: 未能合并实体，可能是 EmbedAgent 未能正确返回相似向量。")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(test())