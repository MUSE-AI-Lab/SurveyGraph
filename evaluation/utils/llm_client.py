"""
LLM客户端
=========

提供LLM调用功能，支持多模型评测和结果融合。

多模型评测说明：
- 支持同时调用多个 T2T 模型进行评测
- 支持多种融合策略：多数投票、平均、加权平均、中位数等
- 可视化评测仍使用单一多模态模型
"""

import json
import re
import logging
import statistics
from typing import Dict, Optional, Any, List, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import os
import time

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from evaluation.config import (
    REMOTE_URL, API_KEY, DEFAULT_MODEL,
    TEMPERATURE, MAX_RETRIES, TIMEOUT,
    T2T_EVALUATION_MODELS, MODEL_WEIGHTS,
    FusionStrategy, DEFAULT_FUSION_STRATEGY,
    MULTI_MODEL_TIMEOUT, MIN_MODELS_FOR_FUSION
)

# 多模型评测专用配置
MULTI_MODEL_MAX_RETRIES = 1  # 多模型评测时每个模型最多重试1次（不要阻塞其他模型）
MULTI_MODEL_OVERALL_TIMEOUT = 90  # 多模型评测整体超时时间（秒），超过这个时间就不等待慢的模型了


logger = logging.getLogger(__name__)


class LLMClient:
    """LLM客户端类"""
    
    def __init__(
        self,
        api_url: str = REMOTE_URL,
        api_key: str = API_KEY,
        model: str = DEFAULT_MODEL,
        temperature: float = TEMPERATURE,
        max_retries: int = MAX_RETRIES,
        timeout: int = TIMEOUT
    ):
        """
        初始化LLM客户端
        
        Args:
            api_url: API地址
            api_key: API密钥
            model: 模型名称
            temperature: 温度参数
            max_retries: 最大重试次数
            timeout: 超时时间
        """
        self.api_url = api_url
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout
        
        if not HAS_OPENAI:
            logger.warning("openai库未安装，LLM功能将不可用")
            self.client = None
        elif not self.api_key:
            logger.warning("API_KEY未设置，LLM功能将不可用")
            self.client = None
        else:
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_url
            )
    
    def chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        response_format: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_retries: Optional[int] = None
    ) -> str:
        """
        调用LLM进行对话
        
        Args:
            prompt: 用户提示
            model: 模型名称（可选）
            temperature: 温度参数（可选）
            response_format: 响应格式，可选"json_object"
            system_prompt: 系统提示（可选）
            max_retries: 最大重试次数（可选，默认使用实例配置）
            
        Returns:
            LLM响应文本
        """
        if not self.client:
            raise RuntimeError("LLM客户端未初始化，请检查API配置")
        
        model = model or self.model
        temperature = temperature if temperature is not None else self.temperature
        retries = max_retries if max_retries is not None else self.max_retries
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        for attempt in range(retries):
            try:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "timeout": self.timeout
                }
                
                if response_format == "json_object":
                    kwargs["response_format"] = {"type": "json_object"}
                
                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
                
            except Exception as e:
                logger.warning(f"LLM调用失败 (尝试 {attempt + 1}/{retries}): {e}")
                if attempt == retries - 1:
                    raise RuntimeError(f"LLM调用失败，已重试{retries}次: {e}")
        
        return ""
    
    def chat_json(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
        max_json_retries: int = 2
    ) -> Dict:
        """
        调用LLM并返回JSON响应，支持JSON解析失败重试
        
        Args:
            prompt: 用户提示
            model: 模型名称（可选）
            temperature: 温度参数（可选）
            system_prompt: 系统提示（可选）
            max_json_retries: JSON解析失败最大重试次数
            
        Returns:
            解析后的JSON对象
        """
        for attempt in range(max_json_retries + 1):
            response = self.chat(
                prompt=prompt,
                model=model,
                temperature=temperature,
                response_format="json_object",
                system_prompt=system_prompt
            )
            result = parse_json_response(response)
            
            if result:  # 解析成功
                return result
            
            if attempt < max_json_retries:
                logger.warning(f"JSON解析失败，正在重试 ({attempt + 1}/{max_json_retries})...")
                # 添加提示让LLM输出更简洁的JSON
                prompt = prompt + "\n\n**IMPORTANT**: Output ONLY valid JSON. Keep the 'analysis' field very brief (under 50 words). Do not use markdown code blocks."
        
        return {}


# 全局LLM客户端实例
_default_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    """获取默认LLM客户端"""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def set_default_client(client: LLMClient):
    """设置默认LLM客户端"""
    global _default_client
    _default_client = client


def call_llm(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = TEMPERATURE,
    max_retries: int = MAX_RETRIES,
    response_format: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> str:
    """
    调用LLM API（便捷函数）
    
    Args:
        prompt: 提示词
        model: 模型名称
        temperature: 温度参数
        max_retries: 最大重试次数
        response_format: 响应格式，可选"json_object"
        system_prompt: 系统提示（可选）
        
    Returns:
        LLM响应文本
    """
    client = get_default_client()
    return client.chat(
        prompt=prompt,
        model=model,
        temperature=temperature,
        response_format=response_format,
        system_prompt=system_prompt,
        max_retries=max_retries
    )


def call_llm_json(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = TEMPERATURE,
    system_prompt: Optional[str] = None,
    max_json_retries: int = 2
) -> Dict:
    """
    调用LLM API并返回JSON（便捷函数，支持JSON解析失败重试）
    
    Args:
        prompt: 提示词
        model: 模型名称
        temperature: 温度参数
        system_prompt: 系统提示（可选）
        max_json_retries: JSON解析失败最大重试次数
        
    Returns:
        解析后的JSON对象
    """
    client = get_default_client()
    return client.chat_json(
        prompt=prompt,
        model=model,
        temperature=temperature,
        system_prompt=system_prompt,
        max_json_retries=max_json_retries
    )


def parse_json_response(response: str) -> Dict:
    """
    解析LLM返回的JSON响应
    
    Args:
        response: LLM响应文本
        
    Returns:
        解析后的JSON对象
    """
    if not response:
        return {}
    
    try:
        # 尝试直接解析
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # 尝试提取JSON代码块
    json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 尝试提取花括号内容
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    logger.error(f"无法解析JSON响应: {response[:200]}")
    return {}


# ==================== 评测专用Prompt模板 ====================

ATOMIC_FACT_EXTRACTION_PROMPT = """You are an expert in scientific writing and information extraction. Your task is to decompose a complex sentence from a survey into a list of simple, self-contained, verifiable "atomic facts".

**Original Sentence**:
"{sentence}"

**Instructions**:
1. Read the original sentence carefully.
2. Identify all distinct claims or pieces of information within the sentence.
3. Rewrite each claim as a standalone, simple statement. This is an "atomic fact".
4. Each atomic fact should be independently verifiable against a source.
5. Do not lose any information from the original sentence, but also do not add new information.

**Output Format (JSON)**:
{{
    "atomic_facts": [
        "First atomic fact.",
        "Second atomic fact.",
        "Third atomic fact."
    ]
}}
"""


CLAIM_VERIFICATION_PROMPT = """You are a meticulous academic fact-checker. Your task is to verify if a claim from a survey is factually supported by a specific quote from its cited source.

**Claim from Survey**:
"{claim}"

**Cited Paper Title**:
"{paper_title}"

**Source Text from Cited Paper**:
---
{source_text}
---

**Instructions**:
1. Carefully read the claim and the source text.
2. Determine if the source text contains direct evidence that supports the claim.
3. If supported, extract the most relevant sentence or phrase from the source text.

**Output Format (JSON)**:
{{
    "is_supported": true/false,
    "confidence": 0.0-1.0,
    "supporting_quote": "If supported, provide the exact quote. Otherwise, empty string.",
    "explanation": "Brief justification for your decision."
}}
"""


CONTENT_QUALITY_PROMPT = """You are an expert academic reviewer evaluating the quality of a survey paper.

**Survey Content Sample**:
---
{content_sample}
---

**Evaluation Criteria**:
1. Clarity: Is the writing clear and easy to understand?
2. Coherence: Is the content logically organized and well-connected?
3. Depth: Does it provide sufficient technical depth?
4. Objectivity: Is the analysis balanced and objective?

**Output Format (JSON)**:
{{
    "clarity_score": 0.0-1.0,
    "coherence_score": 0.0-1.0,
    "depth_score": 0.0-1.0,
    "objectivity_score": 0.0-1.0,
    "overall_quality_score": 0.0-1.0,
    "analysis": "Brief analysis of the content quality."
}}
"""


STRUCTURE_EVALUATION_PROMPT = """You are an academic writing expert evaluating the structure of a survey paper.

**Survey Outline**:
{outline}

**Evaluation Criteria**:
1. Completeness: Does it have all necessary sections (intro, background, main content, conclusion)?
2. Logical Flow: Is the structure logically organized?
3. Balance: Are sections appropriately balanced in scope?
4. Hierarchy: Is the hierarchy clear and appropriate?

**Output Format (JSON)**:
{{
    "completeness_score": 0.0-1.0,
    "logical_flow_score": 0.0-1.0,
    "balance_score": 0.0-1.0,
    "hierarchy_score": 0.0-1.0,
    "overall_structure_score": 0.0-1.0,
    "analysis": "Brief analysis of the structure."
}}
"""


ETHICS_EVALUATION_PROMPT = """You are a senior academic reviewer evaluating the ethical considerations in a **technical survey paper**.

**Important Context**:
This is a TECHNICAL SURVEY paper, not a position paper or ethics-focused paper. Technical surveys primarily aim to summarize and organize existing research. While ethical discussions are valuable, they are NOT mandatory for a high-quality technical survey. Please use a LENIENT scoring standard.

**Survey Content Excerpts**:
---
{content_excerpts}
---

**Evaluation Criteria** (with lenient standards for technical surveys):

1. Societal Impact (Base score: 0.5 for technical surveys)
   - If the paper discusses ANY limitations, challenges, or potential issues → score 0.6-0.8
   - If the paper has explicit ethics/impact discussion → score 0.8-1.0
   - Only score below 0.5 if the paper makes harmful claims without caveats

2. Fairness (Base score: 0.5 for technical surveys)
   - If the paper mentions ANY form of evaluation or comparison → score 0.6-0.7
   - If the paper discusses bias, fairness, or diversity → score 0.8-1.0
   - Only score below 0.5 if the paper shows clear bias in its analysis

3. Responsible Scholarship (Base score: 0.6 for technical surveys)
   - Proper citations and acknowledgment of prior work → score 0.7-0.8
   - Discussion of limitations or future work → score 0.8-1.0

**Output Format (JSON)**:
{{
    "societal_impact_score": 0.5-1.0,
    "fairness_score": 0.5-1.0,
    "responsible_scholarship_score": 0.6-1.0,
    "overall_ethics_score": 0.5-1.0,
    "analysis": "Brief analysis. Remember: this is a technical survey, so ethical depth is a bonus, not a requirement."
}}
"""


MEDIA_QUALITY_PROMPT = """Evaluate this {media_type} from a survey paper.

Caption: "{caption}"
Context: "{context}"

Rate each 0.0-1.0: clarity, informativeness, relevance, design, overall_quality.

Output ONLY valid JSON (no markdown):
{{"clarity_score":0.8,"informativeness_score":0.7,"relevance_score":0.9,"design_score":0.8,"overall_quality_score":0.8,"analysis":"Brief reason"}}
"""


GENERAL_FACTUALNESS_PROMPT = """You are a rigorous fact-checker. Your task is to verify the factual accuracy of a non-cited claim from a survey paper.

**Claim**:
"{claim}"

**Context**: The claim appears in a survey about "{topic}". It does not have a direct citation.

**Instructions**:
1. Analyze the claim. Is it a common knowledge statement, a summary, or a specific assertion?
2. Based on your knowledge, determine if the claim is factually correct.
3. Provide your assessment.

**Output Format (JSON)**:
{{
    "is_factually_correct": true/false/null,
    "confidence": 0.0-1.0,
    "verification_summary": "Brief summary of your findings."
}}
"""


# ==================== 多模型评测功能 ====================

class MultiModelEvaluator:
    """
    多模型评测器
    
    支持同时调用多个模型进行评测，并融合结果。
    """
    
    def __init__(
        self,
        models: List[str] = None,
        api_url: str = REMOTE_URL,
        api_key: str = API_KEY,
        temperature: float = TEMPERATURE,
        timeout: int = MULTI_MODEL_TIMEOUT,
        model_weights: Dict[str, float] = None,
        fusion_strategy: str = DEFAULT_FUSION_STRATEGY
    ):
        """
        初始化多模型评测器
        
        Args:
            models: 模型列表
            api_url: API地址
            api_key: API密钥
            temperature: 温度参数
            timeout: 超时时间
            model_weights: 模型权重（用于加权融合）
            fusion_strategy: 融合策略
        """
        self.models = models or T2T_EVALUATION_MODELS
        self.api_url = api_url
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.temperature = temperature
        self.timeout = timeout
        self.model_weights = model_weights or MODEL_WEIGHTS
        self.fusion_strategy = fusion_strategy
        
        # 为每个模型创建客户端
        self.clients: Dict[str, LLMClient] = {}
        if HAS_OPENAI and self.api_key:
            for model in self.models:
                self.clients[model] = LLMClient(
                    api_url=self.api_url,
                    api_key=self.api_key,
                    model=model,
                    temperature=self.temperature,
                    timeout=self.timeout
                )
    
    def evaluate_with_all_models(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: Optional[str] = "json_object",
        overall_timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        使用所有模型进行评测（真正并行，不等待慢的模型）
        
        Args:
            prompt: 评测提示词
            system_prompt: 系统提示
            response_format: 响应格式
            overall_timeout: 整体超时时间（秒），超过这个时间就不等待还没完成的模型
            
        Returns:
            包含各模型结果和融合结果的字典
        """
        if not self.clients:
            logger.warning("没有可用的模型客户端，回退到默认客户端")
            return {
                "model_results": {},
                "fused_result": call_llm_json(prompt, system_prompt=system_prompt),
                "fusion_strategy": "fallback"
            }
        
        model_results = {}
        overall_timeout = overall_timeout or MULTI_MODEL_OVERALL_TIMEOUT
        start_time = time.time()
        
        # 并发调用所有模型
        with ThreadPoolExecutor(max_workers=len(self.models)) as executor:
            future_to_model = {
                executor.submit(
                    self._call_single_model,
                    model,
                    prompt,
                    system_prompt,
                    response_format
                ): model
                for model in self.models
            }
            
            # 使用 as_completed 但设置整体超时
            # 一旦有足够的模型完成或超时，就停止等待
            pending_futures = set(future_to_model.keys())
            
            while pending_futures:
                # 计算剩余时间
                elapsed = time.time() - start_time
                remaining_timeout = max(0.1, overall_timeout - elapsed)
                
                # 如果已经超时，停止等待
                if elapsed >= overall_timeout:
                    logger.warning(f"多模型评测整体超时 ({overall_timeout}秒)，已完成 {len(model_results)} 个模型")
                    # 取消还在运行的任务
                    for future in pending_futures:
                        future.cancel()
                    break
                
                # 如果已经有足够的结果，可以提前结束
                if len(model_results) >= MIN_MODELS_FOR_FUSION:
                    # 再等一小段时间看看有没有更多结果
                    try:
                        for future in as_completed(pending_futures, timeout=min(5.0, remaining_timeout)):
                            model = future_to_model[future]
                            pending_futures.discard(future)
                            try:
                                result = future.result(timeout=0.1)
                                if result:
                                    model_results[model] = result
                                    logger.info(f"✅ 模型 {model} 评测完成")
                            except Exception as e:
                                logger.warning(f"❌ 模型 {model} 评测失败: {e}")
                    except FuturesTimeoutError:
                        # 额外等待时间用完，使用已有结果
                        logger.info(f"已有 {len(model_results)} 个模型完成，不再等待剩余 {len(pending_futures)} 个模型")
                        for future in pending_futures:
                            future.cancel()
                        break
                else:
                    # 还没有足够的结果，继续等待
                    try:
                        # 等待下一个完成的 future
                        done_futures = []
                        for future in as_completed(pending_futures, timeout=remaining_timeout):
                            model = future_to_model[future]
                            pending_futures.discard(future)
                            try:
                                result = future.result(timeout=0.1)
                                if result:
                                    model_results[model] = result
                                    logger.info(f"✅ 模型 {model} 评测完成")
                            except Exception as e:
                                logger.warning(f"❌ 模型 {model} 评测失败: {e}")
                            
                            # 检查是否已经有足够的结果
                            if len(model_results) >= MIN_MODELS_FOR_FUSION:
                                break
                    except FuturesTimeoutError:
                        logger.warning(f"等待模型响应超时，已完成 {len(model_results)} 个模型")
                        for future in pending_futures:
                            future.cancel()
                        break
        
        # 检查是否有足够的结果进行融合
        if len(model_results) < MIN_MODELS_FOR_FUSION:
            logger.warning(f"成功的模型数量 ({len(model_results)}) 少于最小融合数量 ({MIN_MODELS_FOR_FUSION})")
            # 如果有结果，返回第一个；否则返回空
            if model_results:
                first_result = list(model_results.values())[0]
                return {
                    "model_results": model_results,
                    "fused_result": first_result,
                    "fusion_strategy": "single_model_fallback"
                }
            return {
                "model_results": {},
                "fused_result": {},
                "fusion_strategy": "no_results"
            }
        
        # 融合结果
        fused_result = self._fuse_results(model_results)
        
        logger.info(f"多模型评测完成，使用了 {len(model_results)} 个模型: {list(model_results.keys())}")
        
        return {
            "model_results": model_results,
            "fused_result": fused_result,
            "fusion_strategy": self.fusion_strategy,
            "models_used": list(model_results.keys())
        }
    
    def _call_single_model(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str],
        response_format: Optional[str]
    ) -> Optional[Dict]:
        """
        调用单个模型（多模型评测专用，减少重试次数）
        
        在多模型评测场景下，我们不希望一个模型的重试阻塞其他模型，
        所以这里使用较少的重试次数。
        """
        if model not in self.clients:
            return None
        
        client = self.clients[model]
        try:
            if response_format == "json_object":
                # 多模型评测时减少重试次数，避免阻塞
                return client.chat_json(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_json_retries=1  # 从2次减少到1次
                )
            else:
                response = client.chat(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    response_format=response_format,
                    max_retries=MULTI_MODEL_MAX_RETRIES  # 使用多模型专用的重试次数
                )
                return {"response": response}
        except Exception as e:
            logger.warning(f"模型 {model} 调用失败: {e}")
            return None
    
    def _fuse_results(self, model_results: Dict[str, Dict]) -> Dict:
        """
        融合多个模型的结果
        
        Args:
            model_results: 各模型的结果字典
            
        Returns:
            融合后的结果
        """
        if not model_results:
            return {}
        
        # 获取所有结果的键
        all_keys = set()
        for result in model_results.values():
            if isinstance(result, dict):
                all_keys.update(result.keys())
        
        fused = {}
        
        for key in all_keys:
            values = []
            weights = []
            
            for model, result in model_results.items():
                if isinstance(result, dict) and key in result:
                    value = result[key]
                    values.append(value)
                    weights.append(self.model_weights.get(model, 1.0))
            
            if not values:
                continue
            
            # 根据值类型选择融合方法
            fused[key] = self._fuse_values(values, weights, key)
        
        return fused
    
    def _fuse_values(
        self,
        values: List[Any],
        weights: List[float],
        key: str
    ) -> Any:
        """
        融合单个字段的值
        
        Args:
            values: 值列表
            weights: 权重列表
            key: 字段名
            
        Returns:
            融合后的值
        """
        if not values:
            return None
        
        # 检查值类型
        first_value = values[0]
        
        # 数值类型：使用数值融合
        if isinstance(first_value, (int, float)):
            return self._fuse_numeric_values(values, weights)
        
        # 布尔类型：使用多数投票
        if isinstance(first_value, bool):
            return self._fuse_boolean_values(values, weights)
        
        # 字符串类型：选择最长的或第一个
        if isinstance(first_value, str):
            return self._fuse_string_values(values, key)
        
        # 列表类型：合并去重
        if isinstance(first_value, list):
            return self._fuse_list_values(values)
        
        # 其他类型：返回第一个
        return first_value
    
    def _fuse_numeric_values(
        self,
        values: List[Union[int, float]],
        weights: List[float]
    ) -> float:
        """融合数值"""
        # 过滤无效值
        valid_pairs = [
            (v, w) for v, w in zip(values, weights)
            if isinstance(v, (int, float)) and not (isinstance(v, float) and (v != v))  # 排除 NaN
        ]
        
        if not valid_pairs:
            return 0.0
        
        valid_values, valid_weights = zip(*valid_pairs)
        
        if self.fusion_strategy == FusionStrategy.AVERAGE:
            return sum(valid_values) / len(valid_values)
        
        elif self.fusion_strategy == FusionStrategy.WEIGHTED_AVERAGE:
            total_weight = sum(valid_weights)
            if total_weight == 0:
                return sum(valid_values) / len(valid_values)
            return sum(v * w for v, w in valid_pairs) / total_weight
        
        elif self.fusion_strategy == FusionStrategy.MEDIAN:
            return statistics.median(valid_values)
        
        elif self.fusion_strategy == FusionStrategy.MAX_CONFIDENCE:
            # 返回权重最高的模型的值
            max_idx = valid_weights.index(max(valid_weights))
            return valid_values[max_idx]
        
        else:  # 默认使用平均
            return sum(valid_values) / len(valid_values)
    
    def _fuse_boolean_values(
        self,
        values: List[bool],
        weights: List[float]
    ) -> bool:
        """融合布尔值（多数投票）"""
        valid_values = [v for v in values if isinstance(v, bool)]
        if not valid_values:
            return True  # 默认值
        
        if self.fusion_strategy == FusionStrategy.WEIGHTED_AVERAGE:
            # 加权投票
            true_weight = sum(
                w for v, w in zip(values, weights)
                if isinstance(v, bool) and v
            )
            false_weight = sum(
                w for v, w in zip(values, weights)
                if isinstance(v, bool) and not v
            )
            return true_weight >= false_weight
        else:
            # 简单多数投票
            true_count = sum(1 for v in valid_values if v)
            return true_count > len(valid_values) / 2
    
    def _fuse_string_values(self, values: List[str], key: str) -> str:
        """融合字符串值"""
        valid_values = [v for v in values if isinstance(v, str) and v.strip()]
        if not valid_values:
            return ""
        
        # 对于分析类字段，选择最长的
        if "analysis" in key.lower() or "summary" in key.lower():
            return max(valid_values, key=len)
        
        # 其他情况返回第一个非空值
        return valid_values[0]
    
    def _fuse_list_values(self, values: List[List]) -> List:
        """融合列表值"""
        result = []
        seen = set()
        
        for value_list in values:
            if isinstance(value_list, list):
                for item in value_list:
                    # 尝试去重
                    item_key = str(item) if not isinstance(item, (list, dict)) else id(item)
                    if item_key not in seen:
                        seen.add(item_key)
                        result.append(item)
        
        return result


# 全局多模型评测器实例
_multi_model_evaluator: Optional[MultiModelEvaluator] = None


def get_multi_model_evaluator() -> MultiModelEvaluator:
    """获取全局多模型评测器"""
    global _multi_model_evaluator
    if _multi_model_evaluator is None:
        _multi_model_evaluator = MultiModelEvaluator()
    return _multi_model_evaluator


def set_multi_model_evaluator(evaluator: MultiModelEvaluator):
    """设置全局多模型评测器"""
    global _multi_model_evaluator
    _multi_model_evaluator = evaluator


def call_multi_model_json(
    prompt: str,
    models: List[str] = None,
    system_prompt: Optional[str] = None,
    fusion_strategy: str = DEFAULT_FUSION_STRATEGY
) -> Dict[str, Any]:
    """
    使用多个模型进行评测并融合结果（便捷函数）
    
    Args:
        prompt: 评测提示词
        models: 模型列表（可选，默认使用配置的 T2T 模型）
        system_prompt: 系统提示
        fusion_strategy: 融合策略
        
    Returns:
        融合后的结果字典，包含:
        - fused_result: 融合后的结果
        - model_results: 各模型的原始结果
        - fusion_strategy: 使用的融合策略
        - models_used: 实际使用的模型列表
    """
    evaluator = get_multi_model_evaluator()
    
    # 如果指定了模型列表，创建临时评测器
    if models:
        evaluator = MultiModelEvaluator(
            models=models,
            fusion_strategy=fusion_strategy
        )
    
    return evaluator.evaluate_with_all_models(
        prompt=prompt,
        system_prompt=system_prompt
    )


def fuse_evaluation_results(
    results: Dict[str, Dict],
    strategy: str = DEFAULT_FUSION_STRATEGY,
    weights: Dict[str, float] = None
) -> Dict:
    """
    融合多个评测结果（独立函数）
    
    Args:
        results: 模型名到结果的映射
        strategy: 融合策略
        weights: 模型权重
        
    Returns:
        融合后的结果
    """
    evaluator = MultiModelEvaluator(
        models=list(results.keys()),
        model_weights=weights or MODEL_WEIGHTS,
        fusion_strategy=strategy
    )
    return evaluator._fuse_results(results)
