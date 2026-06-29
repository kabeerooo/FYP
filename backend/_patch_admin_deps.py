"""One-shot patch: add require_admin dependency to all /api/admin/* routes."""
import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Ensure Depends is imported
if "Depends" not in content:
    content = content.replace(
        "from fastapi import FastAPI, Request, HTTPException, Response",
        "from fastapi import Depends, FastAPI, Request, HTTPException, Response",
    )

# Add dependency to every admin route decorator that doesn't already have it
pattern = r'(@app\.(?:get|post|put|delete)\("/api/admin/[^"]+"\))(\))'
replacement = r'\1, dependencies=[Depends(require_admin)]\2'
new_content = re.sub(pattern, replacement, content)

# Guard against accidental double-injection
new_content = new_content.replace(
    ", dependencies=[Depends(require_admin)], dependencies=[Depends(require_admin)]",
    ", dependencies=[Depends(require_admin)]",
)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(new_content)

patched = len(re.findall(r'dependencies=\[Depends\(require_admin\)\]', new_content))
print(f"Patched {patched} admin route(s).")
