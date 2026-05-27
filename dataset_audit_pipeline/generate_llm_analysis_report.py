#!/usr/bin/env python3
"""Generate an LLM-written markdown summary from audit artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate LLM analysis markdown from audit outputs.")
    parser.add_argument("--run-dir", required=True, help="Audit output directory.")
    parser.add_argument("--endpoint", required=True, help="Chat completions endpoint.")
    parser.add_argument("--model-name", required=True, help="Model name.")
    parser.add_argument("--api-key-env", default="DATASET_AUDIT_API_KEY", help="Environment variable name for API key.")
    parser.add_argument("--output-name", default="llm_analysis_report.md", help="Output markdown filename.")
    parser.add_argument("--top-k", type=int, default=12, help="How many top risk samples to include.")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max output tokens.")
    parser.add_argument("--temperature", type=float, default=0, help="Sampling temperature.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv_rows(path: Path, limit: int) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    return rows[:limit]


def load_jsonl_rows(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if len(rows) >= limit:
                break
    return rows


def normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def build_prompt(context: dict[str, Any]) -> str:
    return f"""
你是一个负责数据质量审计复盘的高级分析助手。请根据下面提供的审计结果，生成一份中文 Markdown 报告。

要求：
1. 不要复述无意义过程，重点写结论和判断。
2. 要区分“明确坏标签 / schema问题 / 规则边界问题 / 模型分歧问题”。
3. 要解释这些问题会如何影响训练收益。
4. 给出清晰的后续动作建议，按优先级写。
5. 如果发现模型辅助复核结果里某些字段分歧明显集中，要单独点出来。
6. 报告风格偏正式，适合团队内部汇报。
7. 只输出 Markdown 正文，不要加代码块围栏。

建议结构：
- 标题
- 一、测试概览
- 二、核心结论
- 三、主要问题拆解
- 四、模型辅助复核发现
- 五、对训练的影响
- 六、建议的后续动作
- 七、一句话总结

以下是审计上下文(JSON)：
{json.dumps(context, ensure_ascii=False, indent=2)}
""".strip()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir)
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"Missing API key env: {args.api_key_env}")
    if requests is None and httpx is None:
        raise SystemExit("Neither requests nor httpx is available.")

    run_summary = load_json(run_dir / "run_summary.json")
    static_summary = load_json(run_dir / "static_summary.json")
    consistency_summary = load_json(run_dir / "consistency_summary.json")
    model_risk_summary = load_json(run_dir / "model_risk_summary.json")
    top_risk_rows = load_csv_rows(run_dir / "risk_ranked_rows.csv", args.top_k)
    model_flagged_rows = load_jsonl_rows(run_dir / "model_risk_flagged_rows.jsonl", min(20, args.top_k))

    context = {
        "run_summary": run_summary,
        "static_summary": static_summary,
        "consistency_summary": consistency_summary,
        "model_risk_summary": model_risk_summary,
        "top_risk_rows": top_risk_rows,
        "model_flagged_rows_sample": model_flagged_rows,
    }

    payload = {
        "model": args.model_name,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "messages": [
            {
                "role": "user",
                "content": build_prompt(context),
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if requests is not None:
        response = requests.post(args.endpoint, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
    else:
        with httpx.Client(timeout=300) as client:
            response = client.post(args.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    content = normalize_content(data["choices"][0]["message"]["content"]).strip()
    if not content:
        raise SystemExit("LLM returned empty content.")

    output_path = run_dir / args.output_name
    output_path.write_text(content + "\n", encoding="utf-8")
    print(json.dumps({"output_path": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
