# claude-rules

Правила и скилы для Claude Code: как писать Python и Go. Всё лежит в `.claude/` и
устанавливается в `~/.claude/`, откуда Claude Code читает их в каждом проекте.

## Что где

| Путь | Когда загружается |
|---|---|
| `.claude/rules/python/*.md`, `.claude/rules/go/*.md` | при первом чтении `.py` / `.go` файла: у каждого файла `paths:` во front matter |
| `.claude/rules/*/new-files.md` | в каждой сессии — единственные файлы без front matter: закрывают случай, когда проект создаётся в пустой папке и читать ещё нечего |
| `.claude/skills/python-*/`, `.claude/skills/go-*/` | описание попадает в список, когда прочитан или записан файл из `paths:` скила; сам скил загружается, когда работа совпала с описанием, или по `/имя` |

Карта Python-скилов — таблица в `.claude/rules/python/core.md`. Как писать и проверять правила —
скил `python-rules-authoring` (для Go — `go-rules-authoring`, который ссылается на общие разделы).

## Установка

Правила и скилы копируются в `~/.claude` поверх старых. Синхронизация зеркальная внутри каждой
папки, так что удалённые в репозитории файлы исчезают и там; ничего вне этих папок не трогается.

```bash
for lang in python go; do
  rsync -a --delete --exclude __pycache__ .claude/rules/$lang/ ~/.claude/rules/$lang/
done
for skill in .claude/skills/*/; do
  rsync -a --delete --exclude __pycache__ "$skill" ~/.claude/skills/"$(basename "$skill")"/
done
```

Если задан `$CLAUDE_CONFIG_DIR`, подставьте его вместо `~/.claude`.

## Проверка

```bash
python .claude/skills/python-rules-authoring/scripts/check_rules.py .claude
```

Exit 0 — чисто. Скрипт проверяет бюджет строк (800 на всё, что грузится для каждого `.py`; 500 на
`SKILL.md`), что каждый `python`-блок парсится, что упомянутые скилы и файлы существуют, что
`core.md` называет каждый скил и что у каждого `SKILL.md` есть `name`, `description` и `paths`.
Что он не проверяет и что делается руками: каждый `CORRECT`-пример проходит `mypy --strict` и
запускается против библиотеки той версии, которую называет скил.
