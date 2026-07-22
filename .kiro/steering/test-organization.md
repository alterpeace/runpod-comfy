---
title: Test Organization Standards
inclusion: always
---

# Test Organization Standards

## Test Directory Structure

All tests must be organized in a dedicated `tests/` subdirectory within each project or module.

### Structure

```
project-name/
├── src/
│   ├── module1.py
│   └── module2.py
├── tests/
│   ├── __init__.py
│   ├── test_module1.py
│   └── test_module2.py
├── Pipfile
└── README.md
```

### Naming Conventions

- Test directory: `tests/`
- Test files: `test_*.py` or `*_test.py`
- Test classes: `Test*` (e.g., `TestComfyUIClient`)
- Test functions: `test_*` (e.g., `test_queue_prompt_success`)

### Test File Organization

Each test file should:
- Test a single module or component
- Use descriptive test class names to group related tests
- Include docstrings explaining what is being tested
- Use fixtures for common setup

### Running Tests

**Run all tests:**
```bash
pipenv run pytest
```

**Run specific test file:**
```bash
pipenv run pytest tests/test_module.py
```

**Run with coverage:**
```bash
pipenv run pytest --cov=src tests/
```

**Run with verbose output:**
```bash
pipenv run pytest -v
```

### DO NOT:

- Place test files in the same directory as source code
- Mix test code with production code
- Use non-standard test naming conventions
