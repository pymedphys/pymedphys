"""Evaluate GUI column filters without executing user-supplied Python code."""

import ast
import operator


_COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_BOOLEAN = {ast.BitAnd: operator.and_, ast.BitOr: operator.or_}
_UNARY = {ast.Invert: operator.invert, ast.USub: operator.neg, ast.UAdd: operator.pos}


def evaluate_filter(column, condition):
    """Evaluate comparisons of _ (the selected column) with literals.

    Supports comparisons and their &, | and ~ combinations.
    Calls, attribute access, indexing and other Python expressions are rejected.
    """
    if len(condition) > 1024:
        raise ValueError("filter expression is too long")
    tree = ast.parse(condition, mode="eval")

    def value(node, depth=0):
        if depth > 32:
            raise ValueError("filter expression is too deeply nested")
        if isinstance(node, ast.Name) and node.id == "_":
            return column
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, str, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](value(node.operand, depth + 1))
        if isinstance(node, ast.BinOp) and type(node.op) in _BOOLEAN:
            return _BOOLEAN[type(node.op)](value(node.left, depth + 1), value(node.right, depth + 1))
        if isinstance(node, ast.Compare) and all(type(op) in _COMPARISONS for op in node.ops):
            left = value(node.left, depth + 1)
            result = None
            for op, operand in zip(node.ops, node.comparators):
                right = value(operand, depth + 1)
                comparison = _COMPARISONS[type(op)](left, right)
                result = comparison if result is None else result & comparison
                left = right
            return result
        raise ValueError("unsupported filter expression")

    return value(tree.body)
