"""
Critical Analysis Refiner
=========================

后处理模块，用于增强综述内容的批判性分析深度。

主要功能:
1. 识别缺乏定量证据的段落并建议补充
2. 识别缺乏批判性分析的段落并增强
3. 添加失败模式分析
4. 添加方法间的权衡分析
5. 生成对比表格建议
"""

from __future__ import annotations

import re
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from loguru import logger

import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.models.LLM.ChatAgent import ChatAgent
    HAS_CHAT_AGENT = True
except ImportError:
    HAS_CHAT_AGENT = False


@dataclass
class AnalysisIssue:
    """分析问题"""
    issue_type: str  # "missing_quantitative", "weak_critical", "no_failure_analysis", "no_tradeoff"
    location: str  # 段落位置描述
    original_text: str  # 原始文本片段
    suggestion: str  # 改进建议
    severity: str = "medium"  # "high", "medium", "low"


@dataclass
class RefineResult:
    """优化结果"""
    original_content: str
    refined_content: str
    issues_found: List[AnalysisIssue] = field(default_factory=list)
    improvements_made: List[str] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)


class CriticalAnalysisRefiner:
    """
    批判性分析优化器
    
    用于后处理生成的综述内容，增强其学术深度和批判性分析。
    """
    
    # 分析检查Prompt
    ANALYSIS_CHECK_PROMPT = """你是一位严格的学术综述审稿人。请分析以下综述段落，识别其在批判性分析方面的不足。

## 待分析段落
{paragraph}

## 检查维度

### 1. 定量证据 (Quantitative Evidence)
- 是否包含具体数字（准确率、F1分数、改进百分比等）？
- 比较方法时是否有定量支撑？
- 如果缺乏，标记为 "missing_quantitative"

### 2. 批判性分析 (Critical Analysis)
- 是否只是描述方法而没有评价？
- 是否讨论了方法的优缺点？
- 是否有"为什么有效"的解释？
- 如果缺乏，标记为 "weak_critical"

### 3. 失败模式分析 (Failure Mode Analysis)
- 是否讨论了方法的失败情况？
- 是否提到了边缘情况或局限性？
- 如果缺乏，标记为 "no_failure_analysis"

### 4. 权衡分析 (Trade-off Analysis)
- 比较多个方法时，是否讨论了权衡？
- 是否说明了不同方法适用的场景？
- 如果缺乏，标记为 "no_tradeoff"

## 输出格式 (JSON)
```json
{{
  "issues": [
    {{
      "type": "missing_quantitative",
      "location": "第2句",
      "original_text": "方法A显著优于方法B",
      "suggestion": "添加具体数字，如'方法A在X基准上达到85%准确率，比方法B高3个百分点'",
      "severity": "high"
    }}
  ],
  "overall_quality": "medium",
  "summary": "该段落缺乏定量证据和失败模式分析"
}}
```

只输出JSON，不要其他内容。"""

    # 段落增强Prompt
    PARAGRAPH_ENHANCE_PROMPT = """你是一位学术综述写作专家。请根据以下问题，增强这个段落的批判性分析深度。

## 原始段落
{paragraph}

## 识别的问题
{issues}

## 可用的论文信息（用于补充细节）
{paper_info}

## 增强要求

### 1. 如果缺乏定量证据
- 从论文信息中提取具体数字
- 如果没有确切数字，使用"据报告..."或"在X基准上..."等表述
- 避免使用"显著"、"大幅"等模糊词汇

### 2. 如果批判性分析薄弱
- 添加"为什么有效"的解释
- 添加与其他方法的对比
- 讨论方法的适用范围

### 3. 如果缺乏失败模式分析
- 添加已知的失败情况
- 讨论边缘情况
- 提及局限性

### 4. 如果缺乏权衡分析
- 明确说明不同方法的权衡
- 指出各方法的最佳适用场景

## 格式要求
- 保持LaTeX格式
- 保留原有引用
- 不要改变段落的主题
- 增强内容应自然融入原文

## 输出
直接输出增强后的段落，不要任何说明。"""

    # 对比表格生成Prompt
    COMPARISON_TABLE_PROMPT = """基于以下方法信息，生成一个LaTeX对比表格。

## 方法列表
{methods}

## 表格要求
1. 包含列：方法名称、核心技术、主要优势、主要局限、适用场景
2. 如果有定量数据，添加性能列
3. 使用booktabs样式
4. 表格标题应描述比较的主题

## 输出格式
直接输出LaTeX表格代码，包含\\begin{{table}}到\\end{{table}}。"""

    def __init__(
        self,
        chat_agent: Optional[ChatAgent] = None,
        enable_enhancement: bool = True,
        min_paragraph_length: int = 100
    ):
        """
        初始化批判性分析优化器
        
        Args:
            chat_agent: LLM对话代理
            enable_enhancement: 是否启用自动增强
            min_paragraph_length: 最小段落长度（字符），低于此长度的段落不分析
        """
        self.chat_agent = chat_agent
        env_enable_llm = os.getenv("CRITICAL_ANALYSIS_ENABLE_LLM")
        if env_enable_llm is not None and env_enable_llm.strip().lower() in {"0", "false", "no", "off"}:
            enable_enhancement = False
            logger.info("CRITICAL_ANALYSIS_ENABLE_LLM=false，跳过批判性分析LLM段落增强")
        self.enable_enhancement = enable_enhancement
        self.min_paragraph_length = min_paragraph_length
        
        if self.chat_agent is None and HAS_CHAT_AGENT:
            try:
                self.chat_agent = ChatAgent()
            except Exception as e:
                logger.warning(f"无法创建ChatAgent: {e}")
    
    def analyze_content(
        self,
        content: str,
        paper_info: Optional[Dict[str, Any]] = None
    ) -> RefineResult:
        """
        分析内容并识别问题
        
        Args:
            content: 待分析的综述内容
            paper_info: 可用的论文信息（用于补充细节）
            
        Returns:
            RefineResult对象
        """
        # 1. 分割段落
        paragraphs = self._split_paragraphs(content)
        logger.info(f"分析 {len(paragraphs)} 个段落...")
        
        # 2. 分析每个段落
        all_issues = []
        for i, para in enumerate(paragraphs):
            if len(para.strip()) < self.min_paragraph_length:
                continue
            
            issues = self._analyze_paragraph(para, i)
            all_issues.extend(issues)
        
        # 3. 统计问题
        statistics = self._compute_statistics(all_issues)
        
        # 4. 如果启用增强，进行内容优化
        refined_content = content
        improvements = []
        
        if self.enable_enhancement and all_issues and self.chat_agent:
            refined_content, improvements = self._enhance_content(
                content, paragraphs, all_issues, paper_info
            )
        
        return RefineResult(
            original_content=content,
            refined_content=refined_content,
            issues_found=all_issues,
            improvements_made=improvements,
            statistics=statistics
        )
    
    def _split_paragraphs(self, content: str) -> List[str]:
        """分割段落"""
        # 按双换行分割
        paragraphs = re.split(r'\n\s*\n', content)
        # 过滤空段落和纯LaTeX命令段落
        filtered = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # 跳过纯LaTeX命令（如\section, \subsection等）
            if re.match(r'^\\(section|subsection|subsubsection|begin|end)\{', para):
                continue
            filtered.append(para)
        return filtered
    
    def _analyze_paragraph(self, paragraph: str, index: int) -> List[AnalysisIssue]:
        """分析单个段落"""
        issues = []
        
        # 规则1: 检查定量证据
        if not self._has_quantitative_evidence(paragraph):
            # 检查是否有比较性陈述但缺乏数字
            if self._has_comparison_without_numbers(paragraph):
                issues.append(AnalysisIssue(
                    issue_type="missing_quantitative",
                    location=f"段落 {index + 1}",
                    original_text=self._extract_comparison_sentence(paragraph),
                    suggestion="添加具体的性能数字或百分比",
                    severity="high"
                ))
        
        # 规则2: 检查批判性分析
        if self._is_purely_descriptive(paragraph):
            issues.append(AnalysisIssue(
                issue_type="weak_critical",
                location=f"段落 {index + 1}",
                original_text=paragraph[:100] + "...",
                suggestion="添加'为什么有效'的解释或与其他方法的对比",
                severity="medium"
            ))
        
        # 规则3: 检查失败模式（仅对方法描述段落）
        if self._is_method_description(paragraph) and not self._has_limitation_discussion(paragraph):
            issues.append(AnalysisIssue(
                issue_type="no_failure_analysis",
                location=f"段落 {index + 1}",
                original_text=paragraph[:100] + "...",
                suggestion="添加方法的局限性或失败情况讨论",
                severity="medium"
            ))
        
        # 规则4: 检查权衡分析（仅对比较段落）
        if self._is_comparison_paragraph(paragraph) and not self._has_tradeoff_analysis(paragraph):
            issues.append(AnalysisIssue(
                issue_type="no_tradeoff",
                location=f"段落 {index + 1}",
                original_text=paragraph[:100] + "...",
                suggestion="添加不同方法之间的权衡分析",
                severity="low"
            ))
        
        return issues
    
    def _has_quantitative_evidence(self, text: str) -> bool:
        """检查是否包含定量证据"""
        # 检查数字模式
        patterns = [
            r'\d+\.?\d*\s*%',  # 百分比
            r'\d+\.?\d*\s*(accuracy|precision|recall|F1|BLEU|ROUGE)',  # 指标
            r'(outperforms?|improves?|achieves?)\s+.*\d+',  # 性能描述
            r'\d+\s*(times?|x)\s+(faster|slower|better|worse)',  # 倍数比较
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _has_comparison_without_numbers(self, text: str) -> bool:
        """检查是否有比较但没有数字"""
        comparison_words = [
            'outperforms', 'better than', 'worse than', 'improves',
            'significantly', 'substantially', 'considerably',
            'superior', 'inferior', 'exceeds', 'surpasses'
        ]
        has_comparison = any(word in text.lower() for word in comparison_words)
        has_numbers = bool(re.search(r'\d+\.?\d*\s*%', text))
        return has_comparison and not has_numbers
    
    def _extract_comparison_sentence(self, text: str) -> str:
        """提取包含比较的句子"""
        sentences = re.split(r'[.!?]', text)
        comparison_words = ['outperforms', 'better', 'worse', 'improves', 'significantly']
        for sent in sentences:
            if any(word in sent.lower() for word in comparison_words):
                return sent.strip()[:150]
        return text[:100]
    
    def _is_purely_descriptive(self, text: str) -> bool:
        """检查是否纯描述性（缺乏分析）"""
        # 分析性词汇
        analytical_words = [
            'because', 'therefore', 'however', 'although', 'despite',
            'advantage', 'disadvantage', 'limitation', 'trade-off',
            'effective', 'ineffective', 'suitable', 'unsuitable',
            'reason', 'cause', 'result', 'consequence'
        ]
        analytical_count = sum(1 for word in analytical_words if word in text.lower())
        
        # 如果分析性词汇少于2个，可能是纯描述性
        return analytical_count < 2
    
    def _is_method_description(self, text: str) -> bool:
        """检查是否是方法描述段落"""
        method_indicators = [
            'proposes', 'introduces', 'presents', 'develops',
            'method', 'approach', 'technique', 'algorithm',
            'framework', 'model', 'system'
        ]
        return sum(1 for word in method_indicators if word in text.lower()) >= 2
    
    def _has_limitation_discussion(self, text: str) -> bool:
        """检查是否讨论了局限性"""
        limitation_words = [
            'limitation', 'drawback', 'weakness', 'shortcoming',
            'fails', 'failure', 'cannot', 'unable',
            'challenge', 'difficulty', 'problem',
            'however', 'although', 'despite', 'but'
        ]
        return sum(1 for word in limitation_words if word in text.lower()) >= 2
    
    def _is_comparison_paragraph(self, text: str) -> bool:
        """检查是否是比较段落"""
        # 检查是否有多个引用
        cite_count = len(re.findall(r'\\cite\{[^}]+\}', text))
        comparison_words = ['compare', 'contrast', 'versus', 'vs', 'while', 'whereas']
        has_comparison = any(word in text.lower() for word in comparison_words)
        return cite_count >= 2 or has_comparison
    
    def _has_tradeoff_analysis(self, text: str) -> bool:
        """检查是否有权衡分析"""
        tradeoff_words = [
            'trade-off', 'tradeoff', 'balance', 'sacrifice',
            'at the cost of', 'in exchange for',
            'while', 'whereas', 'on the other hand',
            'suitable for', 'best for', 'preferred when'
        ]
        return any(phrase in text.lower() for phrase in tradeoff_words)
    
    def _compute_statistics(self, issues: List[AnalysisIssue]) -> Dict[str, Any]:
        """计算问题统计"""
        stats = {
            "total_issues": len(issues),
            "by_type": {},
            "by_severity": {"high": 0, "medium": 0, "low": 0}
        }
        
        for issue in issues:
            stats["by_type"][issue.issue_type] = stats["by_type"].get(issue.issue_type, 0) + 1
            stats["by_severity"][issue.severity] += 1
        
        return stats
    
    def _enhance_content(
        self,
        content: str,
        paragraphs: List[str],
        issues: List[AnalysisIssue],
        paper_info: Optional[Dict[str, Any]]
    ) -> Tuple[str, List[str]]:
        """增强内容"""
        if not self.chat_agent:
            return content, []
        
        improvements = []
        enhanced_content = content
        
        # 按段落分组问题
        issues_by_para = {}
        for issue in issues:
            para_idx = int(re.search(r'\d+', issue.location).group()) - 1
            if para_idx not in issues_by_para:
                issues_by_para[para_idx] = []
            issues_by_para[para_idx].append(issue)
        
        # 只处理高优先级问题（避免过度修改）
        high_priority_paras = [
            idx for idx, para_issues in issues_by_para.items()
            if any(i.severity == "high" for i in para_issues)
        ]
        
        for para_idx in high_priority_paras[:5]:  # 最多处理5个段落
            if para_idx >= len(paragraphs):
                continue
            
            original_para = paragraphs[para_idx]
            para_issues = issues_by_para[para_idx]
            
            try:
                enhanced_para = self._enhance_paragraph(
                    original_para, para_issues, paper_info
                )
                
                if enhanced_para and enhanced_para != original_para:
                    enhanced_content = enhanced_content.replace(original_para, enhanced_para)
                    improvements.append(f"增强了段落 {para_idx + 1}: {para_issues[0].issue_type}")
                    
            except Exception as e:
                logger.warning(f"段落增强失败: {e}")
        
        return enhanced_content, improvements
    
    def _enhance_paragraph(
        self,
        paragraph: str,
        issues: List[AnalysisIssue],
        paper_info: Optional[Dict[str, Any]]
    ) -> str:
        """增强单个段落"""
        issues_str = "\n".join([
            f"- {i.issue_type}: {i.suggestion}"
            for i in issues
        ])
        
        paper_info_str = ""
        if paper_info:
            paper_info_str = json.dumps(paper_info, ensure_ascii=False, indent=2)[:2000]
        
        prompt = self.PARAGRAPH_ENHANCE_PROMPT.format(
            paragraph=paragraph,
            issues=issues_str,
            paper_info=paper_info_str or "无额外信息"
        )
        
        if not hasattr(self.chat_agent, "remote_chat_no_retry"):
            logger.warning("ChatAgent缺少remote_chat_no_retry，跳过批判性段落增强以避免重试堆叠")
            return paragraph

        try:
            enhanced = self.chat_agent.remote_chat_no_retry(
                prompt,
                temperature=0.3,
                timeout=180,
            )
        except Exception as e:
            logger.warning(f"批判性段落增强失败，保留原段落: {e}")
            return paragraph

        if not enhanced or self._is_error_response(enhanced):
            logger.warning("批判性段落增强返回错误/空响应，保留原段落")
            return paragraph

        cleaned = self._clean_response(str(enhanced))
        if not cleaned or self._is_error_response(cleaned):
            logger.warning("批判性段落增强清洗后为空或错误响应，保留原段落")
            return paragraph

        return cleaned

    def _is_error_response(self, response: str) -> bool:
        """判断no-retry LLM调用是否返回了错误哨兵。"""
        normalized = str(response).strip().lower()
        return normalized.startswith("error:") or "timeout after" in normalized
    
    def _clean_response(self, response: str) -> str:
        """清理LLM响应"""
        # 移除可能的markdown标记
        response = re.sub(r'^```\w*\n?', '', response)
        response = re.sub(r'\n?```$', '', response)
        return response.strip()
    
    def generate_comparison_table(
        self,
        methods: List[Dict[str, Any]]
    ) -> str:
        """
        生成方法对比表格
        
        Args:
            methods: 方法信息列表，每个包含name, technique, advantage, limitation, use_case
            
        Returns:
            LaTeX表格代码
        """
        if not self.chat_agent:
            return self._generate_simple_table(methods)
        
        methods_str = json.dumps(methods, ensure_ascii=False, indent=2)
        prompt = self.COMPARISON_TABLE_PROMPT.format(methods=methods_str)
        
        try:
            table = self.chat_agent.remote_chat(prompt, temperature=0.2)
            return self._clean_response(table)
        except Exception as e:
            logger.warning(f"表格生成失败: {e}")
            return self._generate_simple_table(methods)
    
    def _generate_simple_table(self, methods: List[Dict[str, Any]]) -> str:
        """生成简单表格（无LLM时的回退）"""
        rows = []
        for m in methods:
            row = f"{m.get('name', 'N/A')} & {m.get('technique', 'N/A')} & {m.get('advantage', 'N/A')} & {m.get('limitation', 'N/A')} \\\\"
            rows.append(row)
        
        table = f"""\\begin{{table}}[h]
\\centering
\\caption{{Method Comparison}}
\\small
\\begin{{tabular}}{{p{{2.5cm}}p{{3cm}}p{{3cm}}p{{3cm}}}}
\\toprule
\\textbf{{Method}} & \\textbf{{Technique}} & \\textbf{{Advantage}} & \\textbf{{Limitation}} \\\\
\\midrule
{chr(10).join(rows)}
\\bottomrule
\\end{{tabular}}
\\end{{table}}"""
        return table
    
    def get_quality_report(self, result: RefineResult) -> str:
        """
        生成质量报告
        
        Args:
            result: RefineResult对象
            
        Returns:
            质量报告字符串
        """
        report = ["=" * 50]
        report.append("综述内容质量分析报告")
        report.append("=" * 50)
        
        stats = result.statistics
        report.append(f"\n总问题数: {stats['total_issues']}")
        
        report.append("\n按类型分布:")
        type_names = {
            "missing_quantitative": "缺乏定量证据",
            "weak_critical": "批判性分析薄弱",
            "no_failure_analysis": "缺少失败模式分析",
            "no_tradeoff": "缺少权衡分析"
        }
        for issue_type, count in stats.get("by_type", {}).items():
            report.append(f"  - {type_names.get(issue_type, issue_type)}: {count}")
        
        report.append("\n按严重程度分布:")
        for severity, count in stats.get("by_severity", {}).items():
            report.append(f"  - {severity}: {count}")
        
        if result.improvements_made:
            report.append(f"\n已进行的改进 ({len(result.improvements_made)}):")
            for imp in result.improvements_made:
                report.append(f"  - {imp}")
        
        report.append("\n" + "=" * 50)
        
        return "\n".join(report)


def refine_survey_content(
    content_path: Path,
    output_path: Optional[Path] = None,
    paper_info_path: Optional[Path] = None
) -> RefineResult:
    """
    优化综述内容
    
    Args:
        content_path: 内容文件路径
        output_path: 输出路径（可选）
        paper_info_path: 论文信息文件路径（可选）
        
    Returns:
        RefineResult对象
    """
    # 读取内容
    content = content_path.read_text(encoding='utf-8')
    
    # 读取论文信息（如果有）
    paper_info = None
    if paper_info_path and paper_info_path.exists():
        with open(paper_info_path, 'r', encoding='utf-8') as f:
            paper_info = json.load(f)
    
    # 创建优化器并分析
    refiner = CriticalAnalysisRefiner()
    result = refiner.analyze_content(content, paper_info)
    
    # 输出报告
    report = refiner.get_quality_report(result)
    print(report)
    
    # 保存结果
    if output_path:
        output_path.write_text(result.refined_content, encoding='utf-8')
        logger.info(f"优化后的内容已保存到: {output_path}")
    
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 2:
        content_path = Path(sys.argv[1])
        output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        paper_info_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        
        result = refine_survey_content(content_path, output_path, paper_info_path)
        print(f"\n分析完成！发现 {len(result.issues_found)} 个问题")
    else:
        print("Usage: python critical_analysis_refiner.py <content_path> [output_path] [paper_info_path]")
