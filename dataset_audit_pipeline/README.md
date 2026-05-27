# 数据质量审计 Pipeline

这套程序用于对视觉数据集做系统化审计，重点发现：

- 静态标签错误
- 静态标签冲突的自动修复机会
- 标签内部逻辑冲突
- 同图 / 同订单 / 同场景一致性问题
- 模型辅助识别出的高风险样本
- 人工复核候选集合

## 主要文件

- `run_audit.py`：主入口
- `generate_llm_analysis_report.py`：基于审计结果生成大模型分析报告
- `run_pipeline.sh`：一键执行入口
- `config.example.json`：通用配置模板
- `tests/test_auto_fix_loop.py`：自动修复回路测试
- `tests/test_resume_retry_validation.py`：续跑 / 重试 / 结构校验测试

## 快速开始

```bash
cd dataset_audit_pipeline
python run_audit.py --config config.example.json
```

如果需要生成大模型分析报告，请先设置：

```bash
export DATASET_AUDIT_API_KEY='your-key'
```

如果要启用“静态冲突自动修复”，请在配置中打开 `auto_fix.enabled`。这一步会先做规则修复，再只对白名单字段发起看图修标，并在每轮结束后重新计算静态问题数。

## 主要产物

每轮运行会在 `output_root/run_name/` 下生成：

- `run_summary.json`
- `auto_fix_summary.json`
- `auto_fix_changes.jsonl`
- `auto_fixed_dataset/`
- `static_summary.json`
- `consistency_summary.json`
- `model_risk_summary.json`
- `risk_ranked_rows.csv`
- `audit_report.md`
- `llm_analysis_report.md`
- `manual_review_pack/`
