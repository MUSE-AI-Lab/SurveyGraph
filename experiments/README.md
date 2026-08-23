# SurveyGraph Experiment Harness

这套实验脚本的目标是：

1. 用本地私有 JSON 保存百炼兼容接口配置与模型目录；
2. 先探测各国产模型的返回结构；
3. 再按“互不覆盖、可独立启动”的方式生成并执行实验矩阵；
4. 让消融、评测回放、baseline smoke 能以不同脚本分别启动。

## 目录

- `experiments/configs/dashscope_models.example.json`
  - 示例配置，不包含真实 key
- `experiments/probe_dashscope_models.py`
  - 探测 DashScope OpenAI-compatible 接口的返回结构
- `experiments/build_experiment_manifests.py`
  - 根据本地私有配置生成实验 manifest
- `experiments/run_suite.py`
  - 读取 manifest，并行启动独立实验进程
- `experiments/launch_*.ps1`
  - 便于在 Windows PowerShell 下直接启动

## 本地私有配置

默认读取：

`experiments/configs/dashscope_models.local.json`

也可通过环境变量覆盖：

`SURVEYGRAPH_EXPERIMENT_CONFIG=path/to/config.json`

## 典型流程

### 1) 探测模型返回结构

```powershell
python experiments/probe_dashscope_models.py
```

### 2) 生成实验矩阵

```powershell
python experiments/build_experiment_manifests.py
```

### 3) 启动消融

```powershell
powershell -ExecutionPolicy Bypass -File experiments/launch_ablation.ps1
```

### 4) 启动评测回放

```powershell
powershell -ExecutionPolicy Bypass -File experiments/launch_eval_replay.ps1
```

### 5) 启动 baseline smoke

```powershell
powershell -ExecutionPolicy Bypass -File experiments/launch_baseline_smoke.ps1
```

### 6) 启动 SurveyGraph smoke（推荐先跑）

Qwen:

```powershell
powershell -ExecutionPolicy Bypass -File experiments/launch_surveygraph_smoke.ps1
```

GLM:

```powershell
powershell -ExecutionPolicy Bypass -File experiments/launch_surveygraph_smoke_glm.ps1
```

DeepSeek:

```powershell
powershell -ExecutionPolicy Bypass -File experiments/launch_surveygraph_smoke_deepseek.ps1
```

如果只想跑一个最小单任务，可直接指定 one-run manifest：

```powershell
python experiments/run_suite.py --manifest experiments/manifests/surveygraph_smoke_qwen_one.generated.json
python experiments/run_suite.py --manifest experiments/manifests/surveygraph_smoke_glm_one.generated.json
python experiments/run_suite.py --manifest experiments/manifests/surveygraph_smoke_deepseek_one.generated.json
```

## 输出

- 模型探测：`outputs/model_probe/<timestamp>/`
- 实验 suite：`outputs/experiment_suites/<suite_name>/<timestamp>/`
- 具体 SurveyGraph 运行：仍然落在 `outputs/<task_id>/`

## 当前推荐启动顺序

1. `launch_probe.ps1`
2. `launch_baseline_smoke.ps1`
3. `launch_surveygraph_smoke*.ps1`
4. `launch_eval_replay_fast.ps1`
5. `launch_ablation_*.ps1`
6. 最后再跑 `launch_eval_replay.ps1`

## Smoke 特殊说明

- `surveygraph_smoke_*` 的目标是“稳定打通关键链路”，不是最终公平评测。
- 真实验证显示，完整 PDF 在 Step 3 的属性抽取 prompt 会逼近甚至超过默认超时门槛。
- 因此 smoke manifest 额外固定了：
  - `--no-memgraph`
  - `--no-hybrid-outline`
  - `MD_TEXT_LENGTH=10000`
  - `ENABLE_AI_IMAGES=false`
- 原因：当前百炼文本模型的主链路（正文、表格、TikZ 动态视觉）可跑通，但 AI image generation 仍会因返回里缺少可解析的 image URL 触发长时间重试。
- 因此 smoke 优先验证“文本+表格+动态视觉+LaTeX 收尾”这一稳定主链路；正式扩展到 AI 图片时，再单独更换图像模型/返回解析逻辑。
- 正式消融 / 评测回放 **不使用** 这个 smoke 专用截断配置。

## 已验证的真实结果（截至当前仓库状态）

- 模型探测：`outputs/model_probe/20260523_140107/probe_results.json`
- baseline smoke：`outputs/experiment_suites/baseline_smoke_suite/20260523_140105/`
- eval replay fast：`outputs/experiment_suites/eval_replay_fast_suite/20260523_142352/`
- SurveyGraph smoke：
  - Qwen one-run：已从旧 checkpoint 恢复并推进到 `COMPLETED`，现已成功生成 `survey.pdf` / `survey_wtmk.pdf`
  - GLM one-run：已从旧 checkpoint 恢复并推进到 `COMPLETED`，现已成功生成 `survey.pdf` / `survey_wtmk.pdf`
  - DeepSeek one-run：已从旧 checkpoint 恢复并推进到 `COMPLETED`，现已成功生成 `survey.pdf` / `survey_wtmk.pdf`

## 当前稳定性修正（已落地）

- Smoke 路径默认关闭 AI 图片：
  - 通过 `ENABLE_AI_IMAGES=false` 避开百炼文本模型在 AI-image 阶段无法返回 image URL 的长时间重试
- PDF 编译新增 fallback：
  - 若 `latexmk` 因 MiKTeX 缺少 `perl` 而失败，会自动回退到
    - `pdflatex`
    - `bibtex`
    - `pdflatex`
    - `pdflatex`
  - 已在真实任务目录验证成功产出 `survey.pdf`
- evaluation 默认只跟随当前国产 profile：
  - 文本评测模型默认由 `DEFAULT_CHATAGENT_MODEL`、`ADVANCED_CHATAGENT_MODEL`、`EVAL_TEXT_MODEL` 去重生成
  - 不再默认混入 `gemini-*` / 旧版 `minimax-m2.1`

## 设计约束

- 每个 run 使用唯一 `task_id`
- 每个 run 独立日志文件
- 每个 suite 独立 summary JSON
- 并发由 manifest 与命令行参数共同控制
- 通过环境变量/本地 JSON 控制模型，不改实验脚本本身
