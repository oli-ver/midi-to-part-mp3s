# Agent instructions for this repository

## General working rules

- Only change what was explicitly requested. If a requested change implies a
  side effect on build logic (e.g. deleting a file the Dockerfile or CI depends
  on, removing a lockfile), ask before doing it.
- Do not commit or push without being asked.
- Keep diffs minimal: no trailing whitespace changes, no reformatting of
  untouched code, preserve the file's final newline.
