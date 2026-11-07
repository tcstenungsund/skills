#!/usr/bin/env python3
"""Validate skills/, fetch pinned external skills from sources.json, build site/.

Python stdlib only. Run from anywhere: python3 scripts/build_site.py
Exit code 1 with one readable Swedish line per problem if anything is wrong.
"""
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB = "https://github.com/"

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LINK = re.compile(r"\]\(([^)\s]+)")
ABSOLUTE = re.compile(r"^([a-z][a-z0-9+.-]*:|#|/)", re.I)
SENSITIVE_NAME = re.compile(r"(?<![a-zåäö])(svar|facit)", re.I)
PERSONNUMMER = re.compile(
    r"(?<!\d)(?:19|20)?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-+]?\d{4}(?!\d)")
CHANGELOG_HEADING = re.compile(r"^(#{1,6})\s*(changelog|versionshistorik|ändringslogg)\b", re.I)
STALE_DAYS = 183
PASTE_LIMIT = 10_000
PASTE_FOOTER = ("Bifoga de nedladdade filerna från webbplatsen om instruktionen "
                "hänvisar till dem.")

PLATFORMS = [
    ("claude", "I Claude", [
        "Klicka på <strong>Ladda ner för Claude</strong> längre ner och spara zip-filen. Packa inte upp den.",
        "Öppna claude.ai och gå till <em>Settings → Capabilities → Skills</em>.",
        "Klicka på <em>Upload skill</em> och välj zip-filen.",
        "Klart. Claude använder skillen av sig själv när den passar.",
    ]),
    ("gemini", "I Gemini", [
        "Klicka på <strong>Kopiera instruktionen</strong> ovan.",
        "Öppna gemini.google.com, välj <em>Gem-hanteraren</em> och sedan <em>Ny Gem</em>.",
        "Klistra in texten i fältet för instruktioner.",
        "Ladda upp filerna under <strong>Filer att ladda upp</strong> som kunskap (om det finns några).",
        "Ge Gem:en skillens namn och version, till exempel ”Skapa prov 1.2.0”, och spara.",
    ]),
    ("chatgpt", "I ChatGPT", [
        "Klicka på <strong>Kopiera instruktionen</strong> ovan.",
        "Öppna chatgpt.com och skapa ett nytt <em>projekt</em>.",
        "Öppna projektets inställningar och klistra in texten under <em>Instruktioner</em>.",
        "Ladda upp filerna under <strong>Filer att ladda upp</strong> till projektet (om det finns några).",
        "Döp projektet till skillens namn och version.",
    ]),
    ("copilot", "I Copilot", [
        "Klicka på <strong>Kopiera instruktionen</strong> ovan.",
        "Öppna Copilot Chat och gå till <em>Settings → Personalization → Custom instructions</em>. "
        "Saknas inställningen eller går den inte att ändra kan skolans IT ha stängt av den – fråga IT.",
        "Klistra in texten och spara.",
        "Rulla till slutet av rutan och kontrollera att sista raden kom med. Copilot kan klippa av "
        "för lång text utan att säga till.",
        "Obs! Copilot har bara <strong>en</strong> instruktionsruta. Klistrar du in en ny skill ersätter du den gamla – ha en skill i taget.",
    ]),
]


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- parsing

def parse_frontmatter(text):
    """Return (meta dict, body). meta is None when there is no frontmatter.

    shortcut: flat `key: value` + `>`/`|` block scalars only, not real YAML;
    upgrade if skills ever need nested keys.
    """
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)(.*)$", text, re.S)
    if not m:
        return None, text
    meta, key, style, block = {}, None, "", []

    def flush():
        if key is not None:
            meta[key] = ("\n" if style.startswith("|") else " ").join(block).strip()

    for line in m.group(1).splitlines():
        if key is not None and (line[:1] in (" ", "\t") or not line.strip()):
            block.append(line.strip())
            continue
        flush()
        key = None
        kv = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if not kv:
            continue
        k, v = kv.groups()
        if not v.startswith(("'", '"')):
            v = re.sub(r"\s+#.*$", "", v)
        v = v.strip()
        if v in ("", ">", ">-", ">+", "|", "|-", "|+"):
            key, style, block = k, v, []
        else:
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            meta[k] = v
    flush()
    return meta, m.group(2)


def relative_links(text):
    return [t for t in LINK.findall(text) if not ABSOLUTE.match(t)]


def changelog(body):
    """Bullet lines of the CHANGELOG section, if any."""
    lines, level, items = body.splitlines(), None, []
    for line in lines:
        h = re.match(r"^(#{1,6})\s", line)
        if level is None:
            m = CHANGELOG_HEADING.match(line)
            if m:
                level = len(m.group(1))
        elif h and len(h.group(1)) <= level:
            break
        elif re.match(r"^\s*[-*]\s+", line):
            items.append(re.sub(r"^\s*[-*]\s+", "", line))
    return items


def paste_block(skill):
    head = f"[{skill['title']} · version {skill['version']} · uppdaterad {skill['updated']}]"
    text = f"{head}\n\n{skill['body'].strip()}\n"
    if skill["links"]:
        text += f"\n{PASTE_FOOTER}\n"
    return text


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def git_date(repo_dir, path):
    code, out, _ = git("log", "-1", "--format=%cs", "--", str(path), cwd=repo_dir)
    return out if code == 0 and ISO_DATE.match(out) else ""


# ------------------------------------------------------------- validation

def check_skill(d, display, allow, external=False):
    """Validate one skill folder. Returns (skill or None, hard, soft).

    hard = problems that stop the skill (and, for local skills, the build);
    soft = warnings. External skills only get hard problems for rules that
    would make the skill unusable or unsafe; the rest become warnings.
    """
    hard, soft = [], []

    def rule(ok, msg, ext_hard=False):
        if not ok:
            (hard if (not external or ext_hard) else soft).append(f"{display}: {msg}")

    rule(KEBAB.match(d.name), "mappnamnet måste vara gemener-med-bindestreck "
         "(inga stora bokstäver, mellanslag eller understreck)", ext_hard=True)
    skill_md = d / "SKILL.md"
    if not skill_md.is_file():
        rule(False, "SKILL.md saknas (måste heta exakt SKILL.md och ligga direkt i mappen)",
             ext_hard=True)
        return None, hard, soft
    meta, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    if meta is None:
        rule(False, "SKILL.md saknar frontmatter (blocket mellan --- överst i filen)",
             ext_hard=True)
        return None, hard, soft

    rule(meta.get("name"), "fältet 'name' saknas i SKILL.md", ext_hard=True)
    rule(meta.get("description"), "fältet 'description' saknas i SKILL.md", ext_hard=True)
    if meta.get("name"):
        rule(meta["name"] == d.name,
             f"'name' ({meta['name']}) måste vara samma som mappnamnet ({d.name})")
    if not external:
        rule(SEMVER.match(meta.get("version", "")),
             "fältet 'version' saknas eller är fel – skriv t.ex. version: 1.2.0")
        rule(ISO_DATE.match(meta.get("updated", "")),
             "fältet 'updated' saknas eller är fel – skriv t.ex. updated: 2026-11-07")
        rule(meta.get("owner"), "fältet 'owner' saknas – skriv namnet på den som ansvarar")
        rule(not (d / "README.md").exists(),
             "README.md får inte finnas i skill-mappen – skriv allt i SKILL.md")
    nlines = body.count("\n") + 1
    rule(nlines <= 500, f"SKILL.md är {nlines} rader lång (max 500) – flytta text till references/")
    if len(meta.get("description", "").split()) > 150:
        soft.append(f"{display}: 'description' är över 150 ord – korta ner den")

    refdir = d / "references"
    if refdir.is_dir():
        for f in sorted(refdir.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(d).as_posix()
            if f.parent != refdir:
                rule(False, f"{rel} ligger i en undermapp – referensfiler får bara ligga "
                     "direkt i references/", ext_hard=True)
            elif f.suffix.lower() == ".md":
                chained = [t for t in relative_links(f.read_text(encoding="utf-8", errors="replace"))
                           if t.split("#")[0].lower().endswith(".md")]
                rule(not chained, f"{rel} länkar vidare till {', '.join(chained)} – referensfiler "
                     "får inte hänvisa till andra referensfiler", ext_hard=True)

    links = relative_links(body)
    for t in links:
        if not (d / t.split("#")[0]).exists():
            soft.append(f"{display}: länken '{t}' i SKILL.md pekar på en fil som inte finns")

    for f in sorted(p for p in d.rglob("*") if p.is_file()):
        rel = f.relative_to(d).as_posix()
        shown = f"{display}/{rel}"
        if shown in allow:
            continue
        if SENSITIVE_NAME.search(rel):
            rule(False, f"filen {rel} ser ut att innehålla svar eller facit – sådant får inte "
                 "publiceras (lägg till sökvägen i sensitive-allow.txt om det är fel)", ext_hard=True)
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if PERSONNUMMER.search(text):
            rule(False, f"filen {rel} innehåller något som liknar ett personnummer – elevdata får "
                 "aldrig publiceras (lägg till sökvägen i sensitive-allow.txt om det är fel)",
                 ext_hard=True)

    if hard:
        return None, hard, soft
    skill = {
        "dir": d,
        "slug": d.name,
        "name": meta["name"],
        "title": meta.get("title") or meta["name"],
        "description": meta["description"],
        "version": meta.get("version", ""),
        "updated": meta.get("updated", ""),
        "owner": meta.get("owner", ""),
        "body": body,
        "links": links,
        "source": None,
    }
    return skill, hard, soft


def load_allow(root):
    f = root / "sensitive-allow.txt"
    if not f.is_file():
        return set()
    return {l.strip() for l in f.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}


def load_local(root, allow, errors, warnings):
    skills = []
    sdir = root / "skills"
    if not sdir.is_dir():
        errors.append("skills/: mappen saknas")
        return skills
    for d in sorted(p for p in sdir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        display = f"skills/{d.name}"
        skill, hard, soft = check_skill(d, display, allow)
        errors += hard
        warnings += soft
        if skill:
            g = git_date(root, d.relative_to(root))
            if g and g > skill["updated"]:
                warnings.append(f"{display}: 'updated' ({skill['updated']}) är äldre än senaste "
                                f"ändringen i git ({g}) – glömde du uppdatera 'updated' och 'version'?")
            skills.append(skill)
    for f in sorted(sdir.iterdir()):
        if f.is_file():
            errors.append(f"skills/{f.name}: lösa filer får inte ligga i skills/ – varje skill "
                          "ska ha en egen mapp")
    return skills


def fetch_source(url, ref, dest):
    """Clone url at a pinned tag/SHA into dest. Returns an error string or ''."""
    if not SHA_RE.match(ref):
        code, heads, err = git("ls-remote", "--heads", url, ref)
        if code:
            return f"kunde inte nå repot ({err or 'okänt fel'})"
        if heads:
            return (f"'{ref}' är en gren, inte en tagg eller commit – lås källan till en tagg "
                    "eller en 40 tecken lång commit-SHA")
        _, tags, _ = git("ls-remote", "--tags", url, ref)
        if not tags:
            return f"taggen '{ref}' finns inte"
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    code, _, err = git("clone", "--quiet", "--filter=blob:none", "--no-checkout", url, str(dest))
    if code:
        return f"kunde inte klona repot ({err})"
    code, _, err = git("-c", "advice.detachedHead=false", "checkout", "--quiet", ref, cwd=dest)
    if code:
        return f"kunde inte checka ut '{ref}' ({err})"
    return ""


def load_external(sources, ext_root, allow, errors, warnings, taken, base=GITHUB):
    skills = []
    if not isinstance(sources, list):
        errors.append("sources.json: filen måste innehålla en lista, t.ex. []")
        return skills
    for i, src in enumerate(sources):
        label = f"sources.json[{i}]"
        if not isinstance(src, dict):
            errors.append(f"{label}: varje källa måste vara ett objekt med 'repo' och 'ref'")
            continue
        repo, ref = str(src.get("repo", "")), str(src.get("ref", ""))
        sub = str(src.get("path", "skills")).strip("/")
        if not REPO_RE.match(repo) or ".." in repo:
            errors.append(f"{label}: 'repo' måste se ut som ägare/namn, t.ex. anthropics/skills")
            continue
        if not REF_RE.match(ref) or ".." in ref:
            errors.append(f"{label} ({repo}): 'ref' saknas eller är ogiltig – ange en tagg eller commit-SHA")
            continue
        if ".." in Path(sub).parts:
            errors.append(f"{label} ({repo}): 'path' får inte innehålla ..")
            continue
        dest = ext_root / repo.replace("/", "__")
        err = fetch_source(f"{base}{repo}.git", ref, dest)
        if err:
            errors.append(f"{label} ({repo}): {err}")
            continue
        sroot = dest / sub if sub else dest
        if not sroot.is_dir():
            errors.append(f"{label} ({repo}): mappen '{sub}' finns inte i {repo}@{ref}")
            continue
        dirs = sorted(p for p in sroot.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
        wanted = src.get("skills")
        if wanted:
            for name in sorted(set(wanted) - {p.name for p in dirs}):
                warnings.append(f"{label} ({repo}): skillen '{name}' finns inte i {repo}@{ref}")
            dirs = [p for p in dirs if p.name in wanted]
        owner = repo.split("/")[0].lower()
        short_ref = ref[:7] if SHA_RE.match(ref) else ref
        for d in dirs:
            rel = d.relative_to(dest).as_posix()
            skill, hard, soft = check_skill(d, f"{repo}/{rel}", allow, external=True)
            warnings += soft
            if not skill:
                warnings += [f"{h} – skillen hoppas över" for h in hard]
                continue
            skill["slug"] = f"{owner}-{d.name}".lower()
            if skill["slug"] in taken:
                warnings.append(f"{repo}/{rel}: adressen '{skill['slug']}' används redan – skillen hoppas över")
                continue
            if not SEMVER.match(skill["version"]):
                skill["version"] = skill["version"] or short_ref
            if not ISO_DATE.match(skill["updated"]):
                skill["updated"] = git_date(dest, rel) or "okänt"
            skill["owner"] = skill["owner"] or repo
            skill["source"] = {"repo": repo, "ref": ref,
                               "url": f"https://github.com/{repo}/tree/{ref}/{rel}"}
            taken.add(skill["slug"])
            skills.append(skill)
    return skills


# ------------------------------------------------------------------ build

DEFAULT_THEME = {"title": "Skills-galleriet", "primary": "#00557f",
                 "background": "#ffffff", "text": "#1a1a1a", "logo": ""}

CSS = """:root{--p:%(primary)s;--bg:%(background)s;--fg:%(text)s;--muted:#4a4a4a;--card:#f3f5f7;--warn:#7a4100}
*{box-sizing:border-box}
body{margin:0;font:1rem/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--fg)}
.top{background:var(--p);padding:.75rem 1rem}
.top a{color:#fff;font-weight:700;font-size:1.15rem;text-decoration:none;display:flex;align-items:center;gap:.6rem}
.logo{height:2rem}
main{max-width:50rem;margin:0 auto;padding:1rem}
a{color:var(--p)}
h1{margin:.5rem 0}
h2{margin-top:2rem}
.card{background:var(--card);border-radius:.5rem;padding:1rem;margin:0 0 1rem}
.card h3{margin:0 0 .25rem}
.meta{color:var(--muted);font-size:.92rem}
.flag{display:inline-block;background:#fff4e5;color:var(--warn);border:1px solid var(--warn);border-radius:1rem;padding:0 .55rem;font-size:.85rem}
.notice{background:#fff4e5;color:#4a2700;border-left:.35rem solid var(--warn);padding:.6rem .8rem}
.version{font-size:1.2rem;font-weight:700;border-left:.35rem solid var(--p);padding:.5rem .8rem;background:var(--card)}
textarea{width:100%%;min-height:14rem;font:.85rem/1.4 ui-monospace,Menlo,Consolas,monospace;padding:.5rem}
button,.btn{display:inline-block;background:var(--p);color:#fff;border:0;border-radius:.4rem;padding:.8rem 1.3rem;font-size:1rem;font-weight:600;text-decoration:none;cursor:pointer}
a:focus-visible,button:focus-visible,textarea:focus-visible{outline:3px solid #ffbf47;outline-offset:2px}
.shot{max-width:100%%;height:auto;border:1px solid #ccc}
footer{max-width:50rem;margin:2rem auto 0;padding:1rem;color:var(--muted);font-size:.85rem;border-top:1px solid #ccc}
"""

COPY_JS = """<script>
document.querySelectorAll('[data-copy]').forEach(function (b) {
  var t = document.getElementById(b.getAttribute('data-copy')), s = document.getElementById('copy-status');
  b.hidden = false;
  b.addEventListener('click', function () {
    function ok() { s.textContent = 'Kopierat! Klistra nu in texten i din AI-tjänst.'; }
    function manual() { s.textContent = 'Det gick inte att kopiera. Markera texten i rutan och kopiera själv.'; }
    function fallback() { t.focus(); t.select(); try { document.execCommand('copy') ? ok() : manual(); } catch (e) { manual(); } }
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(t.value).then(ok, fallback);
    else fallback();
  });
});
</script>"""


def page(title, body, depth, theme, script=""):
    rel = "../" * depth
    logo = f'<img class="logo" src="{rel}{esc(theme["logo"])}" alt="">' if theme.get("logo") else ""
    return f"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS % theme}</style>
</head>
<body>
<header class="top"><a href="{rel}index.html">{logo}{esc(theme["title"])}</a></header>
<main>
{body}
</main>
<footer>
<p>För internt bruk. Våra egna instruktioner får delas under CC BY-SA 4.0.
Skills från andra källor följer licensen i sitt eget repo.</p>
<p>Ändra aldrig en skill direkt i Gemini, ChatGPT eller Copilot – hämta alltid den senaste versionen härifrån.</p>
</footer>
{script}
</body>
</html>
"""


def is_stale(updated, today):
    try:
        return datetime.date.fromisoformat(updated) < today - datetime.timedelta(days=STALE_DAYS)
    except ValueError:
        return False


def meta_line(s, today):
    parts = [f"Version {esc(s['version'])}", f"uppdaterad {esc(s['updated'])}",
             f"ansvarig: {esc(s['owner'])}"]
    out = " · ".join(parts)
    if s["source"]:
        out += (f' · källa: <a href="{esc(s["source"]["url"])}">'
                f'{esc(s["source"]["repo"])}</a>')
    if is_stale(s["updated"], today):
        out += ' <span class="flag">kan behöva ses över</span>'
    return out


def skill_page(s, today, theme, screenshots):
    files = []
    for sub in ("references", "assets"):
        src = s["dir"] / sub
        if src.is_dir():
            files += [f.relative_to(s["dir"]).as_posix()
                      for f in sorted(src.iterdir()) if f.is_file()]
    if files:
        file_list = "<ul>" + "".join(
            f'<li><a href="../../downloads/{esc(s["slug"])}/{esc(f)}" download>'
            f'{esc(f.split("/", 1)[1])}</a></li>' for f in files) + "</ul>"
    else:
        file_list = "<p>Den här skillen har inga extra filer.</p>"

    steps = ""
    paste_len = len(paste_block(s))
    for key, heading, items in PLATFORMS:
        shot = (f'<p><img class="shot" src="../../screenshots/{key}.png" '
                f'alt="Skärmbild: {esc(heading)}"></p>') if key in screenshots else ""
        notice = ""
        if key == "copilot" and paste_len > PASTE_LIMIT:
            notice = (f'<p class="notice"><strong>Obs!</strong> Den här instruktionen är lång '
                      f'({paste_len:,} tecken).'.replace(",", " ") +
                      ' Den kanske inte får plats i Copilot. Kommer inte hela texten med – '
                      'använd skillen i Gemini eller ChatGPT i stället.</p>')
        steps += (f"<h3>{heading}</h3>{notice}<ol>" + "".join(f"<li>{i}</li>" for i in items)
                  + f"</ol>{shot}")

    log = changelog(s["body"])
    history = ("<ul>" + "".join(f"<li>{esc(i)}</li>" for i in log) + "</ul>") if log \
        else "<p>Ingen versionshistorik ännu.</p>"
    source = ""
    if s["source"]:
        source = (f'<p class="meta">Den här skillen kommer från '
                  f'<a href="{esc(s["source"]["url"])}">{esc(s["source"]["repo"])}</a> '
                  f'(version {esc(s["source"]["ref"])}). Licens: se källrepot.</p>')

    body = f"""<p><a href="../../index.html">← Alla skills</a></p>
<h1>{esc(s['title'])}</h1>
<p class="version">Nuvarande version: {esc(s['version'])} ({esc(s['updated'])})</p>
<p class="meta">{meta_line(s, today)}</p>
{source}
<h2>Vad den gör</h2>
<p>{esc(s['description'])}</p>

<h2>Text att klistra in</h2>
<p><button type="button" data-copy="instruktion" hidden>Kopiera instruktionen</button></p>
<p id="copy-status" role="status"></p>
<label for="instruktion">Instruktionen – markera allt och kopiera om knappen inte fungerar:</label>
<textarea id="instruktion" readonly>{esc(paste_block(s))}</textarea>
<p><a href="../../instruktioner/{esc(s['slug'])}.txt">Öppna instruktionen som textfil</a></p>

<h2>Så här gör du</h2>
{steps}
<h2>Ladda ner för Claude</h2>
<p><a class="btn" href="../../downloads/{esc(s['slug'])}.zip" download>Ladda ner för Claude (version {esc(s['version'])})</a></p>

<h2>Filer att ladda upp</h2>
{file_list}

<h2>Versionshistorik</h2>
{history}
"""
    return page(f"{s['title']} – {theme['title']}", body, 2, theme, COPY_JS)


def index_page(local, external, today, theme):
    def cards(skills):
        if not skills:
            return "<p>Inga skills här ännu.</p>"
        return "".join(
            f'<article class="card"><h3><a href="skills/{esc(s["slug"])}/index.html">'
            f'{esc(s["title"])}</a></h3><p>{esc(s["description"])}</p>'
            f'<p class="meta">{meta_line(s, today)}</p></article>'
            for s in sorted(skills, key=lambda s: s["title"].lower()))

    body = f"""<h1>{esc(theme['title'])}</h1>
<p>Här finns skills (färdiga instruktioner) för AI-tjänster som Claude, Gemini, ChatGPT och Copilot.
Klicka på en skill för att kopiera instruktionen eller ladda ner den. Kontrollera versionen ibland –
har din kopia ett lägre versionsnummer än det som står här ska du byta ut den.</p>
<h2>Våra skills</h2>
{cards(local)}
{'<h2>Från andra källor</h2>' + cards(external) if external else ''}
"""
    return page(theme["title"], body, 0, theme)


def build(local, external, out, root, theme, redirects, base_path="", today=None):
    today = today or datetime.date.today()
    if out.exists():
        shutil.rmtree(out)
    for sub in ("skills", "downloads", "instruktioner"):
        (out / sub).mkdir(parents=True)

    screenshots = set()
    for key, _, _ in PLATFORMS:
        shot = root / "docs" / "screenshots" / f"{key}.png"
        if shot.is_file():
            (out / "screenshots").mkdir(exist_ok=True)
            shutil.copy2(shot, out / "screenshots" / shot.name)
            screenshots.add(key)
    if theme.get("logo"):
        logo = root / theme["logo"]
        dest = out / ("logo" + logo.suffix)
        dest.write_bytes(logo.read_bytes())
        theme = {**theme, "logo": dest.name}

    for s in local + external:
        d, slug = s["dir"], s["slug"]
        (out / "skills" / slug).mkdir()
        (out / "skills" / slug / "index.html").write_text(
            skill_page(s, today, theme, screenshots), encoding="utf-8")
        (out / "instruktioner" / f"{slug}.txt").write_text(paste_block(s), encoding="utf-8")
        with zipfile.ZipFile(out / "downloads" / f"{slug}.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    z.write(f, f"{d.name}/{f.relative_to(d).as_posix()}")
        for sub in ("references", "assets"):
            if (d / sub).is_dir():
                shutil.copytree(d / sub, out / "downloads" / slug / sub)

    (out / "index.html").write_text(index_page(local, external, today, theme), encoding="utf-8")
    home = f"{base_path.rstrip('/')}/index.html"
    (out / "404.html").write_text(page(
        f"Sidan finns inte – {theme['title']}",
        f'<h1>Sidan finns inte</h1><p>Skillen kan ha bytt namn eller tagits bort. '
        f'<a href="{esc(home)}">Gå till alla skills</a>.</p>', 0, theme), encoding="utf-8")
    for old, new in redirects.items():
        target = out / "skills" / old
        if KEBAB.match(old) and KEBAB.match(new) and not target.exists():
            target.mkdir()
            (target / "index.html").write_text(
                f'<!doctype html><html lang="sv"><meta charset="utf-8">'
                f'<meta http-equiv="refresh" content="0; url=../{esc(new)}/index.html">'
                f'<title>Flyttad</title><p>Skillen har flyttat: '
                f'<a href="../{esc(new)}/index.html">gå vidare</a>.</p></html>',
                encoding="utf-8")


def read_json(path, default, errors):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{path.name}: ogiltig JSON på rad {e.lineno} ({e.msg})")
        return default


def main(root=ROOT, base=GITHUB):
    errors, warnings = [], []
    allow = load_allow(root)
    theme = {**DEFAULT_THEME, **read_json(root / "site-theme.json", {}, errors)}
    if theme.get("logo") and not (root / theme["logo"]).is_file():
        errors.append(f"site-theme.json: logotypen '{theme['logo']}' finns inte")
    redirects = read_json(root / "redirects.json", {}, errors)
    local = load_local(root, allow, errors, warnings)
    sources = read_json(root / "sources.json", [], errors)
    external = load_external(sources, root / ".external", allow, errors, warnings,
                             {s["slug"] for s in local}, base)
    for s in local + external:
        n = len(paste_block(s))
        if n > PASTE_LIMIT:
            warnings.append(f"{s['slug']}: instruktionen är {n} tecken (rekommenderat max "
                            f"{PASTE_LIMIT}) – flytta text till references/")

    for w in warnings:
        print(f"VARNING: {w}")
    if errors:
        print(f"\nBygget stoppades – {len(errors)} fel måste rättas:", file=sys.stderr)
        for e in errors:
            print(f"  FEL: {e}", file=sys.stderr)
        return 1
    build(local, external, root / "site", root, theme, redirects,
          os.environ.get("SITE_BASE_PATH", ""))
    print(f"Klart: {len(local)} egna och {len(external)} externa skills byggda till site/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
