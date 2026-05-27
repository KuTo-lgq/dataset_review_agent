# Contributing

Thanks for taking a look at Dataset Review Agent.

This project is still evolving, so clear bug reports, usability feedback, and focused pull requests are especially helpful.

## Good First Contribution Areas

- documentation improvements
- better default configs
- UI polish for the review platform
- new issue heuristics in the audit pipeline
- more tests for edge cases
- deployment and packaging improvements

## Development Setup

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the platform locally if needed:

```bash
python -m uvicorn dataset_review_platform_backend.app.main:app --host 127.0.0.1 --port 8017
```

4. Run tests:

```bash
python dataset_review_platform_backend/tests/test_api_smoke.py
python dataset_audit_pipeline/tests/test_resume_retry_validation.py
python dataset_audit_pipeline/tests/test_auto_fix_loop.py
```

## Pull Request Guidelines

- keep changes focused
- prefer incremental improvements over large unrelated refactors
- add or update tests when behavior changes
- document new config fields or workflow changes
- avoid committing local runtime artifacts

## Runtime Artifacts That Should Not Be Committed

These are intentionally treated as local runtime state:

- `dataset_review_platform_backend/data/`
- `dataset_review_platform_backend/exports/`
- `dataset_review_platform_backend/generated_configs/`
- `dataset_review_platform_backend/imported_runs/`
- `dataset_review_platform_backend/task_logs/`
- `dataset_audit_pipeline/runs/`
- `dist/`

## Security and Privacy

Please do not include:

- real API keys
- internal dataset paths
- private audit results
- customer or business-sensitive sample data

If you notice a privacy issue in the repository, please open a minimal issue or contact the maintainer before amplifying the details publicly.
