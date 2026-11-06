#!/usr/bin/env python3
"""Seed the throwaway Gitea (demo data only: users ada/grace/linus, org aurora)."""
import base64, json, sys, urllib.request, urllib.error, time

BASE = "http://127.0.0.1:3399"
PW = "Demo-pass-2026!"


def call(method, path, data=None, user="ada", token=None):
    url = BASE + "/api/v1" + path
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", "token " + token)
    else:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{PW}".encode()).decode())
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, body) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, method, path, e.read().decode()[:300], file=sys.stderr)
        raise


def b64(s):
    return base64.b64encode(s.encode()).decode()


def put_file(repo, path, content, msg, branch="main", new_branch=None, user="ada", sha=None):
    d = {"content": b64(content), "message": msg, "branch": branch}
    if new_branch:
        d["new_branch"] = new_branch
    if sha:
        d["sha"] = sha
        return call("PUT", f"/repos/{repo}/contents/{path}", d, user=user)
    return call("POST", f"/repos/{repo}/contents/{path}", d, user=user)


def sha_of(repo, path, ref):
    return call("GET", f"/repos/{repo}/contents/{path}?ref={ref}")["sha"]


call("POST", "/orgs", {"username": "aurora", "full_name": "Aurora Labs", "description": "Small tools for careful bookkeeping.", "visibility": "public"})
for u in ("grace", "linus"):
    teams = call("GET", "/orgs/aurora/teams")
    owners = [t for t in teams if t["name"] == "Owners"][0]
    call("PUT", f"/teams/{owners['id']}/members/{u}")

call("POST", "/orgs/aurora/repos", {"name": "ledger", "description": "A tiny double-entry ledger for Python.", "auto_init": False, "default_branch": "main", "private": False})
R = "aurora/ledger"

README = """# ledger

A tiny double-entry ledger for Python. No dependencies, no database, just plain data.

## Install

```bash
pip install aurora-ledger
```

## Quick start

```python
from ledger import Ledger, Money

book = Ledger("household")
book.post("rent", debit="expenses:rent", credit="assets:bank", amount=Money("950.00"))
book.post("coffee", debit="expenses:food", credit="assets:cash", amount=Money("3.40"))

print(book.balance("assets:bank"))   # -950.00
```

## Features

| Feature | Status | Notes |
| --- | :---: | --- |
| Double-entry postings | stable | Every posting balances to zero |
| Multi-currency | beta | Rates are supplied by the caller |
| CSV import | planned | See issue #3 |
| Rounding modes | in review | Pull request #1 |

## Roadmap

- [x] Core posting API
- [x] Balance queries
- [ ] Rounding modes
- [ ] CSV import
- [ ] Reports (`ledger.reports`)

> **Note**
> Amounts are stored as integers of the smallest unit to avoid float drift.

## License

MIT. See `LICENSE`.
"""

CORE = '''"""Core ledger types."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

CENTS = 100


class LedgerError(Exception):
    """Raised when a posting would break the books."""


@dataclass(frozen=True)
class Money:
    """An amount stored as integer cents."""

    cents: int

    def __init__(self, value: str | int | Decimal) -> None:
        if isinstance(value, int):
            object.__setattr__(self, "cents", value)
        else:
            object.__setattr__(self, "cents", int(Decimal(value) * CENTS))

    def __add__(self, other: "Money") -> "Money":
        return Money(self.cents + other.cents)

    def __neg__(self) -> "Money":
        return Money(-self.cents)

    def __str__(self) -> str:
        sign = "-" if self.cents < 0 else ""
        whole, frac = divmod(abs(self.cents), CENTS)
        return f"{sign}{whole}.{frac:02d}"


@dataclass
class Posting:
    memo: str
    debit: str
    credit: str
    amount: Money


@dataclass
class Ledger:
    name: str
    postings: list[Posting] = field(default_factory=list)

    def post(self, memo: str, *, debit: str, credit: str, amount: Money) -> Posting:
        if debit == credit:
            raise LedgerError(f"debit and credit are the same account: {debit!r}")
        if amount.cents <= 0:
            raise LedgerError("amount must be positive")
        posting = Posting(memo, debit, credit, amount)
        self.postings.append(posting)
        return posting

    def balance(self, account: str) -> Money:
        total = Money(0)
        for p in self.postings:
            if p.debit == account:
                total = total + p.amount
            elif p.credit == account:
                total = total + (-p.amount)
        return total

    def accounts(self) -> Iterable[str]:
        seen: set[str] = set()
        for p in self.postings:
            seen.update((p.debit, p.credit))
        return sorted(seen)
'''

INIT = '''from .core import Ledger, LedgerError, Money, Posting

__all__ = ["Ledger", "LedgerError", "Money", "Posting"]
__version__ = "0.3.0"
'''

TEST = '''import pytest

from ledger import Ledger, LedgerError, Money


def test_balance_follows_postings():
    book = Ledger("test")
    book.post("rent", debit="expenses:rent", credit="assets:bank", amount=Money("950.00"))
    assert str(book.balance("assets:bank")) == "-950.00"


def test_same_account_is_rejected():
    book = Ledger("test")
    with pytest.raises(LedgerError):
        book.post("oops", debit="a", credit="a", amount=Money("1.00"))
'''

put_file(R, "README.md", README, "Add README")
put_file(R, "ledger/core.py", CORE, "Add core ledger types")
put_file(R, "ledger/__init__.py", INIT, "Expose the public API")
put_file(R, "tests/test_core.py", TEST, "Cover balances and invalid postings")
put_file(R, "LICENSE", "MIT License\n\nCopyright (c) 2026 Aurora Labs\n", "Add license")

# labels
labels = {}
for name, color, desc in [
    ("bug", "#d73a4a", "Something is not working"),
    ("enhancement", "#4a8fd7", "New feature or request"),
    ("documentation", "#7b6fc9", "Improvements or additions to docs"),
    ("good first issue", "#4aa86b", "Good for newcomers"),
    ("help wanted", "#d9a441", "Extra attention is needed"),
    ("wontfix", "#8a939e", "This will not be worked on"),
]:
    labels[name] = call("POST", f"/repos/{R}/labels", {"name": name, "color": color, "description": desc})["id"]

# feature branch with a diff (rounding modes)
CORE2 = CORE.replace(
    "from decimal import Decimal\n",
    "from decimal import ROUND_HALF_EVEN, Decimal\n",
).replace(
    '''            object.__setattr__(self, "cents", int(Decimal(value) * CENTS))
''',
    '''            exact = Decimal(value) * CENTS
            object.__setattr__(self, "cents", int(exact.quantize(Decimal(1), rounding=rounding)))
''',
).replace(
    "def __init__(self, value: str | int | Decimal) -> None:",
    "def __init__(self, value: str | int | Decimal, rounding: str = ROUND_HALF_EVEN) -> None:",
).replace(
    '''        if amount.cents <= 0:
            raise LedgerError("amount must be positive")
''',
    '''        if amount.cents == 0:
            raise LedgerError("amount must not be zero")
''',
).replace(
    '''    def accounts(self) -> Iterable[str]:''',
    '''    def trial_balance(self) -> dict[str, Money]:
        """Return the balance of every account that has postings."""
        return {name: self.balance(name) for name in self.accounts()}

    def accounts(self) -> Iterable[str]:''',
)
put_file(R, "ledger/core.py", CORE2, "Round to the nearest cent with banker's rounding", branch="main", new_branch="feature/rounding", sha=sha_of(R, "ledger/core.py", "main"), user="grace")
put_file(R, "tests/test_core.py", TEST + '''

def test_half_cent_rounds_to_even():
    assert Money("0.005").cents == 0
    assert Money("0.015").cents == 2
''', "Test banker's rounding", branch="feature/rounding", sha=sha_of(R, "tests/test_core.py", "feature/rounding"), user="grace")

pr = call("POST", f"/repos/{R}/pulls", {
    "head": "feature/rounding", "base": "main",
    "title": "Round amounts with banker's rounding",
    "body": "Amounts with more than two decimals were truncated.\n\n- Use `ROUND_HALF_EVEN` by default\n- Allow callers to pass their own rounding mode\n- Add `Ledger.trial_balance()`\n\nCloses #2.",
    "labels": [labels["enhancement"]],
}, user="grace")
PRN = pr["number"]

# issues (some before PR to get numbers right: we created PR first, issues come after)
def issue(title, body, lbls, user="ada", close=False, comments=()):
    i = call("POST", f"/repos/{R}/issues", {"title": title, "body": body, "labels": [labels[l] for l in lbls]}, user=user)
    for who, text in comments:
        call("POST", f"/repos/{R}/issues/{i['number']}/comments", {"body": text}, user=who)
    if close:
        call("PATCH", f"/repos/{R}/issues/{i['number']}", {"state": "closed"}, user="ada")
    return i

issue("Truncated cents when the amount has three decimals", "`Money(\"0.019\")` returns `0.01`.\n\nExpected: `0.02`.\n\n```python\n>>> str(Money(\"0.019\"))\n'0.01'\n```", ["bug"], user="grace",
      comments=[("ada", "Confirmed. Float-free, but `int(Decimal)` truncates. Fix is in #%d." % PRN)])
issue("Import postings from CSV", "Banks export CSV. We should read it into postings.\n\n- [ ] Column mapping\n- [ ] Date parsing\n- [ ] Duplicate detection", ["enhancement", "help wanted"], user="linus")
issue("Document multi-currency usage", "The README mentions multi-currency but has no example.", ["documentation", "good first issue"], user="ada")
issue("Support negative opening balances", "Opening balances are rejected as `amount must be positive`.", ["bug"], user="linus", close=True,
      comments=[("ada", "Fixed by modelling an opening balance as a posting against `equity:opening`.")])
issue("Ship a reports module", "A trial balance and a profit and loss would cover most needs.", ["enhancement"], user="grace")
issue("Rename `Posting.memo` to `Posting.description`", "More consistent with other accounting libraries.", ["wontfix"], user="linus", close=True,
      comments=[("ada", "Keeping `memo`; renaming breaks every caller for little gain.")])
issue("Typo in README quick start", "`print(book.balance(...))` shows `-950.00`, the comment says `950.00`.", ["documentation"], user="grace", close=True)
issue("Crash when a ledger has no postings", "`Ledger('x').accounts()` should return an empty list.\n\nTraceback:\n```\nTraceback (most recent call last):\n  File \"demo.py\", line 3, in <module>\n    list(book.accounts())\nTypeError: 'NoneType' object is not iterable\n```", ["bug", "help wanted"], user="linus")

# merged PR (docs fix)
README2 = README.replace("# -950.00", "# -950.00 (the bank balance goes down)")
put_file(R, "README.md", README2, "Explain the sign of the bank balance", branch="main", new_branch="fix/readme-sign", sha=sha_of(R, "README.md", "main"), user="grace")
pr2 = call("POST", f"/repos/{R}/pulls", {"head": "fix/readme-sign", "base": "main", "title": "Explain the sign in the README quick start", "body": "Clarifies why the balance is negative. Fixes the typo reported in the issue.", "labels": [labels["documentation"]]}, user="grace")
call("POST", f"/repos/{R}/pulls/{pr2['number']}/merge", {"Do": "merge"}, user="ada")

# review with inline comments on the open PR
files = call("GET", f"/repos/{R}/pulls/{PRN}/files", user="ada")
print("files", [f["filename"] for f in files])
call("POST", f"/repos/{R}/pulls/{PRN}/reviews", {
    "event": "COMMENT",
    "body": "Nice direction. Two questions before we merge.",
    "comments": [
        {"path": "ledger/core.py", "body": "Should the rounding mode be validated here? A typo like `\"ROUND_HALF_UP \"` would raise deep inside `quantize`.", "new_position": 29},
        {"path": "ledger/core.py", "body": "Zero-amount postings are noise in a trial balance. Why allow them now?", "new_position": 60},
    ],
}, user="ada")
call("POST", f"/repos/{R}/issues/{PRN}/comments", {"body": "Zero postings are needed for opening a fresh account. I will add a test and validate the mode."}, user="grace")
print("PR", PRN, "merged PR", pr2["number"])
