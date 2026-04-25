import ast

class ImportChecker(ast.NodeVisitor):
    def visit_AsyncFunctionDef(self, node):
        if node.name == '_handle_event':
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom):
                    names = [alias.name for alias in child.names]
                    print(f"Line {child.lineno}: from {child.module} import {', '.join(names)}")
        self.generic_visit(node)

with open('core/engine/actions.py', 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read())

checker = ImportChecker()
checker.visit(tree)
