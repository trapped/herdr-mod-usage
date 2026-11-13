#!/usr/bin/env python3
"""Rebuild layouts/main-mods.json: Herdr's current `main` layout plus every mod's layout.json.

Herdr replaces its shipped `main` layout on every start and never updates copies of it, so a
layout that adds a mod is derived instead of copied. Each mod that wants a place in the window
ships a layout.json with one edit:

  {"insert_before": "<block id>", "block": {...}}   put a block in front of that one
  {"replace_mod": "<mod>", "build": "<script>"}     show this mod wherever <mod> is shown;
                                                    "build" runs first and must exit 0

An edit that does not apply is skipped, and the rest of the layout is still written.
Mods run this on every start, so the layout follows Herdr updates. Once, by hand:
  python3 sync.py && herdr-app do layout.switch '{"name":"main-mods"}'

The same file ships in every mod that uses it. Keep the copies identical.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

MODS = Path(os.path.abspath(__file__)).parent.parent
LAYOUTS = MODS.parent / "layouts"


def walk(node):
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def apply(layout, edit, mod):
    if "build" in edit:
        r = subprocess.run([sys.executable, str(mod / edit["build"])], capture_output=True, text=True)
        if (r.stdout + r.stderr).strip():
            print((r.stdout + r.stderr).strip())
        if r.returncode != 0:
            return False
    done = False
    for node in walk(layout):
        children = node.get("children") or []
        for i, child in enumerate(children):
            if "insert_before" in edit and child.get("id") == edit["insert_before"]:
                children.insert(i, edit["block"])
                return True
        if "replace_mod" in edit and (node.get("content") or {}).get("mod") == edit["replace_mod"]:
            node["content"]["mod"] = mod.name
            done = True
    return done


def main():
    layout = json.loads((LAYOUTS / "main.json").read_text())
    for path in sorted(MODS.glob("*/layout.json")):
        try:
            applied = apply(layout, json.loads(path.read_text()), path.parent)
        except (OSError, ValueError) as e:
            applied = False
            print(f"{path.parent.name}: {e}")
        if not applied:
            print(f"{path.parent.name}: its layout edit did not apply, skipped")
    target = LAYOUTS / "main-mods.json"
    try:
        if json.loads(target.read_text()) == layout:
            return
    except (OSError, ValueError):
        pass
    tmp = target.with_name(f".main-mods.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(layout, indent=2) + "\n")
    os.replace(tmp, target)
    print("updated layouts/main-mods.json")


if __name__ == "__main__":
    main()
