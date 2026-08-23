"""
自动化服务集成测试脚本

模拟客户端调用 FastAPI 接口，验证：
1. Topic 构建功能
2. 自动化维护功能
3. 可视化结果生成
"""

import requests
import time
import sys
import os
import subprocess
import signal
from loguru import logger

BASE_URL = "http://127.0.0.1:8000"

def start_service():
    """自动启动服务"""
    logger.info("正在启动 MEKG Automation Service...")
    # 尝试启动在 8000 端口，如果失败 app.py 会自动切换到 8001
    # 但 uvicorn 命令行参数是固定的，所以这里我们先尝试 8000
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.app:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=os.getcwd(),
        # stdout=subprocess.PIPE,
        # stderr=subprocess.PIPE
    )
    time.sleep(5)
    return process

def test_health_check():
    """测试服务健康状态，自动检测端口"""
    global BASE_URL
    ports = [8000, 8001]
    
    for port in ports:
        url = f"http://127.0.0.1:{port}"
        try:
            resp = requests.get(f"{url}/")
            if resp.status_code == 200:
                logger.info(f"✅ 服务健康检查通过 (端口 {port})")
                BASE_URL = url
                return True
        except requests.exceptions.ConnectionError:
            continue
            
    logger.error("❌ 无法连接到服务 (尝试了端口 8000, 8001)")
    return False

def test_topic_build(topic="LLM Agents"):
    """测试 Topic 构建"""
    logger.info(f"开始测试 Topic 构建: {topic}")
    logger.info("⚠️ 注意: 此步骤涉及实时爬取论文，可能需要 1-3 分钟，请耐心等待...")
    
    payload = {
        "topic": topic,
        "limit": 20,  # 增加节点数以展示更丰富的图谱
        "year_start": 2023
    }
    
    try:
        start_time = time.time()
        # 设置较长的超时时间 (5分钟)
        resp = requests.post(f"{BASE_URL}/topic/build", json=payload, timeout=300)
        elapsed = time.time() - start_time
        
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"✅ Topic 构建成功 (耗时 {elapsed:.2f}s)")
            logger.info(f"   - 节点数: {data['stats']['nodes']}")
            logger.info(f"   - 边数: {data['stats']['edges']}")
            logger.info(f"   - 可视化链接: {BASE_URL}{data['visualization_url']}")
            return True
        else:
            logger.error(f"❌ Topic 构建失败: {resp.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 请求异常: {e}")
        return False

def test_maintenance():
    """测试自动化维护触发"""
    logger.info("开始测试自动化维护触发...")
    
    payload = {"auto_fill": False}  # 测试时不实际爬取，只触发流程
    
    try:
        resp = requests.post(f"{BASE_URL}/maintenance/run", json=payload)
        
        if resp.status_code == 200:
            logger.info("✅ 维护任务已成功提交到后台")
            return True
        else:
            logger.error(f"❌ 维护任务提交失败: {resp.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 请求异常: {e}")
        return False

if __name__ == "__main__":
    logger.info("=== 开始集成测试 ===")
    
    service_process = None
    
    # 1. 检查服务是否已运行
    if not test_health_check():
        logger.info("服务未运行，尝试自动启动...")
        service_process = start_service()
        
        # 再次检查
        if not test_health_check():
            logger.error("❌ 无法启动服务，测试终止")
            # 打印错误日志
            if service_process:
                service_process.kill()
            sys.exit(1)
    
    try:
        # 2. 测试 Topic 构建
        test_topic_build()
        
        # 3. 测试维护任务
        test_maintenance()
        
    finally:
        # 4. 清理
        if service_process:
            logger.info("正在关闭服务...")
            service_process.kill()
            
    logger.info("=== 测试完成 ===")