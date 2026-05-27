# 完整操作说明

## 1. 这套程序是做什么的

这套程序用于审计已经带标签的视觉数据集，特别适合当前这种情况：

- 数据标签本来就是大模型打的
- 我们想知道数据到底哪里有问题
- 我们不希望只靠肉眼全量翻图
- 我们希望把整个流程标准化和自动化

这套程序不把 Gemini3 当最终裁判，而是把 Gemini3 放在“风险发现层”：

- 静态规则负责抓硬错误
- 一致性规则负责抓系统性不稳
- Gemini3 负责扩大风险发现覆盖面
- 人工负责最终确认

## 2. 程序目录

当前主程序目录：

- `/home/reviewer/dataset-review-agent/dataset_audit_pipeline`

核心文件：

- `run_audit.py`
- `run_pipeline.sh`
- `config.example.json`
- `configs/your_dataset.json`
- `README.md`
- `OPERATION_GUIDE.md`

## 3. 运行前要准备什么

### 数据集

程序默认读取这种 JSONL 格式：

```json
{
  "image": "/abs/path/to/image.jpg",
  "conversations": [
    {"from": "human", "value": "...prompt..."},
    {"from": "gpt", "value": "{\"status\": ... }"}
  ]
}
```

### Gemini3 接口

如果要启用模型辅助风险发现，需要准备：

- `endpoint`
- `model_name`
- `DATASET_AUDIT_API_KEY`

推荐先在服务器上设置：

```bash
export DATASET_AUDIT_API_KEY='你的密钥'
```

## 4. 怎么运行

默认运行：

```bash
cd /home/reviewer/dataset-review-agent/dataset_audit_pipeline
export DATASET_AUDIT_API_KEY='你的密钥'
bash run_pipeline.sh
```

指定配置运行：

```bash
cd /home/reviewer/dataset-review-agent/dataset_audit_pipeline
python3 run_audit.py --config configs/your_dataset.json
```

## 5. 程序实际做了哪些事

### 第一层：静态规则审计

会检查：

- 标签是不是合法 JSON
- 顶层字段是否缺失
- 枚举值是否合法
- `status` 和 `skip_reason` 是否冲突
- child / elder / count 等字段是否自洽
- 图片文件是否存在

### 第二层：一致性检查

会检查：

- 同图是否多标签冲突
- train/val 是否共享同一订单
- 同订单 / 同 scene 是否标签不稳定
- 相邻时间窗口内是否出现异常快速翻转

### 第三层：Gemini3 风险发现

Gemini3 不负责盖棺定论，只负责：

- 复看高风险样本
- 给出结构化再判断
- 暴露和原标签差异最大的字段
- 帮我们把更可疑的样本排到前面

### 第四层：统一风险排序

程序会把：

- 静态问题
- 一致性问题
- 模型分歧

合并成统一 `risk_score`，然后输出排序结果。

### 第五层：人工复核包

程序会自动生成：

- 带标签说明的图片
- `review_sheet.csv`
- `manifest.json`

### 第六层：大模型自动分析报告

主流程跑完后，`run_pipeline.sh` 还会自动调用接入的大模型，
基于本轮审计产物生成一份中文结论报告：

- `llm_analysis_report.md`

这份报告更偏汇报和复盘表达，重点会自动总结：

- 核心问题类别
- 高分歧字段
- 对训练的影响
- 后续动作建议

## 6. 结果会生成到哪里

每次运行都会在：

- `output_root/run_name/`

生成一套完整产物。

核心文件有：

- `run_summary.json`
- `static_summary.json`
- `static_flagged_rows.jsonl`
- `consistency_summary.json`
- `consistency_flagged_rows.jsonl`
- `model_risk_summary.json`
- `model_risk_predictions.jsonl`
- `model_risk_flagged_rows.jsonl`
- `model_risk_flagged_rows.csv`
- `risk_ranked_rows.jsonl`
- `risk_ranked_rows.csv`
- `audit_report.md`
- `llm_analysis_report.md`
- `manual_review_pack/`

## 7. 人工复核怎么做

先看：

- `audit_report.md`
- `llm_analysis_report.md`
- `risk_ranked_rows.csv`

再打开：

- `manual_review_pack/images/`
- `manual_review_pack/review_sheet.csv`

图片顶部已经带了：

- 原标签
- 风险桶
- 静态问题
- 一致性问题
- 模型分歧信息

人工只需要判断三件事：

1. 这是明显错标吗
2. 这是规则边界问题吗
3. 这条标签可以保留吗

建议在 `review_sheet.csv` 中填写：

- `confirm_bad_label`
- `needs_rule_update`
- `keep`

## 8. 这套流程的验收标准

如果出现这些问题，建议先清洗再训练：

- 非 JSON 坏标签
- 非法字段值
- 大量 `status / skip_reason` 冲突
- 同图冲突明显
- train/val 泄漏明显
- 高风险样本中人工确认错标比例较高

## 9. 推荐的团队使用方式

建议固定成下面这个节奏：

1. 新数据集进入前先跑审计
2. 先修 `bad_label` 和 `schema_issue`
3. 再审 `model_disagreement` 和 `rule_boundary_issue`
4. 人工结论回写
5. 训练前复跑一次，确认问题下降

这样后面不管换 `v1.1.6`、`v1.1.8` 还是别的数据集，流程都能复用。
