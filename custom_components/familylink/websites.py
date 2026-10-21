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
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
# A second-level public suffix (co.uk, com.au, ...): blocking one blocks a whole
# country's sites. Best effort, there is no public suffix list to check against.
_SUFFIX = re.compile(r"^(?:ac|co|com|edu|gov|net|or|org)\.[a-z]{2}$")


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


def _is_list_domain(token: str) -> bool:
	"""Whether ``token`` is a plain domain a published list may ask us to block."""
	if "*" in token or "/" in token or _IPV4.match(token) or _SUFFIX.match(token):
		return False
	try:
		return normalize_site(token) == token
	except ValueError:
		return False


def parse_site_list(text: str, ignored: list[str] | None = None) -> list[str]:
	"""Domains from a one-per-line list with ``#`` comments (hosts-file lines are tolerated).

	A list comes from a third party, so it is held to plain domains: wildcards,
	web addresses, IP addresses and bare public suffixes such as ``co.uk`` are
	left out, and appended to ``ignored`` when it is given.
	"""
	domains: list[str] = []
	seen: set[str] = set()
	for line in text.splitlines():
		body = line.split("#", 1)[0].strip()
		if not body:
			continue
		token = body.split()[-1].lower()  # "0.0.0.0 example.com" -> example.com
		if token in seen:
			continue
		seen.add(token)
		if _is_list_domain(token):
			domains.append(token)
		elif ignored is not None:
			ignored.append(token)
	return domains
