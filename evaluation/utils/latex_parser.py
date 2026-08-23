"""
LaTeX解析工具
=============

提供LaTeX文件解析功能，包括引用提取、文本提取、大纲提取等。
"""

import re
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
import logging


logger = logging.getLogger(__name__)


def resolve_latex_inputs(main_file_path: Path) -> str:
    """
    递归解析LaTeX的\\input{}和\\include{}命令
    
    Args:
        main_file_path: 主LaTeX文件路径
        
    Returns:
        解析并拼接后的完整文档内容
    """
    root_dir = main_file_path.parent
    visited = set()
    
    def _resolve_recursive(file_path: Path) -> str:
        if file_path in visited:
            logger.warning(f"检测到循环引用，跳过文件: {file_path}")
            return ""
        visited.add(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            logger.warning(f"无法找到引用的文件: {file_path}")
            return ""
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return ""
        
        def replace_input(match):
            relative_path_str = match.group(1)
            if not relative_path_str.endswith('.tex'):
                relative_path_str += '.tex'
            
            # 尝试多种路径解析策略
            included_file_path = (file_path.parent / relative_path_str).resolve()
            
            if not included_file_path.exists():
                included_file_path = (root_dir / relative_path_str).resolve()
            
            return _resolve_recursive(included_file_path)
        
        content = re.sub(r'\\(?:input|include)\{([^}]+)\}', replace_input, content)
        
        return content
    
    return _resolve_recursive(main_file_path)


def extract_citations(content: str) -> Set[str]:
    """
    从LaTeX内容中提取所有引用
    
    Args:
        content: LaTeX内容
        
    Returns:
        引用标签集合
    """
    citations = set()
    
    # 匹配 \cite{...}, \citep{...}, \citet{...} 等格式
    cite_patterns = [
        r'\\cite\{([^}]+)\}',
        r'\\citep\{([^}]+)\}',
        r'\\citet\{([^}]+)\}',
        r'\\citeauthor\{([^}]+)\}',
        r'\\citeyear\{([^}]+)\}'
    ]
    
    for pattern in cite_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            # 处理多引用: \cite{paper1, paper2}
            for paper in match.split(','):
                paper = paper.strip()
                if paper:
                    citations.add(paper)
    
    logger.debug(f"提取到 {len(citations)} 个引用")
    return citations


def extract_citations_from_file(latex_path: Path) -> Set[str]:
    """
    从LaTeX文件中提取所有引用
    
    Args:
        latex_path: LaTeX文件路径
        
    Returns:
        引用标签集合
    """
    content = resolve_latex_inputs(latex_path)
    return extract_citations(content)


def extract_text_from_latex(content: str) -> str:
    """
    从LaTeX内容提取纯文本
    
    Args:
        content: LaTeX内容
        
    Returns:
        提取的纯文本
    """
    # 移除注释
    text = re.sub(r'%.*$', '', content, flags=re.MULTILINE)
    
    # 保留引用标记
    text = re.sub(r'\\cite\{([^}]+)\}', r'[\1]', text)
    
    # 移除其他LaTeX命令
    text = re.sub(r'\\[a-zA-Z]+(\[.*?\])?\{([^}]*)\}', r'\2', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    
    # 移除特殊字符
    text = re.sub(r'[{}$\\]', '', text)
    
    # 规范化空白
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def extract_outline_from_latex(content: str) -> List[Dict]:
    """
    从LaTeX内容提取大纲结构
    
    Args:
        content: LaTeX内容
        
    Returns:
        大纲列表 [{level, title, index}, ...]
    """
    outline = []
    
    # 提取各级标题
    section_pattern = r'\\section\{([^}]+)\}'
    subsection_pattern = r'\\subsection\{([^}]+)\}'
    subsubsection_pattern = r'\\subsubsection\{([^}]+)\}'
    
    # 按顺序提取
    section_idx = 0
    subsection_idx = 0
    subsubsection_idx = 0
    
    # 使用位置信息保持顺序
    all_matches = []
    
    for match in re.finditer(section_pattern, content):
        all_matches.append((match.start(), 1, match.group(1).strip()))
    
    for match in re.finditer(subsection_pattern, content):
        all_matches.append((match.start(), 2, match.group(1).strip()))
    
    for match in re.finditer(subsubsection_pattern, content):
        all_matches.append((match.start(), 3, match.group(1).strip()))
    
    # 按位置排序
    all_matches.sort(key=lambda x: x[0])
    
    # 生成索引
    for pos, level, title in all_matches:
        if level == 1:
            section_idx += 1
            subsection_idx = 0
            subsubsection_idx = 0
            index = str(section_idx)
        elif level == 2:
            subsection_idx += 1
            subsubsection_idx = 0
            index = f"{section_idx}.{subsection_idx}"
        else:
            subsubsection_idx += 1
            index = f"{section_idx}.{subsection_idx}.{subsubsection_idx}"
        
        outline.append({
            "level": level,
            "title": title,
            "index": index
        })
    
    logger.debug(f"提取大纲: {len(outline)} 个章节")
    return outline


def extract_figures_and_tables(content: str) -> Dict[str, List[Dict]]:
    """
    从LaTeX内容提取图片和表格
    
    Args:
        content: LaTeX内容
        
    Returns:
        {"figures": [...], "tables": [...]}
    """
    figures = []
    tables = []
    
    # 提取figure环境
    fig_pattern = r'\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}'
    for match in re.finditer(fig_pattern, content, re.DOTALL):
        fig_content = match.group(1)
        
        # 提取caption
        caption_match = re.search(r'\\caption\{([^}]+)\}', fig_content)
        caption = caption_match.group(1).strip() if caption_match else ""
        
        # 提取label
        label_match = re.search(r'\\label\{([^}]+)\}', fig_content)
        label = label_match.group(1).strip() if label_match else ""
        
        # 提取图片路径
        img_match = re.search(r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}', fig_content)
        img_path = img_match.group(1).strip() if img_match else ""
        
        figures.append({
            "type": "figure",
            "caption": caption,
            "label": label,
            "path": img_path,
            "content": fig_content
        })
    
    # 提取table环境
    tbl_pattern = r'\\begin\{table\*?\}(.*?)\\end\{table\*?\}'
    for match in re.finditer(tbl_pattern, content, re.DOTALL):
        tbl_content = match.group(1)
        
        # 提取caption
        caption_match = re.search(r'\\caption\{([^}]+)\}', tbl_content)
        caption = caption_match.group(1).strip() if caption_match else ""
        
        # 提取label
        label_match = re.search(r'\\label\{([^}]+)\}', tbl_content)
        label = label_match.group(1).strip() if label_match else ""
        
        tables.append({
            "type": "table",
            "caption": caption,
            "label": label,
            "content": tbl_content
        })
    
    logger.debug(f"提取到 {len(figures)} 个图片, {len(tables)} 个表格")
    
    return {
        "figures": figures,
        "tables": tables
    }


def extract_sentences_with_citations(content: str) -> List[Dict]:
    """
    提取包含引用的句子
    
    Args:
        content: LaTeX内容
        
    Returns:
        [{sentence, citations, section}, ...]
    """
    # 先提取章节
    sections = re.findall(
        r'\\section\{([^}]+)\}(.*?)(?=\\section|\\bibliography|\\end\{document\})',
        content,
        re.DOTALL
    )
    
    all_sentences = []
    
    for section_title, section_content in sections:
        # 跳过参考文献等章节
        if any(skip in section_title.lower() for skip in ['abstract', 'reference', 'bibliography', 'acknowledgment']):
            continue
        
        # 分割句子
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', section_content)
        
        for sentence in sentences:
            # 检查是否包含引用
            citations = re.findall(r'\\cite\{([^}]+)\}', sentence)
            
            if citations:
                # 展开多引用
                all_citations = []
                for cite in citations:
                    all_citations.extend([c.strip() for c in cite.split(',')])
                
                # 清理句子
                clean_sentence = _clean_latex_sentence(sentence)
                
                if len(clean_sentence.strip()) > 20:
                    all_sentences.append({
                        "sentence": clean_sentence.strip(),
                        "citations": all_citations,
                        "section": section_title
                    })
    
    logger.debug(f"提取到 {len(all_sentences)} 个带引用的句子")
    return all_sentences


def extract_sentences_without_citations(content: str) -> List[Dict]:
    """
    提取不包含引用的句子（用于通用事实性验证）
    
    Args:
        content: LaTeX内容
        
    Returns:
        [{sentence, section}, ...]
    """
    sections = re.findall(
        r'\\section\{([^}]+)\}(.*?)(?=\\section|\\bibliography|\\end\{document\})',
        content,
        re.DOTALL
    )
    
    all_sentences = []
    
    for section_title, section_content in sections:
        if any(skip in section_title.lower() for skip in ['abstract', 'reference', 'bibliography', 'acknowledgment']):
            continue
        
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', section_content)
        
        for sentence in sentences:
            citations = re.findall(r'\\cite\{([^}]+)\}', sentence)
            
            if not citations:
                clean_sentence = _clean_latex_sentence(sentence)
                
                # 过滤太短或非陈述性句子
                if len(clean_sentence.strip()) > 30 and not clean_sentence.strip().startswith('*'):
                    all_sentences.append({
                        "sentence": clean_sentence.strip(),
                        "section": section_title
                    })
    
    logger.debug(f"提取到 {len(all_sentences)} 个无引用的句子")
    return all_sentences


def _clean_latex_sentence(sentence: str) -> str:
    """清理LaTeX句子"""
    # 保留引用标记
    text = re.sub(r'\\cite\{([^}]+)\}', r'[\1]', sentence)
    
    # 移除其他LaTeX命令
    text = re.sub(r'\\[a-zA-Z]+(\[.*?\])?\{([^}]*)\}', r'\2', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    
    # 移除特殊字符
    text = re.sub(r'[{}$\\]', '', text)
    
    # 规范化空白
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def extract_content_samples(
    content: str,
    num_samples: int = 5,
    sample_length: int = 500
) -> List[str]:
    """
    从LaTeX内容提取内容样本
    
    Args:
        content: LaTeX内容
        num_samples: 采样数量
        sample_length: 每个样本的长度
        
    Returns:
        内容样本列表
    """
    # 提取纯文本
    full_text = extract_text_from_latex(content)
    
    # 分段
    paragraphs = [p.strip() for p in full_text.split('\n') if len(p.strip()) > 100]
    
    if len(paragraphs) < num_samples:
        sentences = re.split(r'(?<=[.!?])\s+', full_text)
        paragraphs = [s.strip() for s in sentences if len(s.strip()) > 100]
    
    # 均匀采样
    samples = []
    if len(paragraphs) <= num_samples:
        samples = paragraphs
    else:
        step = len(paragraphs) // num_samples
        for i in range(0, len(paragraphs), step):
            if len(samples) < num_samples:
                samples.append(paragraphs[i])
    
    # 截断过长的样本
    samples = [s[:sample_length] + "..." if len(s) > sample_length else s for s in samples]
    
    return samples


def parse_bibtex(bibtex_path: Path) -> Dict[str, Dict]:
    """
    解析BibTeX文件
    
    Args:
        bibtex_path: BibTeX文件路径
        
    Returns:
        {citation_key: {title, authors, year, ...}}
    """
    references = {}
    
    try:
        with open(bibtex_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 匹配每个BibTeX条目
        entries = re.findall(
            r'@\w+\{([^,]+),\s*\n(.*?)^\}',
            content,
            re.MULTILINE | re.DOTALL
        )
        
        for cite_key, entry_content in entries:
            cite_key = cite_key.strip()
            
            # 提取title
            title_match = re.search(r'title\s*=\s*\{((?:[^{}]|\{[^{}]*\})+)\}', entry_content)
            title = title_match.group(1) if title_match else ""
            title = re.sub(r'\{.*?\}', '', title)
            title = re.sub(r'\$.*?\$', '', title)
            
            # 提取year
            year_match = re.search(r'year\s*=\s*\{?(\d{4})\}?', entry_content)
            year = int(year_match.group(1)) if year_match else None
            
            # 提取authors
            author_match = re.search(r'author\s*=\s*\{([^}]+)\}', entry_content)
            authors = author_match.group(1) if author_match else ""
            
            references[cite_key] = {
                'title': title,
                'year': year,
                'authors': authors
            }
        
        logger.debug(f"解析 {len(references)} 条BibTeX引用")
        return references
        
    except Exception as e:
        logger.error(f"解析BibTeX文件失败: {e}")
        return {}


def extract_urls(content: str) -> List[str]:
    """
    从LaTeX内容提取URL
    
    Args:
        content: LaTeX内容
        
    Returns:
        URL列表
    """
    urls = []
    
    # 提取 \url{} 中的链接
    url_pattern = r'\\url\{([^}]+)\}'
    urls.extend(re.findall(url_pattern, content))
    
    # 提取 \href{}{} 中的链接
    href_pattern = r'\\href\{([^}]+)\}'
    urls.extend(re.findall(href_pattern, content))
    
    # 去重
    urls = list(set(urls))
    
    logger.debug(f"提取到 {len(urls)} 个URL")
    return urls