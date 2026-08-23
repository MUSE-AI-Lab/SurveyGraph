#!/usr/bin/env python3
"""
SurveyGraph Frontend 启动脚本
"""

import uvicorn
import argparse
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description='SurveyGraph Frontend Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind (default: 8080)')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
    parser.add_argument('--workers', type=int, default=1, help='Number of worker processes')
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    SurveyGraph Frontend                       ║
║                                                              ║
║  🌐 Server: http://{args.host}:{args.port}                          ║
║  📝 Docs:   http://{args.host}:{args.port}/docs                     ║
║  🔄 Reload: {'Enabled' if args.reload else 'Disabled'}                                       ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "frontend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info",
    )


if __name__ == "__main__":
    main()