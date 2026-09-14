# Parental Safety Platform — Backend API (Phase 3)

FastAPI + Pydantic v2 REST service serving network device discovery and DNS monitoring data.

## Quick Start

```bash
# In platform root:
source collector/.venv/bin/activate

# Launch the API server:
parental-api start --port 8000

# Open interactive documentation:
# http://localhost:8000/docs
```

## Running Tests

```bash
python -m pytest backend/tests/ -v
```
