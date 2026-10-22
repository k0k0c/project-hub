import com.sun.source.tree.*;
import com.sun.source.util.*;
import javax.tools.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Parse declarations only. Does not compile or execute the inspected project. */
class ArchitectureSourceScanner {
    static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof String s) {
            StringBuilder out = new StringBuilder("\"");
            for (char c : s.toCharArray()) {
                switch (c) {
                    case '"' -> out.append("\\\""); case '\\' -> out.append("\\\\");
                    case '\n' -> out.append("\\n"); case '\r' -> out.append("\\r"); case '\t' -> out.append("\\t");
                    default -> { if (c < 32) out.append(String.format("\\u%04x", (int)c)); else out.append(c); }
                }
            }
            return out.append('"').toString();
        }
        if (value instanceof Map<?,?> map) {
            List<String> fields = new ArrayList<>();
            map.forEach((k,v) -> fields.add(json(k.toString()) + ":" + json(v)));
            return "{" + String.join(",", fields) + "}";
        }
        if (value instanceof Collection<?> values) return "[" + String.join(",", values.stream().map(ArchitectureSourceScanner::json).toList()) + "]";
        return value.toString();
    }
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("A JDK compiler is required");
        List<String> paths = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8)).lines().filter(s -> !s.isBlank()).toList();
        List<Map<String,Object>> types = new ArrayList<>();
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager manager = compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8)) {
            JavacTask task = (JavacTask)compiler.getTask(null, manager, diagnostics, List.of("-proc:none"), null, manager.getJavaFileObjectsFromStrings(paths));
            Iterable<? extends CompilationUnitTree> units = task.parse();
            Trees trees = Trees.instance(task);
            DocTrees docs = DocTrees.instance(task);
            for (CompilationUnitTree unit : units) {
                String pack = unit.getPackageName() == null ? "" : unit.getPackageName().toString();
                List<String> imports = unit.getImports().stream().map(i -> i.getQualifiedIdentifier().toString()).toList();
                new TreePathScanner<Void,String>() {
                    @Override public Void visitClass(ClassTree node, String parent) {
                        String name = node.getSimpleName().toString();
                        if (name.isBlank()) return null;
                        String qualified = (parent == null ? pack : parent);
                        qualified = qualified.isBlank() ? name : qualified + "." + name;
                        Map<String,Object> row = new LinkedHashMap<>();
                        row.put("name", qualified); row.put("title", name);
                        row.put("type", node.getKind() == Tree.Kind.INTERFACE ? "interface" : node.getKind() == Tree.Kind.ENUM ? "enum" : node.getKind() == Tree.Kind.RECORD ? "record" : "class");
                        row.put("path", Path.of(unit.getSourceFile().toUri()).toAbsolutePath().normalize().toString());
                        long position = trees.getSourcePositions().getStartPosition(unit, node);
                        row.put("line", unit.getLineMap().getLineNumber(position));
                        row.put("bases", node.getKind() == Tree.Kind.INTERFACE ? node.getImplementsClause().stream().map(Object::toString).toList() : node.getExtendsClause() == null ? List.of() : List.of(node.getExtendsClause().toString()));
                        row.put("interfaces", node.getKind() == Tree.Kind.INTERFACE ? List.of() : node.getImplementsClause().stream().map(Object::toString).toList());
                        row.put("imports", imports);
                        List<Map<String,Object>> references = new ArrayList<>();
                        new TreeScanner<Void,Void>() {
                            void reference(Tree node, Tree type) {
                                references.add(Map.of("name", type.toString(), "line", unit.getLineMap().getLineNumber(trees.getSourcePositions().getStartPosition(unit, node))));
                            }
                            @Override public Void visitNewClass(NewClassTree tree, Void value) {
                                reference(tree, tree.getIdentifier()); return super.visitNewClass(tree, value);
                            }
                            @Override public Void visitMemberSelect(MemberSelectTree tree, Void value) {
                                if (tree.getIdentifier().contentEquals("class")) reference(tree, tree.getExpression());
                                return super.visitMemberSelect(tree, value);
                            }
                            @Override public Void visitClass(ClassTree tree, Void value) { return null; }
                        }.scan(node.getMembers(), null);
                        for (Tree member : node.getMembers()) if (member instanceof VariableTree field && field.getType() != null) {
                            references.add(Map.of("name", field.getType().toString(), "line", unit.getLineMap().getLineNumber(trees.getSourcePositions().getStartPosition(unit, field))));
                        }
                        row.put("references", references);
                        String comment = docs.getDocComment(getCurrentPath());
                        row.put("comment", comment == null ? "" : comment.split("\\n\\s*\\n", 2)[0].substring(0, Math.min(400, comment.split("\\n\\s*\\n", 2)[0].length())));
                        row.put("entrypoint", node.getMembers().stream().anyMatch(m -> m instanceof MethodTree method && method.getName().contentEquals("main") && method.getModifiers().getFlags().contains(javax.lang.model.element.Modifier.STATIC) && method.getModifiers().getFlags().contains(javax.lang.model.element.Modifier.PUBLIC) && method.getParameters().size() == 1 && Set.of("String[]", "java.lang.String[]").contains(method.getParameters().get(0).getType().toString()) && method.getReturnType().toString().equals("void")));
                        types.add(row);
                        // Only member types; never descend into methods, anonymous/local classes or variables.
                        for (Tree member : node.getMembers()) if (member instanceof ClassTree) scan(member, qualified);
                        return null;
                    }
                }.scan(unit, null);
            }
        }
        Writer output = new OutputStreamWriter(System.out, StandardCharsets.UTF_8);
        output.write(json(Map.of("types", types, "diagnostics", diagnostics.getDiagnostics().stream().filter(d -> d.getKind() == Diagnostic.Kind.ERROR).map(Object::toString).toList())));
        output.flush();
    }
}
