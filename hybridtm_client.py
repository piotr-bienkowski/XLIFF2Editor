#!/usr/bin/env python3
"""
HybridTM client for XLIFF2Editor.

HybridTM (Maxprograms) is a semantic + fuzzy TM engine.  It runs as a local
HTTP server speaking a single JSON POST endpoint on 127.0.0.1:8050, where every
request is ``{"command": ..., ...}``.

Things the protocol does not make obvious, all of them learned the hard way:

* The search command is the full ``semanticTranslationSearch``.  A wrong command
  name returns ``{"status": "failed", "reason": "Unknown command"}`` rather than
  an empty result, so a typo looks like "no matches" unless the status is read.
* Results come back under ``payload``, not ``matches``.
* ``similarity`` must be a JSON number; a string is rejected.
* An instance must be opened before it can be searched, and a server started
  *before* an instance was created cannot see it -- it needs a restart.
* ``source`` and ``target`` are whole ``<tuv>`` XML strings, and they keep the
  whitespace the source TMX had around ``<seg>``.  Parse them; do not strip
  tags with a regex.
* Language codes must match the TMX exactly: ``en-US`` works where ``en``
  silently returns nothing.

Scoring note: HybridTM's own ``fuzzy`` under-scores a short source contained in
a longer TM sentence, so :func:`best_fuzzy` takes the higher of it and difflib.
``similarity`` is the mean of semantic and fuzzy and is misleading on its own --
semantic alone runs 90+ for unrelated sentences from the same domain.
"""

from __future__ import annotations

import difflib
import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from lxml import etree

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8050
CLI_PATH = Path.home() / 'node_modules' / '.bin' / 'hybridtm'


class HybridTMError(RuntimeError):
    """A HybridTM request failed, or the server could not be reached."""


def _seg_text(tuv_xml: str) -> str:
    """Text of the <seg> inside a returned <tuv> string."""
    if not tuv_xml:
        return ''
    try:
        root = etree.fromstring(tuv_xml.encode('utf-8'))
    except etree.XMLSyntaxError:
        return tuv_xml.strip()
    seg = root.find('seg') if root.tag != 'seg' else root
    if seg is None:
        return ''
    return ''.join(seg.itertext()).strip()


def best_fuzzy(a: str, b: str, reported: float | None) -> int:
    """Higher of HybridTM's fuzzy score and difflib's ratio, as a percent."""
    local = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100
    try:
        remote = float(reported)
    except (TypeError, ValueError):
        remote = 0.0
    return int(round(max(local, remote)))


class HybridTMClient:
    """Talks to a local HybridTM server for one instance."""

    def __init__(self, instance, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 cli_path=CLI_PATH, timeout=180):
        self.instance = instance
        self.host = host
        self.port = port
        self.cli_path = Path(cli_path)
        self.timeout = timeout
        self._opened = False

    # ── transport ────────────────────────────────────────────────────────────

    @property
    def url(self):
        return f'http://{self.host}:{self.port}'

    def server_running(self) -> bool:
        with socket.socket() as probe:
            probe.settimeout(1.0)
            return probe.connect_ex((self.host, self.port)) == 0

    def call(self, command, **params):
        """POST one command; raise HybridTMError unless status is success."""
        body = json.dumps({'command': command, **params}).encode('utf-8')
        request = urllib.request.Request(
            self.url, data=body, headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read())
        except (urllib.error.URLError, OSError) as exc:
            raise HybridTMError(f'HybridTM server unreachable at {self.url}: {exc}')
        except json.JSONDecodeError as exc:
            raise HybridTMError(f'HybridTM returned malformed JSON: {exc}')

        if result.get('status') != 'success':
            raise HybridTMError(result.get('reason') or 'unknown HybridTM error')
        return result.get('payload')

    def start_server(self, wait=30) -> bool:
        """Start `hybridtm serve` in the background; True once it accepts calls."""
        if self.server_running():
            return True
        if not self.cli_path.exists():
            raise HybridTMError(
                f'HybridTM CLI not found at {self.cli_path}.\n'
                'It is a local npm package: install with `npm install hybridtm` '
                'in your home directory (never -g).'
            )
        if shutil.which('node') is None:
            raise HybridTMError('node is not on PATH; HybridTM needs Node 24+.')

        subprocess.Popen(
            [str(self.cli_path), 'serve'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.time() + wait
        while time.time() < deadline:
            if self.server_running():
                return True
            time.sleep(0.5)
        raise HybridTMError('HybridTM server did not start within '
                            f'{wait}s at {self.url}')

    # ── instances ────────────────────────────────────────────────────────────

    def list_instances(self):
        """[{'name', 'path', 'model', ...}] for every registered instance."""
        payload = self.call('list') or []
        out = []
        for entry in payload:
            if isinstance(entry, dict):
                out.append(entry)
            elif isinstance(entry, (list, tuple)) and entry:
                out.append({'name': entry[0]})
            elif isinstance(entry, str):
                out.append({'name': entry.split('\t')[0]})
        return out

    def open(self):
        """Open the instance, starting the server first if needed."""
        if self._opened:
            return
        self.start_server()
        try:
            self.call('open', name=self.instance)
        except HybridTMError as exc:
            if 'does not exist' in str(exc).lower():
                names = ', '.join(i.get('name', '?') for i in self.list_instances())
                raise HybridTMError(
                    f'HybridTM has no instance "{self.instance}".\n'
                    f'Available: {names or "(none)"}\n\n'
                    'If you created it after the server started, the server must '
                    'be restarted before it becomes visible.'
                )
            raise
        self._opened = True

    def close(self):
        if not self._opened:
            return
        try:
            self.call('close', name=self.instance)
        except HybridTMError:
            pass
        self._opened = False

    # ── search ───────────────────────────────────────────────────────────────

    def search(self, text, src_lang, tgt_lang, similarity=55, limit=5):
        """
        Matches for *text*, best first.

        Each match is a dict with plain-text ``source``/``target`` plus
        ``semantic``, ``fuzzy`` (HybridTM's own) and ``best_fuzzy`` (that score
        raised by difflib where HybridTM under-scores a contained source).
        """
        if not (text or '').strip():
            return []
        self.open()
        payload = self.call(
            'semanticTranslationSearch',
            name=self.instance,
            searchStr=text,
            srcLang=src_lang,
            tgtLang=tgt_lang,
            similarity=float(similarity),
            limit=int(limit),
        ) or []

        matches = []
        for entry in payload:
            source = _seg_text(entry.get('source'))
            target = _seg_text(entry.get('target'))
            if not source or not target:
                continue
            matches.append({
                'source': source,
                'target': target,
                'semantic': int(round(float(entry.get('semantic') or 0))),
                'fuzzy': int(round(float(entry.get('fuzzy') or 0))),
                'best_fuzzy': best_fuzzy(text, source, entry.get('fuzzy')),
            })
        matches.sort(key=lambda m: (m['best_fuzzy'], m['semantic']), reverse=True)
        return matches

    def batch_search(self, texts, src_lang, tgt_lang, similarity=55, limit=5,
                     progress=None, should_cancel=None):
        """
        Search many sources, de-duplicating identical ones.

        ``progress(done, total)`` is called as work proceeds and
        ``should_cancel()`` is polled between lookups so a UI can interrupt.
        Returns ``{source_text: [match, ...]}``; a source that errored is absent.
        """
        unique = list(dict.fromkeys(t for t in texts if (t or '').strip()))
        total = len(unique)
        results = {}
        for index, text in enumerate(unique, start=1):
            if should_cancel is not None and should_cancel():
                break
            try:
                results[text] = self.search(text, src_lang, tgt_lang, similarity, limit)
            except HybridTMError:
                pass
            if progress is not None:
                progress(index, total)
        return results
