import os
import sys
import subprocess

def main():
    """
    启动 MEKG 实时仪表盘
    """
    # 获取 live_dashboard.py 的绝对路径
    dashboard_script = os.path.join(os.path.dirname(__file__), "live_dashboard.py")
    
    print(f"🚀 正在启动 MEKG 实时仪表盘...")
    print(f"📂 脚本路径: {dashboard_script}")
    print("🌐 请在浏览器中访问显示的 URL (通常是 http://localhost:8501)")
    
    # 使用 subprocess 调用 streamlit run
    # 这样可以确保使用当前环境的 python 和 streamlit
    # 添加参数跳过首次运行的邮箱提示
    cmd = [
        sys.executable, "-m", "streamlit", "run", dashboard_script,
        "--browser.gatherUsageStats", "false",
        "--server.headless", "true"
    ]
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n👋 仪表盘已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")

if __name__ == "__main__":
    main()