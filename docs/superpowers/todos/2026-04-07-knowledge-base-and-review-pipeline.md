# Knowledge Base + Review Pipeline — Combined Task Checklist

**Created:** 2026-04-07
**For:** Intern onboarding — execute tasks sequentially, check off as you go.

> **Full details for each task are in the original plans:**
> - KB Plan: `docs/superpowers/plans/2026-04-07-knowledge-base-implementation.md`
> - Pipeline Plan: `docs/superpowers/plans/2026-04-07-review-pipeline.md`
>
> This checklist gives you the execution order and a short description.
> When in doubt, open the referenced plan and read the full task.

---

## Phase A: Environment Setup

- [ ] **A1. Install Node.js >= 22** *(KB Plan → Task 1)*
  - Install via https://nodejs.org or `winget install OpenJS.NodeJS.LTS`
  - Verify: `node --version` → v22+

- [ ] **A2. Install MinerU Document Explorer** *(KB Plan → Task 2)*
  - `npm install -g mineru-document-explorer`
  - `pip install pymupdf python-docx python-pptx openpyxl`
  - Verify: `qmd --version`

- [ ] **A3. Create root .gitignore** *(Pipeline Plan → Task 1)*
  - Ignore `data/`, `*.db`, `__pycache__/`, `tmp_review_*.json`
  - Commit

---

## Phase B: Document Processing & Knowledge Base

- [ ] **B1. Write XLSX → Markdown conversion script** *(KB Plan → Task 3)*
  - Create `scripts/xlsx_to_markdown.py`
  - Run conversion for 3 Excel files → `docs/knowledge-base/.staging/`
  - Commit

- [ ] **B2. Index all 26 documents** *(KB Plan → Task 4)*
  - Create `docs/knowledge-base/` directory structure (wiki/, index/, .manual-rules/)
  - `qmd index docs/医院材料学习/` (PDF, DOCX, PPTX)
  - `qmd index docs/knowledge-base/.staging/` (converted XLSX)
  - Verify with test searches: "针法价格", "推拿 一级"
  - Commit

- [ ] **B3. Generate the wiki** *(KB Plan → Task 5)*
  - Create `docs/knowledge-base/wiki-seed.yml` with 5 categories
  - Run `qmd wiki ingest`
  - Review generated pages, reorganize if needed
  - Commit

- [ ] **B4. Configure MCP server** *(KB Plan → Task 6)*
  - Create `.cursor/mcp.json` → `http://localhost:8181/mcp`
  - Start daemon: `qmd mcp --http --daemon`
  - Verify health check
  - Commit

---

## Phase C: Review Pipeline Infrastructure

- [ ] **C1. Write failing tests for review_db.py** *(Pipeline Plan → Task 2)*
  - Create `tests/test_review_db.py` (10 tests)
  - Run tests → all FAIL (module not found)
  - Commit

- [ ] **C2. Implement review_db.py** *(Pipeline Plan → Task 3)*
  - Create `scripts/review_db.py` (SQLite DB + CLI: init/save/status/summary/export)
  - Run tests → all 10 PASS
  - Commit

- [ ] **C3. Verify review_db.py CLI** *(Pipeline Plan → Task 4)*
  - Test `init`, `save`, `status`, `summary` commands end-to-end
  - Clean up test files

---

## Phase D: Skill Versioning (Archive v1)

- [ ] **D1. Archive all 3 existing skills as v1** *(KB Plan → Task 7)*
  - Copy `tcm-treatment-plan/` files → `tcm-treatment-plan/v1/`
  - Copy `tcm-treatment-review/` files → `tcm-treatment-review/v1/`
  - Copy `sh-yb-policy-monitor/` files → `sh-yb-policy-monitor/v1/`
  - Verify 7 archived files across 3 skills
  - Commit

---

## Phase E: Create & Refactor Skills to v2

- [ ] **E1. Create knowledge-base-update skill (v1)** *(KB Plan → Task 8)*
  - Create `skills/knowledge-base-update/v1/SKILL.md` (3 ingestion modes: docs/policy/rules)
  - Copy to root `skills/knowledge-base-update/SKILL.md`
  - Commit

- [ ] **E2. Refactor tcm-treatment-plan to v2** *(KB Plan → Task 9)*
  - Create `skills/tcm-treatment-plan/v2/SKILL.md` — replace hardcoded pricing with KB queries
  - Copy `方案参考.md` to v2/
  - Update root SKILL.md → v2
  - Commit

- [ ] **E3. Rewrite tcm-treatment-review to v2 (pipeline + KB)** *(Pipeline Plan → Task 5 + KB Plan → Task 10)*
  - Create `skills/tcm-treatment-review/v2/SKILL.md` — concurrent pipeline + KB pricing
  - Copy `examples.md` to v2/
  - Update root SKILL.md → v2
  - **This is the merged v2:** one-image-per-subagent pipeline + MCP pricing + SQLite storage + fallback to static prices
  - Commit

- [ ] **E4. Refactor sh-yb-policy-monitor to v2** *(KB Plan → Task 11)*
  - Create `skills/sh-yb-policy-monitor/v2/SKILL.md` — add KB update trigger after fetch
  - Copy `scripts/fetch_policies.py` to v2/
  - Update root SKILL.md → v2
  - Commit

---

## Phase F: Testing & Validation

- [ ] **F1. Test KB update — docs mode** *(KB Plan → Task 12)*
  - Ask agent: "更新知识库，扫描新文档"
  - Verify manifest check + indexing works

- [ ] **F2. Test tcm-treatment-plan v2** *(KB Plan → Task 13)*
  - Ask agent to generate a plan for: 男性，45岁，75kg，颈部酸痛3个月
  - Verify MCP tool calls appear + correct pricing

- [ ] **F3. Test tcm-treatment-review v2 — single image** *(Pipeline Plan → Task 6)*
  - Provide 1 image (or text description)
  - Verify KB pricing query + 7-dimension table output

- [ ] **F4. Test tcm-treatment-review v2 — batch pipeline** *(Pipeline Plan → Task 7)*
  - Provide 3 images (one with 2 stacked forms)
  - Verify: 3 subagents dispatched, 4 results in SQLite, summary report correct

- [ ] **F5. Test multi-form image detection** *(Pipeline Plan → Task 8)*
  - Provide 1 image with 2 forms + irrelevant content
  - Verify: 2 forms identified, irrelevant content ignored, needle stacking caught

- [ ] **F6. Test fallback — MCP down** *(KB Plan → Task 15)*
  - Stop MCP: `qmd mcp stop`
  - Test treatment plan → warning appears
  - Test treatment review → static prices used, warning appears
  - Restart MCP: `qmd mcp --http --daemon`

- [ ] **F7. Test incremental indexing** *(KB Plan → Task 16)*
  - Add a test rule to `.manual-rules/`
  - Index + verify searchable
  - Clean up

- [ ] **F8. Final verification** *(Pipeline Plan → Task 9)*
  - Run `python -m pytest tests/test_review_db.py -v` → all PASS
  - Verify complete file structure
  - Final commit

---

## Quick Reference: Final File Structure

```
hospital-claw/
├── .cursor/mcp.json                           # MinerU MCP config
├── .gitignore                                 # Runtime artifacts ignored
│
├── scripts/
│   ├── xlsx_to_markdown.py                    # XLSX → MD converter
│   └── review_db.py                           # Review pipeline SQLite DB + CLI
│
├── tests/
│   └── test_review_db.py                      # 10 unit tests for review_db
│
├── docs/
│   ├── 医院材料学习/                            # 26 source training documents
│   └── knowledge-base/
│       ├── wiki/                              # Interlinked wiki (5 categories)
│       ├── index/                             # MinerU search index
│       ├── .staging/                          # XLSX → MD conversions
│       ├── .manual-rules/                     # Manually added rules
│       ├── .manifest.json                     # Index tracking
│       └── wiki-seed.yml                      # Wiki taxonomy seed
│
├── skills/
│   ├── tcm-treatment-plan/    (v1/, v2/, SKILL.md)
│   ├── tcm-treatment-review/  (v1/, v2/, SKILL.md, standards.md, examples.md)
│   ├── sh-yb-policy-monitor/  (v1/, v2/, SKILL.md, scripts/)
│   └── knowledge-base-update/ (v1/, SKILL.md)
│
├── data/
│   └── reviews.db                             # Runtime — review pipeline SQLite
│
└── wechat-router/                             # Existing WeChat monitor (unchanged)
```

## Estimated Total Time

| Phase | Tasks | Estimate |
|-------|-------|----------|
| A. Environment Setup | 3 tasks | ~20 min |
| B. Document Processing & KB | 4 tasks | ~60 min (includes model download) |
| C. Review Pipeline Infra | 3 tasks | ~30 min |
| D. Archive v1 | 1 task | ~5 min |
| E. Skill Refactoring | 4 tasks | ~40 min |
| F. Testing | 8 tasks | ~50 min |
| **Total** | **23 tasks** | **~3.5 hours** |
