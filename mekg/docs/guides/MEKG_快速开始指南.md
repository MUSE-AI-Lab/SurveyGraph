# MEKG知识图谱系统 - 快速开始指南

## 🚀 5分钟快速开始

### 第1步：安装依赖

```bash
# 激活虚拟环境（如果有）
# Windows:
.venv\Scripts\activate

# 安装MEKG依赖
pip install -r requirements_mekg.txt
```

**必需依赖**:
- `PyPDF2` - PDF解析
- `httpx` - 异步HTTP客户端  
- `loguru` - 日志记录
- `networkx` - 图分析
- `python-louvain` - 社区发现（可选）

### 第2步：运行测试

```bash
# 方式1：一键测试（推荐）
python test_mekg.py

# 方式2：自定义参数测试
python tasks/mekg_workflow/build_mekg_and_outline.py \
  --topic "your research topic" \
  --target_papers 50
```

### 第3步：查看结果

测试完成后，查看生成的文件：

```bash
# 大纲文件
cat data/mekg_test/mekg/outline.md

# 分析报告
cat data/mekg_test/mekg/analysis_report.json
```

---

## ⚠️ 常见问题修复

### 问题1: 429 Too Many Requests（API限流）

**症状**: 看到大量 `429 Too Many Requests` 错误

**原因**: 并发请求过快

**已修复**: 
- ✅ 降低并发度（从50改为10）
- ✅ 添加请求间延迟
- ✅ 每10个请求后暂停1-2秒

**无需手动操作**，系统已自动处理

### 问题2: PDF下载失败率高

**症状**: 大部分论文PDF下载失败

**已修复**:
- ✅ 实现多源下载策略
  1. OpenAlex PDF链接
  2. arXiv（通过DOI/URL自动识别）
  3. 其他DOI解析服务
- ✅ 搜索2倍数量论文作为候选池
- ✅ 持续下载直到达到目标数量

**示例**：
```
目标: 50篇
搜索: 100篇候选
下载: 依次尝试直到成功50篇
```

### 问题3: PyPDF2 未安装

**症状**: `PyPDF2未安装，请运行: pip install PyPDF2`

**修复**:
```bash
pip install PyPDF2
```

或者一次性安装所有依赖：
```bash
pip install -r requirements_mekg.txt
```

### 问题4: 下载数量不足

**症状**: 指定50篇，结果只有16篇

**原因**: 
1. 搜索结果本身就少（关键词太具体）
2. PDF链接失效率高

**解决方案**:
1. **扩大搜索范围**:
   ```bash
   # 延长年份范围
   python test_mekg.py --year_start 2018 --year_end 2024
   
   # 使用更宽泛的关键词
   --topic "language models"  # 而非 "large language model agents"
   ```

2. **系统会自动**:
   - 搜索2倍数量作为候选池
   - 多源下载（OpenAlex + arXiv）
   - 持续尝试直到达到目标或候选池耗尽

### 问题5: 关系抽取边数为0

**症状**: `生成了 0 个候选论文对`

**原因**: 论文太少或研究领域不重叠

**解决方案**:
- 增加论文数量（至少50-100篇）
- 使用相关度更高的主题
- 扩大年份范围

---

## 📊 性能优化建议

### 针对不同规模的配置

#### 小规模测试（50-100篇）
```bash
python test_mekg.py  # 使用默认配置即可
```

#### 中等规模（500篇）
```bash
python tasks/mekg_workflow/build_mekg_and_outline.py \
  --topic "your topic" \
  --target_papers 500 \
  --year_start 2020 \
  --year_end 2024
```

预计：
- 时间: 1-1.5小时
- 成本: ~$15

#### 大规模（1500篇）
```bash
python tasks/mekg_workflow/build_mekg_and_outline.py \
  --topic "your topic" \
  --target_papers 1500 \
  --year_start 2018 \
  --year_end 2024
```

预计：
- 时间: 3-4小时
- 成本: ~$40

**建议**：
1. 先用50篇测试
2. 确认流程正常后再扩大规模
3. 利用断点续传功能，可以随时中断和恢复

---

## 🔧 高级配置

### 调整并发度

编辑 `src/modules/mekg/enhanced_builder.py`:

```python
# 降低并发（如果遇到限流）
self.pdf_downloader = MultiSourcePDFDownloader(
    pdf_dir=self.papers_dir / "pdfs",
    max_concurrent=5  # 从10改为5
)

# 提高并发（如果网络稳定）
self.pdf_downloader = MultiSourcePDFDownloader(
    pdf_dir=self.papers_dir / "pdfs",
    max_concurrent=20  # 从10改为20
)
```

### 修改搜索倍数

编辑 `src/modules/mekg/enhanced_builder.py`:

```python
# 搜索更多候选（如果PDF下载成功率很低）
search_count = self.target_paper_count * 3  # 从2倍改为3倍
```

### 自定义PDF来源

编辑 `src/modules/paper_acquisition/multi_source_pdf_downloader.py`，
在 `_download_single_with_fallback` 方法中添加新的下载策略。

---

## 📝 系统运行流程

```
1. 智能关键词处理 (1分钟)
   └─ LLM判断是否拆分关键词
   
2. 多关键词搜索 (5-10分钟)
   └─ 搜索2倍数量作为候选池
   
3. 多源PDF下载 (视数量而定)
   ├─ 尝试OpenAlex链接
   ├─ 尝试arXiv（自动识别）
   ├─ 尝试其他DOI源
   └─ 持续下载直到达到目标数量
   
4. PDF解析 (PyPDF2)
   └─ 并发解析，提取文本
   
5. 属性提取 (LLM, 含延迟避免限流)
   └─ 8大类属性，每10个请求暂停1-2秒
   
6. 关系抽取 (基于属性对比)
   └─ 识别5种关系类型
   
7. 图谱分析
   └─ PageRank, 社区发现, 演进路径
   
8. 大纲生成
   └─ 基于图谱结构生成综述大纲
   
9. 保存结果
   └─ MEKG, 大纲, 分析报告
```

---

## ✅ 验证安装

运行以下命令验证系统是否正常：

```python
# 测试脚本
python -c "
import httpx
import loguru
import networkx
try:
    import PyPDF2
    print('✅ 所有依赖已安装')
except ImportError as e:
    print(f'❌ 缺少依赖: {e}')
    print('请运行: pip install -r requirements_mekg.txt')
"
```

---

## 🆘 获取帮助

1. **查看日志文件**:
   ```bash
   # 查看最新日志
   tail -n 100 data/mekg_test/mekg_builder.log
   
   # 查看PDF处理日志  
   tail -n 100 data/mekg_test/papers/pdf_processor.log
   ```

2. **检查进度文件**:
   ```bash
   # 下载进度
   cat data/mekg_test/papers/progress/download_progress.json
   
   # 解析进度
   cat data/mekg_test/papers/progress/parse_progress.json
   ```

3. **参考文档**:
   - 完整使用手册: `tasks/mekg_workflow/README.md`
   - 实施总结: `MEKG_实施总结.md`
   - 设计文档: `MEKG_架构分析与改进方案.md`

---

## 🎯 下一步

安装完成后：

1. 运行测试: `python test_mekg.py`
2. 查看结果: `cat data/mekg_test/mekg/outline.md`
3. 如果成功，增加论文数量运行完整流程
4. 集成到SurveyX工作流（可选）

祝使用愉快！🎉