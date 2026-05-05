```markdown
# browser-use Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you how to contribute to the `browser-use` repository, a Python web application built with Flask. You'll learn the project's coding conventions, commit patterns, file organization, and how to write and run tests. The guide also provides suggested commands for common development workflows.

## Coding Conventions

### File Naming
- Use **camelCase** for all file names.
  - Example: `userRoutes.py`, `dataManager.py`

### Import Style
- Use **relative imports** within the codebase.
  - Example:
    ```python
    from .utils import parseRequest
    from ..models.user import User
    ```

### Export Style
- Use **named exports** (explicitly listing what is exported from a module).
  - Example:
    ```python
    __all__ = ['parseRequest', 'formatResponse']
    ```

### Commit Patterns
- Follow **conventional commit** style.
- Use prefixes: `feat` (for features), `fix` (for bug fixes).
- Commit messages are concise, averaging 67 characters.
  - Example:
    ```
    feat: add user authentication to login route
    fix: correct typo in dataManager.py
    ```

## Workflows

### Add a New Feature
**Trigger:** When you want to introduce a new functionality.
**Command:** `/add-feature`

1. Create a new branch for your feature.
2. Implement the feature using camelCase file naming and relative imports.
3. Write or update tests (see Testing Patterns).
4. Commit your changes using the `feat:` prefix.
5. Open a pull request for review.

### Fix a Bug
**Trigger:** When you need to resolve a bug or issue.
**Command:** `/fix-bug`

1. Create a new branch for your fix.
2. Make the necessary code changes, following coding conventions.
3. Update or add tests to cover the fix.
4. Commit your changes using the `fix:` prefix.
5. Open a pull request for review.

### Run Tests
**Trigger:** To verify your changes do not break existing functionality.
**Command:** `/run-tests`

1. Locate test files matching the `*.test.*` pattern.
2. Run tests using the project's preferred test runner (framework unknown; check project documentation or use `pytest` as a default).
   - Example:
     ```
     pytest
     ```
3. Review test results and address any failures.

## Testing Patterns

- Test files follow the pattern: `*.test.*` (e.g., `userRoutes.test.py`).
- The testing framework is not specified; check for a `requirements.txt` or documentation for specifics.
- Place tests alongside the code they cover or in a dedicated tests directory.
- Example test file:
  ```python
  # userRoutes.test.py
  from .userRoutes import getUser

  def test_get_user_returns_valid_user():
      user = getUser(1)
      assert user.name == "Alice"
  ```

## Commands
| Command        | Purpose                                             |
|----------------|-----------------------------------------------------|
| /add-feature   | Start the process to add a new feature              |
| /fix-bug       | Start the process to fix a bug                      |
| /run-tests     | Run the test suite to validate code changes         |
```
