"""
MEKG Web 控制台启动脚本

功能：
1. 启动 FastAPI 后端服务
2. 自动打开浏览器访问控制台
3. 优雅处理退出

使用方式：
    python scripts/start_mekg_web.py
"""

import subprocess
import sys
import os
import time
import webbrowser
import threading
import signal

def stream_output(process, prefix):
    """实时打印子进程输出"""
    for line in iter(process.stdout.readline, ''):
        print(f"[{prefix}] {line.strip()}")

def main():
    print("🚀 正在启动 MEKG Web 控制台...")
    print("=" * 50)
    
    # 定位项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    os.chdir(project_root)
    
    print(f"📂 工作目录: {os.getcwd()}")
    
    # 启动 FastAPI 后端
    print("📦 启动后端服务 (FastAPI)...")
    backend_script = os.path.join("src", "main.py")
    
    # 使用 uvicorn 启动
    cmd = [
        sys.executable, backend_script
    ]
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy()
        )
        
        # 启动线程读取输出
        threading.Thread(target=stream_output, args=(process, "Backend"), daemon=True).start()
        
        # 等待服务启动
        print("⏳ 等待服务启动...")
        time.sleep(3)
        
        # 检查进程是否还在运行
        if process.poll() is not None:
            print("❌ 服务启动失败")
            sys.exit(1)
            
        print("✅ 服务已启动")
        print("🌐 访问地址: http://localhost:8000")
        print("⌨️  按 Ctrl+C 停止")
        print("=" * 50)

        # 保持运行
        process.wait()

    except KeyboardInterrupt:
        print("\n👋 正在停止服务...")
        if process.poll() is None:
            process.terminate()
        print("✅ 服务已停止")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        if 'process' in locals() and process.poll() is None:
            process.terminate()

if __name__ == "__main__":
    main()