# 操作手册

## 1. 先准备配置

通常我们只需要改配置，不需要改程序。

常用配置文件：

- `config.example.json`
- `configs/your_dataset.json`

最常改的字段有：

- `dataset_name`
- `dataset_dir`
- `splits`
- `output_root`
- `run_name`
- `manual_review.max_items`
- `model_risk.enabled`
- `model_risk.endpoint`
- `model_risk.model_name`
- `model_risk.selection`
- `model_risk.sample_size`

## 2. 设置 Gemini3 密钥

推荐用环境变量，不要写进配置文件。

```bash
export DATASET_AUDIT_API_KEY='你的密钥'
```

如果当前接口不需要密钥，可以不设置。

## 3. 启动审计

使用默认配置：

```bash
cd /home/reviewer/dataset-review-agent/dataset_audit_pipeline
bash run_pipeline.sh
```

使用指定配置：

```bash
cd /home/reviewer/dataset-review-agent/dataset_audit_pipeline
python3 run_audit.py --config configs/your_dataset.json
```

## 4. 先看哪些结果

程序跑完后，建议按这个顺序看：

1. `run_summary.json`
2. `audit_report.md`
3. `llm_analysis_report.md`
4. `static_summary.json`
5. `consistency_summary.json`
6. `model_risk_summary.json`
7. `risk_ranked_rows.csv`

## 5. 每个文件怎么看

`run_summary.json`

- 确认这次跑的是哪个数据集
- 看输出目录在哪
- 看本轮总样本数和问题数

`static_summary.json`

- 看硬错误
- 重点关注坏标签、非法枚举、同图冲突、train/val 泄漏

`consistency_summary.json`

- 看跨样本不稳定
- 重点关注同订单快速翻转、同 scene 冲突

`model_risk_summary.json`

- 看 Gemini3 这层一共复看了多少样本
- 看发现了多少分歧
- 看哪些字段最容易分歧

`llm_analysis_report.md`

- 看大模型根据整轮结果自动写出的结论
- 适合直接作为复盘或汇报初稿
- 建议和 `audit_report.md` 一起看

`risk_ranked_rows.csv`

- 这是最重要的工作队列
- 优先按 `risk_score` 从高到低处理

## 6. 人工复核怎么做

打开：

- `manual_review_pack/images/`
- `manual_review_pack/review_sheet.csv`

图片顶部已经叠加了：

- 原标签
- 静态问题
- 一致性问题
- 模型分歧信息

人工复核时，每张图只需要判断：

1. 这是明确错标吗
2. 这是规则没写清吗
3. 这条标签可以保留吗

推荐在 `review_sheet.csv` 的 `decision` 列填写：

- `confirm_bad_label`
- `needs_rule_update`
- `keep`

## 7. 复核后的处理建议

把人工复核结果分成三类：

1. 删除或重标的样本
2. 需要补规则定义的样本
3. 可保留但适合沉淀成 hard case 的样本

## 8. 什么时候不要直接训练

如果出现这些问题，建议先停下来清洗：

- `label_not_json_object > 0`
- 存在非法字段值
- 存在明显同图冲突
- `status` 和 `skip_reason` 大量不自洽
- 高风险样本里人工确认错标比例很高

## 9. 换新数据集怎么复用

换新数据集时，通常只改：

1. 配置文件
2. 数据集路径
3. split 文件名
4. 人工复核包数量

也就是说，大多数情况下：

换数据，不用重写程序。
