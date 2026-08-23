import uvicorn
import os
import sys
import webbrowser
import threading
import time

def open_browser():
    """等待服务启动后打开浏览器"""
    time.sleep(2)
    webbrowser.open("http://localhost:8770")

if __name__ == "__main__":
    # 确保在项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    os.chdir(project_root)
    sys.path.append(project_root)
    
    print("🚀 启动 MEKG Enterprise Pro...")
    print("🌐 访问地址: http://localhost:8770")
    
    # 自动打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()
    
    # 启动 FastAPI
    # reload=True 在开发模式下很有用
    uvicorn.run("src.app:app", host="0.0.0.0", port=8770, reload=False)
