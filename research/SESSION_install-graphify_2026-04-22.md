---
date: 2026-04-22
branch: feat/rebrand
topic: install-graphify
model: qwen3.6-35b-a3b
---

# AI Research Pitch — Install graphify knowledge graph

## 1. Hook

> _Un SKILL.md dont la `description` frontmatter est le seul champ de trigger — modifier uniquement ce champ pour ajuster le matching, jamais le contenu._

---

## 2. Pourquoi on a exploré

Installation complète de graphify (knowledge graph pour codebase) dans whispy, de l'installation CLI aux hooks git, `.graphifyignore`, `.gitignore`, README, et fix du trigger research-log.

---

## 3. Ce qu'on a fait (et avec quels outils)

### Turn 1 — Install graphify for OpenCode · fetch, bash, write, read

**Instruction :** User requested to install graphify application.

**Actions :**
- `fetch(https://github.com/safishamsi/graphify)` → Got README with install instructions
- `bash(uv tool install graphifyy)` → Installed graphifyy v0.4.29 with 24 packages
- `bash(graphify opencode install)` → Integrated with OpenCode
- `bash(git branch --show-current)` → Current branch: feat/rebrand
- `bash(git log --oneline -5)` → Captured recent commit history
- `write(research/SESSION_install-graphify_2026-04-22.md)` → Created this session log

**Output :**
- `.opencode/plugins/graphify.js` → Created
- `.opencode/opencode.json` → Updated
- `AGENTS.md` → Updated
- `research/SESSION_install-graphify_2026-04-22.md` → Created

**Blockers :** aucun

---

### Turn 2 — Initial graph build · write, bash

**Instruction :** User requested initial graph build and `.graphifyignore` configuration.

**Actions :**
- `write(.graphifyignore)` → Created ignore file with patterns: `node_modules/`, `dist/`, `build/`, `*.generated.py`, `.venv/`, `__pycache__/`, `*.pyc`, `*.egg-info/`, `.coverage`, `htmlcov/`, `.pytest_cache/`
- `bash(graphify update .)` → First graph build: 621 nodes, 2107 edges, 16 communities

**Output :**
- `.graphifyignore` → Created
- `graphify-out/graph.json` → Generated (621 nodes, 2107 edges, 16 communities)
- `graphify-out/graph.html` → Generated
- `graphify-out/GRAPH_REPORT.md` → Generated

**Blockers :** aucun — graph count unchanged after `.graphifyignore` (no `node_modules` or `build/` dirs).

---

### Turn 3 — Git hooks & `.gitignore` · bash, read, edit

**Instruction :** User requested git hook installation and `.gitignore` update for graphify output.

**Actions :**
- `bash(graphify hook install)` → Installed post-commit and post-checkout hooks
- `read(.gitignore)` → Reviewed existing gitignore
- `edit(.gitignore)` → Added `graphify-out/` and `raw/` to gitignore

**Output :**
- `.git/hooks/post-commit` → Installed
- `.git/hooks/post-checkout` → Installed
- `.gitignore` → Updated

**Blockers :** aucun

---

### Turn 4 — README documentation · read, edit

**Instruction :** User requested README update with graphify instructions for project users.

**Actions :**
- `read(README.md)` → Reviewed existing README
- `edit(README.md)` → Added "Knowledge Graph (graphify)" section with setup, commands table, visualization, and configuration
- `edit(README.md)` → Removed duplicate "License" section

**Output :**
- `README.md` → Updated (graphify section + license dedup)

**Blockers :** aucun

---

### Turn 5 — research-log trigger fix · read, edit

**Instruction :** User reported that the research-log skill was not triggering correctly and asked what was changed.

**Actions :**
- `read(skills/research-log/SKILL.md)` → Reviewed skill file (197 lines, no prior modifications)
- `edit(skills/research-log/SKILL.md)` → Updated `description` frontmatter with explicit `Auto-trigger on:` keyword list

**Output :**
- `skills/research-log/SKILL.md` → Updated (added auto-trigger keywords)

**Blockers :** aucun — fix was a single frontmatter `description` update.

---

### Turn 6 — Template migration · read, edit

**Instruction :** User changed the research-log template and requested reformatting the session log to match.

**Actions :**
- `read(skills/research-log/SKILL.md)` → Read new "AI Research Pitch" template (246 lines)
- `write(research/SESSION_install-graphify_2026-04-22.md)` → Restructured entire log to new skeleton (sections 1-7, French headings, new turn format)

**Output :**
- `research/SESSION_install-graphify_2026-04-22.md` → Reformatted to new template

**Blockers :** aucun

---

## 4. Ce qu'on a appris

✅ **Ce qui marche :** Graphify CLI avec hooks git — le graphe se rebuild automatiquement au commit/checkout

❌ **Ce qui ne marche pas :** Le trigger du skill research-log ne matche pas sans mots-clés explicites dans le `description` frontmatter

🔥 **Ce qui change la donne :** Le `description` dans le frontmatter d'un SKILL.md est le SEUL champ de trigger — modifier uniquement ce champ pour ajuster le matching, jamais le contenu du fichier.

---

## 5. Démo

> _1 use case simple — mis à jour dès qu'un artefact clé est produit_

Graphify knowledge graph interactif : `open graphify-out/graph.html` — 621 nœuds, 2107 arêtes, 16 communautés navigables.

---

## 6. Opportunités Zenika

**Mission 1 :** Intégration knowledge graph dans des projets Python/macOS

**Mission 2 :** Automatisation de la documentation codebase via graphify

**Offre potentielle :** Setup complet graphify + hooks + `.graphifyignore` pour équipes de développement

---

## 7. Next Steps

> _Call to action — mis à jour à chaque turn qui révèle une action claire_

- [ ] Explore graphify commands: `graphify query`, `graphify path`, `graphify explain`
- [ ] Use `graphify watch .` for continuous rebuild during development
- [ ] Consider adding `raw/` content for non-code assets (docs, diagrams, etc.) via `graphify add <url>`
- [x] Test graphify integration with Linear MCP for ticket creation

---

## Références & Artefacts

- https://linear.app/zenika/issue/ZEN-21/ai-research-pitch-install-graphify-knowledge-graph
- https://github.com/safishamsi/graphify
- `.opencode/plugins/graphify.js`
- `.opencode/opencode.json`
- `AGENTS.md`
- `research/SESSION_install-graphify_2026-04-22.md`
- `skills/research-log/SKILL.md`
- `.graphifyignore`
- `.gitignore`
- `README.md`
- `graphify-out/graph.json`
- `graphify-out/graph.html`
- `graphify-out/GRAPH_REPORT.md`
