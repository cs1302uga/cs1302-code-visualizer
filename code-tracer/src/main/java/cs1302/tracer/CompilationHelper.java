package cs1302.tracer;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import javax.tools.JavaFileObject.Kind;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.BodyDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;

public class CompilationHelper {
  /**
   * @param classPath          root of the class path where compiled classes were
   *                           output
   * @param compiledClassNames binary names of the classes that were compiled
   * @param mainClass          binary name of the class that contains the main
   *                           method
   */
  public static record CompilationResult(Path classPath, Set<String> compiledClassNames, String mainClass) {
  }

  public static CompilationResult compile(String javaSource) throws IOException {
    /*
     * Parse source code so we can later identify the main method and top-level
     * class
     */
    CompilationUnit sourceCompilationUnit = StaticJavaParser.parse(javaSource);

    /*
     * Create a working directory tree for compilation
     */
    Path workingDir = createWorkingDir();
    String[] topLevelClassBinaryName = findTopLevelClassBinaryName(sourceCompilationUnit).split("\\.");

    Path inputSourceDirectory;
    if (topLevelClassBinaryName.length == 1) {
      inputSourceDirectory = workingDir;
    } else {
      inputSourceDirectory = Files.createDirectories(
          Paths.get(workingDir.toString(), Arrays.copyOf(topLevelClassBinaryName, topLevelClassBinaryName.length - 1)));
    }
    Path inputSourceFile = Paths.get(inputSourceDirectory.toString(),
        topLevelClassBinaryName[topLevelClassBinaryName.length - 1] + Kind.SOURCE.extension);
    Files.writeString(inputSourceFile, javaSource);

    /*
     * Compile Java source code
     */
    Set<String> compiledClassNames = new HashSet<String>();
    JavaCompiler javaCompiler = Objects.requireNonNull(ToolProvider.getSystemJavaCompiler(),
        "Could not get Java compiler");
    DiagnosticCollector<JavaFileObject> diagnosticCollector = new DiagnosticCollector<>();
    // this file manager is used to open source files from disk
    StandardJavaFileManager standardFileManager = javaCompiler.getStandardFileManager(diagnosticCollector, null, null);
    // this file manager is used when outputting class files to disk. it wraps the
    // standard file manager so that we can record what classes are compiled. this
    // is necessary for debugging later.
    JavaFileManager forwardingFileManager = new ForwardingJavaFileManager<StandardJavaFileManager>(
        javaCompiler.getStandardFileManager(diagnosticCollector, null, null)) {
      @Override
      public JavaFileObject getJavaFileForOutput(Location location, String className, Kind kind,
          FileObject sibling) throws IOException {
        compiledClassNames.add(className);
        return super.getJavaFileForOutput(location, className, kind, sibling);
      }
    };
    Iterable<? extends JavaFileObject> compilationUnit = standardFileManager.getJavaFileObjects(inputSourceFile);

    boolean compilationSuccess = javaCompiler
        .getTask(null, forwardingFileManager, diagnosticCollector, List.of("-g"), null, compilationUnit).call();

    if (!compilationSuccess) {
      StringBuilder message = new StringBuilder("Compilation of provided Java source code failed");
      List<?> diagnostics = diagnosticCollector.getDiagnostics();

      if (diagnostics.isEmpty()) {
        message.append('.');
      } else {
        message.append(" with the following messages:\n");
        message.append(
            diagnosticCollector.getDiagnostics().stream()
                .map(Object::toString)
                .collect(Collectors.joining("\n")));
      }

      throw new IllegalArgumentException(message.toString());
    }

    MethodDeclaration mainMethod = findMain(sourceCompilationUnit);
    String mainClass = String.join(".", getAncestorFqn(sourceCompilationUnit, mainMethod));

    return new CompilationResult(workingDir, compiledClassNames, mainClass);
  }

  private static Path createWorkingDir() throws IOException {
    Path workingDir = Files.createTempDirectory("code-tracer");
    Thread workingDirCleanupHook = new Thread(() -> {
      try (Stream<Path> paths = Files.walk(workingDir)) {
        paths.sorted(Comparator.reverseOrder()).map(Path::toFile).forEach(File::delete);
      } catch (IOException e) {
      }
    });
    Runtime.getRuntime().addShutdownHook(workingDirCleanupHook);
    return workingDir;
  }

  private static String findTopLevelClassBinaryName(CompilationUnit compilationUnit) {
    List<Node> topLevelNodes = new ArrayList<>();
    new Node.DirectChildrenIterator(compilationUnit).forEachRemaining(topLevelNodes::add);
    List<TypeDeclaration<?>> topLevelPublicDeclarations = topLevelNodes.stream()
        .filter(n -> n instanceof TypeDeclaration)
        .map(n -> (TypeDeclaration<?>) n)
        .filter(t -> t.isPublic())
        .collect(Collectors.toList());

    if (topLevelPublicDeclarations.size() != 1) {
      String lines = "[" + String.join(", ", topLevelPublicDeclarations.stream()
          .filter(m -> m.getBegin().isPresent())
          .map(m -> m.getBegin().get().line)
          .map(Object::toString)
          .toArray(String[]::new)) + "]";
      throw new IllegalArgumentException(String.format(
          "Java source code must have exactly one public top-level type declaration. Found %d such declarations on lines %s.",
          topLevelPublicDeclarations.size(), lines));
    }

    TypeDeclaration<?> fileClass = topLevelPublicDeclarations.get(0);
    List<String> fqn = getAncestorFqn(compilationUnit, fileClass);
    fqn.add(fileClass.getNameAsString());

    return String.join(".", fqn);
  }

  private static List<String> getAncestorFqn(CompilationUnit compilationUnit, BodyDeclaration<?> node) {
    Iterator<Node> parents = new Node.ParentsVisitor(node);
    List<String> ancestorNames = new LinkedList<>();
    while (parents.hasNext()) {
      Node parent = parents.next();
      if (!(parent instanceof TypeDeclaration<?>)) {
        continue;
      }
      TypeDeclaration<?> parentDecl = (TypeDeclaration<?>) parent;
      ancestorNames.add(0, parentDecl.getNameAsString());
    }

    compilationUnit.getPackageDeclaration().ifPresent(p -> {
      ancestorNames.addAll(0, Arrays.asList(p.getNameAsString().split("\\.")));
    });

    return ancestorNames;
  }

  /**
   * Parse the provided Java source code and locate the main method.
   *
   * @param compilationUnit parsed Java source code
   * @return the declaration node for the main method
   * @throws IllegalArgumentException if the source code doesn't have exactly one
   *                                  main method
   */
  private static MethodDeclaration findMain(CompilationUnit compilationUnit) {
    Predicate<MethodDeclaration> isMain = m -> {
      boolean isNamedMain = m.getNameAsString().equals("main");
      boolean hasVoidReturn = m.getType().isVoidType();
      boolean hasStringArrArg = m.getParameterByType(String[].class).isPresent();
      boolean hasStringVarargsArg = m.getParameterByType(String.class).map(p -> p.isVarArgs()).orElse(false);
      boolean hasOneArg = m.getParameters().size() == 1;
      return m.isPublic() && m.isStatic() && hasVoidReturn && isNamedMain && (hasStringArrArg ^ hasStringVarargsArg)
          && hasOneArg;
    };

    List<MethodDeclaration> mainMethods = compilationUnit.findAll(MethodDeclaration.class, isMain);

    if (mainMethods.size() != 1) {
      String lines = "[" + String.join(", ", mainMethods.stream()
          .filter(m -> m.getBegin().isPresent())
          .map(m -> m.getBegin().get().line)
          .map(Object::toString)
          .toArray(String[]::new)) + "]";
      throw new IllegalArgumentException(
          String.format("Java source code must have exactly one main method. Found %d main methods on lines %s.",
              mainMethods.size(), lines));
    }

    return mainMethods.get(0);
  }
}
