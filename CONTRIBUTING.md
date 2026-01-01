# Contributing to Lightbox

Thanks for your interest in contributing to Lightbox!

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/robertkeenan/lightbox.git
   cd lightbox
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install in development mode:
   ```bash
   pip install -e ".[dev]"
   ```

4. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=lightbox --cov-report=term-missing

# Run specific test file
pytest tests/test_core.py
```

## Code Quality

We use Ruff for linting/formatting and mypy for type checking:

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/
```

Pre-commit hooks run these automatically on commit.

## Pull Request Guidelines

1. **Fork and branch**: Create a feature branch from `main`
2. **Write tests**: Add tests for new functionality
3. **Run checks**: Ensure `pytest`, `ruff`, and `mypy` pass
4. **Keep commits clean**: Use clear, descriptive commit messages
5. **Update docs**: Update README or docstrings if needed

## Code Style

- Follow existing patterns in the codebase
- Use type hints for all function signatures
- Write docstrings for public functions
- Keep functions focused and small

## Questions?

Open an issue for questions or discussion.
