from sympy import *
from sympy.abc import x, y
from sympy.simplify.fu import *
import random
import time
import pandas as pd
import func


def exprgen(root_val, max_ds, global_list, operations):
    def zero():
        return random.choice(operations)(root_val)

    def one():
        return root_val * random.choice(global_list)

    def two():
        return root_val / random.choice(global_list)

    switcher = {
        0: zero,
        1: one,
        2: two
    }

    def get_unique(args):
        funct = switcher.get(args, "invalid")
        return funct()

    new_expr = root_val
    while global_list.count(new_expr) > 0 or new_expr == 1:
        opts = [0, 1, 2]
        new_expr = get_unique(random.choice(opts))
    start_time = time.time()
    trigsimp(new_expr)
    score = time.time() - start_time
    return new_expr, score


class MakePair:
    def __init__(self,a, b):
        self.first = a
        self.second = b


def main(level_expression=None):
    operations = [TR0, TR1, TR2, TR3, TR4, TR5, TR6, TR7, TR8, TR9, TR10, TR10i, TR11, TR12, TR13, TR2i, TRmorrie,
                  TR12i, TR14, TR15, TR16, TR111, TR22, TRpower]
    identities = [sin(x) ** 2 + cos(x) ** 2, sec(x) ** 2 - tan(x) ** 2, csc(x) ** 2 - cot(x) ** 2, tan(x) * cot(x)]
    global_list = [identities]
    df = pd.DataFrame(columns=['Root', 'Identity-Diversity Score Pair', 'Max Diversity score'])
    level_expressions = identities
    root_val = 1
    max_ds = 0.2
    df.append({'Root': root_val, 'Identity-Diversity Score Pair': level_expression, 'Max Diversity score': max_ds})
    root_val = random.choice(level_expressions)
    hot_pair = MakePair(root_val, max_ds)
    for i in range(9):
        level_expression = []
        for j in range(4):
            expr, score = exprgen(root_val, max_ds, global_list)
            global_list.append(expr)
            level_expression.append(expr)
            if max_ds < score:
                max_ds = score
                hot_pair = MakePair(expr, max_ds)
        df.append({'Root': root_val, 'Identity-Diversity Score Pair': level_expression, 'Max Diversity score': max_ds})
        root_val = hot_pair.first
    df.show()


if __name__ == '__main__':
    main()
