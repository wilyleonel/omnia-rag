import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

def main():
    LANGUAGE = Language(tsts.language_typescript())
    parser = Parser(LANGUAGE)
    source = b"""
    import { Request } from 'express';
    export class PaymentController {
        async verifyDeposit(req: Request) {
            return true;
        }
    }
    """
    tree = parser.parse(source)
    print("Tree root:", tree.root_node.type)
    
    query = LANGUAGE.query("""
        (class_declaration name: (type_identifier) @class.name)
        (method_definition name: (property_identifier) @method.name)
    """)
    captures = query.captures(tree.root_node)
    for capture in captures:
        print(f"Captured: {capture[1]} -> {capture[0].text.decode('utf8')}")

if __name__ == "__main__":
    main()
