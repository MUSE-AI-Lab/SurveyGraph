"""
Incremental Processing System
=============================

增量处理系统，支持：
- 基于内容哈希的变更检测
- 状态持久化
- 智能跳过未变更的步骤
- 部分重新处理

使用方法:
    state_store = IncrementalStateStore(state_dir)
    hasher = ContentHasher()
    
    # 检查是否需要重新处理
    papers_hash = hasher.hash_papers(papers)
    if state_store.get("papers_hash") != papers_hash:
        # 论文变化，需要重新生成大纲
        outline = generate_outline(papers)
        state_store.set("papers_hash", papers_hash)
        state_store.set("outline", outline)
    else:
        # 论文未变化，复用之前的大纲
        outline = state_store.get("outline")
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    TypeVar,
    Union,
)
import threading
import shutil

from loguru import logger


T = TypeVar("T")


class ContentHasher:
    """
    内容哈希计算器
    
    用于计算各种数据结构的哈希值，支持：
    - 论文列表
    - 大纲结构
    - 配置参数
    - 任意 JSON 可序列化对象
    """
    
    def __init__(self, algorithm: str = "sha256"):
        """
        初始化哈希计算器
        
        Args:
            algorithm: 哈希算法（sha256, md5, sha1 等）
        """
        self.algorithm = algorithm
    
    def hash_string(self, content: str) -> str:
        """
        计算字符串哈希
        
        Args:
            content: 字符串内容
            
        Returns:
            哈希值（16位十六进制）
        """
        h = hashlib.new(self.algorithm)
        h.update(content.encode("utf-8"))
        return h.hexdigest()[:16]
    
    def hash_dict(self, data: Dict[str, Any], keys: Optional[List[str]] = None) -> str:
        """
        计算字典哈希
        
        Args:
            data: 字典数据
            keys: 只计算指定键的哈希（可选）
            
        Returns:
            哈希值
        """
        if keys:
            data = {k: data.get(k) for k in keys}
        
        # 排序键以确保一致性
        content = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
        return self.hash_string(content)
    
    def hash_list(self, items: List[Any], key_func: Optional[Callable[[Any], str]] = None) -> str:
        """
        计算列表哈希
        
        Args:
            items: 列表数据
            key_func: 提取每个元素的键的函数（可选）
            
        Returns:
            哈希值
        """
        if key_func:
            keys = sorted([key_func(item) for item in items])
            content = json.dumps(keys, ensure_ascii=False)
        else:
            content = json.dumps(items, sort_keys=True, ensure_ascii=False, default=str)
        
        return self.hash_string(content)
    
    def hash_papers(self, papers: List[Dict[str, Any]]) -> str:
        """
        计算论文列表哈希
        
        只考虑论文的核心属性（ID、标题、摘要），忽略元数据变化
        
        Args:
            papers: 论文列表
            
        Returns:
            哈希值
        """
        # 提取核心属性
        core_data = []
        for paper in papers:
            core_data.append({
                "id": paper.get("id", paper.get("paper_id", "")),
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", "")[:500],  # 只取前500字符
            })
        
        # 按 ID 排序以确保一致性
        core_data.sort(key=lambda x: x["id"])
        
        return self.hash_list(core_data)
    
    def hash_outline(self, outline: Dict[str, Any]) -> str:
        """
        计算大纲哈希
        
        Args:
            outline: 大纲数据
            
        Returns:
            哈希值
        """
        # 提取大纲结构（忽略论文挂载信息）
        def extract_structure(sections: List[Dict]) -> List[Dict]:
            result = []
            for sec in sections:
                item = {
                    "title": sec.get("title", sec.get("section title", "")),
                    "description": sec.get("description", sec.get("desc", ""))[:100],
                }
                if "subsections" in sec:
                    item["subsections"] = extract_structure(sec["subsections"])
                result.append(item)
            return result
        
        structure = {
            "title": outline.get("title", ""),
            "sections": extract_structure(outline.get("sections", [])),
        }
        
        return self.hash_dict(structure)
    
    def hash_config(self, config: Any) -> str:
        """
        计算配置哈希
        
        Args:
            config: 配置对象（dataclass 或字典）
            
        Returns:
            哈希值
        """
        if hasattr(config, "__dict__"):
            data = {k: v for k, v in config.__dict__.items() if not k.startswith("_")}
        else:
            data = dict(config)
        
        return self.hash_dict(data)
    
    def hash_file(self, file_path: Path) -> str:
        """
        计算文件哈希
        
        Args:
            file_path: 文件路径
            
        Returns:
            哈希值
        """
        h = hashlib.new(self.algorithm)
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        
        return h.hexdigest()[:16]


@dataclass
class StateEntry:
    """状态条目"""
    key: str
    value: Any
    hash: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class IncrementalStateStore:
    """
    增量状态存储
    
    持久化存储 Pipeline 的中间状态，支持：
    - 键值存储
    - 哈希比较
    - 自动过期
    - 版本管理
    
    使用示例:
        store = IncrementalStateStore(state_dir)
        
        # 存储状态
        store.set("papers_hash", papers_hash)
        store.set("outline", outline_data)
        
        # 获取状态
        if store.get("papers_hash") == current_hash:
            outline = store.get("outline")
        
        # 检查是否需要更新
        if store.needs_update("papers", current_papers, hasher.hash_papers):
            # 处理论文
            store.set("papers", current_papers)
    """
    
    VERSION = "1.0"
    
    def __init__(
        self,
        state_dir: Path,
        ttl: float = 72 * 3600,  # 默认 72 小时过期
        auto_save: bool = True
    ):
        """
        初始化状态存储
        
        Args:
            state_dir: 状态存储目录
            ttl: 状态过期时间（秒）
            auto_save: 是否自动保存
        """
        self.state_dir = Path(state_dir)
        self.ttl = ttl
        self.auto_save = auto_save
        
        self._entries: Dict[str, StateEntry] = {}
        self._lock = threading.RLock()
        self._dirty = False
        
        # 创建目录
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载已有状态
        self._load()
    
    def get(self, key: str, default: T = None) -> Optional[T]:
        """
        获取状态值
        
        Args:
            key: 状态键
            default: 默认值
            
        Returns:
            状态值或默认值
        """
        with self._lock:
            if key not in self._entries:
                return default
            
            entry = self._entries[key]
            
            # 检查是否过期
            if self._is_expired(entry):
                del self._entries[key]
                self._dirty = True
                return default
            
            return entry.value
    
    def set(self, key: str, value: Any, hash_value: Optional[str] = None, **metadata) -> None:
        """
        设置状态值
        
        Args:
            key: 状态键
            value: 状态值
            hash_value: 哈希值（可选，用于变更检测）
            **metadata: 额外元数据
        """
        with self._lock:
            now = datetime.now()
            
            if key in self._entries:
                entry = self._entries[key]
                entry.value = value
                entry.hash = hash_value or ""
                entry.updated_at = now
                entry.metadata.update(metadata)
            else:
                entry = StateEntry(
                    key=key,
                    value=value,
                    hash=hash_value or "",
                    created_at=now,
                    updated_at=now,
                    metadata=metadata,
                )
                self._entries[key] = entry
            
            self._dirty = True
            
            if self.auto_save:
                self._save()
    
    def delete(self, key: str) -> bool:
        """
        删除状态
        
        Args:
            key: 状态键
            
        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                self._dirty = True
                
                if self.auto_save:
                    self._save()
                
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """
        检查状态是否存在
        
        Args:
            key: 状态键
            
        Returns:
            是否存在
        """
        with self._lock:
            if key not in self._entries:
                return False
            
            entry = self._entries[key]
            if self._is_expired(entry):
                del self._entries[key]
                self._dirty = True
                return False
            
            return True
    
    def get_hash(self, key: str) -> Optional[str]:
        """
        获取状态的哈希值
        
        Args:
            key: 状态键
            
        Returns:
            哈希值或 None
        """
        with self._lock:
            if key in self._entries:
                return self._entries[key].hash
            return None
    
    def needs_update(
        self,
        key: str,
        current_value: Any,
        hash_func: Callable[[Any], str]
    ) -> bool:
        """
        检查是否需要更新
        
        Args:
            key: 状态键
            current_value: 当前值
            hash_func: 哈希函数
            
        Returns:
            是否需要更新
        """
        current_hash = hash_func(current_value)
        stored_hash = self.get_hash(key)
        
        return stored_hash != current_hash
    
    def update_if_changed(
        self,
        key: str,
        current_value: Any,
        hash_func: Callable[[Any], str],
        process_func: Callable[[Any], Any]
    ) -> tuple[Any, bool]:
        """
        如果值变化则更新
        
        Args:
            key: 状态键
            current_value: 当前值
            hash_func: 哈希函数
            process_func: 处理函数
            
        Returns:
            (处理结果, 是否更新)
        """
        current_hash = hash_func(current_value)
        stored_hash = self.get_hash(key)
        
        if stored_hash == current_hash:
            # 未变化，返回缓存值
            cached = self.get(key)
            if cached is not None:
                return cached, False
        
        # 需要更新
        result = process_func(current_value)
        self.set(key, result, hash_value=current_hash)
        return result, True
    
    def clear(self) -> None:
        """清空所有状态"""
        with self._lock:
            self._entries.clear()
            self._dirty = True
            
            # 删除状态文件
            state_file = self.state_dir / "state.json"
            if state_file.exists():
                state_file.unlink()
            
            data_dir = self.state_dir / "data"
            if data_dir.exists():
                shutil.rmtree(data_dir)
    
    def list_keys(self) -> List[str]:
        """列出所有状态键"""
        with self._lock:
            # 清理过期条目
            expired = [
                key for key, entry in self._entries.items()
                if self._is_expired(entry)
            ]
            for key in expired:
                del self._entries[key]
            
            if expired:
                self._dirty = True
            
            return list(self._entries.keys())
    
    def get_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取状态信息
        
        Args:
            key: 状态键
            
        Returns:
            状态信息字典
        """
        with self._lock:
            if key not in self._entries:
                return None
            
            entry = self._entries[key]
            return {
                "key": entry.key,
                "hash": entry.hash,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
                "metadata": entry.metadata,
                "expired": self._is_expired(entry),
            }
    
    def save(self) -> None:
        """手动保存状态"""
        self._save()
    
    def _is_expired(self, entry: StateEntry) -> bool:
        """检查条目是否过期"""
        if self.ttl <= 0:
            return False
        
        age = (datetime.now() - entry.updated_at).total_seconds()
        return age > self.ttl
    
    def _load(self) -> None:
        """从磁盘加载状态"""
        state_file = self.state_dir / "state.json"
        if not state_file.exists():
            return
        
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 检查版本
            if data.get("version") != self.VERSION:
                logger.warning(f"State version mismatch, clearing state")
                return
            
            # 加载条目
            for key, entry_data in data.get("entries", {}).items():
                try:
                    # 加载值
                    value = self._load_value(key, entry_data.get("value_type", "json"))
                    
                    entry = StateEntry(
                        key=key,
                        value=value,
                        hash=entry_data.get("hash", ""),
                        created_at=datetime.fromisoformat(entry_data["created_at"]),
                        updated_at=datetime.fromisoformat(entry_data["updated_at"]),
                        metadata=entry_data.get("metadata", {}),
                    )
                    
                    # 跳过过期条目
                    if not self._is_expired(entry):
                        self._entries[key] = entry
                        
                except Exception as e:
                    logger.warning(f"Failed to load state entry '{key}': {e}")
            
            logger.info(f"Loaded {len(self._entries)} state entries")
            
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
    
    def _save(self) -> None:
        """保存状态到磁盘"""
        if not self._dirty:
            return
        
        with self._lock:
            state_file = self.state_dir / "state.json"
            
            # 准备数据
            entries_data = {}
            for key, entry in self._entries.items():
                # 保存值
                value_type = self._save_value(key, entry.value)
                
                entries_data[key] = {
                    "hash": entry.hash,
                    "value_type": value_type,
                    "created_at": entry.created_at.isoformat(),
                    "updated_at": entry.updated_at.isoformat(),
                    "metadata": entry.metadata,
                }
            
            data = {
                "version": self.VERSION,
                "entries": entries_data,
                "saved_at": datetime.now().isoformat(),
            }
            
            # 写入文件
            try:
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                self._dirty = False
                
            except Exception as e:
                logger.error(f"Failed to save state: {e}")
    
    def _load_value(self, key: str, value_type: str) -> Any:
        """加载值"""
        data_dir = self.state_dir / "data"
        
        if value_type == "json":
            value_file = data_dir / f"{key}.json"
            if value_file.exists():
                with open(value_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        elif value_type == "pickle":
            value_file = data_dir / f"{key}.pkl"
            if value_file.exists():
                with open(value_file, "rb") as f:
                    return pickle.load(f)
        elif value_type == "text":
            value_file = data_dir / f"{key}.txt"
            if value_file.exists():
                return value_file.read_text(encoding="utf-8")
        
        return None
    
    def _save_value(self, key: str, value: Any) -> str:
        """保存值并返回类型"""
        data_dir = self.state_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # 尝试 JSON 序列化
        try:
            json_str = json.dumps(value, ensure_ascii=False, default=str)
            value_file = data_dir / f"{key}.json"
            with open(value_file, "w", encoding="utf-8") as f:
                f.write(json_str)
            return "json"
        except (TypeError, ValueError):
            pass
        
        # 尝试字符串
        if isinstance(value, str):
            value_file = data_dir / f"{key}.txt"
            value_file.write_text(value, encoding="utf-8")
            return "text"
        
        # 使用 pickle
        value_file = data_dir / f"{key}.pkl"
        with open(value_file, "wb") as f:
            pickle.dump(value, f)
        return "pickle"


# ============================================================================
# 增量处理装饰器
# ============================================================================

def incremental(
    key: str,
    hash_func: Callable[[Any], str],
    state_store: Optional[IncrementalStateStore] = None
):
    """
    增量处理装饰器
    
    自动检查输入是否变化，如果未变化则返回缓存结果
    
    使用示例:
        @incremental("outline", hasher.hash_papers)
        def generate_outline(papers):
            # 只有当 papers 变化时才会执行
            return expensive_operation(papers)
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(input_value: Any, *args, **kwargs):
            store = state_store or kwargs.pop("_state_store", None)
            
            if store is None:
                # 没有状态存储，直接执行
                return func(input_value, *args, **kwargs)
            
            # 计算输入哈希
            input_hash = hash_func(input_value)
            stored_hash = store.get_hash(key)
            
            if stored_hash == input_hash:
                # 输入未变化，返回缓存结果
                cached = store.get(key)
                if cached is not None:
                    logger.debug(f"Incremental cache hit for '{key}'")
                    return cached
            
            # 执行函数
            result = func(input_value, *args, **kwargs)
            
            # 缓存结果
            store.set(key, result, hash_value=input_hash)
            logger.debug(f"Incremental cache updated for '{key}'")
            
            return result
        
        return wrapper
    return decorator


# ============================================================================
# 便捷函数
# ============================================================================

def create_state_store(
    output_dir: Path,
    task_id: str,
    ttl: float = 72 * 3600
) -> IncrementalStateStore:
    """
    创建状态存储
    
    Args:
        output_dir: 输出目录
        task_id: 任务 ID
        ttl: 过期时间
        
    Returns:
        IncrementalStateStore 实例
    """
    state_dir = output_dir / task_id / ".state"
    return IncrementalStateStore(state_dir, ttl=ttl)