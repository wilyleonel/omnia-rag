import os
from tree_sitter import Language, Parser
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
import tree_sitter_python as tspy

# Initialize parsers and languages
LANGUAGES = {}
try:
    LANGUAGES[".js"] = Language(tsjs.language())
    LANGUAGES[".jsx"] = Language(tsjs.language())
    LANGUAGES[".ts"] = Language(tsts.language_typescript())
    LANGUAGES[".tsx"] = Language(tsts.language_tsx())
    LANGUAGES[".py"] = Language(tspy.language())
except Exception as e:
    print(f"Error cargando Tree-sitter languages: {e}")

# Definición de Queries para cada lenguaje
QUERIES = {
    ".js": """
        (class_declaration name: (identifier) @name) @def
        (function_declaration name: (identifier) @name) @def
        (method_definition name: (property_identifier) @name) @def
    """,
    ".ts": """
        (class_declaration name: (type_identifier) @name) @def
        (function_declaration name: (identifier) @name) @def
        (method_definition name: (property_identifier) @name) @def
        (interface_declaration name: (type_identifier) @name) @def
        (type_alias_declaration name: (type_identifier) @name) @def
    """,
    ".py": """
        (class_definition name: (identifier) @name) @def
        (function_definition name: (identifier) @name) @def
    """
}

# tsx and jsx use similar queries as ts and js
QUERIES[".jsx"] = QUERIES[".js"]
QUERIES[".tsx"] = QUERIES[".ts"]

class ASTChunker:
    def __init__(self):
        self.parsers = {}
        self.compiled_queries = {}
        for ext, lang in LANGUAGES.items():
            parser = Parser(lang)
            self.parsers[ext] = parser
            if ext in QUERIES:
                self.compiled_queries[ext] = lang.query(QUERIES[ext])

    def _get_node_text(self, source_bytes, node):
        return source_bytes[node.start_byte:node.end_byte].decode('utf-8')
        
    def _extract_calls(self, node, source_bytes):
        calls = []
        def walk(n):
            if n.type == 'call_expression':
                fn_node = n.child_by_field_name('function')
                if fn_node:
                    calls.append(self._get_node_text(source_bytes, fn_node))
            for child in n.children:
                walk(child)
        walk(node)
        return list(dict.fromkeys(calls)) # deduplicate keeping order

    def chunk_file(self, filepath, content):
        """
        Analiza el archivo usando AST y devuelve una lista de fragmentos estructurales semánticos (Grafo).
        Si la extensión no es soportada, devuelve [] para hacer fallback a texto plano.
        """
        _, ext = os.path.splitext(filepath)
        if ext not in self.parsers or ext not in self.compiled_queries:
            return []

        parser = self.parsers[ext]
        query = self.compiled_queries[ext]
        source_bytes = content.encode('utf-8')
        
        try:
            tree = parser.parse(source_bytes)
            matches = query.matches(tree.root_node)
            
            chunks = []
            for match in matches:
                captures = match[1]
                if 'def' in captures and 'name' in captures:
                    def_node = captures['def'][0]
                    name_node = captures['name'][0]
                    
                    start_byte = def_node.start_byte
                    
                    target_node = def_node
                    if target_node.parent and target_node.parent.type == 'export_statement':
                        target_node = target_node.parent

                    prev = target_node.prev_sibling
                    while prev and prev.type == 'comment':
                        start_byte = prev.start_byte
                        prev = prev.prev_sibling

                    chunk_text = source_bytes[start_byte:def_node.end_byte].decode('utf-8')
                    symbol_name = self._get_node_text(source_bytes, name_node)
                    
                    if len(chunk_text.strip()) > 15:
                        # Extraer llamadas
                        calls = self._extract_calls(def_node, source_bytes)
                        # No incluir las llamadas a super() para evitar ruido
                        calls = [c for c in calls if c != "super"]
                        
                        # Extraer padre (Clase)
                        belongs_to = "Global"
                        parent = def_node.parent
                        while parent:
                            if parent.type in ['class_declaration', 'interface_declaration', 'class_definition']:
                                for child in parent.children:
                                    if child.type in ['type_identifier', 'identifier']:
                                        belongs_to = self._get_node_text(source_bytes, child)
                                        break
                                break
                            parent = parent.parent

                        # Generar resumen semántico
                        if def_node.type in ['class_declaration', 'class_definition', 'interface_declaration']:
                            summary = f"Clase {symbol_name}. "
                        else:
                            summary = f"Función {symbol_name} perteneciente a {belongs_to}. "
                            
                        if calls:
                            summary += f"Llama internamente a: {', '.join(calls[:20])}."
                        else:
                            summary += "No realiza llamadas a otras funciones."

                        chunks.append({
                            "text": chunk_text,
                            "symbol": symbol_name,
                            "type": def_node.type,
                            "start_line": def_node.start_point[0],
                            "end_line": def_node.end_point[0],
                            "belongs_to": belongs_to,
                            "calls": calls,
                            "summary": summary
                        })
            
            return chunks
        except Exception as e:
            print(f"AST Chunker error en {filepath}: {e}")
            return []
