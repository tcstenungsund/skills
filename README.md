# skills

Gemensamma skills för @tcstenungsund. **Lärare: använd webbplatsen, inte det här repot.**

Maintainer notes (English) below. The full design rationale lives in
[Skills Gallery Build Instruction.md](Skills%20Gallery%20Build%20Instruction.md).

## How it works

- `skills/<kebab-case>/SKILL.md` is the only place a skill is written or edited.
  Never "fix" a skill inside a Gem, ChatGPT project or Copilot. Always change it here.
- On every push to `main`, `.github/workflows/build.yml` runs `scripts/build_site.py`.
  It validates every skill, builds the Swedish gallery into `site/` and deploys it to GitHub Pages.
  Pull requests run the same checks without deploying.
- **`site/` is generated. Never edit it by hand, and never commit it** (it is in `.gitignore`).

One-time setup: Settings → Pages → Source: **GitHub Actions**.

## Files

| File | Purpose |
|------|---------|
| `skills/` | Our skills. Folders starting with `_` (e.g. `_arkiv/`) are skipped. |
| `sources.json` | External public repos to include, pinned to a tag or commit SHA (see below). |
| `site-theme.json` | Site title, brand colors and optional logo path. Keep WCAG AA contrast against white text. |
| `redirects.json` | Optional `{"old-slug": "new-slug"}` for renamed skills. |
| `sensitive-allow.txt` | Optional: one path per line that the svar/facit/personnummer check should ignore, exactly as printed in the error. |
| `docs/screenshots/` | Optional `claude.png`, `gemini.png`, `chatgpt.png`, `copilot.png`. They are shown on every skill page once added. |

## External skills (`sources.json`)

```json
[
  { "repo": "anthropics/skills", "ref": "2c5958ecac7cee2b583967a2c4981d0f4a75c579",
    "path": "skills", "skills": ["pdf"] }
]
```

- `repo` and `ref` are required. `ref` must be a tag or a full 40-character commit SHA. A branch name fails the build,
  because content must not change without a reviewed PR. To update a source, bump `ref` in a PR.
- `path` is the folder in that repo that holds the skill folders (default `skills`). `skills` is an
  optional allowlist (default: all of them).
- External skills never fail the build. If one breaks a rule, it is skipped with a warning.
  A missing `version` becomes the ref, a missing `updated` becomes the git date and a missing `owner` becomes the repo name.
  An unreachable repo or a bad ref **does** fail the build.
- Check the source repo's license before adding it.

## Run locally

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/build_site.py
python3 -m http.server -d site   # open http://localhost:8000
```

Python 3.9+ and git. No pip installs.
