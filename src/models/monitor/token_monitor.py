import json
import threading
from pathlib import Path
from typing import Dict

import yaml

from src.configs.constants import BASE_DIR, OUTPUT_DIR
from src.configs.logger import get_logger
from src.schemas.base import Base

logger = get_logger("src.modules.monitor.token_monitor")


class TokenMonitor(Base):
    def __init__(self, task_id: str, label: str):
        super().__init__(task_id)

        # load LLM pricing file
        self._config_path = BASE_DIR / "src" / "configs" / "LLM.yaml"
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"LLM pricing file doesn't exist: {self._config_path}"
            )
        else:
            self.pricing = self._load_pricing_config()

        self.record_file: Path = OUTPUT_DIR / task_id / "metrics" / "token_monitor.json"
        self.record_file.parent.mkdir(parents=True, exist_ok=True)

        self.record: Dict[str, Dict[str, list]] = {}
        self.label: str = label

        # 添加线程锁
        self._lock = threading.Lock()

    def _load_pricing_config(self) -> Dict:
        try:
            with open(self._config_path, "r") as f:
                config = yaml.safe_load(f)
            return config
        except (yaml.YAMLError, KeyError) as e:
            logger.error(f"加载定价配置失败：{str(e)}")
            raise
        except Exception as e:
            logger.critical(f"无法读取配置文件：{str(e)}")
            raise

    def add_token(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        label: str | None = None,
    ) -> float:
        with self._lock:  # 加锁
            if model not in self.pricing:
                # logger.debug(f"未配置 {model} 的定价信息")
                input_price = self.pricing["default"]["input"]
                output_price = self.pricing["default"]["output"]
            else:
                input_price = self.pricing[model]["input"]
                output_price = self.pricing[model]["output"]

            # 计算本次费用（保留4位小数）
            cost = round(
                (input_tokens / 1000000 * float(input_price))
                + (output_tokens / 1000000 * float(output_price)),
                12,
            )
            # 初始化标签记录结构
            if label == None:
                label = self.label
            if label not in self.record:
                self.record[label] = {}
            # 通过model直接获取记录
            if model not in self.record[label]:
                self.record[label][model] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_cost": cost,
                }
            else:
                # 累加已有记录的值
                self.record[label][model]["input_tokens"] += input_tokens
                self.record[label][model]["output_tokens"] += output_tokens
                self.record[label][model]["total_cost"] = round(
                    self.record[label][model]["total_cost"] + cost, 12
                )
            # 保存记录
            self._save_record(label)
        return cost

    def _save_record(self, label: str) -> None:
        """
        没加线程锁, add token函数中加了线程锁,
        任何调用该函数的地方都要加线程锁
        """
        try:
            # 读取现有记录
            existing = {}
            if self.record_file.exists():
                with open(self.record_file, "r") as f:
                    existing = json.load(f)

            # 仅更新当前标签的记录（保留其他标签数据）
            existing[label] = self.record[label]

            # 原子化写入
            with open(self.record_file, "w") as f:
                json.dump(existing, f, indent=4)

        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"保存token记录失败: {str(e)}")
            raise


def stress_test(monitor: TokenMonitor):
    for _ in range(1000):
        monitor.add_token("gpt-4o", 100, 50, "stress_test")


# python -m src.models.monitor.token_monitor
if __name__ == "__main__":
    # 使用示例
    monitor = TokenMonitor("test", "test_label")

    # 第一次调用
    cost1 = monitor.add_token("gpt-4o", 1500, 800)
    print(f"本次费用: ${cost1}")

    # 第二次调用
    cost2 = monitor.add_token("gpt-4o", 2000, 1200)
    print(f"本次费用: ${cost2}")

    cost3 = monitor.add_token("gpt-4o-mini", 2000, 1200)
    print(f"本次费用: ${cost3}")

    cost4 = monitor.add_token("qwen", 2000, 1200)
    print(f"本次费用: ${cost4}")

    # 查看累计记录
    print("当前记录:", monitor.record)

    # 多线程测试
    threads = [threading.Thread(target=stress_test, args=(monitor,)) for _ in range(10)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 验证结果
    record = monitor.record["stress_test"]["gpt-4o"]
    assert record["input_tokens"] == 100 * 1000 * 10  # 100次/线程 × 10线程
    assert record["output_tokens"] == 50 * 1000 * 10
