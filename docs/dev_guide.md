# Developer Guidelines

## Directory Structure
- `src/`: Source code
- `account/`: Account management logic
- `verify/`: **All verification scripts and ad-hoc tests must be placed here.**
- `docs/`: Documentation

## Verification Scripts
- Always place verification scripts in `verify/`.
- Do not add `verify/` to git if they are temporary, or ensure `.gitignore` handles them if needed.
