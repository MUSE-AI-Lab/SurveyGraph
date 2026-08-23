"""
实体清洗器 - EntityCleaner

借鉴NLP-AKG的设计，检测并修复抽取错误：
- 无效数据（invalid_data）：如"21 document corpus"不是具体数据集名称
- 格式错误（incorrect_format）：如"dataset: MNIST"应该只保留"MNIST"
- 不够具体（not_specific）：如"a neural network"太泛化
- 冗余信息（redundant_info）：如"the proposed method achieves..."

清洗流程：
1. 规则检测常见错误
2. LLM检测复杂错误
3. 无效数据 → 删除
4. 其他错误 → 重新抽取或修复
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from loguru import logger

from src.models.LLM.ChatAgent import ChatAgent
from src.configs.config import DEFAULT_CHATAGENT_MODEL


class ErrorType(Enum):
    """错误类型"""
    VALID = "valid"                     # 有效
    INVALID_DATA = "invalid_data"       # 无效数据
    INCORRECT_FORMAT = "incorrect_format"  # 格式错误
    NOT_SPECIFIC = "not_specific"       # 不够具体
    REDUNDANT_INFO = "redundant_info"   # 冗余信息
    TOO_LONG = "too_long"               # 过长
    TOO_SHORT = "too_short"             # 过短


@dataclass
class CleaningResult:
    """清洗结果"""
    original: str
    cleaned: Optional[str]
    is_valid: bool
    error_type: ErrorType
    confidence: float
    reason: str


@dataclass
class BatchCleaningResult:
    """批量清洗结果"""
    entity_type: str
    total: int
    valid: int
    invalid: int
    cleaned: int
    results: List[CleaningResult]
    
    def to_dict(self) -> Dict:
        return {
            "entity_type": self.entity_type,
            "total": self.total,
            "valid": self.valid,
            "invalid": self.invalid,
            "cleaned": self.cleaned,
            "results": [
                {
                    "original": r.original,
                    "cleaned": r.cleaned,
                    "is_valid": r.is_valid,
                    "error_type": r.error_type.value,
                    "reason": r.reason
                }
                for r in self.results
            ]
        }


class EntityCleaner:
    """
    实体清洗器
    
    检测并修复抽取错误
    """
    
    # 不同实体类型的验证规则
    VALIDATION_RULES = {
        "task": {
            "min_length": 3,
            "max_length": 100,
            "invalid_patterns": [
                r"^(a|an|the)\s+\w+$",  # 太泛化，如"a task"
                r"^\d+\s+\w+",           # 以数字开头
                r"^(this|that|these|those)\s+",  # 指示代词开头
                r"^(our|their|its)\s+",  # 所有格开头
            ],
            "valid_patterns": [
                r"classification",
                r"detection",
                r"recognition",
                r"generation",
                r"translation",
                r"summarization",
                r"extraction",
                r"prediction",
                r"segmentation",
                r"answering",
            ]
        },
        "dataset": {
            "min_length": 2,
            "max_length": 50,
            "invalid_patterns": [
                r"^\d+\s+(documents?|samples?|examples?|images?)",  # 如"21 documents"
                r"^(a|an|the)\s+dataset",
                r"^(our|their|custom)\s+dataset",
                r"^(training|test|validation)\s+set",
            ],
            "valid_patterns": [
                r"^[A-Z][A-Za-z0-9\-_]+$",  # 大写开头的名称
                r"^\w+[-_]\d+",              # 带版本号
            ]
        },
        "method": {
            "min_length": 3,
            "max_length": 200,
            "invalid_patterns": [
                r"^(a|an|the)\s+(new|novel|proposed)\s+",
                r"^(we|they|authors?)\s+",
                r"^(this|that)\s+(paper|work|study)",
            ],
            "valid_patterns": []
        },
        "model": {
            "min_length": 2,
            "max_length": 50,
            "invalid_patterns": [
                r"^(a|an|the)\s+model",
                r"^(our|their|proposed)\s+model",
                r"^model\s*\d*$",
            ],
            "valid_patterns": [
                r"^[A-Z][A-Za-z0-9\-_]+$",  # 大写开头的名称
                r"^[A-Z]{2,}",               # 全大写缩写
            ]
        },
        "metric": {
            "min_length": 2,
            "max_length": 50,
            "invalid_patterns": [
                r"^\d+(\.\d+)?%?$",  # 纯数字
                r"^(a|an|the)\s+",
            ],
            "valid_patterns": [
                r"accuracy",
                r"precision",
                r"recall",
                r"f1",
                r"bleu",
                r"rouge",
                r"perplexity",
                r"loss",
                r"auc",
                r"map",
            ]
        },
        "problem": {
            "min_length": 5,  # 放宽最小长度要求
            "max_length": 500,  # 增加最大长度
            "invalid_patterns": [
                r"^(this|that)\s+(paper|work)\s*$",  # 只匹配完整的无效短语
                r"^(we|they)\s+(propose|present|introduce)\s*$",  # 只匹配完整的无效短语
            ],
            "valid_patterns": []
        },
        "innovation": {
            "min_length": 5,  # 放宽最小长度要求
            "max_length": 800,  # 增加最大长度
            "invalid_patterns": [
                r"^(this|that)\s+(paper|work)\s*$",  # 只匹配完整的无效短语
            ],
            "valid_patterns": []
        }
    }
    
    # 格式修复规则
    FORMAT_FIXES = [
        # 移除前缀
        (r"^(dataset|model|method|task|metric):\s*", ""),
        (r"^(the|a|an)\s+", ""),
        # 移除引号
        (r'^["\'](.+)["\']$', r"\1"),
        # 移除括号说明
        (r"\s*\([^)]*\)\s*$", ""),
        # 移除尾部标点
        (r"[.,;:]+$", ""),
        # 规范化空格
        (r"\s+", " "),
    ]
    
    # LLM清洗Prompt
    CLEAN_ENTITY_PROMPT = """You are an expert in cleaning and validating academic entities extracted from papers.

**Entity Type**: {entity_type}
**Original Value**: {entity}
**Context** (if available): {context}

Please analyze this entity and determine:
1. Is it a valid {entity_type}?
2. If not valid, what's the error type?
3. If it can be fixed, provide the cleaned version.

Error types:
- invalid_data: The value is not a valid {entity_type} (e.g., "21 documents" is not a dataset name)
- incorrect_format: The format is wrong but can be fixed (e.g., "dataset: MNIST" should be "MNIST")
- not_specific: Too generic (e.g., "a neural network" for model)
- redundant_info: Contains unnecessary information
- too_long: Exceeds reasonable length
- too_short: Too short to be meaningful

Return ONLY a JSON object:
{{
    "is_valid": true/false,
    "error_type": "valid" or one of the error types above,
    "cleaned": "cleaned value or null if invalid",
    "reason": "brief explanation"
}}

Your response (JSON only):"""

    def __init__(
        self,
        chat_agent: ChatAgent = None,
        use_llm: bool = False,
        model: str = None
    ):
        """
        初始化实体清洗器
        
        Args:
            chat_agent: LLM对话代理
            use_llm: 是否使用LLM进行清洗
            model: 使用的模型（默认使用配置文件中的DEFAULT_CHATAGENT_MODEL）
        """
        self.chat_agent = chat_agent or ChatAgent()
        self.use_llm = use_llm
        self.model = model or DEFAULT_CHATAGENT_MODEL
        
        # 编译正则表达式
        self.compiled_rules = {}
        for entity_type, rules in self.VALIDATION_RULES.items():
            self.compiled_rules[entity_type] = {
                "invalid": [re.compile(p, re.IGNORECASE) for p in rules["invalid_patterns"]],
                "valid": [re.compile(p, re.IGNORECASE) for p in rules["valid_patterns"]]
            }
        
        self.compiled_fixes = [(re.compile(p, re.IGNORECASE), r) for p, r in self.FORMAT_FIXES]
        
        logger.info(f"EntityCleaner initialized with use_llm={use_llm}")
    
    def clean_entity(
        self,
        entity: str,
        entity_type: str,
        context: str = None
    ) -> CleaningResult:
        """
        清洗单个实体
        
        Args:
            entity: 实体值
            entity_type: 实体类型
            context: 抽取上下文
        
        Returns:
            CleaningResult对象
        """
        if not entity or not entity.strip():
            return CleaningResult(
                original=entity,
                cleaned=None,
                is_valid=False,
                error_type=ErrorType.INVALID_DATA,
                confidence=1.0,
                reason="Empty entity"
            )
        
        # 1. 应用格式修复
        cleaned = self._apply_format_fixes(entity)
        
        # 2. 规则验证
        error_type, confidence, reason = self._rule_validate(cleaned, entity_type)
        
        if error_type == ErrorType.VALID:
            return CleaningResult(
                original=entity,
                cleaned=cleaned if cleaned != entity else None,
                is_valid=True,
                error_type=ErrorType.VALID,
                confidence=confidence,
                reason=reason
            )
        
        # 3. 如果规则检测到错误，尝试修复
        if error_type in [ErrorType.INCORRECT_FORMAT, ErrorType.REDUNDANT_INFO]:
            # 尝试进一步清洗
            further_cleaned = self._further_clean(cleaned, entity_type)
            if further_cleaned and further_cleaned != cleaned:
                # 重新验证
                new_error, new_conf, new_reason = self._rule_validate(further_cleaned, entity_type)
                if new_error == ErrorType.VALID:
                    return CleaningResult(
                        original=entity,
                        cleaned=further_cleaned,
                        is_valid=True,
                        error_type=ErrorType.VALID,
                        confidence=new_conf,
                        reason=f"Fixed: {reason}"
                    )
                cleaned = further_cleaned
        
        # 4. 如果启用LLM，使用LLM进行清洗
        if self.use_llm and error_type != ErrorType.INVALID_DATA:
            llm_result = self._llm_clean(entity, entity_type, context)
            if llm_result.is_valid:
                return llm_result
        
        # 5. 返回最终结果
        return CleaningResult(
            original=entity,
            cleaned=cleaned if error_type != ErrorType.INVALID_DATA else None,
            is_valid=error_type == ErrorType.VALID,
            error_type=error_type,
            confidence=confidence,
            reason=reason
        )
    
    def _apply_format_fixes(self, entity: str) -> str:
        """应用格式修复规则"""
        result = entity.strip()
        
        for pattern, replacement in self.compiled_fixes:
            result = pattern.sub(replacement, result)
        
        return result.strip()
    
    def _rule_validate(
        self,
        entity: str,
        entity_type: str
    ) -> Tuple[ErrorType, float, str]:
        """规则验证"""
        rules = self.VALIDATION_RULES.get(entity_type, self.VALIDATION_RULES["task"])
        compiled = self.compiled_rules.get(entity_type, self.compiled_rules.get("task"))
        
        # 长度检查
        if len(entity) < rules["min_length"]:
            return ErrorType.TOO_SHORT, 0.9, f"Too short (min {rules['min_length']})"
        
        if len(entity) > rules["max_length"]:
            return ErrorType.TOO_LONG, 0.9, f"Too long (max {rules['max_length']})"
        
        # 无效模式检查
        for pattern in compiled["invalid"]:
            if pattern.search(entity):
                return ErrorType.INVALID_DATA, 0.8, f"Matches invalid pattern"
        
        # 有效模式检查（如果有）
        if compiled["valid"]:
            for pattern in compiled["valid"]:
                if pattern.search(entity):
                    return ErrorType.VALID, 0.9, "Matches valid pattern"
            # 如果有有效模式但都不匹配，降低置信度
            return ErrorType.VALID, 0.6, "No valid pattern matched but no invalid pattern either"
        
        return ErrorType.VALID, 0.7, "Passed basic validation"
    
    def _further_clean(self, entity: str, entity_type: str) -> Optional[str]:
        """进一步清洗"""
        result = entity
        
        # 移除常见前缀
        prefixes_to_remove = [
            "the proposed ",
            "our proposed ",
            "a novel ",
            "an improved ",
            "the new ",
        ]
        
        for prefix in prefixes_to_remove:
            if result.lower().startswith(prefix):
                result = result[len(prefix):]
        
        # 移除常见后缀
        suffixes_to_remove = [
            " method",
            " approach",
            " technique",
            " algorithm",
            " framework",
            " system",
            " model",
        ]
        
        for suffix in suffixes_to_remove:
            if result.lower().endswith(suffix) and len(result) > len(suffix) + 3:
                # 只有当剩余部分足够长时才移除
                potential = result[:-len(suffix)]
                if len(potential.strip()) >= 3:
                    result = potential
        
        return result.strip() if result.strip() else None
    
    def _llm_clean(
        self,
        entity: str,
        entity_type: str,
        context: str = None
    ) -> CleaningResult:
        """使用LLM清洗"""
        prompt = self.CLEAN_ENTITY_PROMPT.format(
            entity_type=entity_type,
            entity=entity,
            context=context[:500] if context else "Not available"
        )
        
        try:
            response = self.chat_agent.remote_chat(
                text_content=prompt,
                temperature=0.3,
                model=self.model
            )
            
            result = self._parse_json_response(response)
            
            is_valid = result.get("is_valid", False)
            error_type_str = result.get("error_type", "invalid_data")
            cleaned = result.get("cleaned")
            reason = result.get("reason", "LLM cleaning")
            
            try:
                error_type = ErrorType(error_type_str)
            except ValueError:
                error_type = ErrorType.INVALID_DATA if not is_valid else ErrorType.VALID
            
            return CleaningResult(
                original=entity,
                cleaned=cleaned,
                is_valid=is_valid,
                error_type=error_type,
                confidence=0.8,
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"Error in LLM cleaning: {e}")
            return CleaningResult(
                original=entity,
                cleaned=None,
                is_valid=False,
                error_type=ErrorType.INVALID_DATA,
                confidence=0.5,
                reason=f"LLM error: {str(e)[:50]}"
            )
    
    def _parse_json_response(self, response: str) -> Dict:
        """解析LLM返回的JSON"""
        import json
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取JSON块
        json_patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{[^{}]*\}'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        return {}
    
    def batch_clean(
        self,
        entities: List[str],
        entity_type: str,
        contexts: List[str] = None
    ) -> BatchCleaningResult:
        """
        批量清洗实体
        
        Args:
            entities: 实体列表
            entity_type: 实体类型
            contexts: 上下文列表（可选）
        
        Returns:
            BatchCleaningResult对象
        """
        results = []
        valid_count = 0
        invalid_count = 0
        cleaned_count = 0
        
        for i, entity in enumerate(entities):
            context = contexts[i] if contexts and i < len(contexts) else None
            result = self.clean_entity(entity, entity_type, context)
            results.append(result)
            
            if result.is_valid:
                valid_count += 1
                if result.cleaned:
                    cleaned_count += 1
            else:
                invalid_count += 1
        
        return BatchCleaningResult(
            entity_type=entity_type,
            total=len(entities),
            valid=valid_count,
            invalid=invalid_count,
            cleaned=cleaned_count,
            results=results
        )
    
    def get_valid_entities(
        self,
        entities: List[str],
        entity_type: str
    ) -> List[str]:
        """
        获取有效实体列表
        
        Args:
            entities: 实体列表
            entity_type: 实体类型
        
        Returns:
            有效实体列表（已清洗）
        """
        batch_result = self.batch_clean(entities, entity_type)
        
        valid_entities = []
        for result in batch_result.results:
            if result.is_valid:
                valid_entities.append(result.cleaned or result.original)
        
        return valid_entities


# 便捷函数
def clean_entities(
    entities: List[str],
    entity_type: str,
    use_llm: bool = False
) -> List[str]:
    """
    便捷函数：清洗实体列表
    
    Args:
        entities: 实体列表
        entity_type: 实体类型
        use_llm: 是否使用LLM
    
    Returns:
        清洗后的有效实体列表
    """
    cleaner = EntityCleaner(use_llm=use_llm)
    return cleaner.get_valid_entities(entities, entity_type)


if __name__ == "__main__":
    # 测试
    cleaner = EntityCleaner(use_llm=False)
    
    # 测试数据集清洗
    test_datasets = [
        "MNIST",
        "dataset: ImageNet",
        "the CIFAR-10 dataset",
        "21 document corpus",
        "our custom dataset",
        "SQuAD 1.1",
        "a",
        "",
        "This is a very long dataset name that exceeds the maximum allowed length for dataset entities",
    ]
    
    print("Testing dataset cleaning:")
    result = cleaner.batch_clean(test_datasets, "dataset")
    print(f"  Total: {result.total}, Valid: {result.valid}, Invalid: {result.invalid}, Cleaned: {result.cleaned}")
    for r in result.results:
        status = "✓" if r.is_valid else "✗"
        cleaned_str = f" -> '{r.cleaned}'" if r.cleaned else ""
        print(f"  {status} '{r.original}'{cleaned_str} ({r.error_type.value}: {r.reason})")
    
    # 测试任务清洗
    test_tasks = [
        "text classification",
        "a task",
        "the proposed method",
        "sentiment analysis",
        "21 classification tasks",
        "QA",
    ]
    
    print("\nTesting task cleaning:")
    result = cleaner.batch_clean(test_tasks, "task")
    for r in result.results:
        status = "✓" if r.is_valid else "✗"
        cleaned_str = f" -> '{r.cleaned}'" if r.cleaned else ""
        print(f"  {status} '{r.original}'{cleaned_str} ({r.error_type.value})")
    
    # 测试模型清洗
    test_models = [
        "BERT",
        "GPT-4",
        "a model",
        "our proposed model",
        "the Transformer",
        "model 1",
    ]
    
    print("\nTesting model cleaning:")
    result = cleaner.batch_clean(test_models, "model")
    for r in result.results:
        status = "✓" if r.is_valid else "✗"
        cleaned_str = f" -> '{r.cleaned}'" if r.cleaned else ""
        print(f"  {status} '{r.original}'{cleaned_str} ({r.error_type.value})")