import os
from tree_sitter import Language, Parser
import tree_sitter_typescript as tsts

LANGUAGES = {".ts": Language(tsts.language_typescript())}

query_text = """
    (class_declaration name: (type_identifier) @name) @def
    (function_declaration name: (identifier) @name) @def
    (method_definition name: (property_identifier) @name) @def
"""

code = """
class PaymentController {
    processDeposit() {
        const result = this.useCase.execute();
        axios.post("http://webhook", result);
        kafka.publish("payment.success", result);
    }
}
"""

parser = Parser(LANGUAGES[".ts"])
tree = parser.parse(code.encode('utf-8'))
query = LANGUAGES[".ts"].query(query_text)
matches = query.matches(tree.root_node)

def extract_calls(node, source_bytes):
    calls = []
    def walk(n):
        if n.type == 'call_expression':
            fn_node = n.child_by_field_name('function')
            if fn_node:
                calls.append(source_bytes[fn_node.start_byte:fn_node.end_byte].decode('utf-8'))
        for child in n.children:
            walk(child)
    walk(node)
    return calls

for match in matches:
    captures = match[1]
    def_node = captures['def'][0]
    name_node = captures['name'][0]
    
    name = code.encode('utf-8')[name_node.start_byte:name_node.end_byte].decode('utf-8')
    calls = extract_calls(def_node, code.encode('utf-8'))
    print(f"Node: {name}, Type: {def_node.type}")
    print(f"  Calls: {calls}")

