import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

def collect_metrics_data(outputs_dir="outputs"):
    """收集所有符合条件的任务指标数据"""
    outputs_path = Path(outputs_dir)
    token_data = defaultdict(lambda: defaultdict(list))  # 结构：{stage: {model: [metrics]}}
    time_data = defaultdict(list)                        # 结构：{stage: [durations]}
    
    # 遍历outputs目录
    for task_dir in outputs_path.iterdir():
        if not task_dir.is_dir():
            continue
        
        # 检查必要文件存在性
        if not (task_dir / "survey_wtmk.pdf").exists():
            continue
        if not (task_dir / "metrics").exists():
            continue
            
        # 处理token监控数据
        token_file = task_dir / "metrics" / "token_monitor.json"
        if token_file.exists():
            with open(token_file) as f:
                try:
                    data = json.load(f)
                    for stage, models in data.items():
                        for model, metrics in models.items():
                            token_data[stage][model].append({
                                "input_tokens": metrics["input_tokens"],
                                "output_tokens": metrics["output_tokens"],
                                "total_cost": metrics["total_cost"]
                            })
                except Exception as e:
                    print(f"Error reading {token_file}: {str(e)}")
        
        # 处理时间监控数据
        time_file = task_dir / "metrics" / "time_monitor.json"
        if time_file.exists():
            with open(time_file) as f:
                try:
                    data = json.load(f)
                    for stage, metrics in data.items():
                        if "duration" in metrics:
                            time_data[stage].append(metrics["duration"])
                except Exception as e:
                    print(f"Error reading {time_file}: {str(e)}")
    
    return token_data, time_data

def generate_reports(token_data, time_data):
    """生成统计报告"""
    # Token统计报告
    token_rows = []
    for stage, models in token_data.items():
        for model, metrics_list in models.items():
            avg_input = sum(m["input_tokens"] for m in metrics_list) / len(metrics_list)
            avg_output = sum(m["output_tokens"] for m in metrics_list) / len(metrics_list)
            avg_cost = sum(m["total_cost"] for m in metrics_list) / len(metrics_list)
            
            token_rows.append({
                "阶段名称": stage,
                "模型名称": model,
                "平均输入token": round(avg_input, 2),
                "平均输出token": round(avg_output, 2),
                "平均成本": round(avg_cost, 6)
            })
    
    # Time统计报告
    time_rows = []
    for stage, durations in time_data.items():
        if durations:
            avg_duration = sum(durations) / 60 / len(durations)
            time_rows.append({
                "阶段名称": stage,
                "平均耗时(分钟)": round(avg_duration, 2),
                "样本数量": len(durations)
            })
    
    return pd.DataFrame(token_rows), pd.DataFrame(time_rows)

def save_to_excel(token_df, time_df):
    """保存到Excel文件"""
    with pd.ExcelWriter("metrics_summary.xlsx") as writer:
        # 写入数据
        token_df.to_excel(writer, sheet_name="Token统计", index=False)
        time_df.to_excel(writer, sheet_name="耗时统计", index=False)
        
        # 获取工作表对象
        token_sheet = writer.sheets["Token统计"]
        time_sheet = writer.sheets["耗时统计"]
        
        # 设置Token统计列宽
        for idx, col_name in enumerate(token_df.columns):
            max_len = max(
                token_df[col_name].astype(str).str.len().max(),  # 数据最大长度
                len(str(col_name))  # 列标题长度
            ) + 2
            token_sheet.set_column(idx, idx, max_len)
        
        # 设置耗时统计列宽
        for idx, col_name in enumerate(time_df.columns):
            max_len = max(
                time_df[col_name].astype(str).str.len().max(),
                len(str(col_name))
            ) + 2
            time_sheet.set_column(idx, idx, max_len)

if __name__ == "__main__":
    token_data, time_data = collect_metrics_data()
    token_df, time_df = generate_reports(token_data, time_data)
    save_to_excel(token_df, time_df)
    print(f"报告已生成：{Path('metrics_summary.xlsx').resolve()}")