import subprocess
import sys
import time
import os
import signal
import threading

def stream_output(process, prefix):
    """实时打印子进程输出"""
    for line in iter(process.stdout.readline, ''):
        print(f"[{prefix}] {line.strip()}")

def main():
    print("🚀 正在启动 MEKG 企业级控制中心...")
    
    # 1. 启动后端 (FastAPI)
    print("📦 启动后端服务 (FastAPI)...")
    backend_script = os.path.join("src", "app.py")
    backend_cmd = [sys.executable, backend_script]
    backend_process = subprocess.Popen(
        backend_cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ.copy() # 继承环境变量
    )
    
    # 启动线程读取后端输出
    threading.Thread(target=stream_output, args=(backend_process, "Backend"), daemon=True).start()
    
    # 等待几秒让后端启动
    time.sleep(3)
    
    # 2. 启动前端 (Streamlit)
    print("🖥️ 启动前端控制台 (Streamlit)...")
    frontend_script = os.path.join("scripts", "enterprise_dashboard.py")
    frontend_cmd = [
        sys.executable, "-m", "streamlit", "run", frontend_script,
        "--browser.gatherUsageStats", "false",
        "--server.headless", "true",
        "--server.address", "localhost",
        "--server.port", "8501"
    ]
    frontend_process = subprocess.Popen(
        frontend_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ.copy()
    )
    
    # 启动线程读取前端输出
    threading.Thread(target=stream_output, args=(frontend_process, "Frontend"), daemon=True).start()
    
    print("\n✅ 系统启动成功!")
    print("🌐 控制台访问地址: http://localhost:8501")
    print("🔧 API 文档地址: http://localhost:8000/docs")
    print("⌨️ 按 Ctrl+C 停止所有服务\n")
    
    try:
        # 主线程保持运行，直到收到中断信号
        while True:
            time.sleep(1)
            # 检查子进程是否存活
            if backend_process.poll() is not None:
                print("❌ 后端服务意外退出")
                break
            if frontend_process.poll() is not None:
                print("❌ 前端服务意外退出")
                break
                
    except KeyboardInterrupt:
        print("\n👋 正在停止服务...")
    finally:
        # 终止子进程
        if backend_process.poll() is None:
            backend_process.terminate()
        if frontend_process.poll() is None:
            frontend_process.terminate()
        print("✅ 服务已停止")

if __name__ == "__main__":
    # 自动定位项目根目录
    # 假设脚本位于 [root]/scripts/start_enterprise.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    # 切换工作目录
    os.chdir(project_root)
    
    # 再次检查
    if not os.path.exists("src"):
        print(f"❌ 错误: 无法定位项目根目录 (尝试路径: {project_root})")
        print("请确保脚本位于 'scripts' 目录下，且项目包含 'src' 目录")
        sys.exit(1)
        
    print(f"📂 工作目录: {os.getcwd()}")
    main()