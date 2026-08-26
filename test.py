import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser
lang = Language(tsts.language_tsx())
parser = Parser(lang)

code = b"export const MyComp = () => { return 1; };\nconst MyComp2 = function() {};"
tree = parser.parse(code)
query = lang.query("""
    (lexical_declaration 
        (variable_declarator 
            name: (identifier) @name 
            value: [(arrow_function) (function_expression)]
        )
    ) @def
""")
captures = query.captures(tree.root_node)
print(captures)
