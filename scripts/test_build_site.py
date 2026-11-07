"""Tests for build_site.py. Stdlib only, no network: run with
python3 -m unittest discover -s scripts -p 'test_*.py'
"""
import datetime
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as b  # noqa: E402

GOOD = """---
name: {name}
description: >-
  Gör något bra. Använd när
  läraren ber om det.
version: 1.2.0
updated: 2026-11-07
owner: Anna Andersson
---
# Rubrik

Se [kraven](references/krav.md).

## CHANGELOG

- 2026-11-07 – 1.2.0: Ny text.
"""


def make_skill(parent, name, text=None, files=None):
    d = Path(parent) / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(text if text is not None else GOOD.format(name=name), encoding="utf-8")
    for rel, content in (files or {"references/krav.md": "# Krav\n"}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(content, encoding="utf-8")
    return d


def git(cwd, *args, date="2026-01-15T12:00:00"):
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True, env=env)


class TestParse(unittest.TestCase):
    def test_frontmatter_folded_comments_quotes(self):
        meta, body = b.parse_frontmatter(
            "---\nname: x   # comment\ndescription: >-\n  rad ett\n  rad två\n"
            "title: \"Mitt # namn\"\n---\nkropp\n")
        self.assertEqual(meta, {"name": "x", "description": "rad ett rad två", "title": "Mitt # namn"})
        self.assertEqual(body, "kropp\n")

    def test_no_frontmatter(self):
        self.assertEqual(b.parse_frontmatter("hej"), (None, "hej"))

    def test_changelog(self):
        self.assertEqual(b.changelog(GOOD.format(name="x")), ["2026-11-07 – 1.2.0: Ny text."])


class TestLocalRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "skills").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, allow=()):
        errors, warnings = [], []
        skills = b.load_local(self.root, set(allow), errors, warnings)
        return skills, errors, warnings

    def assertError(self, *needles):
        _, errors, _ = self.load()
        self.assertTrue(any(all(n in e for n in needles) for e in errors), errors)

    def test_good_skill_passes(self):
        make_skill(self.root / "skills", "bra-skill")
        skills, errors, _ = self.load()
        self.assertEqual(errors, [])
        self.assertEqual(skills[0]["version"], "1.2.0")

    def test_archived_skipped(self):
        make_skill(self.root / "skills", "_arkiv", text="trasig")
        self.assertEqual(self.load()[1], [])

    def test_camel_case_folder(self):
        make_skill(self.root / "skills", "createProv", GOOD.format(name="createProv"))
        self.assertError("skills/createProv", "gemener-med-bindestreck")

    def test_missing_version(self):
        make_skill(self.root / "skills", "x", GOOD.format(name="x").replace("version: 1.2.0\n", ""))
        self.assertError("skills/x", "'version'")

    def test_name_mismatch(self):
        make_skill(self.root / "skills", "x", GOOD.format(name="y"))
        self.assertError("skills/x", "samma som mappnamnet")

    def test_missing_skill_md(self):
        (self.root / "skills" / "tom").mkdir()
        self.assertError("skills/tom", "SKILL.md saknas")

    def test_readme_forbidden(self):
        make_skill(self.root / "skills", "x", files={"references/krav.md": "", "README.md": ""})
        self.assertError("skills/x", "README.md")

    def test_reference_chain(self):
        make_skill(self.root / "skills", "x", files={
            "references/krav.md": "Se [mer](mer.md)", "references/mer.md": ""})
        self.assertError("skills/x", "references/krav.md", "mer.md")

    def test_reference_subfolder(self):
        make_skill(self.root / "skills", "x", files={
            "references/krav.md": "", "references/djup/a.md": ""})
        self.assertError("skills/x", "undermapp")

    def test_too_long(self):
        make_skill(self.root / "skills", "x", GOOD.format(name="x") + "rad\n" * 500)
        self.assertError("skills/x", "max 500")

    def test_sensitive_name_and_allow(self):
        make_skill(self.root / "skills", "x", files={"references/krav.md": "", "assets/facit-prov1.md": ""})
        self.assertError("skills/x", "facit")
        self.assertEqual(self.load(allow={"skills/x/assets/facit-prov1.md"})[1], [])

    def test_ansvar_is_not_svar(self):
        make_skill(self.root / "skills", "x", files={"references/krav.md": "", "assets/ansvar.md": ""})
        self.assertEqual(self.load()[1], [])

    def test_personnummer(self):
        make_skill(self.root / "skills", "x", files={"references/krav.md": "Elev 050312-1234"})
        self.assertError("skills/x", "personnummer")

    def test_dangling_link_warns_and_footer(self):
        make_skill(self.root / "skills", "x", files={"assets/a.txt": ""})
        skills, errors, warnings = self.load()
        self.assertEqual(errors, [])
        self.assertTrue(any("references/krav.md" in w for w in warnings), warnings)
        self.assertIn(b.PASTE_FOOTER, b.paste_block(skills[0]))


class TestBuild(unittest.TestCase):
    def test_outputs_and_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_skill(root / "skills", "bra-skill")
            errors, warnings = [], []
            local = b.load_local(root, set(), errors, warnings)
            b.build(local, [], root / "site", root, dict(b.DEFAULT_THEME), {"gammal": "bra-skill"},
                    today=datetime.date(2027, 9, 1))
            site = root / "site"
            with zipfile.ZipFile(site / "downloads" / "bra-skill.zip") as z:
                self.assertIn("bra-skill/SKILL.md", z.namelist())
                self.assertIn("bra-skill/references/krav.md", z.namelist())
            self.assertTrue((site / "downloads" / "bra-skill" / "references" / "krav.md").is_file())
            txt = (site / "instruktioner" / "bra-skill.txt").read_text(encoding="utf-8")
            self.assertIn("version 1.2.0", txt)
            self.assertNotIn("owner:", txt)
            pg = (site / "skills" / "bra-skill" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Nuvarande version: 1.2.0 (2026-11-07)", pg)
            self.assertNotIn("screenshots/", pg)
            self.assertNotIn("kanske inte får plats i Copilot", pg)
            long = dict(local[0], slug="lang", body="x" * (b.PASTE_LIMIT + 1))
            self.assertIn("kanske inte får plats i Copilot", b.skill_page(long, datetime.date.today(),
                                                                         b.DEFAULT_THEME, set()))
            idx = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn("kan behöva ses över", idx)
            self.assertIn("bra-skill/index.html", (site / "skills" / "gammal" / "index.html").read_text())
            self.assertTrue((site / "404.html").is_file())


class TestExternal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.base = f"file://{t}/remotes/"
        repo = t / "remotes" / "acme" / "skills.git"
        sk = repo / "skills"
        make_skill(sk, "rubric", "---\nname: rubric\ndescription: Hjälper till.\n---\nText\n", files={})
        make_skill(sk, "trasig", "ingen frontmatter", files={})
        make_skill(sk, "annan", "---\nname: annan\ndescription: x\n---\n", files={})
        git(repo, "init", "-q", "-b", "main")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "init")
        git(repo, "tag", "v1")
        self.ext = t / "ext"

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, sources, taken=()):
        errors, warnings = [], []
        skills = b.load_external(sources, self.ext, set(), errors, warnings, set(taken), self.base)
        return skills, errors, warnings

    def test_pinned_tag_fills_gaps(self):
        skills, errors, warnings = self.load([{"repo": "acme/skills", "ref": "v1",
                                               "skills": ["rubric", "trasig", "saknas"]}])
        self.assertEqual(errors, [])
        self.assertEqual(len(skills), 1)
        s = skills[0]
        self.assertEqual((s["slug"], s["version"], s["owner"], s["updated"]),
                         ("acme-rubric", "v1", "acme/skills", "2026-01-15"))
        self.assertIn("tree/v1/skills/rubric", s["source"]["url"])
        self.assertTrue(any("trasig" in w and "hoppas över" in w for w in warnings), warnings)
        self.assertTrue(any("saknas" in w for w in warnings), warnings)

    def test_branch_ref_fails(self):
        _, errors, _ = self.load([{"repo": "acme/skills", "ref": "main"}])
        self.assertTrue(any("gren" in e for e in errors), errors)

    def test_missing_tag_and_bad_repo(self):
        _, errors, _ = self.load([{"repo": "acme/skills", "ref": "v9"}, {"repo": "../x", "ref": "v1"}])
        self.assertEqual(len(errors), 2, errors)

    def test_slug_collision_skipped(self):
        skills, errors, warnings = self.load([{"repo": "acme/skills", "ref": "v1"}], taken={"acme-rubric"})
        self.assertEqual(errors, [])
        self.assertEqual([s["slug"] for s in skills], ["acme-annan"])


if __name__ == "__main__":
    unittest.main()
