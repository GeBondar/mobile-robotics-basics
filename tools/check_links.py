#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка локальных ссылок в markdown-файлах курса.

Запуск:

    python tools/check_links.py            # проверить весь репозиторий
    python tools/check_links.py --strict   # предупреждения тоже валят проверку
    python tools/check_links.py --stats    # добавить сводку по разобранным ссылкам

Скрипт не требует внешних зависимостей (только стандартная библиотека) и
работает одинаково в Linux, macOS и Windows.

Что проверяется:

* локальные ссылки и картинки во всех `.md` — цель должна существовать на диске
  и совпадать по регистру (GitHub раздаёт файлы с Linux, регистр там значим);
* якоря `#заголовок` — как внутри файла, так и в форме `файл.md#заголовок`;
* таблица уроков в корневом `README.md` — она должна соответствовать
  фактическому списку каталогов `lesson N (...)` и `appendix X (...)`.

Разбор markdown учитывает:

* форму `[текст](<путь с пробелами>)` и заголовки ссылок `[текст](путь "title")`;
* процентное кодирование `%20` и прочие `%XX`;
* reference-style ссылки `[текст][id]` вместе с определениями `[id]: путь`;
* HTML-вставки `<img src=...>` и `<a href=...>`;
* вложенные скобки: `[![alt](img.png)](target.md)`.

Из разбора исключаются fenced-блоки кода (``` и ~~~), инлайн-код в обратных
кавычках, HTML-комментарии, а также вендоренные и служебные каталоги
(см. EXCLUDED_DIRS и EXCLUDED_PATH_PARTS).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from urllib.parse import unquote

# --------------------------------------------------------------------------
# Что не обходим
# --------------------------------------------------------------------------

# Каталоги, которые пропускаем на любом уровне вложенности.
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
    ".ipynb_checkpoints",
    "build",
    "install",
    "log",
}

# Пути относительно корня репозитория (в POSIX-виде), которые пропускаем
# целиком: чужие репозитории, клонируемые локально скриптами приложения Б.
EXCLUDED_PATH_PARTS = (
    "appendix B (microduck policy inference)/microduck",
    "appendix B (microduck policy inference)/microduck_rl",
    "appendix B (microduck policy inference)/policies",
)

# Схемы, которые считаем внешними и не проверяем.
EXTERNAL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

# Абсолютные ссылки на этот же репозиторий: по соглашению курса они должны быть
# относительными.
SELF_REPO_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/[^/]+/mobile-robotics-basics(?:/|$)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Диагностика
# --------------------------------------------------------------------------


class Problem:
    """Одна найденная проблема: файл, строка, колонка, текст."""

    def __init__(self, level, path, line, col, message, hint=None):
        self.level = level  # "error" | "warning"
        self.path = path  # относительный POSIX-путь от корня репозитория
        self.line = line  # 1-based
        self.col = col  # 1-based
        self.message = message
        self.hint = hint

    def format_plain(self):
        head = "%s:%d:%d: %s: %s" % (
            self.path,
            self.line,
            self.col,
            self.level.upper(),
            self.message,
        )
        if self.hint:
            head += "\n        подсказка: " + self.hint
        return head

    def format_github(self):
        # Аннотация GitHub Actions: подсветит строку прямо в диффе.
        text = self.message
        if self.hint:
            text += " | подсказка: " + self.hint
        text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return "::%s file=%s,line=%d,col=%d::%s" % (
            self.level,
            self.path,
            self.line,
            self.col,
            text,
        )


# --------------------------------------------------------------------------
# Маскирование кода
# --------------------------------------------------------------------------

FENCE_OPEN_RE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


def mask_fenced_blocks(lines):
    """Заменяет строки внутри fenced-блоков пробелами, сохраняя нумерацию."""
    out = list(lines)
    i = 0
    n = len(lines)
    while i < n:
        m = FENCE_OPEN_RE.match(lines[i])
        # Открывающий забор из обратных кавычек не может содержать ` в info-строке.
        if m and not (m.group("fence")[0] == "`" and "`" in m.group("info")):
            fence_char = m.group("fence")[0]
            fence_len = len(m.group("fence"))
            out[i] = ""
            i += 1
            while i < n:
                close = re.match(
                    r"^ {0,3}(%s{%d,}) *$" % (re.escape(fence_char), fence_len),
                    lines[i],
                )
                out[i] = ""
                i += 1
                if close:
                    break
            continue
        i += 1
    return out


def mask_spans(text, spans):
    """Заменяет указанные диапазоны пробелами, не трогая переводы строк."""
    if not spans:
        return text
    chars = list(text)
    for start, end in spans:
        for k in range(start, min(end, len(chars))):
            if chars[k] != "\n":
                chars[k] = " "
    return "".join(chars)


def find_inline_code_spans(text):
    """Диапазоны инлайн-кода: пара одинаковых по длине серий обратных кавычек."""
    spans = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "`":
            # Экранированная кавычка кодом не открывается.
            backslashes = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                backslashes += 1
                j -= 1
            run_start = i
            while i < n and text[i] == "`":
                i += 1
            run_len = i - run_start
            if backslashes % 2 == 1:
                continue
            # Ищем закрывающую серию ровно такой же длины.
            k = i
            while k < n:
                if text[k] == "`":
                    close_start = k
                    while k < n and text[k] == "`":
                        k += 1
                    if k - close_start == run_len:
                        spans.append((run_start, k))
                        i = k
                        break
                else:
                    k += 1
            else:
                # Закрытия нет — это обычный текст, кавычки не маскируем.
                pass
        else:
            i += 1
    return spans


def find_html_comment_spans(text):
    return [(m.start(), m.end()) for m in re.finditer(r"<!--.*?-->", text, re.DOTALL)]


def build_masked_text(raw):
    """Возвращает текст той же длины, где код и комментарии заменены пробелами."""
    lines = raw.split("\n")
    masked_lines = mask_fenced_blocks(lines)
    # Восстанавливаем длину каждой строки, чтобы смещения не разъехались.
    rebuilt = []
    for original, masked in zip(lines, masked_lines):
        rebuilt.append(masked if masked else " " * len(original))
    text = "\n".join(rebuilt)
    text = mask_spans(text, find_html_comment_spans(text))
    text = mask_spans(text, find_inline_code_spans(text))
    return text


def line_col(offsets, pos):
    """Переводит смещение в паре (строка, колонка), обе 1-based."""
    lo, hi = 0, len(offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if offsets[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1, pos - offsets[lo] + 1


def line_offsets(text):
    offsets = [0]
    for m in re.finditer(r"\n", text):
        offsets.append(m.end())
    return offsets


# --------------------------------------------------------------------------
# Разбор ссылок
# --------------------------------------------------------------------------


class Link:
    def __init__(self, dest, pos, kind, raw):
        self.dest = dest
        self.pos = pos  # смещение начала ссылки в тексте
        self.kind = kind  # "inline" | "reference" | "html"
        self.raw = raw


def _is_escaped(text, pos):
    backslashes = 0
    j = pos - 1
    while j >= 0 and text[j] == "\\":
        backslashes += 1
        j -= 1
    return backslashes % 2 == 1


def _match_bracket(text, start):
    """Ищет закрывающую `]` для `[` в позиции start с учётом вложенности."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _parse_destination(text, i):
    """Разбирает `(<dest> "title")` начиная с позиции открывающей скобки.

    Возвращает (dest, end_index) либо (None, None), если это не ссылка.
    """
    n = len(text)
    assert text[i] == "("
    i += 1
    while i < n and text[i] in " \t\n":
        i += 1
    if i >= n:
        return None, None

    if text[i] == "<":
        j = i + 1
        buf = []
        while j < n and text[j] not in ("\n",):
            if text[j] == "\\" and j + 1 < n:
                buf.append(text[j + 1])
                j += 2
                continue
            if text[j] == ">":
                break
            buf.append(text[j])
            j += 1
        if j >= n or text[j] != ">":
            return None, None
        dest = "".join(buf)
        i = j + 1
    else:
        buf = []
        depth = 0
        j = i
        while j < n:
            ch = text[j]
            if ch == "\\" and j + 1 < n:
                buf.append(text[j + 1])
                j += 2
                continue
            if ch in " \t\n":
                break
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            buf.append(ch)
            j += 1
        if depth != 0:
            return None, None
        dest = "".join(buf)
        i = j

    # Необязательный заголовок ссылки.
    while i < n and text[i] in " \t\n":
        i += 1
    if i < n and text[i] in "\"'(":
        closer = {'"': '"', "'": "'", "(": ")"}[text[i]]
        j = i + 1
        while j < n:
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == closer:
                break
            j += 1
        if j >= n:
            return None, None
        i = j + 1
        while i < n and text[i] in " \t\n":
            i += 1

    if i >= n or text[i] != ")":
        return None, None
    return dest, i + 1


REF_DEF_RE = re.compile(
    r"^ {0,3}\[(?P<id>[^\]\n]+)\]:[ \t]*(?P<dest><[^>\n]*>|\S+)", re.MULTILINE
)

HTML_ATTR_RE = re.compile(
    r"<(?:img|a|source|video|embed|iframe)\b[^>]*?\b(?:src|href)\s*=\s*"
    r"(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'|(?P<bare>[^\s>]+))",
    re.IGNORECASE,
)


def parse_links(text):
    """Возвращает (список Link, список позиций непонятых конструкций `](`)."""
    links = []
    suspicious = []

    # Определения reference-style ссылок.
    ref_defs = {}
    for m in REF_DEF_RE.finditer(text):
        dest = m.group("dest")
        if dest.startswith("<") and dest.endswith(">"):
            dest = dest[1:-1]
        ref_id = m.group("id").strip().lower()
        ref_defs[ref_id] = (dest, m.start("dest"))
        links.append(Link(dest, m.start("dest"), "reference", m.group(0)))

    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch != "[" or _is_escaped(text, i):
            i += 1
            continue
        close = _match_bracket(text, i)
        if close == -1:
            i += 1
            continue
        label = text[i + 1 : close]
        after = close + 1
        if after < n and text[after] == "(":
            dest, end = _parse_destination(text, after)
            if dest is None:
                suspicious.append(close)
                i = close + 1
                continue
            links.append(Link(dest, i, "inline", text[i:end]))
            i = end
            continue
        if after < n and text[after] == "[":
            ref_close = _match_bracket(text, after)
            if ref_close != -1:
                ref_id = text[after + 1 : ref_close].strip().lower()
                if not ref_id:
                    ref_id = label.strip().lower()
                if ref_id in ref_defs:
                    dest, _ = ref_defs[ref_id]
                    links.append(Link(dest, i, "reference", text[i : ref_close + 1]))
                i = ref_close + 1
                continue
        i = close + 1

    for m in HTML_ATTR_RE.finditer(text):
        dest = m.group("dq") or m.group("sq") or m.group("bare") or ""
        if dest:
            links.append(Link(dest, m.start(), "html", m.group(0)))

    links.sort(key=lambda link: link.pos)
    return links, suspicious


# --------------------------------------------------------------------------
# Якоря
# --------------------------------------------------------------------------

ATX_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(?P<text>.*?)[ \t]*#*[ \t]*$")
SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")


def _strip_emphasis(s):
    """Снимает markdown-выделение, не трогая подчёркивания внутри слов.

    `send_goal`, `ROS_DISTRO`, `rqt_console` должны остаться как есть:
    в CommonMark подчёркивание внутри слова выделения не открывает,
    и GitHub оставляет его в якоре.
    """
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r"\1", s)
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", s)
    return s


def strip_inline_markup(s):
    """Убирает разметку из текста заголовка, оставляя видимый текст."""
    # Инлайн-код выносим из-под правил выделения: внутри него `*` и `_`
    # остаются обычными символами.
    code_chunks = []

    def stash(m):
        code_chunks.append(m.group(2))
        return "\x00%d\x00" % (len(code_chunks) - 1)

    s = re.sub(r"(`+)(.*?)\1", stash, s)

    s = re.sub(r"<[^>]+>", "", s)  # HTML-теги
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)  # картинки
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # ссылки
    s = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", s)  # reference-ссылки
    s = _strip_emphasis(s)
    s = re.sub(r"\\(.)", r"\1", s)  # экранирование

    def restore(m):
        return code_chunks[int(m.group(1))]

    s = re.sub(r"\x00(\d+)\x00", restore, s)
    return s.strip()


def github_slug(heading_text):
    """Слаг заголовка по правилам GitHub (Unicode сохраняется)."""
    text = strip_inline_markup(heading_text).lower()
    out = []
    for ch in text:
        if ch in " \t":
            out.append("-")
            continue
        if ch == "-" or ch == "_":
            out.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "N", "M") or cat in ("Pc", "Cf"):
            out.append(ch)
        # остальное (пунктуация, эмодзи) отбрасывается
    return "".join(out)


def collect_anchors(raw):
    """Множество якорей файла с учётом дедупликации GitHub (`-1`, `-2`, ...)."""
    lines = raw.split("\n")
    masked = mask_fenced_blocks(lines)
    anchors = set()
    seen = {}

    def add(text):
        base = github_slug(text)
        if not base:
            return
        count = seen.get(base, 0)
        slug = base if count == 0 else "%s-%d" % (base, count)
        seen[base] = count + 1
        anchors.add(slug)

    for idx, line in enumerate(masked):
        if not line:
            continue
        m = ATX_RE.match(line)
        if m:
            add(m.group("text"))
            continue
        if SETEXT_RE.match(line) and idx > 0:
            prev = masked[idx - 1]
            if prev.strip() and not ATX_RE.match(prev) and "|" not in prev:
                add(prev)

    # Пользовательские якоря вида <a id="..."> / <a name="...">
    for m in re.finditer(
        r"<a\b[^>]*?\b(?:id|name)\s*=\s*[\"']([^\"']+)[\"']", raw, re.IGNORECASE
    ):
        anchors.add(m.group(1))
    for m in re.finditer(r"<[^>]*\bid\s*=\s*[\"']([^\"']+)[\"']", raw, re.IGNORECASE):
        anchors.add(m.group(1))
    return anchors


# --------------------------------------------------------------------------
# Файловая система: точное совпадение регистра
# --------------------------------------------------------------------------


class CaseIndex:
    """Кэш listdir для проверки регистра на регистронезависимых ФС."""

    def __init__(self):
        self._cache = {}

    def entries(self, directory):
        key = os.path.normcase(os.path.abspath(directory))
        if key not in self._cache:
            try:
                self._cache[key] = set(os.listdir(directory))
            except OSError:
                self._cache[key] = set()
        return self._cache[key]

    def resolve(self, root, rel_parts):
        """Возвращает ("ok"|"missing"|"case", фактический_путь_или_None)."""
        current = root
        for part in rel_parts:
            if part in ("", "."):
                continue
            if part == "..":
                current = os.path.dirname(current)
                continue
            entries = self.entries(current)
            if part in entries:
                current = os.path.join(current, part)
                continue
            lowered = {e.lower(): e for e in entries}
            actual = lowered.get(part.lower())
            if actual is None:
                return "missing", None
            return "case", os.path.join(current, actual)
        return "ok", current


# --------------------------------------------------------------------------
# Обход репозитория
# --------------------------------------------------------------------------


def is_excluded(rel_posix):
    for part in EXCLUDED_PATH_PARTS:
        if rel_posix == part or rel_posix.startswith(part + "/"):
            return True
    return False


def iter_markdown_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""
        keep = []
        for d in sorted(dirnames):
            if d in EXCLUDED_DIRS or d.endswith(".egg-info"):
                continue
            child = (rel_dir + "/" + d) if rel_dir else d
            if is_excluded(child):
                continue
            keep.append(d)
        dirnames[:] = keep
        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            rel = (rel_dir + "/" + name) if rel_dir else name
            yield rel


def read_text(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


# --------------------------------------------------------------------------
# Проверка ссылок
# --------------------------------------------------------------------------


def split_dest(dest):
    """Делит цель на путь и якорь, не путая якорь с `#` внутри имени файла."""
    if "#" in dest:
        path, _, anchor = dest.partition("#")
        return path, anchor
    return dest, ""


def check_file(root, rel_path, anchors_cache, case_index, problems, stats):
    abs_path = os.path.join(root, rel_path.replace("/", os.sep))
    raw = read_text(abs_path)
    masked = build_masked_text(raw)
    offsets = line_offsets(masked)
    links, suspicious = parse_links(masked)

    # Контроль полноты парсера: каждое вхождение `](` вне кода должно попасть
    # внутрь разобранной inline-ссылки. Непокрытые — либо экранированные
    # `\[...\]`, либо кривая разметка (о ней ниже отдельное предупреждение).
    inline_spans = [
        (link.pos, link.pos + len(link.raw)) for link in links if link.kind == "inline"
    ]
    for m in re.finditer(r"\]\(", masked):
        stats["raw_occurrences"] += 1
        if not any(start <= m.start() < end for start, end in inline_spans):
            stats["unparsed_occurrences"] += 1
    stats["parsed_inline"] += len(inline_spans)

    for pos in suspicious:
        line, col = line_col(offsets, pos)
        snippet = masked[pos : pos + 60].split("\n")[0]
        problems.append(
            Problem(
                "warning",
                rel_path,
                line,
                col,
                "конструкция `](...)` не разобрана как ссылка: %r" % snippet,
                "путь с пробелами оформляйте угловыми скобками: "
                "[текст](<lesson 9 (lidar sensors)/2d_lidar.md>)",
            )
        )

    for link in links:
        dest = link.dest.strip()
        line, col = line_col(offsets, link.pos)
        if not dest:
            problems.append(
                Problem("error", rel_path, line, col, "пустая цель ссылки `]()`")
            )
            continue

        if SELF_REPO_RE.match(dest):
            stats["self_urls"] += 1
            problems.append(
                Problem(
                    "warning",
                    rel_path,
                    line,
                    col,
                    "абсолютная ссылка на собственный репозиторий: %s" % dest,
                    "по соглашению курса ссылки внутрь репозитория должны быть "
                    "относительными",
                )
            )
            continue

        if dest.startswith("//") or EXTERNAL_SCHEME_RE.match(dest):
            stats["external"] += 1
            continue

        path_part, anchor = split_dest(dest)
        path_part = unquote(path_part)
        anchor = unquote(anchor)

        # Ссылка только на якорь внутри текущего файла.
        if not path_part:
            stats["anchors"] += 1
            if rel_path not in anchors_cache:
                anchors_cache[rel_path] = collect_anchors(raw)
            if anchor and anchor not in anchors_cache[rel_path]:
                problems.append(
                    Problem(
                        "error",
                        rel_path,
                        line,
                        col,
                        "нет заголовка для якоря `#%s`" % anchor,
                        "заголовки файла дают якоря: "
                        + ", ".join(sorted(anchors_cache[rel_path])[:5])
                        + (" ..." if len(anchors_cache[rel_path]) > 5 else ""),
                    )
                )
            continue

        stats["local"] += 1

        if path_part.startswith("/"):
            base_dir = root
            rel_parts = [p for p in path_part.split("/") if p]
            hint = (
                "на GitHub ведущий `/` уводит в корень сайта, а не репозитория; "
                "используйте путь относительно текущего файла"
            )
        else:
            base_dir = root
            current_dir = os.path.dirname(rel_path)
            joined = (current_dir + "/" + path_part) if current_dir else path_part
            rel_parts = []
            for part in joined.replace("\\", "/").split("/"):
                if part in ("", "."):
                    continue
                if part == "..":
                    if rel_parts:
                        rel_parts.pop()
                    continue
                rel_parts.append(part)
            hint = None

        status, actual = case_index.resolve(base_dir, rel_parts)
        target_rel = "/".join(rel_parts)

        if status == "missing":
            problems.append(
                Problem(
                    "error",
                    rel_path,
                    line,
                    col,
                    "битая ссылка: `%s` -> нет файла `%s`" % (dest, target_rel),
                    hint,
                )
            )
            continue
        if status == "case":
            actual_rel = os.path.relpath(actual, root).replace(os.sep, "/")
            problems.append(
                Problem(
                    "error",
                    rel_path,
                    line,
                    col,
                    "регистр не совпадает: `%s` -> на диске `%s`" % (dest, actual_rel),
                    "GitHub раздаёт файлы с Linux, там регистр значим",
                )
            )
            continue

        if anchor:
            if not target_rel.lower().endswith(".md"):
                continue
            if target_rel not in anchors_cache:
                anchors_cache[target_rel] = collect_anchors(
                    read_text(os.path.join(root, target_rel.replace("/", os.sep)))
                )
            if anchor not in anchors_cache[target_rel]:
                problems.append(
                    Problem(
                        "error",
                        rel_path,
                        line,
                        col,
                        "битый якорь: в `%s` нет заголовка `#%s`" % (target_rel, anchor),
                    )
                )


# --------------------------------------------------------------------------
# Таблица уроков в README.md
# --------------------------------------------------------------------------

LESSON_DIR_RE = re.compile(r"^lesson (\d+) \(.+\)$")
APPENDIX_DIR_RE = re.compile(r"^appendix ([A-Za-zА-Яа-я]) \(.+\)$")
STRUCTURE_HEADING_RE = re.compile(r"^ {0,3}##\s+(?:Карта|Структура)\s+курса\s*$", re.IGNORECASE)


def course_dirs(root):
    """Фактические каталоги уроков и приложений в корне репозитория."""
    lessons = {}
    appendices = {}
    for name in sorted(os.listdir(root)):
        if not os.path.isdir(os.path.join(root, name)):
            continue
        m = LESSON_DIR_RE.match(name)
        if m:
            lessons.setdefault(int(m.group(1)), []).append(name)
            continue
        m = APPENDIX_DIR_RE.match(name)
        if m:
            appendices.setdefault(m.group(1).upper(), []).append(name)
    return lessons, appendices


def split_table_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def check_readme_table(root, problems):
    readme_rel = "README.md"
    readme_abs = os.path.join(root, readme_rel)
    if not os.path.exists(readme_abs):
        problems.append(
            Problem("error", readme_rel, 1, 1, "в корне репозитория нет README.md")
        )
        return

    raw = read_text(readme_abs)
    lines = raw.split("\n")
    masked_lines = mask_fenced_blocks(lines)

    start = None
    for idx, line in enumerate(masked_lines):
        if line and STRUCTURE_HEADING_RE.match(line):
            start = idx
            break
    if start is None:
        problems.append(
            Problem(
                "error",
                readme_rel,
                1,
                1,
                "не найден раздел `## Карта курса` с таблицей уроков",
                "проверка таблицы уроков опирается на этот заголовок",
            )
        )
        return

    # Первая таблица после заголовка.
    rows = []  # (номер_строки_1based, ячейки)
    in_table = False
    for idx in range(start + 1, len(masked_lines)):
        line = masked_lines[idx]
        if line is None:
            continue
        stripped = line.strip()
        if not stripped:
            if in_table:
                break
            continue
        if stripped.startswith("#"):
            break
        if not stripped.startswith("|"):
            if in_table:
                break
            continue
        in_table = True
        cells = split_table_row(stripped)
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append((idx + 1, cells))

    if len(rows) < 2:
        problems.append(
            Problem(
                "error",
                readme_rel,
                start + 1,
                1,
                "после заголовка `## Карта курса` не найдена таблица уроков",
            )
        )
        return

    header, body = rows[0], rows[1:]
    del header

    lessons, appendices = course_dirs(root)
    referenced_dirs = {}
    seen_numbers = {}

    for line_no, cells in body:
        if len(cells) < 2:
            problems.append(
                Problem(
                    "error",
                    readme_rel,
                    line_no,
                    1,
                    "строка таблицы уроков должна иметь минимум 2 колонки "
                    "(номер и ссылка на урок), найдено %d" % len(cells),
                )
            )
            continue
        number_cell = cells[0]
        # Ссылка на материал урока может стоять в ЛЮБОЙ колонке, кроме первой
        # (в ней номер). Таблица курса менялась: раньше «номер | тема | навигация»,
        # теперь «номер | урок | статей | что ставим | железо | результат», и
        # ссылка переехала из последней колонки во вторую.
        nav_cell = " ".join(cells[1:])

        links, _ = parse_links(nav_cell)
        local = [
            link
            for link in links
            if not EXTERNAL_SCHEME_RE.match(link.dest) and not link.dest.startswith("//")
        ]
        if not local:
            problems.append(
                Problem(
                    "error",
                    readme_rel,
                    line_no,
                    1,
                    "в строке таблицы `%s` нет локальной ссылки на материал"
                    % number_cell,
                )
            )
            continue

        target = unquote(split_dest(local[0].dest)[0])
        top = target.replace("\\", "/").split("/")[0]
        if top not in referenced_dirs:
            referenced_dirs[top] = line_no
        else:
            problems.append(
                Problem(
                    "error",
                    readme_rel,
                    line_no,
                    1,
                    "каталог `%s` указан в таблице уроков дважды "
                    "(первый раз — строка %d)" % (top, referenced_dirs[top]),
                )
            )

        if not os.path.isdir(os.path.join(root, top.replace("/", os.sep))):
            problems.append(
                Problem(
                    "error",
                    readme_rel,
                    line_no,
                    1,
                    "таблица уроков ссылается на каталог `%s`, которого нет на диске"
                    % top,
                )
            )
            continue

        m_num = re.fullmatch(r"\d+", number_cell)
        m_dir = LESSON_DIR_RE.match(top)
        if m_num:
            num = int(number_cell)
            if num in seen_numbers:
                problems.append(
                    Problem(
                        "error",
                        readme_rel,
                        line_no,
                        1,
                        "номер урока %d встречается в таблице дважды "
                        "(первый раз — строка %d)" % (num, seen_numbers[num]),
                    )
                )
            else:
                seen_numbers[num] = line_no
            if m_dir and int(m_dir.group(1)) != num:
                problems.append(
                    Problem(
                        "error",
                        readme_rel,
                        line_no,
                        1,
                        "урок %d в таблице ведёт на каталог `%s` (урок %s)"
                        % (num, top, m_dir.group(1)),
                        "после перенумерации уроков номер в таблице и номер "
                        "в имени каталога должны совпадать",
                    )
                )
            elif not m_dir:
                problems.append(
                    Problem(
                        "error",
                        readme_rel,
                        line_no,
                        1,
                        "урок %d в таблице ведёт на каталог `%s`, который не "
                        "является каталогом урока" % (num, top),
                    )
                )

    # Каталоги на диске, которых нет в таблице.
    for num in sorted(lessons):
        for name in lessons[num]:
            if name not in referenced_dirs:
                problems.append(
                    Problem(
                        "error",
                        readme_rel,
                        start + 1,
                        1,
                        "каталог `%s` есть на диске, но его нет в таблице уроков"
                        % name,
                    )
                )
    for letter in sorted(appendices):
        for name in appendices[letter]:
            if name not in referenced_dirs:
                problems.append(
                    Problem(
                        "error",
                        readme_rel,
                        start + 1,
                        1,
                        "каталог `%s` есть на диске, но его нет в таблице уроков"
                        % name,
                    )
                )

    # Два каталога с одним и тем же номером урока.
    for num in sorted(lessons):
        if len(lessons[num]) > 1:
            problems.append(
                Problem(
                    "error",
                    readme_rel,
                    start + 1,
                    1,
                    "номер урока %d занят сразу несколькими каталогами: %s"
                    % (num, ", ".join("`%s`" % n for n in lessons[num])),
                )
            )


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Проверка локальных ссылок и таблицы уроков курса."
    )
    parser.add_argument(
        "--root",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="корень репозитория (по умолчанию — каталог выше tools/)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="считать предупреждения ошибками",
    )
    parser.add_argument(
        "--no-readme-table",
        action="store_true",
        help="не проверять таблицу уроков в README.md",
    )
    parser.add_argument(
        "--only-readme-table",
        action="store_true",
        help="проверить только таблицу уроков в README.md",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="вывести сводку по разобранным ссылкам",
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="дополнительно печатать аннотации GitHub Actions",
    )
    args = parser.parse_args(argv)

    # Сообщения на русском: на Windows консоль по умолчанию не UTF-8.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.stderr.write("Нет каталога: %s\n" % root)
        return 2

    problems = []
    stats = {
        "files": 0,
        "local": 0,
        "external": 0,
        "anchors": 0,
        "self_urls": 0,
        "raw_occurrences": 0,
        "unparsed_occurrences": 0,
        "parsed_inline": 0,
    }
    anchors_cache = {}
    case_index = CaseIndex()

    if not args.only_readme_table:
        for rel_path in iter_markdown_files(root):
            stats["files"] += 1
            try:
                check_file(root, rel_path, anchors_cache, case_index, problems, stats)
            except UnicodeDecodeError as exc:
                problems.append(
                    Problem(
                        "error", rel_path, 1, 1, "файл не читается как UTF-8: %s" % exc
                    )
                )

    if not args.no_readme_table:
        check_readme_table(root, problems)

    problems.sort(key=lambda p: (p.path, p.line, p.col, p.level))

    errors = [p for p in problems if p.level == "error"]
    warnings = [p for p in problems if p.level == "warning"]

    use_github = args.github or os.environ.get("GITHUB_ACTIONS") == "true"

    for problem in problems:
        print(problem.format_plain())
        if use_github:
            print(problem.format_github())

    if problems:
        print("")

    if args.stats:
        print("Разобрано файлов .md: %d" % stats["files"])
        print(
            "Ссылок: локальных %d, якорей внутри файла %d, внешних %d"
            % (stats["local"], stats["anchors"], stats["external"])
        )
        print(
            "Контроль парсера: вхождений `](` вне кода %d, "
            "разобрано inline-ссылок %d, не разобрано вхождений %d"
            % (
                stats["raw_occurrences"],
                stats["parsed_inline"],
                stats["unparsed_occurrences"],
            )
        )
        print("")

    if args.only_readme_table:
        print(
            "Проверена таблица уроков в README.md: ошибок %d, предупреждений %d."
            % (len(errors), len(warnings))
        )
    else:
        print(
            "Проверено %d файлов .md: ошибок %d, предупреждений %d."
            % (stats["files"], len(errors), len(warnings))
        )

    if errors:
        if args.only_readme_table:
            reason = "таблица уроков в README.md разошлась с каталогами на диске"
        elif args.no_readme_table:
            reason = "в markdown есть битые локальные ссылки или якоря"
        else:
            reason = "битые локальные ссылки или расхождения в README.md"
        print("")
        print("ПРОВЕРКА НЕ ПРОЙДЕНА: %s." % reason)
        print("Каждая строка выше — это файл:строка:колонка и суть проблемы.")
        print("Локальный повтор проверки: python tools/check_links.py --stats")
        return 1
    if warnings and args.strict:
        print("")
        print("ПРОВЕРКА НЕ ПРОЙДЕНА (--strict): есть предупреждения.")
        return 1
    print("Проверка пройдена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
