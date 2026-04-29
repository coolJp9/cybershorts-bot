# Contributing to CyberShorts Bot

Thank you for considering a contribution! This document covers how to get your changes merged smoothly.

---

## Code of Conduct

Be respectful and constructive. Discrimination, harassment, or hostile behaviour will not be tolerated.

---

## How to Contribute

### Reporting Bugs

1. Search [existing issues](../../issues) first.
2. If the bug is new, open an issue and include:
   - A clear, descriptive title
   - Steps to reproduce
   - Expected vs actual behaviour
   - Python version, OS, and relevant log output

### Suggesting Features

Open a [Feature Request](../../issues/new?template=feature_request.md) issue and describe:
- What problem you are solving
- What the solution should look like
- Any relevant alternatives you considered

### Submitting a Pull Request

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```

2. **Install dev dependencies:**
   ```bash
   pip install -r requirements-dev.txt
   pre-commit install
   ```

3. **Write your changes** following the style guide below.

4. **Add or update tests** in `tests/`. All new public functions should have at least one test.

5. **Run the quality checks:**
   ```bash
   make lint
   make test
   ```

6. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat: add subtitle burn-in to assembled video
   fix: handle RSS feed with missing pubDate field
   docs: update README setup section
   ```

7. **Open a Pull Request** against `main`. Fill in the PR template.

---

## Code Style

- **Formatter:** `black` (line length 100)
- **Linter:** `ruff`
- **Type hints:** required for all public functions
- **Docstrings:** one-line summary for public functions; multi-line only if the behaviour is non-obvious
- **Logging:** use module-level `log = logging.getLogger("CyberBot.<module>")`, not print statements
- **No hardcoded secrets:** all credentials and API keys must come from environment variables

---

## Module Conventions

| Layer              | Location                      | Responsibility                         |
|--------------------|-------------------------------|----------------------------------------|
| Configuration      | `app/config/settings.py`      | Single source of truth for all config  |
| Fetchers           | `app/fetchers/`               | HTTP I/O only; return plain dicts      |
| Summarizer         | `app/summarizer/`             | Story selection and scoring logic      |
| Script generator   | `app/script_generator/`       | AI prompt construction and fallbacks   |
| TTS                | `app/tts/`                    | Audio generation; no business logic    |
| Video engine       | `app/video_engine/`           | FFmpeg wrappers; no AI calls           |
| Uploader           | `app/uploader/`               | YouTube API; quota and credential mgmt |
| Utilities          | `app/utils/`                  | Shared helpers with no domain logic    |

---

## Running Tests

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## Commit Signing

We encourage (but do not require) GPG-signed commits.

---

Thank you for your time and effort!
