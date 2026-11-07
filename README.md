# Skills Gallery

[![Tests](https://img.shields.io/github/actions/workflow/status/tcstenungsund/skills/build.yml?branch=main&label=tests&logo=githubactions&logoColor=white)](https://github.com/tcstenungsund/skills/actions/workflows/build.yml)
[![Vibe coded](https://img.shields.io/badge/vibe-coded-ff69b4)](https://en.wikipedia.org/wiki/Vibe_coding)
[![Coded with Claude Code](https://img.shields.io/badge/coded%20with-Claude%20Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](scripts/build_site.py)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](scripts/build_site.py)
[![Agent Skills](https://img.shields.io/badge/format-Agent%20Skills-6e40c9)](https://agentskills.io)
[![Website](https://img.shields.io/badge/webbplats-GitHub%20Pages-222?logo=githubpages)](https://tcstenungsund.github.io/skills/)

Shared AI skills for the teachers of @tcstenungsund. They are written once in the open
[Agent Skills](https://agentskills.io) `SKILL.md` format and published as a Swedish website
that works with Claude, Gemini, ChatGPT and Microsoft Copilot.

> **Lärare:** du behöver inte göra något här. Använd
> [webbplatsen](https://tcstenungsund.github.io/skills/), där du kopierar instruktionen eller laddar ner skillen.

---

## Contents

- [Why this exists](#why-this-exists)
- [How it works](#how-it-works)
- [Writing a skill](#writing-a-skill)
- [External skills](#external-skills)
- [Configuration](#configuration)
- [Governance](#governance)
- [Development](#development)
- [Deployment](#deployment)
- [Design decisions](#design-decisions)
- [License](#license)

## Why this exists

Teachers solve the same problems again and again: writing tests, grading against
*kunskapskrav*, creating assignments, applying the school's graphical profile. They use
different AI services and different account tiers, so no single platform can be assumed. The skills therefore have to be
*pulled* from a website. They cannot be pushed through admin tooling.

The main risk is **version drift**. A skill pasted into a Gem, project or Copilot does not update when the source changes.
Every part of the gallery is built so that a stale copy is easy to spot and easy to replace.

**The rule:** this repository is the only place a skill is written or edited. Never "fix" a skill inside
Gemini, ChatGPT, Copilot or a chat. Everything is exported *from* here.

## How it works

```
skills/<name>/SKILL.md ──► GitHub Action ──► validate ──► build site/ ──► GitHub Pages
sources.json (pinned) ───┘
```

On every push to `main`, [`build.yml`](.github/workflows/build.yml) runs the tests and then
[`scripts/build_site.py`](scripts/build_site.py). The script validates every skill and builds a static website in Swedish.
Pull requests run the same checks without deploying. A rule violation fails the build with a plain-language
message that names the folder. Nothing broken is ever published.

Each skill gets exactly **three exports**:

| Export | For | Details |
|--------|-----|---------|
| **Paste-block** | Gemini, ChatGPT, Copilot | `SKILL.md` body without frontmatter, with a version header line. Copy button on the page, plus `/instruktioner/<slug>.txt`. |
| **ZIP** | Claude (and any Agent Skills consumer) | Unpacks to `<name>/SKILL.md`. Upload via *Settings → Capabilities → Skills*, which works on free plans too. |
| **Files** | Knowledge-file slots | Everything in `references/` and `assets/`, downloadable one file at a time. |

There is one paste-block for every platform. Per-platform copies of the text would drift apart within a term.
What differs between platforms is the *installation steps*, and those are shown on the page:

- **Gemini:** paste the block into a new Gem and upload the files as knowledge.
- **ChatGPT:** paste the block into a Project's instructions. Custom GPTs are being retired, so nothing here is GPT-specific.
- **Copilot:** there is only *one* global custom-instruction box per user, so a teacher can use one skill at a time.

Every skill page shows **`Nuvarande version: X (date)`** and its owner, and the index flags skills
that haven't been updated in six months as *kan behöva ses över*.

`site/` is generated. Never edit it by hand, and never commit it.

## Writing a skill

The full guide in Swedish is in [docs/ny-skill.md](docs/ny-skill.md), and the pre-merge checklist is in [docs/CHECKLIST.md](docs/CHECKLIST.md).

```
skills/
└── skapa-prov/              # lowercase kebab-case, equal to `name`
    ├── SKILL.md             # required, exact spelling
    ├── references/          # optional, context files, one level deep
    └── assets/              # optional, templates and other downloads
```

```yaml
---
name: skapa-prov           # must equal the folder name
title: Skapa prov          # optional display name shown to teachers
description: >-            # loaded at every session start; decides when the skill fires
  Skapar prov utifrån kurs och kunskapskrav. Använd när läraren vill skapa ett prov ...
version: 1.2.0             # semver, bump on every change
updated: 2026-11-07        # ISO date of the last substantive change
owner: Kenneth Frantzen    # the person who answers questions about it
---
```

End the body with a `## CHANGELOG` section (`- date – version: change`). It is shown as the
version history on the skill page.

**Versioning:** patch = typo or small fix; minor = added content; major = changed behaviour or removal.
File names and structure must not change in a patch version.

**Enforced by the build** (for local skills the build fails, and the message names the folder):

- the folder name is kebab-case, `SKILL.md` exists, and there is no `README.md` inside the skill folder
- `name` equals the folder name, and `description`, `version` (semver), `updated` (ISO date) and `owner` are present
- the body is at most 500 lines
- reference files sit directly in `references/` and never link to other reference files. Agents may read only part of a chained file and miss what's at the end.
- no file names containing *svar* or *facit*, and nothing that looks like a personnummer

**Warnings:** relative links in the body (the paste-block then gets a footer asking teachers to attach
the downloaded files), links to missing files, a `description` over 150 words, a paste-block
over 10,000 characters, and an `updated` date older than the last git commit to the skill.

## External skills

Skills from other **public** GitHub repositories can be listed on the same page, under *Från andra källor*.
They are declared in [`sources.json`](sources.json):

```json
[
  {
    "repo": "anthropics/skills",
    "ref": "2c5958ecac7cee2b583967a2c4981d0f4a75c579",
    "path": "skills",
    "skills": ["pdf"]
  }
]
```

| Key | Required | Meaning |
|-----|----------|---------|
| `repo` | yes | `owner/name` on GitHub. |
| `ref` | yes | A tag or a full 40-character commit SHA. A branch name fails the build, because content must not change without a reviewed PR. |
| `path` | no | The folder that holds the skill folders. Default `skills`. |
| `skills` | no | An allowlist of skill folder names. Default: all of them. |

- External skills **never fail the build**. A skill that breaks a rule is skipped with a warning.
- Missing fields are filled in: `version` becomes the ref, `updated` the git date, and `owner` the repository.
- An unreachable repository or a bad `ref` **does** fail the build, so a source can't silently disappear.
- To update a source, bump `ref` in a PR. Check the source's license before adding it.

## Configuration

| File | Purpose |
|------|---------|
| [`site-theme.json`](site-theme.json) | Site title, brand colors and optional logo path. Keep WCAG AA contrast against white text. |
| [`sources.json`](sources.json) | External skill sources (see above). |
| `redirects.json` | Optional `{"old-slug": "new-slug"}` map for renamed skills. |
| `sensitive-allow.txt` | Optional false-positive list for the svar/facit/personnummer check, with one path per line exactly as printed in the error. |
| `docs/screenshots/` | Optional `claude.png`, `gemini.png`, `chatgpt.png` and `copilot.png`, shown on every skill page once added. |

## Governance

- **One named owner per skill.** The owner is accountable for updates and answers ("ask Anna" is the support model).
- **All changes go through pull requests**, which gives review and rollback and enforces the edit-only-here rule.
- **Lifecycle:** draft → PR → review → published on merge.
- **Deprecation:** move the folder to `skills/_arkiv/`, since folders starting with `_` are skipped. Don't delete it, because teachers mid-term may still need the old version. Add a `redirects.json` entry when a skill is renamed.
- **Review cadence:** check each skill's `updated` date at the start of every term.
- **Never** put pupil-identifying data or exam answer keys in a skill. The repository and website are public.

## Development

You need Python 3.9+ and git. There are no pip installs.

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'   # tests, no network needed
python3 scripts/build_site.py                            # validate + build into site/
python3 -m http.server -d site                           # preview at http://localhost:8000
```

## Deployment

1. The repository is public. GitHub Pages on a private repository requires a paid plan.
2. Under *Settings → Pages → Source*, choose **GitHub Actions**.
3. Merge to `main`. The workflow builds the site and deploys it with the official `actions/*` Pages actions,
   which are pinned to commit SHAs.

## Design decisions

- **Git as the backend, a website as the frontend.** Git gives versioning, review, rollback and a single source of
  truth. The website gives teachers a zero-threshold way in. Neither covers both needs on its own.
- **`SKILL.md` stays canonical even though the consumers differ.** Agent Skills is an open standard that more and more
  platforms adopt. Authoring in it keeps the skills ready to import as platforms converge, while the paste-block
  serves everyone else today.
- **Exactly three exports, and no per-platform text.** One paste-block, plus installation steps for each platform.
- **The anti-drift measures are the real product.** Version stamps, dates, named owners, staleness flags and changelogs.
  The export formats are the easy part.
- **No dependencies, and no framework.** Hand-written HTML with a few lines of vanilla JavaScript. Copying falls back
  to selecting the text in the box when JavaScript or the Clipboard API isn't available.

## License

The code is licensed under the [GNU Affero General Public License v3.0](LICENSE).
The instructional content of our own skills may be shared under CC BY-SA 4.0. External skills keep
the license of their source repository.
