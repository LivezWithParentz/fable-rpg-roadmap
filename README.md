# Greyhaven development roadmap

Public website for the Fable-inspired RPG roadmap. The game repository stays private.

**Site:** https://livezwithparentz.github.io/fable-rpg-roadmap/

## Automatic updates

The `Refresh and publish roadmap` workflow checks the private source every five minutes. GitHub may delay scheduled jobs. It publishes when source data changes; opening the workflow and choosing **Run workflow** requests an immediate refresh. An already open page checks for a new published snapshot once a minute.

The publisher reads every issue labelled `roadmap`, its title, selected description sections, acceptance checklist and audit evidence. It reads execution status, priority and area from the GitHub Project. Closed issues become Completed; reopening allows the Project's reopened-item automation to choose execution status. New labelled issues are discovered automatically. Unscheduled work appears under Later.

Keep source issues updated. Useful description headings: `Outcome`, `Milestone scope`, `Scope and current evidence`, `Acceptance checklist`, and `Evidence recorded in PLAN.md`. An optional `Public roadmap` section can provide a public-facing summary. Code blocks and unrelated sections are excluded. This is one-way publication; the website does not update issues, `PLAN.md`, or feature maturity.

`PLAN.md` in the private game repository remains authoritative for scope and milestone evidence. Completed tracking does not imply every manual acceptance gate passed. The source repository's **Auto-close issues with merged linked pull requests** setting and the Project's merge/auto-close workflows are disabled. Close source issues explicitly after acceptance; merging code does not grant it. Character-art review remains held pending Alex's models.

## Credentials and publication boundary

Only `docs/` is deployed. No game scenes, scripts, model assets, raw issue bodies, local paths or credentials are copied from the game repository. Selected prose may name game files while describing evidence. Private issue links are labelled as maintainer links.

Two separate encrypted Actions secrets grant read access:

- `PROJECT_READ_TOKEN`: classic token with **only `read:project`**. It reads the personal Project, without repository/code permissions.
- `ISSUE_READ_TOKEN`: fine-grained token restricted to `godot-game-main`, with **Issues: read** and required **Metadata: read**. It cannot read code or change issues.

The publisher repository's own `GITHUB_TOKEN` saves public snapshots; it cannot access the private game code. The source credentials expire **October 17, 2027** and must be rotated in repository Actions secrets before then. They are never included in browser JavaScript or JSON. The Project must remain public so the repository-only issue reader can discover membership IDs for new issues. GitHub still restricts source issue details to repository members; the website publishes selected text separately. `project-map.json` caches issue-to-Project membership IDs only. Making the Project private again breaks discovery for new items; existing cached links continue to refresh.

## Local preview and refresh

Serve `docs/` with `python -m http.server 8784 --directory docs`. No dependencies or build are required.

With an existing GitHub CLI session that can read both source issues and Projects, run:

```powershell
$env:ROADMAP_LOCAL_AUTH = '1'
python scripts/sync.py
Remove-Item Env:ROADMAP_LOCAL_AUTH
```

Changes to the website deploy on push to `main`. Automatic refreshes commit public JSON and membership IDs only. A failed refresh leaves the last published site intact and is visible in Actions. Check the source timestamp on the site and the workflow history to distinguish published data from a fresh check with no changes.
