"""Publish selected issue text and project fields. Never copy repository files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = 'LivezWithParentz/godot-game-main'
OWNER, NAME = REPOSITORY.split('/')
PROJECT = 1


def graphql(query: str, token_name: str) -> dict:
    env = os.environ.copy()
    if env.get(token_name):
        env['GH_TOKEN'] = env[token_name]
    elif not env.get('ROADMAP_LOCAL_AUTH'):
        raise RuntimeError(f'Missing encrypted Actions secret: {token_name}')
    run = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=' + query],
                         env=env, capture_output=True, text=True, timeout=90)
    try:
        payload = json.loads(run.stdout)
    except json.JSONDecodeError:
        raise RuntimeError('GitHub did not return a valid API response') from None
    errors = payload.get('errors', [])
    # A repository-only issue reader may expose project membership IDs while
    # rejecting project details. Nothing except the IDs is requested here.
    fatal = [e for e in errors if 'projectItems' not in e.get('path', [])]
    if fatal or not payload.get('data'):
        raise RuntimeError('GitHub source access failed: ' + '; '.join(e['message'] for e in fatal))
    return payload['data']


def get_issues() -> list[dict]:
    result, cursor = [], None
    while True:
        after = ',after:' + json.dumps(cursor) if cursor else ''
        query = '''query { repository(owner:"%s",name:"%s") { issues(first:100%s) {
          nodes { number title body state url updatedAt
            labels(first:30) { nodes { name } }
            projectItems(first:30) { nodes { id } }
            comments(last:10) { nodes { body } }
          } pageInfo { hasNextPage endCursor }
        } } }''' % (OWNER, NAME, after)
        page = graphql(query, 'ISSUE_READ_TOKEN')['repository']['issues']
        result.extend(page['nodes'])
        if not page['pageInfo']['hasNextPage']:
            return result
        cursor = page['pageInfo']['endCursor']


def get_project() -> dict:
    result, cursor = {}, None
    while True:
        after = ',after:' + json.dumps(cursor) if cursor else ''
        query = '''query { user(login:"%s") { projectV2(number:%s) { items(first:100%s) {
          nodes { id fieldValues(first:30) { nodes {
            ... on ProjectV2ItemFieldSingleSelectValue {
              name field { ... on ProjectV2SingleSelectField { name } }
            }
            ... on ProjectV2ItemFieldTextValue {
              text field { ... on ProjectV2Field { name } }
            }
          } } } pageInfo { hasNextPage endCursor }
        } } } }''' % (OWNER, PROJECT, after)
        page = graphql(query, 'PROJECT_READ_TOKEN')['user']['projectV2']['items']
        for item in page['nodes']:
            result[item['id']] = {value.get('field', {}).get('name'): value.get('name', value.get('text'))
                                  for value in item['fieldValues']['nodes'] if value.get('field')}
            result[item['id']]['position'] = len(result)
        if not page['pageInfo']['hasNextPage']:
            return result
        cursor = page['pageInfo']['endCursor']


def plain(text: str) -> str:
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'[`*_]', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def sections(body: str) -> dict[str, list[str]]:
    result, heading, fenced = {}, '', False
    for line in body.splitlines():
        if line.strip().startswith('```'):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = re.match(r'^#{1,6}\s+(.+)', line)
        if match:
            heading = plain(match[1]).lower().rstrip(':')
            result.setdefault(heading, [])
        elif line.strip():
            result.setdefault(heading, []).append(line.strip())
    return result


def text_lines(lines: list[str]) -> list[str]:
    result = []
    for line in lines:
        if re.match(r'^[-*]\s*\[[ xX]\]', line) or line.startswith('|'):
            continue
        cleaned = plain(re.sub(r'^[-+]\s*', '', line))
        if not re.match(r'^(Owner|Area|Milestone|Execution status|Feature maturity|Documentation):', cleaned):
            result.append(cleaned)
    return result


def first_section(parts: dict, names: list[str]) -> list[str]:
    return next((text_lines(parts[n]) for n in names if parts.get(n)), [])


def publish_item(issue: dict, project: dict, mapping: dict) -> dict | None:
    labels = [label['name'] for label in issue['labels']['nodes']]
    if 'roadmap' not in labels:
        return None
    match = re.match(r'^\[([A-Z]+-[A-Za-z0-9]+)\]\s*(.*)', issue['title'])
    key, title = (match[1], match[2]) if match else (f'OPS-ISSUE{issue["number"]}', issue['title'])
    title = re.sub(r'\s*\(Completed\)\s*$', '', title)
    category = key.split('-')[0].lower()
    if category not in ['game', 'art', 'qa', 'ops']:
        category = next((x for x in ['game', 'art', 'qa', 'ops'] if x in labels), 'ops')
    memberships = [entry['id'] for entry in issue.get('projectItems', {}).get('nodes', [])
                   if entry and entry.get('id')]
    linked = next((item_id for item_id in memberships if item_id in project), None)
    if linked:
        mapping[str(issue['number'])] = linked
    project_id = linked or mapping.get(str(issue['number']))
    fields = project.get(project_id, {})
    body = issue['body'] or ''
    parts = sections(body)
    scope = first_section(parts, ['public roadmap', 'milestone scope', 'scope and current evidence',
                                 'route to review', 'scope', 'outcome'])
    summary_lines = first_section(parts, ['public roadmap', 'milestone scope', 'outcome'])
    if not summary_lines:
        summary_lines = [line for line in text_lines(parts.get('', []))
                         if not re.match(r'^(Owner|Area|Milestone|Execution status|Feature maturity|Documentation):', line)]
    summary = ' '.join(summary_lines[:1]) or title + '.'
    if len(summary) > 330:
        summary = summary[:327].rsplit(' ', 1)[0] + '…'
    if not scope:
        scope = summary_lines[1:5]
    acceptance = []
    for heading, lines in parts.items():
        if 'acceptance' in heading or (not heading and key.startswith('OPS-')):
            for line in lines:
                checked = re.match(r'^[-*]\s*\[([ xX])\]\s*(.+)', line)
                if checked:
                    acceptance.append({'done': checked[1].lower() == 'x', 'text': plain(checked[2])})
    evidence = first_section(parts, ['evidence recorded in plan.md', 'current evidence', 'current state'])
    note = ''
    for comment in reversed(issue['comments']['nodes']):
        if 'Implementation audit' in comment['body']:
            verified = re.search(r'\*\*Fresh verification:\*\*\s*(.+)', comment['body'])
            limit = re.search(r'\*\*Limits / remaining gates:\*\*\s*(.+)', comment['body'])
            if verified:
                evidence = [plain(verified[1])]
            if limit:
                note = plain(limit[1])
            break
    explicit = re.search(r'Feature maturity:\s*(Planned|Prototype|Implemented|Validated)', body)
    status_match = re.search(r'Execution status:\*?\*?\s*(Backlog|In progress|Review|Done)', body, re.I)
    fallback_status = status_match[1].capitalize() if status_match else 'Backlog'
    status = fields.get('Status') or ('Done' if issue['state'] == 'CLOSED' else fallback_status)
    if status not in ['Backlog', 'In progress', 'Review', 'Done']:
        raise RuntimeError(f'Unsupported execution status on issue {issue["number"]}')
    if issue['state'] == 'CLOSED':
        status = 'Done'
    milestone = re.search(r'^GAME-M(\d+)([abc]?)$', key)
    order = int(milestone[1]) * 10 + (ord(milestone[2]) - 96 if milestone[2] else 0) if milestone else fields.get('position', issue['number'])
    if key == 'ART-02':
        note = 'Character art remains on hold pending Alex’s models and the relevant review. Delivery and technical checks do not imply visual approval.'
    return {'key': key, 'number': issue['number'], 'title': plain(title), 'category': category,
            'summary': summary, 'scope': scope[:12], 'evidence': evidence[:8], 'acceptance': acceptance,
            'status': status, 'priority': fields.get('Priority') or None,
            'area': fields.get('Area') or {'game': 'Gameplay', 'art': 'Art production', 'qa': 'Acceptance', 'ops': 'Production tooling'}[category],
            'maturity': explicit[1] if explicit else None, 'note': note,
            'url': issue['url'], 'updatedAt': issue['updatedAt'], 'order': order,
            'statusSource': 'project' if fields else 'issue'}


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    mapping_path = ROOT / 'project-map.json'
    mapping = json.loads(mapping_path.read_text(encoding='utf-8')) if mapping_path.exists() else {}
    issues, project = get_issues(), get_project()
    items = [item for issue in issues if (item := publish_item(issue, project, mapping))]
    if not items:
        raise RuntimeError('Refusing to replace the roadmap with an empty source')
    items.sort(key=lambda x: x['number'])
    canonical = json.dumps(items, ensure_ascii=False, sort_keys=True)
    if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN .*PRIVATE KEY', canonical):
        raise RuntimeError('Credential-like content found; publication stopped')
    version = hashlib.sha256(canonical.encode()).hexdigest()
    target = ROOT / 'docs/roadmap.json'
    old = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    changed = old.get('contentVersion') != version
    if changed:
        payload = {'schemaVersion': 1, 'contentVersion': version,
                   'syncedAt': datetime.now(timezone.utc).isoformat(), 'items': items}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    mapping_path.write_text(json.dumps(mapping, indent=2) + '\n', encoding='utf-8')
    fallback = [i['key'] for i in items if i['statusSource'] != 'project' and i['status'] != 'Done']
    print(f'Roadmap: {len(items)} items; {len(project)} project memberships; changed={changed}.')
    if fallback:
        print('Project membership not yet linked for: ' + ', '.join(fallback))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f'changed={str(changed).lower()}\n')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Roadmap refresh stopped: {error}', file=sys.stderr)
        sys.exit(1)
