#!/usr/bin/env python3
"""
Reels Vault MCP Server

MCP server for querying your Reels Vault knowledge base from Claude, Cursor, or any MCP-compatible AI tool.

Usage:
    python3 mcp/server.py

Environment:
    REELS_VAULT_PATH: Path to your Reels Vault knowledge base (default: ./vault)
"""

import os
import json
import glob
from pathlib import Path
from typing import Optional

VAULT_PATH = os.environ.get("REELS_VAULT_PATH", os.path.join(os.path.dirname(__file__), "..", "vault"))


def search_vault(query: str, filter_creator: Optional[str] = None, filter_topic: Optional[str] = None) -> list:
    """Search the vault for matching content."""
    results = []
    vault = Path(VAULT_PATH)

    # Search extracts
    extracts_dir = vault / "extracts"
    if extracts_dir.exists():
        for f in extracts_dir.glob("*.md"):
            if f.name == "Extracts.md":
                continue
            content = f.read_text()
            if query.lower() in content.lower():
                if filter_creator and filter_creator.lower() not in content.lower():
                    continue
                results.append({
                    "type": "extract",
                    "file": str(f),
                    "name": f.stem,
                    "snippet": content[:500],
                })

    # Search topics
    topics_dir = vault / "topics"
    if topics_dir.exists():
        for f in topics_dir.glob("*.md"):
            content = f.read_text()
            if query.lower() in content.lower():
                if filter_topic and filter_topic.lower() not in f.stem.lower():
                    continue
                results.append({
                    "type": "topic",
                    "file": str(f),
                    "name": f.stem,
                    "snippet": content[:500],
                })

    # Search recipes
    recipes_dir = vault / "recipes"
    if recipes_dir.exists():
        for f in recipes_dir.glob("*.md"):
            if f.name == "Recipe Book.md":
                continue
            content = f.read_text()
            if query.lower() in content.lower():
                results.append({
                    "type": "recipe",
                    "file": str(f),
                    "name": f.stem,
                    "snippet": content[:500],
                })

    return results


def get_creator(creator_name: str) -> dict:
    """Get all content from a specific creator."""
    vault = Path(VAULT_PATH)
    creators_dir = vault / "creators"

    for f in creators_dir.glob("*.md"):
        if creator_name.lower() in f.stem.lower():
            return {
                "name": f.stem,
                "content": f.read_text(),
                "file": str(f),
            }

    return None


def list_creators() -> list:
    """List all creators in the vault."""
    vault = Path(VAULT_PATH)
    creators_dir = vault / "creators"
    creators = []

    if creators_dir.exists():
        for f in creators_dir.glob("*.md"):
            if f.name not in ("Creator Profiles.md", "Creator Template.md"):
                creators.append(f.stem)

    return creators


def list_topics() -> list:
    """List all topics in the vault."""
    vault = Path(VAULT_PATH)
    topics_dir = vault / "topics"
    topics = []

    if topics_dir.exists():
        for f in topics_dir.glob("*.md"):
            topics.append(f.stem)

    return topics


def get_recipes(topic: Optional[str] = None) -> list:
    """Get recipes, optionally filtered by topic."""
    vault = Path(VAULT_PATH)
    recipes_dir = vault / "recipes"
    recipes = []

    if recipes_dir.exists():
        for f in recipes_dir.glob("*.md"):
            if f.name == "Recipe Book.md":
                continue
            content = f.read_text()
            if topic and topic.lower() not in content.lower():
                continue
            recipes.append({
                "name": f.stem,
                "content": content,
            })

    return recipes


if __name__ == "__main__":
    # Simple test
    print("Reels Vault MCP Server")
    print(f"Vault path: {VAULT_PATH}")
    print(f"Creators: {list_creators()}")
    print(f"Topics: {list_topics()}")
