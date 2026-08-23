import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

from src.configs.constants import OUTPUT_DIR
from src.configs.logger import get_logger
from src.schemas.base import Base

logger = get_logger("src.modules.monitor.time_monitor")


class TimeMonitor(Base):
    def __init__(self, task_id: str):
        super().__init__(task_id)

        self.record_file: Path = OUTPUT_DIR / task_id / "metrics" / "time_monitor.json"
        self.record_file.parent.mkdir(parents=True, exist_ok=True)

        self.record: Dict[str, Dict[str, float]] = {}

    def start(self, label: str) -> None:
        """记录指定标签的开始时间（秒级时间戳）"""
        if not isinstance(label, str):
            raise TypeError(f"Label must be string, got {type(label).__name__}")

        self.record[label] = {
            "start": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end": None,
            "duration": None,
        }

    def end(self, label: str) -> float:
        """计算时间差并写入文件，返回持续时间（秒）"""
        if label not in self.record:
            raise KeyError(f"Label '{label}' not found in records")

        record = self.record[label]
        start_time = datetime.strptime(record["start"], "%Y-%m-%d %H:%M:%S")
        end_time = datetime.now()

        # 更新记录字段
        record["end"] = end_time.strftime("%Y-%m-%d %H:%M:%S")
        record["duration"] = round((end_time - start_time).total_seconds(), 2)

        self._save_record(label)
        return record["duration"]

    def _save_record(self, label: str) -> None:
        """原子化写入操作，追加模式保存数据"""
        try:
            # 读取现有记录
            existing = {}
            if self.record_file.exists():
                with open(self.record_file, "r") as f:
                    existing = json.load(f)

            # 合并数据（保留历史记录）
            existing[label] = self.record[label]

            # 原子化写入
            with open(self.record_file, "w") as f:
                json.dump(existing, f, indent=4)

        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to save monitoring record: {str(e)}")
            raise


# python -m src.models.monitor.time_monitor
if __name__ == "__main__":
    monitor = TimeMonitor("test")
    monitor.start("test")
    time.sleep(3)
    monitor.end("test")
    print(monitor.record)
