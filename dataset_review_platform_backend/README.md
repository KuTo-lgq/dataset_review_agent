# 数据复核平台后端

这是本项目的本地验收平台后端与静态前端资源，负责把审计结果变成可交互的人工复核工作台。

## 能力

- 接入原始数据集目录或已有 audit run 目录
- 发起本地 / 远端审计任务
- 展示 Agent 验收结论
- 展示自动修复摘要
- 展示模型自动改标记录
- 展示审计报告和模型分析报告
- 浏览高风险样本并人工修正标签
- 导出 cleaned dataset
- 基于导出数据集再次发起审计
- 支持任务进度、停止、失败后续跑

## 现在的主工作流

1. 接入修后的数据集目录，或者接入已有 audit run
2. 发起审计任务
3. 等待静态审计、auto-fix、一致性检查、模型风险发现完成
4. 阅读 Agent 结论
5. 查看自动修复摘要和模型自动改标记录
6. 对仍有风险的样本做人工改标
7. 导出 cleaned dataset
8. 生成中文验收报告

如果当前 run 的剩余样本都已经是 `clean`，并且没有阻塞问题，平台会直接给出“可直接导出”的状态，而不是强制继续人工复核。

## 启动

在项目根目录运行：

```bash
python -m uvicorn dataset_review_platform_backend.app.main:app --host 127.0.0.1 --port 8017
```

## 测试

```bash
python dataset_review_platform_backend/tests/test_api_smoke.py
```

## 目录

```text
dataset_review_platform_backend/
  app/
  static/
  tests/
  demo_data/
```

运行期目录会自动创建：

- `data/`
- `exports/`
- `generated_configs/`
- `imported_runs/`
- `task_logs/`

## 配置说明

平台支持通过环境变量注入模型端点、API Key，以及远端审计配置。开源仓库中的默认值都是占位示例，实际使用时请通过 `.env` 或 shell 环境自行配置。
