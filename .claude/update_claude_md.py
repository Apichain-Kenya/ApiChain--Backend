"""
Auto-update script for .claude/CLAUDE.md

Regenerates content between <!-- AUTO:SECTION --> markers without touching
hand-written sections (architecture decisions, design principles, known issues, etc.).

Auto-updated sections:
  - FILE_STRUCTURE: directory tree of the project
  - DEPENDENCIES: parsed from requirements.txt

Usage:
  python .claude/update_claude_md.py          # run manually
  (also runs automatically via post-merge git hook after git pull)
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

# Resolve paths relative to repo root (script lives in scripts/)
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CLAUDE_MD = REPO_ROOT / ".claude" / "CLAUDE.md"
BACKEND_DIR = REPO_ROOT / "backend"
REQUIREMENTS = BACKEND_DIR / "requirements.txt"


def generate_file_structure():
    """Generate directory tree for the project."""
    lines = [
        "```",
        "ApiChain--Backend/",
    ]

    def walk_dir(base_path, prefix="", rel_root=REPO_ROOT):
        entries = []
        try:
            for entry in sorted(base_path.iterdir()):
                name = entry.name
                # Skip hidden dirs (except .claude), venvs, caches, uploads content
                if name in (
                    ".git", ".venv", "venv", "__pycache__", "node_modules",
                    ".mypy_cache", ".pytest_cache", "htmlcov",
                ):
                    continue
                if name.startswith(".") and name not in (".claude", ".env", ".gitignore"):
                    continue
                entries.append(entry)
        except PermissionError:
            return []
        return entries

    def build_tree(base_path, prefix=""):
        result = []
        entries = walk_dir(base_path)
        for i, entry in enumerate(entries):
            connector = "\u2514\u2500\u2500 " if i == len(entries) - 1 else "\u251c\u2500\u2500 "
            extension = "    " if i == len(entries) - 1 else "\u2502   "

            if entry.is_dir():
                # Add description comments for known directories
                comment = get_dir_comment(entry.name, entry)
                suffix = f"/{comment}" if comment else "/"
                result.append(f"{prefix}{connector}{entry.name}{suffix}")
                result.extend(build_tree(entry, prefix + extension))
            else:
                comment = get_file_comment(entry.name, entry)
                suffix = comment if comment else ""
                result.append(f"{prefix}{connector}{entry.name}{suffix}")
        return result

    def get_dir_comment(name, path):
        comments = {
            ".claude": "",
            "scripts": "                        # Auto-update hooks and utilities",
            "hooks": "",
            "backend": "",
            "alembic": "",
            "versions": "",
            "uploads": "",
            "farmers": "                # Farmer document uploads",
            "aggregators": "            # Aggregator document uploads",
            "app": "",
            "models": "",
            "schemas": "",
            "routers": "",
        }
        return comments.get(name, "")

    def get_file_comment(name, path):
        comments = {
            "CLAUDE.md": "               # Project context for Claude Code",
            "README.md": "",
            ".gitignore": "",
            "post-merge": "            # Git hook template",
            "setup-hooks.sh": "              # Hook installer",
            "update_claude_md.py": "         # CLAUDE.md auto-updater",
            ".env": "                        # Environment variables (not committed)",
            "requirements.txt": "            # Python dependencies",
            "alembic.ini": "                 # Alembic configuration",
            "env.py": "                  # Migration environment",
            "script.py.mako": "          # Migration template",
            "main.py": "",
            "database.py": "",
            "auth.py": "",
            "public.py": "",
        }
        return comments.get(name, "")

    tree_lines = build_tree(REPO_ROOT)
    lines.extend(f"\u2502   {line}" if i == 0 else line for i, line in enumerate(tree_lines))

    # Fix: just add all lines under root
    result = ["```", "ApiChain--Backend/"]
    for line in build_tree(REPO_ROOT):
        result.append(line)
    result.append("```")
    return "\n".join(result)


def generate_dependencies():
    """Parse requirements.txt and generate a markdown table."""
    if not REQUIREMENTS.exists():
        return "| (requirements.txt not found) | | |"

    lines = [
        "| Package | Version | Purpose |",
        "|---------|---------|---------|",
    ]

    purpose_map = {
        "fastapi": "Web framework",
        "uvicorn": "ASGI server",
        "sqlalchemy": "ORM",
        "psycopg2-binary": "PostgreSQL driver",
        "python-dotenv": ".env file loading",
        "passlib": "Password hashing context",
        "bcrypt": "bcrypt algorithm",
        "python-jose": "JWT encoding/decoding",
        "cryptography": "Cryptographic functions",
        "python-multipart": "Form/file upload parsing",
        "geoalchemy2": "PostGIS support for SQLAlchemy",
        "shapely": "Geometric object creation",
        "alembic": "Database migrations",
        "twilio": "SMS OTP delivery",
        "pydantic[email]": "Email validation (EmailStr)",
        "pydantic": "Data validation",
    }

    with open(REQUIREMENTS) as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line or raw_line.startswith("#"):
                continue

            # Parse package==version or just package
            match = re.match(r"^([a-zA-Z0-9_\-\[\]]+)(?:[=<>!~]+(.+))?$", raw_line)
            if not match:
                continue

            pkg = match.group(1)
            version = match.group(2) or "latest"
            purpose = purpose_map.get(pkg.lower(), "")
            lines.append(f"| {pkg} | {version} | {purpose} |")

    return "\n".join(lines)


def update_section(content, section_name, new_content):
    """Replace content between <!-- AUTO:NAME --> and <!-- /AUTO:NAME --> markers."""
    pattern = re.compile(
        rf"(<!-- AUTO:{section_name} -->)\n.*?\n(<!-- /AUTO:{section_name} -->)",
        re.DOTALL,
    )
    replacement = f"\\1\n{new_content}\n\\2"
    updated, count = pattern.subn(replacement, content)
    if count == 0:
        print(f"  Warning: <!-- AUTO:{section_name} --> markers not found in CLAUDE.md")
    else:
        print(f"  Updated: {section_name}")
    return updated


def main():
    if not CLAUDE_MD.exists():
        print(f"Error: {CLAUDE_MD} not found. Nothing to update.")
        return

    print(f"Updating {CLAUDE_MD}")
    content = CLAUDE_MD.read_text(encoding="utf-8")

    # Update each auto-generated section
    content = update_section(content, "FILE_STRUCTURE", generate_file_structure())
    content = update_section(content, "DEPENDENCIES", generate_dependencies())

    CLAUDE_MD.write_text(content, encoding="utf-8")
    print(f"Done. Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
