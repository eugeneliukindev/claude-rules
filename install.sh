#!/usr/bin/env bash
# Link the ruleset and skills into each agent's home config; rerun after adding a skill.
set -euo pipefail

repository="$(cd "$(dirname "$0")" && pwd)"

link() {
  local source="$1" target="$2"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    # an identical copy from an earlier install gives way to the link; anything else is the user's
    if diff -rq "$source" "$target" >/dev/null 2>&1; then
      rm -r "$target"
    else
      echo "skip $target: it differs from $source, merge it by hand" >&2
      return
    fi
  fi
  mkdir -p "$(dirname "$target")"
  ln -sfn "$source" "$target"
  echo "$target -> $source"
}

# Claude Code reads every file in ~/.claude/rules; Codex and Zed read one personal AGENTS.md each
link "$repository/AGENTS.md" ~/.claude/rules/design.md
link "$repository/AGENTS.md" ~/.codex/AGENTS.md
link "$repository/AGENTS.md" ~/.config/zed/AGENTS.md

# Claude Code reads only ~/.claude/skills; the other Agent Skills hosts read ~/.agents/skills
for skill in "$repository"/skills/*/; do
  skill="${skill%/}"
  link "$skill" ~/.claude/skills/"$(basename "$skill")"
  link "$skill" ~/.agents/skills/"$(basename "$skill")"
done
