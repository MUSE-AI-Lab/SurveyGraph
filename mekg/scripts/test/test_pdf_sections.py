import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.modules.mekg.pdf_processor import PDFProcessor

def test_section_extraction():
    print("🧪 测试 PDF 章节分割功能...")
    
    # 模拟一篇论文的文本内容
    mock_paper_text = """
Deep Learning for Graphs
Author Name

Abstract
This paper proposes a new graph neural network. It outperforms existing methods.

1. Introduction
Graph neural networks are powerful. However, they have limitations.
We propose a new method to address this.

2. Related Work
Previous works include GCN and GAT.

3. Method
Our method consists of three parts. First, we define the graph convolution.
Second, we introduce attention.

4. Experiments
We evaluate on Cora and Citeseer.
Results show 5% improvement.

5. Conclusion
In this paper, we proposed a novel GNN.

References
[1] Kipf et al.
[2] Velickovic et al.
"""
    
    processor = PDFProcessor()
    sections = processor.extract_sections(mock_paper_text)
    
    print("\n📊 提取结果:")
    for section, content in sections.items():
        if section == "full_text": continue
        preview = content[:50].replace('\n', ' ') + "..." if content else "[Empty]"
        print(f"- {section.ljust(15)}: {preview}")
        
    # 验证关键章节是否存在
    assert "method" in sections and len(sections["method"]) > 0, "❌ Method section missing"
    assert "experiment" in sections and len(sections["experiment"]) > 0, "❌ Experiment section missing"
    
    print("\n✅ 测试通过！章节分割逻辑正常工作。")

if __name__ == "__main__":
    test_section_extraction()