#!/usr/bin/env python3
"""Fable: a small dynamically-typed language.

This file is the entire implementation: lexer, parser, a closure-compiling
tree evaluator, and a set of deliberately low-level built-ins (pixels/rects,
key state, files, clock, basic math).  Nothing here knows anything about any
particular application written in Fable.

Usage:  python3 interpreter.py program.fb [args...]
"""
import math
import operator
import os
import sys
import time

# ---------------------------------------------------------------- lexer ----

KEYWORDS = {
    'fn', 'var', 'if', 'else', 'while', 'return', 'break', 'continue',
    'true', 'false', 'nil', 'and', 'or', 'not', 'use',
}
TWO_CHAR = {'==', '!=', '<=', '>=', '&&', '||'}
ONE_CHAR = set('+-*/%<>=(){}[],;!')
ESCAPES = {'n': '\n', 't': '\t', '"': '"', '\\': '\\'}


class FableError(Exception):
    pass


def lex(src):
    toks = []
    i, line, n, depth = 0, 1, len(src), 0
    while i < n:
        c = src[i]
        if c == '\n':
            if depth == 0:
                toks.append(('sep', ';', line))
            line += 1
            i += 1
        elif c in ' \t\r':
            i += 1
        elif c == '#':
            while i < n and src[i] != '\n':
                i += 1
        elif c == '"':
            i += 1
            buf = []
            while i < n and src[i] != '"':
                ch = src[i]
                if ch == '\\' and i + 1 < n:
                    buf.append(ESCAPES.get(src[i + 1], src[i + 1]))
                    i += 2
                else:
                    if ch == '\n':
                        line += 1
                    buf.append(ch)
                    i += 1
            if i >= n:
                raise FableError('line %d: unclosed string' % line)
            i += 1
            toks.append(('str', ''.join(buf), line))
        elif c.isdigit() or (c == '.' and i + 1 < n and src[i + 1].isdigit()):
            j = i
            isfloat = False
            while j < n and (src[j].isdigit() or src[j] == '.'):
                if src[j] == '.':
                    isfloat = True
                j += 1
            if j < n and src[j] in 'eE':
                k = j + 1
                if k < n and src[k] in '+-':
                    k += 1
                if k < n and src[k].isdigit():
                    isfloat = True
                    j = k
                    while j < n and src[j].isdigit():
                        j += 1
            text = src[i:j]
            toks.append(('num', float(text) if isfloat else int(text), line))
            i = j
        elif c.isalpha() or c == '_':
            j = i
            while j < n and (src[j].isalnum() or src[j] == '_'):
                j += 1
            word = src[i:j]
            toks.append(('kw' if word in KEYWORDS else 'name', word, line))
            i = j
        else:
            two = src[i:i + 2]
            if two in TWO_CHAR:
                toks.append(('op', two, line))
                i += 2
            elif c in ONE_CHAR:
                if c in '([':
                    depth += 1
                elif c in ')]':
                    depth = max(0, depth - 1)
                toks.append(('op', c, line))
                i += 1
            else:
                raise FableError('line %d: bad character %r' % (line, c))
    toks.append(('eof', '', line))
    return toks


# --------------------------------------------------------------- parser ----
# AST nodes are plain tuples; the first element is a short tag string.

class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def at(self, kind, val=None):
        k, v, _ = self.toks[self.i]
        return k == kind and (val is None or v == val)

    def eat(self, kind, val=None):
        if not self.at(kind, val):
            k, v, ln = self.peek()
            raise FableError('line %d: expected %s %r, got %r' % (ln, kind, val, v))
        return self.next()

    def skip_seps(self):
        while self.at('sep') or self.at('op', ';'):
            self.next()

    def program(self):
        items = []
        self.skip_seps()
        while not self.at('eof'):
            items.append(self.statement())
            self.skip_seps()
        return items

    def suite(self):
        self.eat('op', '{')
        body = []
        self.skip_seps()
        while not self.at('op', '}'):
            body.append(self.statement())
            self.skip_seps()
        self.eat('op', '}')
        return body

    def statement(self):
        k, v, ln = self.peek()
        if k == 'kw':
            if v == 'fn':
                self.next()
                name = self.eat('name')[1]
                self.eat('op', '(')
                params = []
                while not self.at('op', ')'):
                    params.append(self.eat('name')[1])
                    if self.at('op', ','):
                        self.next()
                self.eat('op', ')')
                return ('fn', name, params, self.suite(), ln)
            if v == 'var':
                self.next()
                name = self.eat('name')[1]
                self.eat('op', '=')
                return ('decl', name, self.expression(), ln)
            if v == 'if':
                self.next()
                return self.if_tail(ln)
            if v == 'while':
                self.next()
                cond = self.expression()
                return ('while', cond, self.suite(), ln)
            if v == 'return':
                self.next()
                if self.at('sep') or self.at('op', ';') or self.at('op', '}'):
                    return ('ret', None, ln)
                return ('ret', self.expression(), ln)
            if v == 'break':
                self.next()
                return ('brk', ln)
            if v == 'continue':
                self.next()
                return ('cont', ln)
        expr = self.expression()
        if self.at('op', '='):
            self.next()
            value = self.expression()
            if expr[0] == 'name':
                return ('asn', expr[1], value, ln)
            if expr[0] == 'index':
                return ('setidx', expr[1], expr[2], value, ln)
            raise FableError('line %d: cannot assign to this expression' % ln)
        return ('expr', expr, ln)

    def if_tail(self, ln):
        cond = self.expression()
        then = self.suite()
        other = None
        save = self.i
        self.skip_seps()
        if self.at('kw', 'else'):
            self.next()
            if self.at('kw', 'if'):
                _, _, ln2 = self.next()
                other = [self.if_tail(ln2)]
            else:
                other = self.suite()
        else:
            self.i = save
        return ('if', cond, then, other, ln)

    # precedence climbing
    def expression(self):
        return self.or_expr()

    def or_expr(self):
        e = self.and_expr()
        while self.at('kw', 'or') or self.at('op', '||'):
            self.next()
            e = ('or', e, self.and_expr())
        return e

    def and_expr(self):
        e = self.cmp_expr()
        while self.at('kw', 'and') or self.at('op', '&&'):
            self.next()
            e = ('and', e, self.cmp_expr())
        return e

    def cmp_expr(self):
        e = self.add_expr()
        while self.at('op') and self.peek()[1] in ('==', '!=', '<', '<=', '>', '>='):
            op = self.next()[1]
            e = ('bin', op, e, self.add_expr())
        return e

    def add_expr(self):
        e = self.mul_expr()
        while self.at('op') and self.peek()[1] in ('+', '-'):
            op = self.next()[1]
            e = ('bin', op, e, self.mul_expr())
        return e

    def mul_expr(self):
        e = self.unary()
        while self.at('op') and self.peek()[1] in ('*', '/', '%'):
            op = self.next()[1]
            e = ('bin', op, e, self.unary())
        return e

    def unary(self):
        if self.at('op', '-'):
            self.next()
            return ('neg', self.unary())
        if self.at('kw', 'not') or self.at('op', '!'):
            self.next()
            return ('not', self.unary())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            if self.at('op', '('):
                self.next()
                args = []
                while not self.at('op', ')'):
                    args.append(self.expression())
                    if self.at('op', ','):
                        self.next()
                self.eat('op', ')')
                e = ('call', e, args)
            elif self.at('op', '['):
                self.next()
                ix = self.expression()
                self.eat('op', ']')
                e = ('index', e, ix)
            else:
                return e

    def primary(self):
        k, v, ln = self.next()
        if k == 'num':
            return ('num', v)
        if k == 'str':
            return ('lit', v)
        if k == 'name':
            return ('name', v)
        if k == 'kw':
            if v == 'true':
                return ('num', 1)
            if v == 'false':
                return ('num', 0)
            if v == 'nil':
                return ('lit', None)
        if k == 'op' and v == '(':
            e = self.expression()
            self.eat('op', ')')
            return e
        if k == 'op' and v == '[':
            items = []
            while not self.at('op', ']'):
                items.append(self.expression())
                if self.at('op', ','):
                    self.next()
            self.eat('op', ']')
            return ('list', items)
        raise FableError('line %d: unexpected %r' % (ln, v))


# ----------------------------------------------------- closure compiler ----

class ReturnSignal(Exception):
    __slots__ = ('value',)

    def __init__(self):
        self.value = None


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


RET = ReturnSignal()
BRK = BreakSignal()
CONT = ContinueSignal()

BIN_OPS = {
    '+': operator.add, '-': operator.sub, '*': operator.mul,
    '/': operator.truediv, '%': operator.mod,
    '==': operator.eq, '!=': operator.ne,
    '<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge,
}


class FnValue:
    __slots__ = ('name', 'arity', 'pad', 'body')

    def __init__(self, name, arity, n_locals):
        self.name = name
        self.arity = arity
        self.pad = [None] * (n_locals - arity)
        self.body = None

    def call(self, vals):
        if len(vals) != self.arity:
            raise FableError('%s expects %d arguments, got %d'
                             % (self.name, self.arity, len(vals)))
        vals.extend(self.pad)
        try:
            self.body(vals)
        except ReturnSignal as sig:
            return sig.value
        return None


def collect_locals(body, found):
    for st in body:
        tag = st[0]
        if tag == 'decl':
            if st[1] not in found:
                found.append(st[1])
        elif tag == 'if':
            collect_locals(st[2], found)
            if st[3]:
                collect_locals(st[3], found)
        elif tag == 'while':
            collect_locals(st[2], found)


class Compiler:
    def __init__(self):
        self.gnames = {}
        self.gvals = []

    def gslot(self, name):
        if name in self.gnames:
            return self.gnames[name]
        ix = len(self.gvals)
        self.gnames[name] = ix
        self.gvals.append(None)
        return ix

    def define(self, name, value):
        self.gvals[self.gslot(name)] = value

    def run_program(self, items):
        # pass 1: register every function and top-level var name
        for st in items:
            if st[0] == 'fn':
                self.gslot(st[1])
            elif st[0] == 'decl':
                self.gslot(st[1])
        # pass 2: compile function bodies
        top = []
        for st in items:
            if st[0] == 'fn':
                _, name, params, body, ln = st
                names = list(params)
                collect_locals(body, names)
                if len(names) != len(set(names)):
                    raise FableError('line %d: duplicate local in %s' % (ln, name))
                scope = {nm: ix for ix, nm in enumerate(names)}
                fval = FnValue(name, len(params), len(names))
                fval.body = self.suite(body, scope)
                self.gvals[self.gnames[name]] = fval
            else:
                top.append(st)
        runner = self.suite(top, {})
        try:
            runner([])
        except ReturnSignal:
            pass

    # ---- statements -> closures taking the local frame, returning None ----

    def suite(self, body, scope):
        steps = [self.stmt(st, scope) for st in body]
        if len(steps) == 1:
            return steps[0]

        def run(frame, _steps=steps):
            for step in _steps:
                step(frame)
        return run

    def stmt(self, st, scope):
        tag = st[0]
        if tag == 'expr':
            ev = self.expr(st[1], scope)

            def run(frame, _ev=ev):
                _ev(frame)
            return run
        if tag in ('decl', 'asn'):
            name, value = st[1], self.expr(st[2], scope)
            if name in scope:
                ix = scope[name]

                def run(frame, _ix=ix, _v=value):
                    frame[_ix] = _v(frame)
                return run
            if name not in self.gnames:
                raise FableError('line %d: unknown name %r (declare with var)'
                                 % (st[3], name))
            gix = self.gnames[name]

            def run(frame, _g=self.gvals, _ix=gix, _v=value):
                _g[_ix] = _v(frame)
            return run
        if tag == 'setidx':
            obj = self.expr(st[1], scope)
            ix = self.expr(st[2], scope)
            value = self.expr(st[3], scope)

            def run(frame, _o=obj, _i=ix, _v=value):
                _o(frame)[int(_i(frame))] = _v(frame)
            return run
        if tag == 'if':
            cond = self.expr(st[1], scope)
            then = self.suite(st[2], scope)
            other = self.suite(st[3], scope) if st[3] else None
            if other is None:
                def run(frame, _c=cond, _t=then):
                    if _c(frame):
                        _t(frame)
                return run

            def run(frame, _c=cond, _t=then, _e=other):
                if _c(frame):
                    _t(frame)
                else:
                    _e(frame)
            return run
        if tag == 'while':
            cond = self.expr(st[1], scope)
            body = self.suite(st[2], scope)

            def run(frame, _c=cond, _b=body):
                while _c(frame):
                    try:
                        _b(frame)
                    except BreakSignal:
                        break
                    except ContinueSignal:
                        continue
            return run
        if tag == 'ret':
            if st[1] is None:
                def run(frame):
                    RET.value = None
                    raise RET
                return run
            value = self.expr(st[1], scope)

            def run(frame, _v=value):
                RET.value = _v(frame)
                raise RET
            return run
        if tag == 'brk':
            def run(frame):
                raise BRK
            return run
        if tag == 'cont':
            def run(frame):
                raise CONT
            return run
        if tag == 'fn':
            raise FableError('line %d: fn definitions must be top-level' % st[4])
        raise FableError('cannot compile statement %r' % (tag,))

    # ---- expressions -> closures taking the local frame, returning value --

    def expr(self, node, scope):
        tag = node[0]
        if tag == 'num' or tag == 'lit':
            v = node[1]
            return lambda frame, _v=v: _v
        if tag == 'name':
            name = node[1]
            if name in scope:
                ix = scope[name]
                return lambda frame, _ix=ix: frame[_ix]
            if name not in self.gnames:
                raise FableError('unknown name %r' % name)
            gix = self.gnames[name]
            return lambda frame, _g=self.gvals, _ix=gix: _g[_ix]
        if tag == 'bin':
            fn = BIN_OPS[node[1]]
            lhs = self.expr(node[2], scope)
            rhs = self.expr(node[3], scope)
            return lambda frame, _f=fn, _l=lhs, _r=rhs: _f(_l(frame), _r(frame))
        if tag == 'and':
            lhs = self.expr(node[1], scope)
            rhs = self.expr(node[2], scope)
            return lambda frame, _l=lhs, _r=rhs: _l(frame) and _r(frame)
        if tag == 'or':
            lhs = self.expr(node[1], scope)
            rhs = self.expr(node[2], scope)
            return lambda frame, _l=lhs, _r=rhs: _l(frame) or _r(frame)
        if tag == 'neg':
            ev = self.expr(node[1], scope)
            return lambda frame, _e=ev: -_e(frame)
        if tag == 'not':
            ev = self.expr(node[1], scope)
            return lambda frame, _e=ev: not _e(frame)
        if tag == 'index':
            obj = self.expr(node[1], scope)
            ix = self.expr(node[2], scope)
            return lambda frame, _o=obj, _i=ix: _o(frame)[int(_i(frame))]
        if tag == 'list':
            items = [self.expr(it, scope) for it in node[1]]
            return lambda frame, _it=items: [ev(frame) for ev in _it]
        if tag == 'call':
            callee = self.expr(node[1], scope)
            args = [self.expr(a, scope) for a in node[2]]

            def run(frame, _c=callee, _a=args):
                fn = _c(frame)
                vals = [ev(frame) for ev in _a]
                if fn.__class__ is FnValue:
                    return fn.call(vals)
                return fn(*vals)
            return run
        raise FableError('cannot compile expression %r' % (tag,))


# ------------------------------------------------------------- built-ins ---

def to_text(v):
    if v is None:
        return 'nil'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return '[' + ', '.join(to_text(x) for x in v) + ']'
    return str(v)


def b_num(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        try:
            return float(s)
        except (TypeError, ValueError):
            return None


def b_read_text(path):
    try:
        with open(path, 'r') as fh:
            return fh.read()
    except OSError:
        return None


def b_write_text(path, text):
    try:
        with open(path, 'w') as fh:
            fh.write(text)
        return 1
    except OSError:
        return 0


# -------------------------------------------------------------- graphics ---
# Two output targets: a Tk canvas, or a no-op sink (FABLE_HEADLESS=1) so
# programs can run under tests and benchmarks without a window server.

class NullPane:
    def __init__(self, w, h, scale, title):
        self.gone = False

    def rect(self, x, y, w, h, color):
        pass

    def text(self, x, y, s, color, size):
        pass

    def flush(self):
        pass

    def pressed(self, name):
        return 0


class DumpPane(NullPane):
    """Offscreen target: rasterizes rects and writes a BMP on each flush.

    Enabled with FABLE_DUMP=/path/out.bmp — useful for eyeballing frames
    in environments with no window server.
    """

    def __init__(self, w, h, scale, title):
        self.gone = False
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)
        self.path = os.environ.get('FABLE_DUMP')

    def rect(self, x, y, w, h, color):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        span = bytes((r, g, b)) * (x1 - x0)
        stride = self.w * 3
        for row in range(y0, y1):
            base = row * stride + x0 * 3
            self.buf[base:base + len(span)] = span

    def flush(self):
        w, h = self.w, self.h
        pad = (4 - (w * 3) % 4) % 4
        row_size = w * 3 + pad
        data_size = row_size * h
        header = bytearray(54)
        header[0:2] = b'BM'
        header[2:6] = (54 + data_size).to_bytes(4, 'little')
        header[10:14] = (54).to_bytes(4, 'little')
        header[14:18] = (40).to_bytes(4, 'little')
        header[18:22] = w.to_bytes(4, 'little')
        header[22:26] = h.to_bytes(4, 'little')
        header[26:28] = (1).to_bytes(2, 'little')
        header[28:30] = (24).to_bytes(2, 'little')
        header[34:38] = data_size.to_bytes(4, 'little')
        body = bytearray()
        zero = b'\x00' * pad
        stride = w * 3
        for row in range(h - 1, -1, -1):  # BMP rows are bottom-up
            base = row * stride
            line = self.buf[base:base + stride]
            line[0::3], line[2::3] = line[2::3], line[0::3]  # RGB -> BGR
            body += line + zero
        with open(self.path, 'wb') as fh:
            fh.write(bytes(header) + bytes(body))


class TkPane:
    def __init__(self, w, h, scale, title):
        import tkinter
        self.scale = scale
        self.gone = False
        self.down = set()
        self.root = tkinter.Tk()
        self.root.title(title)
        self.root.resizable(False, False)
        self.canvas = tkinter.Canvas(
            self.root, width=w * scale, height=h * scale,
            highlightthickness=0, bg='#000000')
        self.canvas.pack()
        self.root.bind('<KeyPress>', self._key_down)
        self.root.bind('<KeyRelease>', self._key_up)
        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self.root.update()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(200, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()

    def _key_down(self, event):
        self.down.add(event.keysym.lower())

    def _key_up(self, event):
        self.down.discard(event.keysym.lower())

    def _close(self):
        self.gone = True
        try:
            self.root.destroy()
        except Exception:
            pass

    def rect(self, x, y, w, h, color):
        s = self.scale
        self.canvas.create_rectangle(
            x * s, y * s, (x + w) * s, (y + h) * s, fill=color, width=0)

    def text(self, x, y, string, color, size):
        s = self.scale
        self.canvas.create_text(
            x * s, y * s, text=string, fill=color, anchor='nw',
            font=('Menlo', int(size * s)))

    def flush(self):
        if self.gone:
            return
        try:
            self.canvas.update()
            self.canvas.delete('all')
        except Exception:
            self.gone = True

    def pressed(self, name):
        return 1 if name in self.down else 0


PANE = [None]


def b_gfx_open(w, h, scale, title):
    if os.environ.get('FABLE_DUMP'):
        cls = DumpPane
    elif os.environ.get('FABLE_HEADLESS') == '1':
        cls = NullPane
    else:
        cls = TkPane
    PANE[0] = cls(int(w), int(h), int(scale), title)
    return 1


def _color(r, g, b):
    r = 0 if r < 0 else (255 if r > 255 else int(r))
    g = 0 if g < 0 else (255 if g > 255 else int(g))
    b = 0 if b < 0 else (255 if b > 255 else int(b))
    return '#%02x%02x%02x' % (r, g, b)


def b_gfx_rect(x, y, w, h, r, g, b):
    PANE[0].rect(int(x), int(y), int(w), int(h), _color(r, g, b))
    return None


def b_gfx_text(x, y, s, r, g, b, size):
    PANE[0].text(int(x), int(y), s, _color(r, g, b), size)
    return None


def b_gfx_flush():
    PANE[0].flush()
    return None


def b_gfx_done():
    pane = PANE[0]
    return 1 if (pane is None or pane.gone) else 0


def b_key(name):
    return PANE[0].pressed(name)


def install_builtins(comp, script_args):
    comp.define('print', lambda v: print(to_text(v), flush=True))
    comp.define('str', to_text)
    comp.define('num', b_num)
    comp.define('len', lambda x: len(x))
    comp.define('substr', lambda s, i, n: s[int(i):int(i) + int(n)])
    comp.define('split', lambda s, sep: s.split(sep))
    comp.define('arr', lambda n, fill: [fill] * int(n))
    comp.define('push', lambda a, v: (a.append(v), None)[1])
    comp.define('pop', lambda a: a.pop())
    comp.define('floor', lambda x: int(math.floor(x)))
    comp.define('ceil', lambda x: int(math.ceil(x)))
    comp.define('abs', abs)
    comp.define('sqrt', math.sqrt)
    comp.define('sin', math.sin)
    comp.define('cos', math.cos)
    comp.define('tan', math.tan)
    comp.define('atan2', math.atan2)
    comp.define('pow', lambda a, b: a ** b)
    comp.define('min', min)
    comp.define('max', max)
    comp.define('pi', lambda: math.pi)
    comp.define('clock_ms', lambda: time.perf_counter() * 1000.0)
    comp.define('sleep_ms', lambda n: (time.sleep(n / 1000.0), None)[1])
    comp.define('read_text', b_read_text)
    comp.define('write_text', b_write_text)
    comp.define('argv', lambda: list(script_args))
    comp.define('gfx_open', b_gfx_open)
    comp.define('gfx_rect', b_gfx_rect)
    comp.define('gfx_text', b_gfx_text)
    comp.define('gfx_flush', b_gfx_flush)
    comp.define('gfx_done', b_gfx_done)
    comp.define('key', b_key)


# ------------------------------------------------------------ entrypoint ---

def load_source(path, seen):
    """Read a .fb file, splicing in `use "other.fb"` lines (deduplicated)."""
    try:
        full = os.path.abspath(path)
    except OSError:  # getcwd may be unavailable in sandboxes
        full = os.path.normpath(path)
    if full in seen:
        return ''
    seen.add(full)
    try:
        with open(full, 'r') as fh:
            text = fh.read()
    except OSError as err:
        raise FableError('cannot open %s: %s' % (path, err))
    base = os.path.dirname(full)
    out = []
    for ln in text.split('\n'):
        stripped = ln.strip()
        if stripped.startswith('use ') and '"' in stripped:
            target = stripped.split('"')[1]
            out.append(load_source(os.path.join(base, target), seen))
        else:
            out.append(ln)
    return '\n'.join(out)


def run_file(path, script_args):
    src = load_source(path, set())
    items = Parser(lex(src)).program()
    comp = Compiler()
    install_builtins(comp, script_args)
    comp.run_program(items)


def main():
    if len(sys.argv) < 2:
        print('usage: python3 interpreter.py program.fb [args...]')
        sys.exit(2)
    try:
        os.getcwd()
    except OSError:
        # Sandboxed launch dirs can forbid getcwd, which Tk needs.
        import tempfile
        for fallback in (os.path.dirname(os.path.abspath(sys.argv[1])),
                         tempfile.gettempdir()):
            try:
                os.chdir(fallback)
                os.getcwd()
                break
            except OSError:
                continue
    try:
        run_file(sys.argv[1], sys.argv[2:])
    except FableError as err:
        print('fable error: %s' % err, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
