# OpenClaw Review Deployment + WeChat Daily Monitor — Combined Task Checklist

**Created:** 2026-04-10  
**For:** Execute in order, check off as work completes.

> This checklist combines three related workstreams:
> - Workstream 1: adapt and deploy `tcm-treatment-review` to the mac mini OpenClaw runtime ("小龙虾"), then verify end-to-end treatment-form upload and review.
> - Workstream 2: create a new `wechat-daily-monitor` skill using the article-fetch pipeline from `will-17173/wechat-article-to-markdown-skill`, then wire the outputs into the knowledge-base refresh and indexing flow.
> - Workstream 3: deploy all repo-owned skills to the mac mini OpenClaw environment and run end-to-end validation for each skill, not only `tcm-treatment-review`.
>
> The checklist is intentionally self-contained because the first phase is a target-runtime discovery pass: the OpenClaw deployment contract on the mac mini must be confirmed before implementation details are locked.

---

## Phase A: Target Runtime Discovery

- [ ] **A1. Capture the OpenClaw contract on the mac mini**
  - SSH into the mac mini and identify the OpenClaw working tree, service entrypoint, skill loading path, upload path, and subagent/job dispatch mechanism.
  - Record where uploaded images land on disk, how result artifacts are surfaced back to the UI, and how logs are retrieved.
  - Save the findings to `docs/superpowers/specs/2026-04-10-openclaw-review-integration-notes.md`.

- [ ] **A2. Audit current treatment-review assumptions against the target runtime**
  - Inspect `skills/tcm-treatment-review/SKILL.md`, `skills/tcm-treatment-review/v2/SKILL.md`, and `scripts/review_db.py`.
  - Produce a mismatch list covering:
    - Cursor/Task-specific wording vs OpenClaw-native orchestration
    - Windows-only command/path assumptions
    - temp JSON file handling
    - SQLite file location assumptions
    - batch fan-out / fan-in behavior

- [ ] **A3. Lock the migration path**
  - If the current v2 skill needs runtime-facing changes, create `skills/tcm-treatment-review/v3/SKILL.md`.
  - Update root `skills/tcm-treatment-review/SKILL.md` only after the mac mini flow is validated.
  - Reuse `scripts/review_db.py` unless the runtime audit proves the CLI contract must change.

---

## Phase B: Adapt `tcm-treatment-review` for OpenClaw

- [ ] **B1. Make the orchestration instructions OpenClaw-native**
  - Replace Cursor/Task-specific language with the actual OpenClaw worker/subagent mechanism found in Phase A.
  - Preserve the current one-image-per-worker rule so image/result mismatches do not regress.
  - Preserve the current single-image fast path and the multi-image SQLite-backed aggregation path.

- [ ] **B2. Remove machine-specific assumptions**
  - Replace hardcoded Windows paths with repo-relative paths or environment-driven locations.
  - Where shell examples remain in the skill, include the macOS form required by the mac mini runtime.
  - Confirm `data/reviews.db` and temp JSON cleanup work on both Windows and macOS.

- [ ] **B3. Decide whether `review_db.py` needs changes**
  - Keep `scripts/review_db.py` unchanged if OpenClaw can call the current `init`, `save`, `status`, `summary`, and `export` commands directly.
  - Only change the script if the runtime needs different path handling, output formatting, or session lifecycle behavior.
  - If modified, add or update focused tests in `tests/test_review_db.py`.

- [ ] **B4. Produce the deployment-ready skill**
  - Create `skills/tcm-treatment-review/v3/SKILL.md` if the runtime-specific refactor is material.
  - Keep the current v2 behavior set:
    - knowledge-base pricing lookup
    - static-price fallback
    - multi-form detection
    - batch review persistence in SQLite
  - Point root `skills/tcm-treatment-review/SKILL.md` to the validated version.

---

## Phase C: Deploy to the mac mini and validate end-to-end

- [ ] **C1. Copy the required files to the OpenClaw host**
  - Deploy the validated `skills/tcm-treatment-review/` files.
  - Include `scripts/review_db.py` and any runtime notes/config files required by the host.
  - Confirm the host-side venv/dependency state before running any validation commands.

- [ ] **C2. Validate the upload -> review -> result flow**
  - Run a single-image upload test end-to-end.
  - Run a 3-image batch test including 1 image with 2 stacked treatment forms.
  - Confirm:
    - the upload reaches the correct runtime path
    - OpenClaw fans work out correctly across workers/subagents
    - SQLite receives all expected results
    - the final summary re-aggregates correctly for the UI

- [ ] **C3. Record evidence and operational notes**
  - Save screenshots, logs, and outcomes to `docs/superpowers/test-results/2026-04-10-openclaw-review-validation.md`.
  - Record pass/fail status, known gaps, and rollback notes.

---

## Phase D: Create the `wechat-daily-monitor` skill

- [ ] **D1. Vendor the article-fetch pipeline into this repo**
  - Reuse the method from `will-17173/wechat-article-to-markdown-skill`:
    - request the WeChat article HTML
    - repair lazy-loaded image URLs
    - download article images locally
    - convert the article body to Markdown
    - run output cleanup/formatting
  - Add the repo-owned script at `scripts/wechat_article_pipeline.py`.
  - Keep dependencies minimal. If `requests` is not already available in the project venv, document/install it as part of the execution pass.

- [ ] **D2. Lock the storage layout for fetched articles**
  - Save fetched content under `docs/医院材料学习/公众号每日监测/YYYY-MM-DD/<account>/<NN_title>/`.
  - Store:
    - the cleaned Markdown file
    - downloaded images
    - optional cleaned HTML when needed for debugging
    - article metadata (`source account`, `publish time`, `matched keywords`, `priority`, `local path`)

- [ ] **D3. Define how the skill obtains article URLs**
  - Preferred path: use the existing WeChat tooling under `wechat-router/wechat-decrypt/` and its MCP surface to discover recent `mp.weixin.qq.com` links for the monitored official accounts.
  - Fallback path: allow the operator to provide one or more article URLs manually.
  - Make both modes explicit in the skill contract so the runtime behavior is predictable.

- [ ] **D4. Create the new skill files**
  - Create `skills/wechat-daily-monitor/v1/SKILL.md`.
  - Copy the validated version to `skills/wechat-daily-monitor/SKILL.md`.
  - Encode the monitoring rules from `docs/superpowers/specs/公众号每日监测.md`:
    - `P0`: immediate alert
    - `P1`: same-day digest
    - `P2`: weekly digest
    - `P3/P4`: archive/filter

- [ ] **D5. Define the run outputs**
  - Each run should produce:
    - fetched article Markdown folders
    - a structured monitoring report
    - urgent alerts for `P0`
    - a daily summary for `P1`
    - weekly candidates for `P2`
    - an archive trail for `P3/P4`

---

## Phase E: Update knowledge-base auto-refresh and indexing

- [ ] **E1. Update the KB skill contract**
  - Modify `skills/knowledge-base-update/SKILL.md` and `skills/knowledge-base-update/v2/SKILL.md`.
  - Explicitly document that native Markdown outputs under `docs/医院材料学习/公众号每日监测/` are part of the `source_md` refresh path.
  - Add trigger wording for syncing newly fetched WeChat-monitor articles into the KB workflow.

- [ ] **E2. Decide whether a dedicated KB mode is necessary**
  - Prefer reusing the existing `docs` mode if the article outputs live under `docs/医院材料学习/`.
  - Add a dedicated `wechat` mode only if operators need distinct commands, reporting, or partial refresh behavior.

- [ ] **E3. Verify manifest coverage**
  - Confirm `scripts/update_kb_manifest.py` already includes the new article directory via its recursive scan.
  - Only change the script if the chosen output path is missed.

- [ ] **E4. Add automatic post-fetch indexing**
  - After the new monitor skill saves article Markdown files, it must trigger KB refresh automatically.
  - Minimum required refresh steps:

```powershell
python scripts/update_kb_manifest.py
qmd collection add "docs/医院材料学习" --name source_md --mask "**/*.md"
```

  - If binary conversions or wiki refresh are needed by the final operator flow, reuse the existing `knowledge-base-update` skill instructions rather than duplicating logic.

---

## Phase F: Deploy All Skills to the mac mini OpenClaw Host

- [ ] **F1. Build the deployable skill inventory**
  - Include the current root skills:
    - `skills/tcm-treatment-review/SKILL.md`
    - `skills/tcm-treatment-plan/SKILL.md`
    - `skills/sh-yb-policy-monitor/SKILL.md`
    - `skills/knowledge-base-update/SKILL.md`
  - Add `skills/wechat-daily-monitor/SKILL.md` after Phase D is complete.
  - For each skill, list the companion scripts, docs, and data directories that must exist on the host for the skill to work.

- [ ] **F2. Deploy shared runtime dependencies once**
  - Ensure the mac mini host has the correct repo checkout, Python venv, Python dependencies, Node/qmd tooling, and required KB directories.
  - Confirm the host has every shared script needed by the skill set, including:
    - `scripts/review_db.py`
    - `scripts/update_kb_manifest.py`
    - `scripts/xlsx_to_markdown.py`
    - `scripts/binary_docs_to_markdown.py`
    - `scripts/wechat_article_pipeline.py`
    - `skills/sh-yb-policy-monitor/scripts/fetch_policies.py`

- [ ] **F3. Deploy all skill bundles**
  - Sync each skill directory and its required companion files to the OpenClaw host.
  - Confirm the OpenClaw runtime can discover all deployed skills in its configured skill-loading path.
  - Do not treat files as deployed until the host-side runtime lists or loads them successfully.

- [ ] **F4. Run end-to-end validation for every deployed skill**
  - `tcm-treatment-review`: single-image path + batch-image path
  - `tcm-treatment-plan`: generate a sample plan and verify KB-backed pricing or documented fallback
  - `sh-yb-policy-monitor`: fetch recent policy content and verify local output plus KB-copy/update behavior
  - `knowledge-base-update`: run the `docs` flow and at least one `rules` flow, then verify manifest refresh and collection update
  - `wechat-daily-monitor`: validate the manual-URL path; validate the discovered-link path too if the host has usable WeChat data access

- [ ] **F5. Record the full host validation evidence**
  - Save evidence to `docs/superpowers/test-results/2026-04-10-openclaw-all-skills-validation.md`.
  - Record passed, failed, and skipped scenarios per skill, including host-specific caveats and rollback notes.

---

## Phase G: Validation Matrix

- [ ] **G1. Smoke-test the article pipeline**
  - Run:

```powershell
python scripts/wechat_article_pipeline.py "<mp.weixin.url>" --output-dir "docs/医院材料学习/公众号每日监测"
```

  - Verify title extraction, local image downloads, Markdown cleanup, and stable folder naming.

- [ ] **G2. Validate priority classification**
  - Use sample articles that should land in `P0`, `P1`, and `P2` based on `docs/superpowers/specs/公众号每日监测.md`.
  - Confirm the generated summary respects the documented urgency rules.

- [ ] **G3. Validate KB searchability**
  - Refresh the KB after importing at least one article.
  - Verify the article can be discovered through the existing KB search/query/wiki-read workflow.

- [ ] **G4. Validate both operator paths**
  - Manual-link path: operator supplies URL -> skill fetches article -> KB refresh runs -> article becomes searchable.
  - Discovered-link path: skill finds a new article link from monitored sources -> fetches it -> classifies it -> KB refresh runs -> summary is produced.

- [ ] **G5. Final handoff**
  - Update the checklist status.
  - Record remaining gaps and follow-up items.
  - Choose the execution style for implementation: subagent-driven or inline.

---

## Candidate File Changes

```text
hospital-claw/
├── docs/
│   ├── 医院材料学习/
│   │   └── 公众号每日监测/
│   │       └── YYYY-MM-DD/<account>/<NN_title>/
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-04-10-openclaw-review-integration-notes.md
│       └── test-results/
│           ├── 2026-04-10-openclaw-review-validation.md
│           └── 2026-04-10-openclaw-all-skills-validation.md
├── scripts/
│   └── wechat_article_pipeline.py
└── skills/
    ├── knowledge-base-update/
    │   ├── SKILL.md
    │   └── v2/SKILL.md
    ├── tcm-treatment-review/
    │   ├── SKILL.md
    │   └── v3/SKILL.md
    └── wechat-daily-monitor/
        ├── SKILL.md
        └── v1/SKILL.md
```

## Suggested Execution Order

1. Finish Phases A-C first so the OpenClaw runtime contract is known and the treatment-review flow works on the host.
2. Implement Phases D-E after the article storage layout and KB reuse path are locked.
3. Complete Phase F only after all required scripts, KB assets, and skills are present on the mac mini host.
4. Do not close the checklist until Phase G evidence is written.

## Estimated Effort

| Phase | Tasks | Estimate |
|------|------|----------|
| A. Discovery | 3 tasks | ~45-60 min |
| B. Review skill adaptation | 4 tasks | ~60-90 min |
| C. Deployment + E2E validation | 3 tasks | ~45-75 min |
| D. New WeChat monitor skill | 5 tasks | ~90-120 min |
| E. KB refresh/index integration | 4 tasks | ~30-45 min |
| F. All-skills host rollout + validation | 5 tasks | ~60-90 min |
| G. Validation matrix | 5 tasks | ~45-60 min |
| **Total** | **29 tasks** | **~6.5-9 hours** |
