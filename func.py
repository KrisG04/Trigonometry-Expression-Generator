from __future__ import print_function, division
from collections import defaultdict
from sympy.core.add import Add
from sympy.core.basic import S
from sympy.core.compatibility import ordered, range
from sympy.core.expr import Expr
from sympy.core.exprtools import Factors, gcd_terms, factor_terms
from sympy.core.function import expand_mul
from sympy.core.mul import Mul
from sympy.core.numbers import pi, I
from sympy.core.power import Pow
from sympy.core.symbol import Dummy
from sympy.core.sympify import sympify
from sympy.functions.combinatorial.factorials import binomial
from sympy.functions.elementary.hyperbolic import (
    cosh, sinh, tanh, coth, sech, csch, HyperbolicFunction)
from sympy.functions.elementary.trigonometric import (
    cos, sin, tan, cot, sec, csc, sqrt, TrigonometricFunction)
from sympy.ntheory.factor_ import perfect_power
from sympy.polys.polytools import factor
from sympy.simplify.fu import RL2, RL1
from sympy.simplify.simplify import bottom_up
from sympy.strategies.tree import greedy
from sympy.strategies.core import identity, debug
from sympy import SYMPY_DEBUG


def TR0(rv):
    return rv.normal().factor().expand()


def TR1(rv):
    def f(rv):
        if isinstance(rv, sec):
            a = rv.args[0]
            return S.One / cos(a)
        elif isinstance(rv, csc):
            a = rv.args[0]
            return S.One / sin(a)
        return rv

    return bottom_up(rv, f)


def TR2(rv):
    def f(rv):
        if isinstance(rv, tan):
            a = rv.args[0]
            return sin(a) / cos(a)
        elif isinstance(rv, cot):
            a = rv.args[0]
            return cos(a) / sin(a)
        return rv

    return bottom_up(rv, f)


def TR2i(rv, half=False):
    def f(rv):
        if not rv.is_Mul:
            return rv

        n, d = rv.as_numer_denom()
        if n.is_Atom or d.is_Atom:
            return rv

        def ok(k, e):
            # initial filtering of factors
            return (
                    (e.is_integer or k.is_positive) and (
                    k.func in (sin, cos) or (half and
                                             k.is_Add and
                                             len(k.args) >= 2 and
                                             any(any(isinstance(ai, cos) or ai.is_Pow and ai.base is cos
                                                     for ai in Mul.make_args(a)) for a in k.args))))

        n = n.as_powers_dict()
        ndone = [(k, n.pop(k)) for k in list(n.keys()) if not ok(k, n[k])]
        if not n:
            return rv

        d = d.as_powers_dict()
        ddone = [(k, d.pop(k)) for k in list(d.keys()) if not ok(k, d[k])]
        if not d:
            return rv

        # factoring if necessary

        def factorize(d, ddone):
            newk = []
            for k in d:
                if k.is_Add and len(k.args) > 1:
                    knew = factor(k) if half else factor_terms(k)
                    if knew != k:
                        newk.append((k, knew))
            if newk:
                for i, (k, knew) in enumerate(newk):
                    del d[k]
                    newk[i] = knew
                newk = Mul(*newk).as_powers_dict()
                for k in newk:
                    v = d[k] + newk[k]
                    if ok(k, v):
                        d[k] = v
                    else:
                        ddone.append((k, v))
                del newk

        factorize(n, ndone)
        factorize(d, ddone)

        # joining
        t = []
        for k in n:
            if isinstance(k, sin):
                a = cos(k.args[0], evaluate=False)
                if a in d and d[a] == n[k]:
                    t.append(tan(k.args[0]) ** n[k])
                    n[k] = d[a] = None
                elif half:
                    a1 = 1 + a
                    if a1 in d and d[a1] == n[k]:
                        t.append((tan(k.args[0] / 2)) ** n[k])
                        n[k] = d[a1] = None
            elif isinstance(k, cos):
                a = sin(k.args[0], evaluate=False)
                if a in d and d[a] == n[k]:
                    t.append(tan(k.args[0]) ** -n[k])
                    n[k] = d[a] = None
            elif half and k.is_Add and k.args[0] is S.One and \
                    isinstance(k.args[1], cos):
                a = sin(k.args[1].args[0], evaluate=False)
                if a in d and d[a] == n[k] and (d[a].is_integer or \
                                                a.is_positive):
                    t.append(tan(a.args[0] / 2) ** -n[k])
                    n[k] = d[a] = None

        if t:
            rv = Mul(*(t + [b ** e for b, e in n.items() if e])) / \
                 Mul(*[b ** e for b, e in d.items() if e])
            rv *= Mul(*[b ** e for b, e in ndone]) / Mul(*[b ** e for b, e in ddone])

        return rv

    return bottom_up(rv, f)


def TR3(rv):
    from sympy.simplify.simplify import signsimp
    def f(rv):
        if not isinstance(rv, TrigonometricFunction):
            return rv
        rv = rv.func(signsimp(rv.args[0]))
        if not isinstance(rv, TrigonometricFunction):
            return rv
        if (rv.args[0] - S.Pi / 4).is_positive is (S.Pi / 2 - rv.args[0]).is_positive is True:
            fmap = {cos: sin, sin: cos, tan: cot, cot: tan, sec: csc, csc: sec}
            rv = fmap[rv.func](S.Pi / 2 - rv.args[0])
        return rv

    return bottom_up(rv, f)


def TR4(rv):
    return rv


def _TR56(rv, f, g, h, max, pow):
    def _f(rv):
        if not (rv.is_Pow and rv.base.func == f):
            return rv
        if not rv.exp.is_real:
            return rv

        if (rv.exp < 0) == True:
            return rv
        if (rv.exp > max) == True:
            return rv
        if rv.exp == 2:
            return h(g(rv.base.args[0]) ** 2)
        else:
            if rv.exp == 4:
                e = 2
            elif not pow:
                if rv.exp % 2:
                    return rv
                e = rv.exp // 2
            else:
                p = perfect_power(rv.exp)
                if not p:
                    return rv
                e = rv.exp // 2
            return h(g(rv.base.args[0]) ** 2) ** e

    return bottom_up(rv, _f)


def TR5(rv, max=4, pow=False):
    return _TR56(rv, sin, cos, lambda x: 1 - x, max=max, pow=pow)


def TR6(rv, max=4, pow=False):
    return _TR56(rv, cos, sin, lambda x: 1 - x, max=max, pow=pow)


def TR7(rv):
    def f(rv):
        if not (rv.is_Pow and rv.base.func == cos and rv.exp == 2):
            return rv
        return (1 + cos(2 * rv.base.args[0])) / 2

    return bottom_up(rv, f)


def TR8(rv, first=True):
    def f(rv):
        if not (
                rv.is_Mul or
                rv.is_Pow and
                rv.base.func in (cos, sin) and
                (rv.exp.is_integer or rv.base.is_positive)):
            return rv

        if first:
            n, d = [expand_mul(i) for i in rv.as_numer_denom()]
            newn = TR8(n, first=False)
            newd = TR8(d, first=False)
            if newn != n or newd != d:
                rv = gcd_terms(newn / newd)
                if rv.is_Mul and rv.args[0].is_Rational and \
                        len(rv.args) == 2 and rv.args[1].is_Add:
                    rv = Mul(*rv.as_coeff_Mul())
            return rv

        args = {cos: [], sin: [], None: []}
        for a in ordered(Mul.make_args(rv)):
            if a.func in (cos, sin):
                args[a.func].append(a.args[0])
            elif (a.is_Pow and a.exp.is_Integer and a.exp > 0 and \
                  a.base.func in (cos, sin)):
                # XXX this is ok but pathological expression could be handled
                # more efficiently as in TRmorrie
                args[a.base.func].extend([a.base.args[0]] * a.exp)
            else:
                args[None].append(a)
        c = args[cos]
        s = args[sin]
        if not (c and s or len(c) > 1 or len(s) > 1):
            return rv

        args = args[None]
        n = min(len(c), len(s))
        for i in range(n):
            a1 = s.pop()
            a2 = c.pop()
            args.append((sin(a1 + a2) + sin(a1 - a2)) / 2)
        while len(c) > 1:
            a1 = c.pop()
            a2 = c.pop()
            args.append((cos(a1 + a2) + cos(a1 - a2)) / 2)
        if c:
            args.append(cos(c.pop()))
        while len(s) > 1:
            a1 = s.pop()
            a2 = s.pop()
            args.append((-cos(a1 + a2) + cos(a1 - a2)) / 2)
        if s:
            args.append(sin(s.pop()))
        return TR8(expand_mul(Mul(*args)))

    return bottom_up(rv, f)


def TR9(rv):
    def f(rv):
        if not rv.is_Add:
            return rv

        def do(rv, first=True):
            if not rv.is_Add:
                return rv

            args = list(ordered(rv.args))
            if len(args) != 2:
                hit = False
                for i in range(len(args)):
                    ai = args[i]
                    if ai is None:
                        continue
                    for j in range(i + 1, len(args)):
                        aj = args[j]
                        if aj is None:
                            continue
                        was = ai + aj
                        new = do(was)
                        if new != was:
                            args[i] = new  # update in place
                            args[j] = None
                            hit = True
                            break  # go to next i
                if hit:
                    rv = Add(*[_f for _f in args if _f])
                    if rv.is_Add:
                        rv = do(rv)

                return rv

            # two-arg Add
            split = trig_split(*args)
            if not split:
                return rv
            gcd, n1, n2, a, b, iscos = split

            # application of rule if possible
            if iscos:
                if n1 == n2:
                    return gcd * n1 * 2 * cos((a + b) / 2) * cos((a - b) / 2)
                if n1 < 0:
                    a, b = b, a
                return -2 * gcd * sin((a + b) / 2) * sin((a - b) / 2)
            else:
                if n1 == n2:
                    return gcd * n1 * 2 * sin((a + b) / 2) * cos((a - b) / 2)
                if n1 < 0:
                    a, b = b, a
                return 2 * gcd * cos((a + b) / 2) * sin((a - b) / 2)

        return process_common_addends(rv, do)  # DON'T sift by free symbols

    return bottom_up(rv, f)


def TR10(rv, first=True):

    def f(rv):
        if not rv.func in (cos, sin):
            return rv

        f = rv.func
        arg = rv.args[0]
        if arg.is_Add:
            if first:
                args = list(ordered(arg.args))
            else:
                args = list(arg.args)
            a = args.pop()
            b = Add._from_args(args)
            if b.is_Add:
                if f == sin:
                    return sin(a) * TR10(cos(b), first=False) + \
                           cos(a) * TR10(sin(b), first=False)
                else:
                    return cos(a) * TR10(cos(b), first=False) - \
                           sin(a) * TR10(sin(b), first=False)
            else:
                if f == sin:
                    return sin(a) * cos(b) + cos(a) * sin(b)
                else:
                    return cos(a) * cos(b) - sin(a) * sin(b)
        return rv

    return bottom_up(rv, f)


def TR10i(rv):
    global _ROOT2, _ROOT3, _invROOT3
    if _ROOT2 is None:
        _roots()

    def f(rv):
        if not rv.is_Add:
            return rv

        def do(rv, first=True):

            if not rv.is_Add:
                return rv

            args = list(ordered(rv.args))
            if len(args) != 2:
                hit = False
                for i in range(len(args)):
                    ai = args[i]
                    if ai is None:
                        continue
                    for j in range(i + 1, len(args)):
                        aj = args[j]
                        if aj is None:
                            continue
                        was = ai + aj
                        new = do(was)
                        if new != was:
                            args[i] = new  # update in place
                            args[j] = None
                            hit = True
                            break  # go to next i
                if hit:
                    rv = Add(*[_f for _f in args if _f])
                    if rv.is_Add:
                        rv = do(rv)

                return rv

            # two-arg Add
            split = trig_split(*args, two=True)
            if not split:
                return rv
            gcd, n1, n2, a, b, same = split

            # identify and get c1 to be cos then apply rule if possible
            if same:  # coscos, sinsin
                gcd = n1 * gcd
                if n1 == n2:
                    return gcd * cos(a - b)
                return gcd * cos(a + b)
            else:  # cossin, cossin
                gcd = n1 * gcd
                if n1 == n2:
                    return gcd * sin(a + b)
                return gcd * sin(b - a)

        rv = process_common_addends(
            rv, do, lambda x: tuple(ordered(x.free_symbols)))
        while rv.is_Add:
            byrad = defaultdict(list)
            for a in rv.args:
                hit = 0
                if a.is_Mul:
                    for ai in a.args:
                        if ai.is_Pow and ai.exp is S.Half and \
                                ai.base.is_Integer:
                            byrad[ai].append(a)
                            hit = 1
                            break
                if not hit:
                    byrad[S.One].append(a)
            args = []
            for a in byrad:
                for b in [_ROOT3 * a, _invROOT3]:
                    if b in byrad:
                        for i in range(len(byrad[a])):
                            if byrad[a][i] is None:
                                continue
                            for j in range(len(byrad[b])):
                                if byrad[b][j] is None:
                                    continue
                                was = Add(byrad[a][i] + byrad[b][j])
                                new = do(was)
                                if new != was:
                                    args.append(new)
                                    byrad[a][i] = None
                                    byrad[b][j] = None
                                    break
            if args:
                rv = Add(*(args + [Add(*[_f for _f in v if _f])
                                   for v in byrad.values()]))
            else:
                rv = do(rv)  # final pass to resolve any new inducible pairs
                break

        return rv

    return bottom_up(rv, f)


def TR11(rv, base=None):
    def f(rv):
        if not rv.func in (cos, sin):
            return rv

        if base:
            f = rv.func
            t = f(base * 2)
            co = S.One
            if t.is_Mul:
                co, t = t.as_coeff_Mul()
            if not t.func in (cos, sin):
                return rv
            if rv.args[0] == t.args[0]:
                c = cos(base)
                s = sin(base)
                if f is cos:
                    return (c ** 2 - s ** 2) / co
                else:
                    return 2 * c * s / co
            return rv

        elif not rv.args[0].is_Number:
            # make a change if the leading coefficient's numerator is
            # divisible by 2
            c, m = rv.args[0].as_coeff_Mul(rational=True)
            if c.p % 2 == 0:
                arg = c.p // 2 * m / c.q
                c = TR11(cos(arg))
                s = TR11(sin(arg))
                if rv.func == sin:
                    rv = 2 * s * c
                else:
                    rv = c ** 2 - s ** 2
        return rv

    return bottom_up(rv, f)


def TR12(rv, first=True):

    def f(rv):
        if not rv.func == tan:
            return rv

        arg = rv.args[0]
        if arg.is_Add:
            if first:
                args = list(ordered(arg.args))
            else:
                args = list(arg.args)
            a = args.pop()
            b = Add._from_args(args)
            if b.is_Add:
                tb = TR12(tan(b), first=False)
            else:
                tb = tan(b)
            return (tan(a) + tb) / (1 - tan(a) * tb)
        return rv

    return bottom_up(rv, f)


def TR12i(rv):
    from sympy import factor

    def f(rv):
        if not (rv.is_Add or rv.is_Mul or rv.is_Pow):
            return rv

        n, d = rv.as_numer_denom()
        if not d.args or not n.args:
            return rv

        dok = {}

        def ok(di):
            m = as_f_sign_1(di)
            if m:
                g, f, s = m
                if s is S.NegativeOne and f.is_Mul and len(f.args) == 2 and \
                        all(isinstance(fi, tan) for fi in f.args):
                    return g, f

        d_args = list(Mul.make_args(d))
        for i, di in enumerate(d_args):
            m = ok(di)
            if m:
                g, t = m
                s = Add(*[_.args[0] for _ in t.args])
                dok[s] = S.One
                d_args[i] = g
                continue
            if di.is_Add:
                di = factor(di)
                if di.is_Mul:
                    d_args.extend(di.args)
                    d_args[i] = S.One
            elif di.is_Pow and (di.exp.is_integer or di.base.is_positive):
                m = ok(di.base)
                if m:
                    g, t = m
                    s = Add(*[_.args[0] for _ in t.args])
                    dok[s] = di.exp
                    d_args[i] = g ** di.exp
                else:
                    di = factor(di)
                    if di.is_Mul:
                        d_args.extend(di.args)
                        d_args[i] = S.One
        if not dok:
            return rv

        def ok(ni):
            if ni.is_Add and len(ni.args) == 2:
                a, b = ni.args
                if isinstance(a, tan) and isinstance(b, tan):
                    return a, b

        n_args = list(Mul.make_args(factor_terms(n)))
        hit = False
        for i, ni in enumerate(n_args):
            m = ok(ni)
            if not m:
                m = ok(-ni)
                if m:
                    n_args[i] = S.NegativeOne
                else:
                    if ni.is_Add:
                        ni = factor(ni)
                        if ni.is_Mul:
                            n_args.extend(ni.args)
                            n_args[i] = S.One
                        continue
                    elif ni.is_Pow and (
                            ni.exp.is_integer or ni.base.is_positive):
                        m = ok(ni.base)
                        if m:
                            n_args[i] = S.One
                        else:
                            ni = factor(ni)
                            if ni.is_Mul:
                                n_args.extend(ni.args)
                                n_args[i] = S.One
                            continue
                    else:
                        continue
            else:
                n_args[i] = S.One
            hit = True
            s = Add(*[_.args[0] for _ in m])
            ed = dok[s]
            newed = ed.extract_additively(S.One)
            if newed is not None:
                if newed:
                    dok[s] = newed
                else:
                    dok.pop(s)
            n_args[i] *= -tan(s)

        if hit:
            rv = Mul(*n_args) / Mul(*d_args) / Mul(*[(Add(*[
                tan(a) for a in i.args]) - 1) ** e for i, e in dok.items()])

        return rv

    return bottom_up(rv, f)


def TR13(rv):
    def f(rv):
        if not rv.is_Mul:
            return rv
        args = {tan: [], cot: [], None: []}
        for a in ordered(Mul.make_args(rv)):
            if a.func in (tan, cot):
                args[a.func].append(a.args[0])
            else:
                args[None].append(a)
        t = args[tan]
        c = args[cot]
        if len(t) < 2 and len(c) < 2:
            return rv
        args = args[None]
        while len(t) > 1:
            t1 = t.pop()
            t2 = t.pop()
            args.append(1 - (tan(t1) / tan(t1 + t2) + tan(t2) / tan(t1 + t2)))
        if t:
            args.append(tan(t.pop()))
        while len(c) > 1:
            t1 = c.pop()
            t2 = c.pop()
            args.append(1 + cot(t1) * cot(t1 + t2) + cot(t2) * cot(t1 + t2))
        if c:
            args.append(cot(c.pop()))
        return Mul(*args)

    return bottom_up(rv, f)


def TRmorrie(rv):
    def f(rv, first=True):
        if not rv.is_Mul:
            return rv
        if first:
            n, d = rv.as_numer_denom()
            return f(n, 0) / f(d, 0)

        args = defaultdict(list)
        coss = {}
        other = []
        for c in rv.args:
            b, e = c.as_base_exp()
            if e.is_Integer and isinstance(b, cos):
                co, a = b.args[0].as_coeff_Mul()
                args[a].append(co)
                coss[b] = e
            else:
                other.append(c)

        new = []
        for a in args:
            c = args[a]
            c.sort()
            no = []
            while c:
                k = 0
                cc = ci = c[0]
                while cc in c:
                    k += 1
                    cc *= 2
                if k > 1:
                    newarg = sin(2 ** k * ci * a) / 2 ** k / sin(ci * a)
                    # see how many times this can be taken
                    take = None
                    ccs = []
                    for i in range(k):
                        cc /= 2
                        key = cos(a * cc, evaluate=False)
                        ccs.append(cc)
                        take = min(coss[key], take or coss[key])
                    # update exponent counts
                    for i in range(k):
                        cc = ccs.pop()
                        key = cos(a * cc, evaluate=False)
                        coss[key] -= take
                        if not coss[key]:
                            c.remove(cc)
                    new.append(newarg ** take)
                else:
                    no.append(c.pop(0))
            c[:] = no

        if new:
            rv = Mul(*(new + other + [
                cos(k * a, evaluate=False) for a in args for k in args[a]]))

        return rv

    return bottom_up(rv, f)


def TR14(rv, first=True):
    def f(rv):
        if not rv.is_Mul:
            return rv

        if first:
            # sort them by location in numerator and denominator
            # so the code below can just deal with positive exponents
            n, d = rv.as_numer_denom()
            if d is not S.One:
                newn = TR14(n, first=False)
                newd = TR14(d, first=False)
                if newn != n or newd != d:
                    rv = newn / newd
                return rv

        other = []
        process = []
        for a in rv.args:
            if a.is_Pow:
                b, e = a.as_base_exp()
                if not (e.is_integer or b.is_positive):
                    other.append(a)
                    continue
                a = b
            else:
                e = S.One
            m = as_f_sign_1(a)
            if not m or m[1].func not in (cos, sin):
                if e is S.One:
                    other.append(a)
                else:
                    other.append(a ** e)
                continue
            g, f, si = m
            process.append((g, e.is_Number, e, f, si, a))

        # sort them to get like terms next to each other
        process = list(ordered(process))

        # keep track of whether there was any change
        nother = len(other)

        # access keys
        keys = (g, t, e, f, si, a) = list(range(6))

        while process:
            A = process.pop(0)
            if process:
                B = process[0]

                if A[e].is_Number and B[e].is_Number:
                    # both exponents are numbers
                    if A[f] == B[f]:
                        if A[si] != B[si]:
                            B = process.pop(0)
                            take = min(A[e], B[e])

                            # reinsert any remainder
                            # the B will likely sort after A so check it first
                            if B[e] != take:
                                rem = [B[i] for i in keys]
                                rem[e] -= take
                                process.insert(0, rem)
                            elif A[e] != take:
                                rem = [A[i] for i in keys]
                                rem[e] -= take
                                process.insert(0, rem)

                            if isinstance(A[f], cos):
                                t = sin
                            else:
                                t = cos
                            other.append((-A[g] * B[g] * t(A[f].args[0]) ** 2) ** take)
                            continue

                elif A[e] == B[e]:
                    # both exponents are equal symbols
                    if A[f] == B[f]:
                        if A[si] != B[si]:
                            B = process.pop(0)
                            take = A[e]
                            if isinstance(A[f], cos):
                                t = sin
                            else:
                                t = cos
                            other.append((-A[g] * B[g] * t(A[f].args[0]) ** 2) ** take)
                            continue

            # either we are done or neither condition above applied
            other.append(A[a] ** A[e])

        if len(other) != nother:
            rv = Mul(*other)

        return rv

    return bottom_up(rv, f)


def TR15(rv, max=4, pow=False):
    def f(rv):
        if not (isinstance(rv, Pow) and isinstance(rv.base, sin)):
            return rv

        ia = 1 / rv
        a = _TR56(ia, sin, cot, lambda x: 1 + x, max=max, pow=pow)
        if a != ia:
            rv = a
        return rv

    return bottom_up(rv, f)


def TR16(rv, max=4, pow=False):
    def f(rv):
        if not (isinstance(rv, Pow) and isinstance(rv.base, cos)):
            return rv

        ia = 1 / rv
        a = _TR56(ia, cos, tan, lambda x: 1 + x, max=max, pow=pow)
        if a != ia:
            rv = a
        return rv

    return bottom_up(rv, f)


def TR111(rv):
    def f(rv):
        if not (
                isinstance(rv, Pow) and
                (rv.base.is_positive or rv.exp.is_integer and rv.exp.is_negative)):
            return rv

        if isinstance(rv.base, tan):
            return cot(rv.base.args[0]) ** -rv.exp
        elif isinstance(rv.base, sin):
            return csc(rv.base.args[0]) ** -rv.exp
        elif isinstance(rv.base, cos):
            return sec(rv.base.args[0]) ** -rv.exp
        return rv

    return bottom_up(rv, f)


def TR22(rv, max=4, pow=False):
    def f(rv):
        if not (isinstance(rv, Pow) and rv.base.func in (cot, tan)):
            return rv

        rv = _TR56(rv, tan, sec, lambda x: x - 1, max=max, pow=pow)
        rv = _TR56(rv, cot, csc, lambda x: x - 1, max=max, pow=pow)
        return rv

    return bottom_up(rv, f)


def TRpower(rv):
    def f(rv):
        if not (isinstance(rv, Pow) and isinstance(rv.base, (sin, cos))):
            return rv
        b, n = rv.as_base_exp()
        x = b.args[0]
        if n.is_Integer and n.is_positive:
            if n.is_odd and isinstance(b, cos):
                rv = 2 ** (1 - n) * Add(*[binomial(n, k) * cos((n - 2 * k) * x)
                                          for k in range((n + 1) / 2)])
            elif n.is_odd and isinstance(b, sin):
                rv = 2 ** (1 - n) * (-1) ** ((n - 1) / 2) * Add(*[binomial(n, k) *
                                                                  (-1) ** k * sin((n - 2 * k) * x) for k in
                                                                  range((n + 1) / 2)])
            elif n.is_even and isinstance(b, cos):
                rv = 2 ** (1 - n) * Add(*[binomial(n, k) * cos((n - 2 * k) * x)
                                          for k in range(n / 2)])
            elif n.is_even and isinstance(b, sin):
                rv = 2 ** (1 - n) * (-1) ** (n / 2) * Add(*[binomial(n, k) *
                                                            (-1) ** k * cos((n - 2 * k) * x) for k in range(n / 2)])
            if n.is_even:
                rv += 2 ** (-n) * binomial(n, n / 2)
        return rv

    return bottom_up(rv, f)


def L(rv):

    if SYMPY_DEBUG:
        (TR0, TR1, TR2, TR3, TR4, TR5, TR6, TR7, TR8, TR9, TR10, TR11, TR12, TR13,
        TR2i, TRmorrie, TR14, TR15, TR16, TR12i, TR111, TR22
        )= list(map(debug,
        (TR0, TR1, TR2, TR3, TR4, TR5, TR6, TR7, TR8, TR9, TR10, TR11, TR12, TR13,
        TR2i, TRmorrie, TR14, TR15, TR16, TR12i, TR111, TR22)))



    CTR1 = [(TR5, TR0), (TR6, TR0), identity]

    CTR2 = (TR11, [(TR5, TR0), (TR6, TR0), TR0])

    CTR3 = [(TRmorrie, TR8, TR0), (TRmorrie, TR8, TR10i, TR0), identity]

    CTR4 = [(TR4, TR10i), identity]

    RL1 = (TR4, TR3, TR4, TR12, TR4, TR13, TR4, TR0)

    RL2 = [
        (TR4, TR3, TR10, TR4, TR3, TR11),
        (TR5, TR7, TR11, TR4),
        (CTR3, CTR1, TR9, CTR2, TR4, TR9, TR9, CTR4),
        identity,
        ]


def fu(rv, measure=lambda x: (L(x), x.count_ops())):
    fRL1 = greedy(RL1, measure)
    fRL2 = greedy(RL2, measure)

    was = rv
    rv = sympify(rv)
    if not isinstance(rv, Expr):
        return rv.func(*[fu(a, measure=measure) for a in rv.args])
    rv = TR1(rv)
    if rv.has(tan, cot):
        rv1 = fRL1(rv)
        if (measure(rv1) < measure(rv)):
            rv = rv1
        if rv.has(tan, cot):
            rv = TR2(rv)
    if rv.has(sin, cos):
        rv1 = fRL2(rv)
        rv2 = TR8(TRmorrie(rv1))
        rv = min([was, rv, rv1, rv2], key=measure)
    return min(TR2i(rv), rv, key=measure)


def process_common_addends(rv, do, key2=None, key1=True):

    # collect by absolute value of coefficient and key2
    absc = defaultdict(list)
    if key1:
        for a in rv.args:
            c, a = a.as_coeff_Mul()
            if c < 0:
                c = -c
                a = -a  # put the sign on `a`
            absc[(c, key2(a) if key2 else 1)].append(a)
    elif key2:
        for a in rv.args:
            absc[(S.One, key2(a))].append(a)
    else:
        raise ValueError('must have at least one key')

    args = []
    hit = False
    for k in absc:
        v = absc[k]
        c, _ = k
        if len(v) > 1:
            e = Add(*v, evaluate=False)
            new = do(e)
            if new != e:
                e = new
                hit = True
            args.append(c * e)
        else:
            args.append(c * v[0])
    if hit:
        rv = Add(*args)

    return rv


fufuncs = '''
    TR0 TR1 TR2 TR3 TR4 TR5 TR6 TR7 TR8 TR9 TR10 TR10i TR11
    TR12 TR13 L TR2i TRmorrie TR12i
    TR14 TR15 TR16 TR111 TR22'''.split()
FU = dict(list(zip(fufuncs, list(map(locals().get, fufuncs)))))


def _roots():
    global _ROOT2, _ROOT3, _invROOT3
    _ROOT2, _ROOT3 = sqrt(2), sqrt(3)
    _invROOT3 = 1 / _ROOT3


_ROOT2 = None


def trig_split(a, b, two=False):
    global _ROOT2, _ROOT3, _invROOT3
    if _ROOT2 is None:
        _roots()

    a, b = [Factors(i) for i in (a, b)]
    ua, ub = a.normal(b)
    gcd = a.gcd(b).as_expr()
    n1 = n2 = 1
    if S.NegativeOne in ua.factors:
        ua = ua.quo(S.NegativeOne)
        n1 = -n1
    elif S.NegativeOne in ub.factors:
        ub = ub.quo(S.NegativeOne)
        n2 = -n2
    a, b = [i.as_expr() for i in (ua, ub)]

    def pow_cos_sin(a, two):
        c = s = None
        co = S.One
        if a.is_Mul:
            co, a = a.as_coeff_Mul()
            if len(a.args) > 2 or not two:
                return None
            if a.is_Mul:
                args = list(a.args)
            else:
                args = [a]
            a = args.pop(0)
            if isinstance(a, cos):
                c = a
            elif isinstance(a, sin):
                s = a
            elif a.is_Pow and a.exp is S.Half:  # autoeval doesn't allow -1/2
                co *= a
            else:
                return None
            if args:
                b = args[0]
                if isinstance(b, cos):
                    if c:
                        s = b
                    else:
                        c = b
                elif isinstance(b, sin):
                    if s:
                        c = b
                    else:
                        s = b
                elif b.is_Pow and b.exp is S.Half:
                    co *= b
                else:
                    return None
            return co if co is not S.One else None, c, s
        elif isinstance(a, cos):
            c = a
        elif isinstance(a, sin):
            s = a
        if c is None and s is None:
            return
        co = co if co is not S.One else None
        return co, c, s

    # get the parts
    m = pow_cos_sin(a, two)
    if m is None:
        return
    coa, ca, sa = m
    m = pow_cos_sin(b, two)
    if m is None:
        return
    cob, cb, sb = m

    # check them
    if (not ca) and cb or ca and isinstance(ca, sin):
        coa, ca, sa, cob, cb, sb = cob, cb, sb, coa, ca, sa
        n1, n2 = n2, n1
    if not two:  # need cos(x) and cos(y) or sin(x) and sin(y)
        c = ca or sa
        s = cb or sb
        if not isinstance(c, s.func):
            return None
        return gcd, n1, n2, c.args[0], s.args[0], isinstance(c, cos)
    else:
        if not coa and not cob:
            if (ca and cb and sa and sb):
                if isinstance(ca, sa.func) is not isinstance(cb, sb.func):
                    return
                args = {j.args for j in (ca, sa)}
                if not all(i.args in args for i in (cb, sb)):
                    return
                return gcd, n1, n2, ca.args[0], sa.args[0], isinstance(ca, sa.func)
        if ca and sa or cb and sb or \
                two and (ca is None and sa is None or cb is None and sb is None):
            return
        c = ca or sa
        s = cb or sb
        if c.args != s.args:
            return
        if not coa:
            coa = S.One
        if not cob:
            cob = S.One
        if coa is cob:
            gcd *= _ROOT2
            return gcd, n1, n2, c.args[0], pi / 4, False
        elif coa / cob == _ROOT3:
            gcd *= 2 * cob
            return gcd, n1, n2, c.args[0], pi / 3, False
        elif coa / cob == _invROOT3:
            gcd *= 2 * coa
            return gcd, n1, n2, c.args[0], pi / 6, False


def as_f_sign_1(e):
    if not e.is_Add or len(e.args) != 2:
        return
    # exact match
    a, b = e.args
    if a in (S.NegativeOne, S.One):
        g = S.One
        if b.is_Mul and b.args[0].is_Number and b.args[0] < 0:
            a, b = -a, -b
            g = -g
        return g, b, a
    # gcd match
    a, b = [Factors(i) for i in e.args]
    ua, ub = a.normal(b)
    gcd = a.gcd(b).as_expr()
    if S.NegativeOne in ua.factors:
        ua = ua.quo(S.NegativeOne)
        n1 = -1
        n2 = 1
    elif S.NegativeOne in ub.factors:
        ub = ub.quo(S.NegativeOne)
        n1 = 1
        n2 = -1
    else:
        n1 = n2 = 1
    a, b = [i.as_expr() for i in (ua, ub)]
    if a is S.One:
        a, b = b, a
        n1, n2 = n2, n1
    if n1 == -1:
        gcd = -gcd
        n2 = -n2

    if b is S.One:
        return gcd, a, n2


def _osborne(e, d):

    def f(rv):
        if not isinstance(rv, HyperbolicFunction):
            return rv
        a = rv.args[0]
        a = a * d if not a.is_Add else Add._from_args([i * d for i in a.args])
        if isinstance(rv, sinh):
            return I * sin(a)
        elif isinstance(rv, cosh):
            return cos(a)
        elif isinstance(rv, tanh):
            return I * tan(a)
        elif isinstance(rv, coth):
            return cot(a) / I
        elif isinstance(rv, sech):
            return sec(a)
        elif isinstance(rv, csch):
            return csc(a) / I
        else:
            raise NotImplementedError('unhandled %s' % rv.func)

    return bottom_up(e, f)


def _osbornei(e, d):

    def f(rv):
        if not isinstance(rv, TrigonometricFunction):
            return rv
        const, x = rv.args[0].as_independent(d, as_Add=True)
        a = x.xreplace({d: S.One}) + const * I
        if isinstance(rv, sin):
            return sinh(a) / I
        elif isinstance(rv, cos):
            return cosh(a)
        elif isinstance(rv, tan):
            return tanh(a) / I
        elif isinstance(rv, cot):
            return coth(a) * I
        elif isinstance(rv, sec):
            return sech(a)
        elif isinstance(rv, csc):
            return csch(a) * I
        else:
            raise NotImplementedError('unhandled %s' % rv.func)

    return bottom_up(e, f)


def hyper_as_trig(rv):
    from sympy.simplify.simplify import signsimp
    from sympy.simplify.radsimp import collect

    # mask off trig functions
    trigs = rv.atoms(TrigonometricFunction)
    reps = [(t, Dummy()) for t in trigs]
    masked = rv.xreplace(dict(reps))

    # get inversion substitutions in place
    reps = [(v, k) for k, v in reps]

    d = Dummy()

    return _osborne(masked, d), lambda x: collect(signsimp(
        _osbornei(x, d).xreplace(dict(reps))), S.ImaginaryUnit)


def sincos_to_sum(expr):

    if not expr.has(cos, sin):
        return expr
    else:
        return TR8(expand_mul(TRpower(expr)))
