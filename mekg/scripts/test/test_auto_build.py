import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.modules.mekg.pipeline_orchestrator import MEKGPipelineOrchestrator, BuildAction

async def test_auto_build():
    print("🧪 测试自动构建触发逻辑...")
    
    # Mock 数据库和收集器，避免真实操作
    mock_db = MagicMock()
    # 模拟 Topic 不存在
    mock_db.get_topic_status.return_value = {"exists": False, "paper_count": 0}
    # 模拟子图谱提取
    mock_db.execute_cypher.return_value = []
    
    orchestrator = MEKGPipelineOrchestrator(db=mock_db)
    
    # Mock 内部方法以避免真实爬取
    orchestrator._stage_crawl = AsyncMock(return_value=[{"id": "p1", "title": "Test Paper"}])
    orchestrator._stage_store = AsyncMock()
    orchestrator._stage_pdf_process = AsyncMock(return_value=[])
    orchestrator._stage_extract_attributes = AsyncMock(return_value=[])
    orchestrator._stage_discover_relations = AsyncMock(return_value=[])
    orchestrator._stage_community_detection = AsyncMock(return_value={})
    
    topic = "NonExistentTopic"
    print(f"请求 Topic: {topic}")
    
    # 调用 get_or_build_subgraph
    result = await orchestrator.get_or_build_subgraph(topic)
    
    # 验证是否触发了 build_topic
    # 我们通过检查 _stage_crawl 是否被调用来验证
    if orchestrator._stage_crawl.called:
        print("✅ 成功触发自动构建！(_stage_crawl 被调用)")
        print(f"构建动作: {orchestrator._stage_crawl.call_args}")
    else:
        print("❌ 未触发自动构建！")
        
    print("\n测试完成。")

if __name__ == "__main__":
    asyncio.run(test_auto_build())