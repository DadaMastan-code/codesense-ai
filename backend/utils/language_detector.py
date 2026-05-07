from __future__ import annotations

import re

SUPPORTED_LANGUAGES = [
    "python",
    "javascript",
    "typescript",
    "java",
    "cpp",
    "csharp",
    "go",
    "rust",
    "php",
    "ruby",
    "swift",
    "kotlin",
]

_SIGNATURES: list[tuple[str, list[str]]] = [
    ("python", [
        r"^\s*def\s+\w+\s*\(", r"^\s*class\s+\w+.*:", r"import\s+\w+",
        r"from\s+\w+\s+import", r"print\(", r"if\s+__name__\s*==",
        r":\s*$", r"^\s*#",
    ]),
    ("typescript", [
        r":\s*(string|number|boolean|void|any|unknown|never)\b",
        r"\binterface\s+\w+", r"\btype\s+\w+\s*=", r"<[A-Z]\w*>",
        r"import\s+.*from\s+['\"]", r"export\s+(default\s+)?(class|function|const|interface)",
    ]),
    ("javascript", [
        r"\bconst\s+\w+\s*=", r"\blet\s+\w+\s*=", r"\bvar\s+\w+\s*=",
        r"=>\s*{", r"function\s+\w+\s*\(", r"require\s*\(",
        r"module\.exports", r"console\.\w+\(",
    ]),
    ("java", [
        r"\bpublic\s+(static\s+)?(void|class|interface)\b",
        r"\bprivate\s+\w+\s+\w+", r"System\.out\.print",
        r"@Override", r"import\s+java\.", r"\bextends\s+\w+\b",
        r"\bimplements\s+\w+\b",
    ]),
    ("cpp", [
        r"#include\s*<", r"\bstd::", r"\bcout\s*<<", r"\bcin\s*>>",
        r"int\s+main\s*\(", r"\btemplate\s*<", r"nullptr\b",
    ]),
    ("csharp", [
        r"\bnamespace\s+\w+", r"\busing\s+System", r"\bConsole\.",
        r"\bpublic\s+class\b", r"\bstring\[\]", r"\.cs\b",
        r"\bvar\s+\w+\s*=\s*new\b",
    ]),
    ("go", [
        r"\bpackage\s+\w+", r"\bfunc\s+\w+\s*\(", r"\bfmt\.",
        r":=", r"\bgo\s+\w+\(", r"\bchan\s+\w+", r"\bgoroutine\b",
    ]),
    ("rust", [
        r"\bfn\s+\w+\s*\(", r"\blet\s+mut\b", r"\bimpl\s+\w+",
        r"\bpub\s+fn\b", r"\buse\s+std::", r"println!\(", r"\bmatch\b.*{",
    ]),
    ("php", [
        r"<\?php", r"\$\w+\s*=", r"echo\s+", r"function\s+\w+\s*\(",
        r"\barray\s*\(", r"->", r"::",
    ]),
    ("ruby", [
        r"\bdef\s+\w+", r"\bend\b", r"\bputs\b", r"\battr_accessor\b",
        r"\bclass\s+\w+\b", r"\bdo\s*\|", r"\.each\b",
    ]),
    ("swift", [
        r"\bfunc\s+\w+\s*\(", r"\bvar\s+\w+\s*:", r"\blet\s+\w+\s*:",
        r"\bimport\s+Foundation\b", r"\bprint\(", r"\bguard\s+let\b",
        r"\bif\s+let\b",
    ]),
    ("kotlin", [
        r"\bfun\s+\w+\s*\(", r"\bval\s+\w+\s*=", r"\bvar\s+\w+\s*=",
        r"\bdata\s+class\b", r"println\(", r"\bnullable\b",
        r"::\w+",
    ]),
]


def detect_language(code: str) -> str:
    """Return the most-likely programming language for the given code snippet."""
    scores: dict[str, int] = {lang: 0 for lang, _ in _SIGNATURES}
    for lang, patterns in _SIGNATURES:
        for pattern in patterns:
            if re.search(pattern, code, re.MULTILINE):
                scores[lang] += 1

    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "unknown"
