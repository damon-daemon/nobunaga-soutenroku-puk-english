"""Buffer-overflow guards: the longest text that can reach each fixed-size buffer.

English is longer than the Japanese and the game copies text into fixed buffers with
no length checks. This module measures the longest possible expansion of every
message that reaches one and fails tl.py apply / the build when it would not fit.
Audit: notes/overflow_audit.md.

Expansion model (interpreter 0x1E87D0): text bytes count as is, {02} prints and %s
count VAR bytes (the longest English name or table entry), %d / numbers NUMBER,
{01}C inserts the longest expansion of the inserted entry, {01}J the target instead
of the rest. A taken IF body ends in 05 05 05 (return), so IFs are alternatives: the
longest path counts.

usage: .venv/bin/python tools/overflow.py      # longest expansions vs limits
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
import msgbuf, msgscript

VAR = 48                 # a {02} print / %s: longest English name or table entry
                         # (names.py check fails on any tl/names entry longer than this)
NUMBER = 11
MSG_BUF = msgbuf.LIMIT   # message output buffer (writer cuts the text there; msgbuf.py)
# (block, entry) -> (limit, where): message expansion incl. the %s string
SITES = {(39, 5215): (111, 'memory card: sprintf into 112-byte stack buffers (0x284D00, 0x285170)'),
         (39, 5216): (255, 'memory card: sprintf into 256-byte stack buffers (0x285A70, 0x2862A8)')}
# Blocks 39 and 40 stay loaded on the heap (malloc(TOC size + 0x1000), 0x204920) in a
# ~4.24 MB heap. Measured 2026-10-24 (issue #3): the military-phase Info > Minor Powers list
# peaks at heap top 0x1F8B000 with +693 KB of English (limit = stack base, 0x1F90000 before
# elfseg cut the stack; +320 KB since). Don't raise this without re-measuring that screen.
HEAP_GROWTH = 1 << 20
# save headers: 0x1C70E0 memcpy's clan [16], given [16], full name [24] with no NUL of its own
# (namehook.py makes those copies NUL-terminate, cutting the name); 0x289D64 strcpy(slot+0x38,
# full name) [32] and 0x289D98 clan [32] (namehook.py checks this limit)
SAVE_SLOT = 31
RUN = 255                # rich-text layout (0x26E5B0) caps a run (line) at 255 bytes

def _tree(toks):
    """tokens -> nodes: ('t', bytes, kind) | ('if', [body nodes]) | ('ret',)."""
    root = []
    stack = [root]
    for kind, b in toks:
        if kind == 'if':
            node = ('if', [])
            stack[-1].append(node)
            stack.append(node[1])
        elif kind in ('end', 'eom'):
            stack[-1].append(('ret',))
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1].append(('t', b, kind))
    return root

class Measure:
    """Longest expansion of messages; get(block, entry) -> bytes or None."""

    def __init__(self, get):
        self.get = get
        self.memo = {}
        self.active = set()

    def msg(self, n, i):
        k = (n, i)
        if k in self.memo:
            return self.memo[k]
        if k in self.active:                # recursion: count as one variable
            return VAR
        b = self.get(n, i)
        if b is None:
            return 0
        self.active.add(k)
        try:
            v = self.seq(n, _tree(msgscript.tokens(b)))[0]
        except msgscript.ParseError:
            v = len(b) + 8 * VAR
        self.active.discard(k)
        self.memo[k] = v
        return v

    def item(self, n, kind, b):
        """-> (bytes, stop) of one token."""
        if kind == 'text':
            return len(b), False
        if kind == 'nl':
            return 1, False
        if kind == 'cmd':
            if b[:2] == b'\x01J' and len(b) >= 4:
                return self.msg(n, b[2] | b[3] << 8), True
            return 0, False
        c = b[0]
        if c == 0x01 and b[1:2] == b'C' and len(b) >= 4:
            return self.msg(n, b[2] | b[3] << 8), False
        if c == 0x25:
            return (VAR if b[-1:] == b's' else NUMBER), False
        if c == 0x02:
            return VAR, False
        return 0, False                     # 1B/1A/1C codes and stray bytes print nothing

    def seq(self, n, nodes):
        """-> (longest bytes, always returns)."""
        total = best = 0
        for node in nodes:
            if node[0] == 'if':
                v, _ = self.seq(n, node[1])
                best = max(best, total + v)
                continue
            if node[0] == 'ret':
                return max(best, total), True
            v, stop = self.item(n, node[2], node[1])
            total += v
            if stop:
                return max(best, total), True
        return max(best, total), False

def check(get, sizes):
    """-> list of error strings. get(block, entry) -> final bytes or None;
    sizes = {block: entry count}."""
    m = Measure(get)
    errs = []
    if MSG_BUF:
        for n, count in sizes.items():
            for i in range(count):
                v = m.msg(n, i)
                if v > MSG_BUF:
                    errs.append('msg%d #%d: expands to %d bytes > %d (message buffer)' % (n, i, v, MSG_BUF))
    for (n, i), (limit, where) in sorted(SITES.items()):
        v = m.msg(n, i)
        if v > limit:
            errs.append('msg%d #%d: expands to %d bytes > %d: %s' % (n, i, v, limit, where))
    return errs

def main():
    import tl, msgfile
    english, bad = tl.build_all(quiet=True)
    get = lambda n, e: tl.message(n, e) if e < len(tl.rows_of(n)) else None
    m = Measure(get)
    for n in msgfile.BLOCKS:
        worst = sorted(((m.msg(n, i), i) for i in range(len(tl.rows_of(n)))), reverse=True)
        print('msg%d longest expansions:' % n, ', '.join('#%d %d' % (i, v) for v, i in worst[:10]))
    errs = check(get, {n: len(tl.rows_of(n)) for n in msgfile.BLOCKS})
    print('\n'.join(errs) or 'no message overflows')

if __name__ == '__main__':
    main()
