"""
Dependency Injection Container
==============================

组件容器和依赖注入系统，用于：
- 管理 Pipeline 组件的生命周期
- 支持组件替换和测试
- 延迟初始化
- 单例管理

使用方法:
    # 创建容器
    container = ComponentContainer()
    
    # 注册组件
    container.register("paper_collector", EnhancedPaperCollector, chat_agent=agent)
    
    # 获取组件（延迟初始化）
    collector = container.get("paper_collector")
    
    # 使用预配置的组件集
    components = PipelineComponents.create_default(chat_agent)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Optional,
    Type,
    TypeVar,
    Union,
)
import threading
from functools import wraps

from loguru import logger


T = TypeVar("T")


class ComponentNotFoundError(Exception):
    """组件未找到异常"""
    pass


class ComponentInitError(Exception):
    """组件初始化异常"""
    pass


@dataclass
class ComponentRegistration:
    """组件注册信息"""
    name: str
    factory: Union[Type, Callable[..., Any]]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    singleton: bool = True
    lazy: bool = True
    instance: Optional[Any] = None
    initialized: bool = False


class ComponentContainer:
    """
    组件容器
    
    管理 Pipeline 组件的注册、初始化和获取。
    支持：
    - 延迟初始化（lazy initialization）
    - 单例模式
    - 依赖注入
    - 组件替换
    
    使用示例:
        container = ComponentContainer()
        
        # 注册组件类
        container.register("collector", EnhancedPaperCollector, chat_agent=agent)
        
        # 注册工厂函数
        container.register("service", lambda: MyService(), singleton=True)
        
        # 注册已有实例
        container.register_instance("config", my_config)
        
        # 获取组件
        collector = container.get("collector")
    """
    
    def __init__(self):
        """初始化容器"""
        self._registrations: Dict[str, ComponentRegistration] = {}
        self._lock = threading.RLock()
    
    def register(
        self,
        name: str,
        factory: Union[Type, Callable[..., Any]],
        *args,
        singleton: bool = True,
        lazy: bool = True,
        **kwargs
    ) -> "ComponentContainer":
        """
        注册组件
        
        Args:
            name: 组件名称
            factory: 组件类或工厂函数
            *args: 初始化位置参数
            singleton: 是否单例
            lazy: 是否延迟初始化
            **kwargs: 初始化关键字参数
            
        Returns:
            self（支持链式调用）
        """
        with self._lock:
            registration = ComponentRegistration(
                name=name,
                factory=factory,
                args=args,
                kwargs=kwargs,
                singleton=singleton,
                lazy=lazy,
            )
            
            self._registrations[name] = registration
            
            # 如果不是延迟初始化，立即创建实例
            if not lazy:
                self._initialize_component(registration)
            
            logger.debug(f"Registered component: {name} (singleton={singleton}, lazy={lazy})")
            
        return self
    
    def register_instance(self, name: str, instance: Any) -> "ComponentContainer":
        """
        注册已有实例
        
        Args:
            name: 组件名称
            instance: 组件实例
            
        Returns:
            self（支持链式调用）
        """
        with self._lock:
            registration = ComponentRegistration(
                name=name,
                factory=lambda: instance,
                singleton=True,
                lazy=False,
                instance=instance,
                initialized=True,
            )
            self._registrations[name] = registration
            logger.debug(f"Registered instance: {name}")
            
        return self
    
    def get(self, name: str) -> Any:
        """
        获取组件
        
        Args:
            name: 组件名称
            
        Returns:
            组件实例
            
        Raises:
            ComponentNotFoundError: 组件未注册
            ComponentInitError: 组件初始化失败
        """
        with self._lock:
            if name not in self._registrations:
                raise ComponentNotFoundError(f"Component not found: {name}")
            
            registration = self._registrations[name]
            
            # 如果是单例且已初始化，直接返回
            if registration.singleton and registration.initialized:
                return registration.instance
            
            # 初始化组件
            return self._initialize_component(registration)
    
    def get_optional(self, name: str, default: T = None) -> Optional[T]:
        """
        获取组件（可选）
        
        Args:
            name: 组件名称
            default: 默认值
            
        Returns:
            组件实例或默认值
        """
        try:
            return self.get(name)
        except (ComponentNotFoundError, ComponentInitError):
            return default
    
    def has(self, name: str) -> bool:
        """
        检查组件是否已注册
        
        Args:
            name: 组件名称
            
        Returns:
            是否已注册
        """
        return name in self._registrations
    
    def _initialize_component(self, registration: ComponentRegistration) -> Any:
        """
        初始化组件
        
        Args:
            registration: 组件注册信息
            
        Returns:
            组件实例
        """
        try:
            # 解析依赖（kwargs 中的 $ref:xxx 格式）
            resolved_kwargs = self._resolve_dependencies(registration.kwargs)
            
            # 创建实例
            instance = registration.factory(*registration.args, **resolved_kwargs)
            
            # 如果是单例，保存实例
            if registration.singleton:
                registration.instance = instance
                registration.initialized = True
            
            logger.debug(f"Initialized component: {registration.name}")
            return instance
            
        except Exception as e:
            raise ComponentInitError(
                f"Failed to initialize component '{registration.name}': {e}"
            ) from e
    
    def _resolve_dependencies(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析依赖引用
        
        支持 $ref:component_name 格式的依赖引用
        
        Args:
            kwargs: 原始参数
            
        Returns:
            解析后的参数
        """
        resolved = {}
        for key, value in kwargs.items():
            if isinstance(value, str) and value.startswith("$ref:"):
                # 解析依赖引用
                ref_name = value[5:]
                resolved[key] = self.get(ref_name)
            else:
                resolved[key] = value
        return resolved
    
    def reset(self, name: Optional[str] = None) -> None:
        """
        重置组件（清除实例，下次获取时重新初始化）
        
        Args:
            name: 组件名称，如果为 None 则重置所有
        """
        with self._lock:
            if name:
                if name in self._registrations:
                    self._registrations[name].instance = None
                    self._registrations[name].initialized = False
            else:
                for reg in self._registrations.values():
                    reg.instance = None
                    reg.initialized = False
    
    def unregister(self, name: str) -> bool:
        """
        取消注册组件
        
        Args:
            name: 组件名称
            
        Returns:
            是否成功取消
        """
        with self._lock:
            if name in self._registrations:
                del self._registrations[name]
                return True
            return False
    
    def list_components(self) -> Dict[str, Dict[str, Any]]:
        """
        列出所有注册的组件
        
        Returns:
            组件信息字典
        """
        with self._lock:
            return {
                name: {
                    "singleton": reg.singleton,
                    "lazy": reg.lazy,
                    "initialized": reg.initialized,
                    "factory": str(reg.factory),
                }
                for name, reg in self._registrations.items()
            }


@dataclass
class PipelineComponents:
    """
    Pipeline 组件集合
    
    封装 Pipeline 所需的所有组件，支持：
    - 默认组件创建
    - 自定义组件注入
    - 组件替换
    
    使用示例:
        # 使用默认组件
        components = PipelineComponents.create_default(chat_agent)
        
        # 自定义部分组件
        components = PipelineComponents.create_default(
            chat_agent,
            paper_collector=MyCustomCollector()
        )
        
        # 完全自定义
        components = PipelineComponents(
            paper_collector=my_collector,
            outline_generator=my_generator,
            ...
        )
    """
    
    # 核心组件
    paper_collector: Optional[Any] = None
    outline_generator: Optional[Any] = None
    content_generator: Optional[Any] = None
    evaluator: Optional[Any] = None
    latex_generator: Optional[Any] = None
    
    # 可选组件
    post_refiner: Optional[Any] = None
    global_reflector: Optional[Any] = None
    evolutionary_analyzer: Optional[Any] = None
    critical_analyzer: Optional[Any] = None
    
    # 服务组件
    llm_service: Optional[Any] = None
    task_queue: Optional[Any] = None
    state_store: Optional[Any] = None
    
    @classmethod
    def create_default(
        cls,
        chat_agent: Any,
        task_id: str = "",
        output_dir: Optional[Path] = None,
        **overrides
    ) -> "PipelineComponents":
        """
        创建默认组件集
        
        Args:
            chat_agent: ChatAgent 实例
            task_id: 任务 ID
            output_dir: 输出目录
            **overrides: 覆盖的组件
            
        Returns:
            PipelineComponents 实例
        """
        from mekg.src.core.llm_service import LLMService, LLMServiceConfig
        
        # 创建 LLM 服务
        llm_service = overrides.get("llm_service")
        if llm_service is None and chat_agent:
            llm_config = LLMServiceConfig(
                enable_cache=True,
                cache_dir=output_dir / ".cache" if output_dir else None,
            )
            llm_service = LLMService(chat_agent, llm_config)
        
        # 延迟导入组件（避免循环导入）
        paper_collector = overrides.get("paper_collector")
        if paper_collector is None:
            try:
                from mekg.src.processing.enhanced_paper_collector import EnhancedPaperCollector
                paper_collector = EnhancedPaperCollector(chat_agent=chat_agent)
            except ImportError:
                logger.warning("EnhancedPaperCollector not available")
        
        outline_generator = overrides.get("outline_generator")
        if outline_generator is None:
            try:
                from mekg.src.survey.outline_generator import MEKGOutlineGenerator
                outline_generator = MEKGOutlineGenerator(chat_agent=chat_agent)
            except ImportError:
                logger.warning("MEKGOutlineGenerator not available")
        
        content_generator = overrides.get("content_generator")
        if content_generator is None:
            try:
                from mekg.src.survey.content_generator import MEKGContentGenerator
                content_generator = MEKGContentGenerator(chat_agent=chat_agent)
            except ImportError:
                logger.warning("MEKGContentGenerator not available")
        
        evaluator = overrides.get("evaluator")
        # evaluator 需要 mekg_data，延迟创建
        
        latex_generator = overrides.get("latex_generator")
        if latex_generator is None and task_id:
            try:
                from src.models.generator.latex_generator import LatexGenerator
                latex_generator = LatexGenerator(task_id=task_id)
            except ImportError:
                logger.warning("LatexGenerator not available")
        
        # 可选组件
        post_refiner = overrides.get("post_refiner")
        if post_refiner is None and task_id:
            try:
                from src.models.post_refine import PostRefiner
                post_refiner = PostRefiner(
                    task_id=task_id,
                    chat_agent=chat_agent,
                    enable_dynamic_visuals=True,
                    enable_reference_images=True
                )
            except ImportError:
                logger.warning("PostRefiner not available")
        
        global_reflector = overrides.get("global_reflector")
        if global_reflector is None:
            try:
                from src.modules.post_refine.global_reflector import GlobalReflector
                global_reflector = GlobalReflector(chat_agent=chat_agent)
            except ImportError:
                pass
        
        evolutionary_analyzer = overrides.get("evolutionary_analyzer")
        if evolutionary_analyzer is None:
            try:
                from src.modules.analysis.evolutionary_analyzer import EvolutionaryAnalyzer
                evolutionary_analyzer = EvolutionaryAnalyzer(chat_agent=chat_agent)
            except ImportError:
                pass
        
        critical_analyzer = overrides.get("critical_analyzer")
        if critical_analyzer is None:
            try:
                from src.modules.post_refine.critical_analysis_refiner import CriticalAnalysisRefiner
                critical_analyzer = CriticalAnalysisRefiner(chat_agent=chat_agent)
            except ImportError:
                pass
        
        # 任务队列和状态存储
        task_queue = overrides.get("task_queue")
        state_store = overrides.get("state_store")
        
        return cls(
            paper_collector=paper_collector,
            outline_generator=outline_generator,
            content_generator=content_generator,
            evaluator=evaluator,
            latex_generator=latex_generator,
            post_refiner=post_refiner,
            global_reflector=global_reflector,
            evolutionary_analyzer=evolutionary_analyzer,
            critical_analyzer=critical_analyzer,
            llm_service=llm_service,
            task_queue=task_queue,
            state_store=state_store,
        )
    
    def get_component(self, name: str) -> Optional[Any]:
        """
        获取组件
        
        Args:
            name: 组件名称
            
        Returns:
            组件实例或 None
        """
        return getattr(self, name, None)
    
    def set_component(self, name: str, component: Any) -> None:
        """
        设置组件
        
        Args:
            name: 组件名称
            component: 组件实例
        """
        if hasattr(self, name):
            setattr(self, name, component)
        else:
            raise ValueError(f"Unknown component: {name}")
    
    def list_available(self) -> Dict[str, bool]:
        """
        列出组件可用性
        
        Returns:
            组件名称到可用性的映射
        """
        return {
            "paper_collector": self.paper_collector is not None,
            "outline_generator": self.outline_generator is not None,
            "content_generator": self.content_generator is not None,
            "evaluator": self.evaluator is not None,
            "latex_generator": self.latex_generator is not None,
            "post_refiner": self.post_refiner is not None,
            "global_reflector": self.global_reflector is not None,
            "evolutionary_analyzer": self.evolutionary_analyzer is not None,
            "critical_analyzer": self.critical_analyzer is not None,
            "llm_service": self.llm_service is not None,
            "task_queue": self.task_queue is not None,
            "state_store": self.state_store is not None,
        }


# ============================================================================
# 依赖注入装饰器
# ============================================================================

def inject(*dependencies: str):
    """
    依赖注入装饰器
    
    自动从全局容器注入依赖
    
    使用示例:
        @inject("llm_service", "paper_collector")
        def my_function(llm_service, paper_collector, other_arg):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 从全局容器获取依赖
            container = get_global_container()
            for dep in dependencies:
                if dep not in kwargs:
                    kwargs[dep] = container.get(dep)
            return func(*args, **kwargs)
        return wrapper
    return decorator


# 全局容器实例
_global_container: Optional[ComponentContainer] = None
_container_lock = threading.Lock()


def get_global_container() -> ComponentContainer:
    """获取全局容器"""
    global _global_container
    with _container_lock:
        if _global_container is None:
            _global_container = ComponentContainer()
        return _global_container


def set_global_container(container: ComponentContainer) -> None:
    """设置全局容器"""
    global _global_container
    with _container_lock:
        _global_container = container


def reset_global_container() -> None:
    """重置全局容器"""
    global _global_container
    with _container_lock:
        _global_container = None