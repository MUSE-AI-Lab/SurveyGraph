"""
SurveyGraph Frontend - 进程管理器
==================================

独立的进程管理系统，将任务执行进程与 FastAPI 解耦。
支持 Windows 和 Linux 系统。

核心功能：
1. 启动独立的任务执行进程
2. 持久化 PID 信息到文件系统
3. 监控进程状态
4. FastAPI 重启后恢复进程跟踪
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
import platform

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import PROJECT_ROOT, AppConfig

logger = logging.getLogger(__name__)

# 进程信息存储目录
PROCESS_DIR = AppConfig.OUTPUT_DIR / ".processes"
PROCESS_DIR.mkdir(parents=True, exist_ok=True)

# 日志缓冲区大小
LOG_BUFFER_SIZE = 1000


class ProcessInfo:
    """进程信息类"""
    
    def __init__(
        self,
        task_id: str,
        pid: int,
        command: List[str],
        started_at: str,
        status: str = "running",
        log_file: Optional[str] = None,
        exit_code: Optional[int] = None
    ):
        self.task_id = task_id
        self.pid = pid
        self.command = command
        self.started_at = started_at
        self.status = status  # running, completed, failed, terminated
        self.log_file = log_file
        self.exit_code = exit_code
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "pid": self.pid,
            "command": self.command,
            "started_at": self.started_at,
            "status": self.status,
            "log_file": self.log_file,
            "exit_code": self.exit_code
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessInfo":
        return cls(
            task_id=data["task_id"],
            pid=data["pid"],
            command=data["command"],
            started_at=data["started_at"],
            status=data.get("status", "running"),
            log_file=data.get("log_file"),
            exit_code=data.get("exit_code")
        )
    
    def save(self):
        """保存进程信息到文件"""
        info_file = PROCESS_DIR / f"{self.task_id}.json"
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, task_id: str) -> Optional["ProcessInfo"]:
        """从文件加载进程信息"""
        info_file = PROCESS_DIR / f"{task_id}.json"
        if not info_file.exists():
            return None
        try:
            with open(info_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load process info for {task_id}: {e}")
            return None
    
    def delete(self):
        """删除进程信息文件"""
        info_file = PROCESS_DIR / f"{self.task_id}.json"
        if info_file.exists():
            info_file.unlink()


class ProcessManager:
    """进程管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._is_windows = platform.system() == "Windows"
        self._monitor_tasks: Dict[str, asyncio.Task] = {}
        logger.info(f"ProcessManager initialized on {platform.system()}")
    
    def _get_log_file(self, task_id: str) -> Path:
        """获取任务的日志文件路径"""
        log_dir = AppConfig.OUTPUT_DIR / task_id / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / "pipeline.log"
    
    def _is_process_running(self, pid: int) -> bool:
        """检查进程是否正在运行"""
        try:
            if self._is_windows:
                # Windows: 使用 tasklist 命令
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                return str(pid) in result.stdout
            else:
                # Linux/Unix: 发送信号 0 检查进程
                os.kill(pid, 0)
                return True
        except (OSError, subprocess.SubprocessError):
            return False
    
    def _terminate_process(self, pid: int, force: bool = False) -> bool:
        """终止进程"""
        try:
            if self._is_windows:
                # Windows: 使用 taskkill，同时终止子进程树
                cmd = ["taskkill", "/PID", str(pid), "/T"]  # /T 终止进程树
                if force:
                    cmd.append("/F")
                subprocess.run(cmd, capture_output=True)
            else:
                # Linux/Unix: 发送信号
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.kill(pid, sig)
            return True
        except Exception as e:
            logger.error(f"Failed to terminate process {pid}: {e}")
            return False
    
    def _find_task_process(self, task_id: str, log_file: Path) -> Optional[int]:
        """
        查找任务对应的 Python 进程 PID
        
        在 Windows 上，由于使用 cmd.exe /c start 启动，需要找到实际的 Python 进程
        """
        if not self._is_windows:
            return None
        
        try:
            # 使用 WMIC 查找包含 task_id 的 Python 进程
            result = subprocess.run(
                ["wmic", "process", "where",
                 f"commandline like '%{task_id}%' and name='python.exe'",
                 "get", "processid"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            # 解析输出，获取 PID
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # 跳过标题行
                line = line.strip()
                if line and line.isdigit():
                    return int(line)
        except Exception as e:
            logger.warning(f"Failed to find task process: {e}")
        
        # 备选方案：查找 PowerShell 进程
        try:
            result = subprocess.run(
                ["wmic", "process", "where",
                 f"commandline like '%{task_id}%' and name='powershell.exe'",
                 "get", "processid"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:
                line = line.strip()
                if line and line.isdigit():
                    return int(line)
        except Exception as e:
            logger.warning(f"Failed to find PowerShell process: {e}")
        
        return None
    
    async def start_task(
        self,
        task_id: str,
        topic: str,
        config: Optional[Dict[str, Any]] = None,
        resume: bool = False,
        from_step: Optional[int] = None,
        uploaded_files: Optional[List[Dict[str, Any]]] = None,
        enable_arxiv_search: bool = True
    ) -> ProcessInfo:
        """
        启动任务执行进程
        
        Args:
            task_id: 任务 ID
            topic: 研究主题
            config: 配置参数
            resume: 是否从断点恢复
            from_step: 从指定步骤开始
            uploaded_files: 上传的文件列表
            enable_arxiv_search: 是否启用 arXiv 搜索
        
        Returns:
            ProcessInfo: 进程信息
        """
        # 检查是否已有运行中的进程
        existing = ProcessInfo.load(task_id)
        if existing and self._is_process_running(existing.pid):
            logger.warning(f"Task {task_id} already has a running process (PID: {existing.pid})")
            return existing
        
        # 构建命令
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "tasks" / "mekg_run.py"),
            "--topic", topic,
            "--task_id", task_id,
        ]
        
        # 添加配置参数
        if config:
            if config.get("max_papers"):
                cmd.extend(["--max_papers", str(config["max_papers"])])
            if config.get("year_start"):
                cmd.extend(["--year_start", str(config["year_start"])])
            if config.get("year_end"):
                cmd.extend(["--year_end", str(config["year_end"])])
            
            # 布尔参数
            if config.get("enable_critic"):
                cmd.append("--enable_critic")
            if config.get("enable_refine"):
                cmd.append("--enable_refine")
            if config.get("enable_reflection"):
                cmd.append("--enable-reflection")
            else:
                cmd.append("--no-reflection")
            if config.get("use_hybrid_outline"):
                cmd.append("--use-hybrid-outline")
            else:
                cmd.append("--no-hybrid-outline")
            if config.get("use_global_reflector"):
                cmd.append("--use-global-reflector")
            else:
                cmd.append("--no-global-reflector")
            if config.get("use_evolutionary_analyzer"):
                cmd.append("--use-evolutionary-analyzer")
            else:
                cmd.append("--no-evolutionary-analyzer")
            if config.get("run_evaluation", True):
                cmd.append("--run-evaluation")
            else:
                cmd.append("--no-evaluation")
        
        # 是否启用 arXiv 搜索
        if not enable_arxiv_search:
            cmd.append("--no-arxiv")
        
        # 上传的文件列表
        if uploaded_files:
            # 提取文件路径列表
            file_paths = []
            for f in uploaded_files:
                if isinstance(f, dict):
                    path = f.get("path")
                    if path:
                        file_paths.append(path)
                elif isinstance(f, str):
                    file_paths.append(f)
            
            if file_paths:
                # 将文件路径列表作为 JSON 字符串传递
                import json as json_module
                cmd.extend(["--uploaded-files", json_module.dumps(file_paths)])
        
        # 恢复模式
        if resume:
            cmd.append("--resume")
        
        # 准备日志文件
        log_file = self._get_log_file(task_id)
        
        logger.info(f"Starting task process: {' '.join(cmd)}")
        logger.info(f"Log file: {log_file}")
        
        # 启动进程
        # 使用 subprocess.Popen 而不是 asyncio.create_subprocess_exec
        # 这样进程完全独立于 FastAPI
        
        if self._is_windows:
            # Windows: 使用 cmd.exe /c start 启动完全独立的进程
            # 这是最可靠的方式，确保：
            # 1. 进程完全独立于父进程（FastAPI 重启不会终止任务）
            # 2. 有独立的控制台窗口显示实时日志
            # 3. 报错时窗口不会立即关闭
            
            # 初始化日志文件
            with open(log_file, 'w', encoding='utf-8') as log_f:
                log_f.write(f"Task {task_id} started at {datetime.now().isoformat()}\n")
                log_f.write(f"Command: {' '.join(cmd)}\n")
                log_f.write("=" * 50 + "\n")
            
            # 创建一个批处理脚本来运行任务
            # 这样可以：
            # 1. 使用 Tee-Object 同时输出到控制台和文件
            # 2. 在出错时暂停，让用户看到错误信息
            # 3. 完全独立于父进程
            batch_script = AppConfig.OUTPUT_DIR / task_id / "run_task.bat"
            batch_script.parent.mkdir(parents=True, exist_ok=True)
            
            # 转义路径中的特殊字符
            python_exe = sys.executable.replace("'", "''")
            log_file_str = str(log_file).replace("'", "''")
            
            # 构建命令行参数 - 所有参数都用单引号包裹，避免空格问题
            # 在 PowerShell 中，单引号内的内容是字面量，不会被解析
            def escape_for_powershell(arg: str) -> str:
                """转义 PowerShell 参数"""
                # 转义单引号（在 PowerShell 中用两个单引号表示一个单引号）
                escaped = arg.replace("'", "''")
                return f"'{escaped}'"
            
            cmd_args = ' '.join(escape_for_powershell(arg) for arg in cmd[1:])
            
            # 创建批处理脚本
            # 注意：PowerShell 中使用 & 运算符调用命令时，路径和参数都需要正确引用
            # 使用单引号包裹所有参数，避免空格和特殊字符问题
            python_exe_ps = escape_for_powershell(sys.executable)
            
            batch_content = f'''@echo off
chcp 65001 >nul
title SurveyGraph Task: {task_id}
echo ============================================================
echo SurveyGraph Task Runner
echo Task ID: {task_id}
echo Started: %date% %time%
echo ============================================================
echo.

cd /d "{PROJECT_ROOT}"

REM 使用 PowerShell 的 Tee-Object 同时输出到控制台和文件
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "& {{ & {python_exe_ps} {cmd_args} 2>&1 | Tee-Object -FilePath '{log_file_str}' -Append; $exitCode = $LASTEXITCODE; Write-Host ''; Write-Host '============================================================'; if ($exitCode -eq 0) {{ Write-Host 'Task completed successfully!' -ForegroundColor Green }} else {{ Write-Host ('Task failed with exit code: ' + $exitCode) -ForegroundColor Red; Write-Host ''; Write-Host 'Press any key to close this window...' -ForegroundColor Yellow; $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') }}; exit $exitCode }}"

REM 如果 PowerShell 执行失败，回退到直接运行
if errorlevel 9009 (
    echo PowerShell not available, running directly...
    "{sys.executable}" {' '.join(f'"{arg}"' if ' ' in arg else arg for arg in cmd[1:])}
    if errorlevel 1 (
        echo.
        echo Task failed! Press any key to close...
        pause >nul
    )
)
'''
            
            with open(batch_script, 'w', encoding='utf-8') as f:
                f.write(batch_content)
            
            # 使用 cmd.exe /c start 启动批处理脚本
            # /c 表示执行完命令后关闭 cmd
            # start 命令会创建一个新的独立进程
            # "" 是窗口标题（必须有，否则路径会被当作标题）
            # /wait 不使用，让进程完全独立
            start_cmd = f'start "" "{batch_script}"'
            
            # 使用 DETACHED_PROCESS 确保进程完全独立
            process = subprocess.Popen(
                start_cmd,
                shell=True,
                cwd=str(PROJECT_ROOT),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # 等待一小段时间让批处理脚本启动
            import time
            time.sleep(0.5)
            
            # 获取实际运行的进程 PID
            # 由于使用了 start 命令，process.pid 是 cmd.exe 的 PID
            # 我们需要找到实际的 Python 进程
            actual_pid = self._find_task_process(task_id, log_file)
            if actual_pid:
                process_pid = actual_pid
            else:
                # 如果找不到，使用 cmd.exe 的 PID（可能已经退出）
                process_pid = process.pid
            # 记录找到的 PID
            logger.info(f"Task {task_id} actual PID: {process_pid}")
        else:
            # Linux/Unix: 使用 start_new_session=True 创建新会话
            # 使进程成为会话领导者，独立于父进程
            with open(log_file, 'w', encoding='utf-8') as log_f:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    cwd=str(PROJECT_ROOT),
                    start_new_session=True,
                    preexec_fn=os.setpgrp  # 创建新进程组
                )
            process_pid = process.pid
        
        # 创建进程信息
        process_info = ProcessInfo(
            task_id=task_id,
            pid=process_pid,
            command=cmd,
            started_at=datetime.now().isoformat(),
            status="running",
            log_file=str(log_file)
        )
        
        # 保存进程信息
        process_info.save()
        
        logger.info(f"Task {task_id} started with PID {process_pid}")
        
        # 启动监控任务
        await self._start_monitor(task_id)
        
        return process_info
    
    async def _start_monitor(self, task_id: str):
        """启动进程监控"""
        if task_id in self._monitor_tasks:
            return
        
        async def monitor():
            """监控进程状态"""
            while True:
                await asyncio.sleep(5)  # 每 5 秒检查一次
                
                process_info = ProcessInfo.load(task_id)
                if not process_info:
                    break
                
                if process_info.status != "running":
                    break
                
                if not self._is_process_running(process_info.pid):
                    # 进程已结束，检查退出状态
                    exit_code = await self._get_exit_code(task_id, process_info.pid)
                    
                    if exit_code == 0:
                        process_info.status = "completed"
                    else:
                        process_info.status = "failed"
                    
                    process_info.exit_code = exit_code
                    process_info.save()
                    
                    # 更新数据库状态
                    await self._update_task_status(task_id, process_info.status, exit_code)
                    
                    logger.info(f"Task {task_id} process ended with status: {process_info.status}")
                    break
            
            # 清理监控任务
            if task_id in self._monitor_tasks:
                del self._monitor_tasks[task_id]
        
        self._monitor_tasks[task_id] = asyncio.create_task(monitor())
    
    async def _get_exit_code(self, task_id: str, pid: int) -> int:
        """获取进程退出码"""
        # 尝试从日志文件中读取退出状态
        process_info = ProcessInfo.load(task_id)
        if process_info and process_info.log_file:
            log_file = Path(process_info.log_file)
            if log_file.exists():
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        # 检查是否有成功完成的标志
                        if "completed" in content.lower() or "✅" in content:
                            return 0
                        if "error" in content.lower() or "failed" in content.lower() or "❌" in content:
                            return 1
                except Exception as e:
                    logger.error(f"Failed to read log file: {e}")
        
        # 默认返回 -1 表示未知
        return -1
    
    async def _update_task_status(self, task_id: str, status: str, exit_code: int):
        """更新数据库中的任务状态"""
        try:
            from services.task_service import TaskService
            from core.models import TaskStatus, LogLevel
            
            if status == "completed":
                # 获取输出路径
                paths = TaskService.get_output_paths(task_id)
                await TaskService.complete_task(
                    task_id,
                    output_dir=str(paths["output_dir"]),
                    mekg_data_path=str(paths["mekg_data"]) if paths["mekg_data"].exists() else None,
                    outline_path=str(paths["outline"]) if paths["outline"].exists() else None,
                    pdf_path=str(paths["pdf"]) if paths["pdf"].exists() else str(paths["pdf_wtmk"]) if paths["pdf_wtmk"].exists() else None,
                    evaluation_path=str(paths["evaluation"]) if paths["evaluation"].exists() else None,
                    visualization_path=str(paths["visualization"]) if paths["visualization"].exists() else None
                )
                
                # 添加完成日志
                task = await TaskService.get_task_by_task_id(task_id)
                if task:
                    await TaskService.add_task_log(
                        task.id,
                        step=11,
                        step_name="COMPLETED",
                        level=LogLevel.INFO,
                        message="任务执行完成"
                    )
                
                # 推送完成通知
                try:
                    from api.websocket import push_completion
                    await push_completion(task_id, success=True)
                except Exception:
                    pass
            
            elif status == "failed":
                await TaskService.fail_task(task_id, f"Pipeline 执行失败，退出码: {exit_code}")
                
                # 添加失败日志
                task = await TaskService.get_task_by_task_id(task_id)
                if task:
                    await TaskService.add_task_log(
                        task.id,
                        step=task.current_step,
                        step_name=task.current_step_name or "UNKNOWN",
                        level=LogLevel.ERROR,
                        message=f"Pipeline 执行失败，退出码: {exit_code}"
                    )
                
                # 推送失败通知
                try:
                    from api.websocket import push_completion
                    await push_completion(task_id, success=False)
                except Exception:
                    pass
        
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
    
    def get_process_info(self, task_id: str) -> Optional[ProcessInfo]:
        """获取进程信息"""
        process_info = ProcessInfo.load(task_id)
        if process_info:
            # 更新运行状态
            if process_info.status == "running":
                if not self._is_process_running(process_info.pid):
                    process_info.status = "terminated"
                    process_info.save()
        return process_info
    
    def is_task_running(self, task_id: str) -> bool:
        """检查任务是否正在运行"""
        process_info = self.get_process_info(task_id)
        if not process_info:
            return False
        return process_info.status == "running" and self._is_process_running(process_info.pid)
    
    async def stop_task(self, task_id: str, force: bool = False) -> bool:
        """停止任务"""
        process_info = ProcessInfo.load(task_id)
        if not process_info:
            return False
        
        if not self._is_process_running(process_info.pid):
            process_info.status = "terminated"
            process_info.save()
            return True
        
        # 终止进程
        success = self._terminate_process(process_info.pid, force)
        
        if success:
            # 等待进程结束
            for _ in range(10):
                await asyncio.sleep(0.5)
                if not self._is_process_running(process_info.pid):
                    break
            
            process_info.status = "terminated"
            process_info.save()
            
            # 更新数据库状态
            try:
                from services.task_service import TaskService
                from core.models import TaskStatus
                await TaskService.update_task_status(task_id, TaskStatus.PAUSED)
            except Exception as e:
                logger.error(f"Failed to update task status: {e}")
        
        return success
    
    def get_task_logs(self, task_id: str, lines: int = 100, follow: bool = False) -> List[str]:
        """获取任务日志"""
        process_info = ProcessInfo.load(task_id)
        if not process_info or not process_info.log_file:
            return []
        
        log_file = Path(process_info.log_file)
        if not log_file.exists():
            return []
        
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                return all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return []
    
    async def get_task_logs_stream(self, task_id: str):
        """流式获取任务日志（用于实时监控）"""
        process_info = ProcessInfo.load(task_id)
        if not process_info or not process_info.log_file:
            return
        
        log_file = Path(process_info.log_file)
        if not log_file.exists():
            return
        
        # 从文件末尾开始读取
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            # 移动到文件末尾
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    yield line.strip()
                else:
                    # 检查进程是否还在运行
                    if not self.is_task_running(task_id):
                        break
                    await asyncio.sleep(0.1)
    
    def get_all_running_tasks(self) -> List[ProcessInfo]:
        """获取所有运行中的任务"""
        running_tasks = []
        
        for info_file in PROCESS_DIR.glob("*.json"):
            try:
                task_id = info_file.stem
                process_info = ProcessInfo.load(task_id)
                if process_info and process_info.status == "running":
                    if self._is_process_running(process_info.pid):
                        running_tasks.append(process_info)
                    else:
                        # 进程已结束但状态未更新
                        process_info.status = "terminated"
                        process_info.save()
            except Exception as e:
                logger.error(f"Failed to load process info from {info_file}: {e}")
        
        return running_tasks
    
    async def recover_monitors(self):
        """恢复所有运行中任务的监控（FastAPI 重启后调用）"""
        running_tasks = self.get_all_running_tasks()
        
        for process_info in running_tasks:
            logger.info(f"Recovering monitor for task {process_info.task_id} (PID: {process_info.pid})")
            await self._start_monitor(process_info.task_id)
        
        logger.info(f"Recovered {len(running_tasks)} task monitors")
    
    def cleanup_old_processes(self, max_age_hours: int = 72):
        """清理旧的进程信息文件"""
        now = datetime.now()
        
        for info_file in PROCESS_DIR.glob("*.json"):
            try:
                process_info = ProcessInfo.load(info_file.stem)
                if process_info:
                    started_at = datetime.fromisoformat(process_info.started_at)
                    age_hours = (now - started_at).total_seconds() / 3600
                    
                    if age_hours > max_age_hours and process_info.status != "running":
                        process_info.delete()
                        logger.info(f"Cleaned up old process info: {process_info.task_id}")
            except Exception as e:
                logger.error(f"Failed to cleanup {info_file}: {e}")


# 全局进程管理器实例
process_manager = ProcessManager()