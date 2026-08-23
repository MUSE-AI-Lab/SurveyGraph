"""
MEKG 控制面板启动脚本

使用方式：
    python scripts/start_mekg_panel.py
    
或直接：
    streamlit run scripts/mekg_control_panel.py
"""

import subprocess
import sys
import os
import webbrowser
import time

def main():
    print("🧠 MEKG 控制面板启动中...")
    print("=" * 50)
    
    # 定位项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    os.chdir(project_root)
    
    print(f"📂 工作目录: {os.getcwd()}")
    
    # 检查依赖
    try:
        import streamlit
        import pyvis
        print("✅ 依赖检查通过")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install streamlit pyvis")
        sys.exit(1)
    
    # 启动Streamlit
    panel_script = os.path.join("scripts", "mekg_control_panel.py")
    
    cmd = [
        sys.executable, "-m", "streamlit", "run", panel_script,
        "--browser.gatherUsageStats", "false",
        "--server.address", "localhost",
        "--server.port", "8502",
        "--theme.base", "dark"
    ]
    
    print(f"🚀 启动命令: {' '.join(cmd)}")
    print("=" * 50)
    print("🌐 访问地址: http://localhost:8502")
    print("⌨️  按 Ctrl+C 停止")
    print("=" * 50)
    
    # 延迟打开浏览器
    def open_browser():
        time.sleep(2)
        webbrowser.open("http://localhost:8502")
    
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    
    # 运行
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n👋 已停止")

if __name__ == "__main__":
    main()