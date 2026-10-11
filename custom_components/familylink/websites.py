"""Website patterns for Family Link's Chrome site lists.

Google stores patterns verbatim and does not validate them (it accepts a
``*`` in the middle or a 254-character host), so they are checked here.
Accepted forms, as the Family Link app documents them:

- a website (host): ``www.example.com``
- a domain wildcard: ``*.example.com``, ``*.example.*`` (``*.`` prefix and
  ``.*`` suffix only)
- a web address: ``https://example.org/path`` (kept as given; Chrome matches
  it exactly)
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST = re.compile(rf"^(?=.{{1,253}}$){_LABEL}(?:\.{_LABEL})+$")
_WILDCARD = re.compile(rf"^\*\.(?:{_LABEL}\.)*{_LABEL}(?:\.\*|\.[a-z]{{2,63}})$")


def normalize_site(value: str) -> str:
	"""The pattern to send for ``value``; raises ValueError when it isn't valid."""
	text = str(value or "").strip()
	if not text or any(c.isspace() for c in text):
		raise ValueError(f"Not a website: {value!r}")
	if "://" in text:
		parts = urlsplit(text)
		host = (parts.hostname or "").lower()
		if parts.scheme not in ("http", "https") or not _HOST.match(host):
			raise ValueError(f"Not a valid web address: {value!r}")
		if not parts.path.strip("/") and not parts.query:
			return host  # a bare https://example.com means the site
		return text
	text = text.lower().rstrip("/")
	if "*" in text:
		if not _WILDCARD.match(text):
			raise ValueError(f"Wildcards are only allowed as a leading '*.' or a trailing '.*': {value!r}")
		return text
	if not _HOST.match(text):
		raise ValueError(f"Not a valid website: {value!r}")
	return text


def domain_patterns(domain: str) -> list[str]:
	"""Patterns blocking a domain and its subdomains: ``example.com`` -> ``*.example.com``, ``example.com``.

	Google doesn't say whether ``*.example.com`` covers ``example.com``, so both are sent.
	"""
	host = normalize_site(domain)
	if "*" in host or "/" in host:
		return [host]
	return [f"*.{host}", host]


def parse_site_list(text: str) -> list[str]:
	"""Domains from a one-per-line list with ``#`` comments (hosts-file lines are tolerated)."""
	domains: list[str] = []
	seen: set[str] = set()
	for line in text.splitlines():
		body = line.split("#", 1)[0].strip()
		if not body:
			continue
		token = body.split()[-1].lower()  # "0.0.0.0 example.com" -> example.com
		if token in seen:
			continue
		try:
			normalize_site(token)
		except ValueError:
			continue
		seen.add(token)
		domains.append(token)
	return domains
