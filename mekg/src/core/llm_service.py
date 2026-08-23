"""
LLM Service Layer
==================

统一的 LLM 调用层，提供：
- 自动重试机制
- 响应缓存
- 速率限制
- 批量调用
- 流式输出支持
- 统一的错误处理

使用方法:
    service = LLMService(chat_agent)
    
    # 单次调用（带缓存和重试）
    response = await service.call(prompt, temperature=0.3)
    
    # 批量调用（自动并发控制）
    responses = await service.batch_call(prompts, max_concurrency=50)
    
    # 流式调用
    async for chunk in service.stream_call(prompt):
        print(chunk, end="")
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    TypeVar,
    Union,
)
from pathlib import Path
from functools import wraps
import threading
from collections import OrderedDict

from loguru import logger

# Type variable for generic return types
T = TypeVar("T")


@dataclass
class LLMServiceConfig:
    """LLM 服务配置"""
    
    # 重试配置
    max_retries: int = 3
    retry_base_delay: float = 1.0  # 指数退避基础延迟（秒）
    retry_max_delay: float = 30.0  # 最大重试延迟（秒）
    
    # 速率限制配置
    rate_limit_calls: int = 100  # 每个周期最大调用次数
    rate_limit_period: float = 60.0  # 周期长度（秒）
    
    # 缓存配置
    enable_cache: bool = True
    cache_max_size: int = 1000  # 最大缓存条目数
    cache_ttl: float = 3600.0  # 缓存过期时间（秒）
    cache_dir: Optional[Path] = None  # 持久化缓存目录
    
    # 并发配置
    default_max_concurrency: int = 50
    
    # 超时配置
    default_timeout: float = 120.0
    
    # 默认模型参数
    default_temperature: float = 0.3
    default_model: Optional[str] = None


class RateLimiter:
    """
    令牌桶速率限制器
    
    支持异步等待，当超过速率限制时自动等待
    """
    
    def __init__(self, max_calls: int, period: float):
        """
        初始化速率限制器
        
        Args:
            max_calls: 每个周期最大调用次数
            period: 周期长度（秒）
        """
        self.max_calls = max_calls
        self.period = period
        self.calls: List[float] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """
        获取调用许可
        
        如果超过速率限制，会自动等待直到可以调用
        """
        async with self._lock:
            now = time.time()
            
            # 清理过期的调用记录
            self.calls = [t for t in self.calls if now - t < self.period]
            
            if len(self.calls) >= self.max_calls:
                # 需要等待
                oldest_call = self.calls[0]
                wait_time = self.period - (now - oldest_call)
                if wait_time > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    # 重新清理
                    now = time.time()
                    self.calls = [t for t in self.calls if now - t < self.period]
            
            self.calls.append(time.time())
    
    def reset(self) -> None:
        """重置速率限制器"""
        self.calls.clear()


class LRUCache:
    """
    LRU 缓存实现
    
    支持：
    - 最大容量限制
    - TTL 过期
    - 线程安全
    - 可选持久化
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        ttl: float = 3600.0,
        persist_dir: Optional[Path] = None
    ):
        """
        初始化 LRU 缓存
        
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存过期时间（秒）
            persist_dir: 持久化目录（可选）
        """
        self.max_size = max_size
        self.ttl = ttl
        self.persist_dir = persist_dir
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.RLock()
        
        # 加载持久化缓存
        if persist_dir:
            self._load_from_disk()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在或已过期返回 None
        """
        with self._lock:
            if key not in self._cache:
                return None
            
            value, timestamp = self._cache[key]
            
            # 检查是否过期
            if time.time() - timestamp > self.ttl:
                del self._cache[key]
                return None
            
            # 移动到末尾（最近使用）
            self._cache.move_to_end(key)
            return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        with self._lock:
            # 如果已存在，先删除
            if key in self._cache:
                del self._cache[key]
            
            # 检查容量
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = (value, time.time())
            
            # 持久化
            if self.persist_dir:
                self._save_to_disk()
    
    def delete(self, key: str) -> bool:
        """
        删除缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            if self.persist_dir:
                cache_file = self.persist_dir / "llm_cache.json"
                if cache_file.exists():
                    cache_file.unlink()
    
    def _load_from_disk(self) -> None:
        """从磁盘加载缓存"""
        if not self.persist_dir:
            return
        
        cache_file = self.persist_dir / "llm_cache.json"
        if not cache_file.exists():
            return
        
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            now = time.time()
            for key, (value, timestamp) in data.items():
                # 只加载未过期的条目
                if now - timestamp <= self.ttl:
                    self._cache[key] = (value, timestamp)
            
            logger.info(f"Loaded {len(self._cache)} cache entries from disk")
        except Exception as e:
            logger.warning(f"Failed to load cache from disk: {e}")
    
    def _save_to_disk(self) -> None:
        """保存缓存到磁盘"""
        if not self.persist_dir:
            return
        
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.persist_dir / "llm_cache.json"
        
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(dict(self._cache), f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save cache to disk: {e}")
    
    def __len__(self) -> int:
        return len(self._cache)
    
    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


class LLMService:
    """
    统一的 LLM 调用服务层
    
    提供：
    - 自动重试机制（指数退避）
    - 响应缓存（LRU + TTL）
    - 速率限制（令牌桶）
    - 批量调用（自动并发控制）
    - 流式输出支持
    - 统一的错误处理
    
    使用示例:
        # 创建服务
        service = LLMService(chat_agent)
        
        # 单次调用
        response = await service.call("Hello, world!")
        
        # 批量调用
        responses = await service.batch_call(["Q1", "Q2", "Q3"])
        
        # 带缓存键的调用（用于确定性缓存）
        response = await service.call(prompt, cache_key="my_custom_key")
    """
    
    def __init__(
        self,
        chat_agent: Any,
        config: Optional[LLMServiceConfig] = None
    ):
        """
        初始化 LLM 服务
        
        Args:
            chat_agent: ChatAgent 实例
            config: 服务配置
        """
        self.chat_agent = chat_agent
        self.config = config or LLMServiceConfig()
        
        # 初始化速率限制器
        self.rate_limiter = RateLimiter(
            max_calls=self.config.rate_limit_calls,
            period=self.config.rate_limit_period
        )
        
        # 初始化缓存
        self.cache: Optional[LRUCache] = None
        if self.config.enable_cache:
            self.cache = LRUCache(
                max_size=self.config.cache_max_size,
                ttl=self.config.cache_ttl,
                persist_dir=self.config.cache_dir
            )
        
        # 统计信息
        self._stats = {
            "total_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "retries": 0,
            "errors": 0,
        }
        self._stats_lock = threading.Lock()
    
    def _hash_prompt(self, prompt: str, **kwargs) -> str:
        """
        计算 prompt 的哈希值（用于缓存键）
        
        Args:
            prompt: 提示词
            **kwargs: 其他影响结果的参数
            
        Returns:
            哈希字符串
        """
        # 包含影响结果的参数
        cache_params = {
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.config.default_temperature),
            "model": kwargs.get("model", self.config.default_model),
        }
        
        content = json.dumps(cache_params, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _update_stats(self, **updates) -> None:
        """更新统计信息"""
        with self._stats_lock:
            for key, value in updates.items():
                if key in self._stats:
                    self._stats[key] += value
    
    @property
    def stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._stats_lock:
            return dict(self._stats)
    
    async def call(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        model: Optional[str] = None,
        cache_key: Optional[str] = None,
        skip_cache: bool = False,
        **kwargs
    ) -> str:
        """
        调用 LLM（带缓存、重试、速率限制）
        
        Args:
            prompt: 提示词
            temperature: 温度参数
            timeout: 超时时间
            model: 模型名称
            cache_key: 自定义缓存键（可选）
            skip_cache: 是否跳过缓存
            **kwargs: 其他参数传递给 chat_agent
            
        Returns:
            LLM 响应文本
            
        Raises:
            Exception: 所有重试失败后抛出最后一个异常
        """
        self._update_stats(total_calls=1)
        
        # 设置默认值
        temperature = temperature if temperature is not None else self.config.default_temperature
        timeout = timeout if timeout is not None else self.config.default_timeout
        model = model or self.config.default_model
        
        # 计算缓存键
        if cache_key is None:
            cache_key = self._hash_prompt(prompt, temperature=temperature, model=model)
        
        # 检查缓存
        if self.cache and not skip_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                self._update_stats(cache_hits=1)
                logger.debug(f"Cache hit for key: {cache_key[:8]}...")
                return cached
            self._update_stats(cache_misses=1)
        
        # 速率限制
        await self.rate_limiter.acquire()
        
        # 重试逻辑
        last_exception = None
        for attempt in range(self.config.max_retries):
            try:
                # 调用 LLM
                call_kwargs = {
                    "temperature": temperature,
                    "timeout": timeout,
                    **kwargs
                }
                if model:
                    call_kwargs["model"] = model
                
                # 检查是否支持异步调用
                if hasattr(self.chat_agent, "async_remote_chat"):
                    response = await self.chat_agent.async_remote_chat(
                        text_content=prompt,
                        **call_kwargs
                    )
                else:
                    # 在线程池中运行同步调用
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.chat_agent.remote_chat(prompt, **call_kwargs)
                    )
                
                # 缓存结果
                if self.cache and not skip_cache:
                    self.cache.set(cache_key, response)
                
                return response
                
            except Exception as e:
                last_exception = e
                self._update_stats(retries=1)
                
                if attempt < self.config.max_retries - 1:
                    # 计算退避延迟
                    delay = min(
                        self.config.retry_base_delay * (2 ** attempt),
                        self.config.retry_max_delay
                    )
                    logger.warning(
                        f"LLM call failed (attempt {attempt + 1}/{self.config.max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"LLM call failed after {self.config.max_retries} attempts: {e}")
        
        self._update_stats(errors=1)
        raise last_exception
    
    async def batch_call(
        self,
        prompts: List[str],
        *,
        max_concurrency: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        model: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs
    ) -> List[Union[str, Exception]]:
        """
        批量调用 LLM（自动并发控制）
        
        Args:
            prompts: 提示词列表
            max_concurrency: 最大并发数
            temperature: 温度参数
            timeout: 超时时间
            model: 模型名称
            progress_callback: 进度回调函数 (completed, total)
            **kwargs: 其他参数
            
        Returns:
            响应列表（与输入顺序对应，失败的返回 Exception）
        """
        if not prompts:
            return []
        
        max_concurrency = max_concurrency or self.config.default_max_concurrency
        semaphore = asyncio.Semaphore(max_concurrency)
        completed = 0
        completed_lock = asyncio.Lock()
        
        async def call_with_semaphore(prompt: str, index: int) -> tuple[int, Union[str, Exception]]:
            nonlocal completed
            async with semaphore:
                try:
                    result = await self.call(
                        prompt,
                        temperature=temperature,
                        timeout=timeout,
                        model=model,
                        **kwargs
                    )
                    return index, result
                except Exception as e:
                    return index, e
                finally:
                    async with completed_lock:
                        completed += 1
                        if progress_callback:
                            progress_callback(completed, len(prompts))
        
        # 创建所有任务
        tasks = [
            call_with_semaphore(prompt, i)
            for i, prompt in enumerate(prompts)
        ]
        
        # 并发执行
        results_with_index = await asyncio.gather(*tasks)
        
        # 按原始顺序排列结果
        results = [None] * len(prompts)
        for index, result in results_with_index:
            results[index] = result
        
        return results
    
    async def stream_call(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        流式调用 LLM
        
        Args:
            prompt: 提示词
            temperature: 温度参数
            timeout: 超时时间
            model: 模型名称
            **kwargs: 其他参数
            
        Yields:
            响应文本片段
        """
        self._update_stats(total_calls=1)
        
        # 设置默认值
        temperature = temperature if temperature is not None else self.config.default_temperature
        timeout = timeout if timeout is not None else self.config.default_timeout
        model = model or self.config.default_model
        
        # 速率限制
        await self.rate_limiter.acquire()
        
        # 检查是否支持流式调用
        if hasattr(self.chat_agent, "stream_chat"):
            call_kwargs = {
                "temperature": temperature,
                "timeout": timeout,
                **kwargs
            }
            if model:
                call_kwargs["model"] = model
            
            async for chunk in self.chat_agent.stream_chat(prompt, **call_kwargs):
                yield chunk
        else:
            # 不支持流式，回退到普通调用
            response = await self.call(
                prompt,
                temperature=temperature,
                timeout=timeout,
                model=model,
                skip_cache=True,  # 流式调用不缓存
                **kwargs
            )
            yield response
    
    def call_sync(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        同步调用 LLM（用于非异步上下文）
        
        Args:
            prompt: 提示词
            temperature: 温度参数
            timeout: 超时时间
            model: 模型名称
            **kwargs: 其他参数
            
        Returns:
            LLM 响应文本
        """
        try:
            loop = asyncio.get_running_loop()
            # 如果已经在事件循环中，使用线程池
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.call(
                        prompt,
                        temperature=temperature,
                        timeout=timeout,
                        model=model,
                        **kwargs
                    )
                )
                return future.result()
        except RuntimeError:
            # 没有运行中的事件循环，直接运行
            return asyncio.run(
                self.call(
                    prompt,
                    temperature=temperature,
                    timeout=timeout,
                    model=model,
                    **kwargs
                )
            )
    
    def clear_cache(self) -> None:
        """清空缓存"""
        if self.cache:
            self.cache.clear()
            logger.info("LLM cache cleared")
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        with self._stats_lock:
            for key in self._stats:
                self._stats[key] = 0
    
    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        if not self.cache:
            return {"enabled": False}
        
        return {
            "enabled": True,
            "size": len(self.cache),
            "max_size": self.cache.max_size,
            "ttl": self.cache.ttl,
            "persist_dir": str(self.cache.persist_dir) if self.cache.persist_dir else None,
        }


# 便捷函数：创建带默认配置的 LLM 服务
def create_llm_service(
    chat_agent: Any,
    enable_cache: bool = True,
    cache_dir: Optional[Path] = None,
    max_concurrency: int = 50,
    rate_limit_calls: int = 100,
) -> LLMService:
    """
    创建 LLM 服务的便捷函数
    
    Args:
        chat_agent: ChatAgent 实例
        enable_cache: 是否启用缓存
        cache_dir: 缓存目录
        max_concurrency: 最大并发数
        rate_limit_calls: 速率限制
        
    Returns:
        LLMService 实例
    """
    config = LLMServiceConfig(
        enable_cache=enable_cache,
        cache_dir=cache_dir,
        default_max_concurrency=max_concurrency,
        rate_limit_calls=rate_limit_calls,
    )
    return LLMService(chat_agent, config)