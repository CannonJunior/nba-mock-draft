### 🔄 Project Awareness & Context
- **NEVER HARDCODE A VALUE** when the same value can be written into a configuration file and read into data instead.
- **Use consistent naming conventions, file structure, and architecture patterns** as described in this file.
- **Use `uv`** for all Python package management.

### 🌐 Port Management - CRITICAL
- **ALWAYS run this web application on port 8985 ONLY.** Never change the port without explicit user permission.
- **The default server port is 8985** - maintain this consistency across all sessions.

### 🧱 Code Structure & Modularity
- **Never create a file longer than 500 lines of code.**
- **Organize code into clearly separated modules**, grouped by feature or responsibility.
- **Use clear, consistent imports** (prefer relative imports within packages).
- **Use python_dotenv and load_env()** for environment variables.

### 🧪 Testing & Reliability
- **Always create Pytest unit tests for new features**.
- **Tests should live in a `/tests` folder** mirroring the main app structure.

### 📎 Style & Conventions
- **Follow PEP8**, use type hints, and format with `black`.
- **Use `pydantic` for data validation**.
- Write **docstrings for every function** using the Google style.

### 📦 Package Management - CRITICAL
- **ALWAYS use `uv` instead of `pip`** for Python package management.
- Commands: `uv add <package>`, `uv run <script>`, `uv sync`
- Use `uv run server.py` instead of `python3 server.py`
