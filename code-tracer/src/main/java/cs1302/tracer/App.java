package cs1302.tracer;

import org.apache.commons.cli.Options;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.apache.commons.cli.ParseException;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Optional;
import java.util.Queue;
import java.util.Scanner;
import java.util.Set;
import java.util.function.Predicate;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import javax.tools.JavaFileObject.Kind;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.DefaultParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Option;

import com.github.javaparser.ParseProblemException;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.BodyDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.sun.jdi.AbsentInformationException;
import com.sun.jdi.ArrayReference;
import com.sun.jdi.ArrayType;
import com.sun.jdi.Bootstrap;
import com.sun.jdi.ClassType;
import com.sun.jdi.Field;
import com.sun.jdi.IncompatibleThreadStateException;
import com.sun.jdi.Method;
import com.sun.jdi.ObjectReference;
import com.sun.jdi.PrimitiveValue;
import com.sun.jdi.StackFrame;
import com.sun.jdi.ThreadReference;
import com.sun.jdi.Value;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.connect.LaunchingConnector;
import com.sun.jdi.event.ClassPrepareEvent;
import com.sun.jdi.event.Event;
import com.sun.jdi.event.MethodExitEvent;
import com.sun.jdi.event.StepEvent;
import com.sun.jdi.event.ThreadStartEvent;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.request.ClassPrepareRequest;
import com.sun.jdi.request.MethodEntryRequest;
import com.sun.jdi.request.MethodExitRequest;
import com.sun.jdi.request.StepRequest;
import com.sun.jdi.request.ThreadStartRequest;

/**
 * Hello world!
 */
public class App {
  public static void main(String[] args) throws Exception {
    CommandLine opts = App.getOptions(args).orElseThrow();

    /*
     * Read Java source code input to a string (and parse it for later)
     */
    String source;
    if (opts.getOptionValue("input") != null) {
      source = Files.readString(Paths.get(opts.getOptionValue("input")));
    } else {
      StringBuilder sb = new StringBuilder();
      try (Scanner scan = new Scanner(System.in)) {
        while (scan.hasNextLine()) {
          sb.append(scan.nextLine()).append('\n');
        }
      }
      source = sb.toString();
    }

    CompilationUnit sourceCompilationUnit = StaticJavaParser.parse(source);

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
    Files.writeString(inputSourceFile, source);

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

    /*
     * Start debugging session for newly compiled code
     */
    MethodDeclaration mainMethod = findMain(sourceCompilationUnit);

    LaunchingConnector launchingConnector = Bootstrap.virtualMachineManager().defaultConnector();
    Map<String, Connector.Argument> env = launchingConnector.defaultArguments();

    env.get("main").setValue(String.join(".", getAncestorFqn(sourceCompilationUnit, mainMethod)));
    env.get("options").setValue("-classpath " + workingDir.toString());
    VirtualMachine vm = launchingConnector.launch(env);

    // the JVM will crash if output buffers (stdout/err) are filled, so we start
    // some threads to empty them as they're populated. TODO we should probably do
    // something more interesting with the program's output.
    Thread.ofVirtual().start(() -> {
      InputStream stdout = vm.process().getInputStream();
      while (true) {
        try {
          while (stdout.available() > 0) {
            try {
              Thread.sleep(100);
            } catch (InterruptedException e) {
            }
            stdout.readAllBytes();
          }
        } catch (IOException e) {

        }
      }
    });

    Thread.ofVirtual().start(() -> {
      InputStream stderr = vm.process().getErrorStream();
      while (true) {
        try {
          while (stderr.available() > 0) {
            try {
              Thread.sleep(100);
            } catch (InterruptedException e) {
            }
            stderr.readAllBytes();
          }
        } catch (IOException e) {

        }
      }
    });

    // fire an event when exiting main
    {
      MethodExitRequest methodExitRequest = vm.eventRequestManager().createMethodExitRequest();
      methodExitRequest.addClassFilter(String.join(".", getAncestorFqn(sourceCompilationUnit, mainMethod)));
      methodExitRequest.enable();
    }

    for (String className : compiledClassNames) {
      // fire an event each time one of our classes is prepared, mostly as a
      // springboard for setting up further eventrequests
      ClassPrepareRequest classPrepareRequest = vm.eventRequestManager().createClassPrepareRequest();
      classPrepareRequest.addClassFilter(className);
      classPrepareRequest.enable();
    }

    List<ClassType> loadedClasses = new ArrayList<>();

    boolean endEventLoop = false;
    while (!endEventLoop) {
      for (Event event : vm.eventQueue().remove()) {
        switch (event) {
          case ClassPrepareEvent cpe -> {
            System.out.println("CPE for " + cpe.referenceType());
            ClassType ct = (ClassType) cpe.referenceType();
            if (compiledClassNames.contains(ct.name())) {
              loadedClasses.add(ct);
              // NOTE this requests a step given that we're already at a breakpoint, I think.
              // we want this to create breakpoints.
              //StepRequest sr = vm.eventRequestManager().createStepRequest(cpe.thread(),
              //    StepRequest.STEP_LINE,
              //    StepRequest.STEP_OVER);
              //sr.addClassFilter(ct.name());
              //sr.enable();
            }
          }
          case MethodExitEvent mee -> {
            Method method = mee.method();
            // this is the JNI signature for a method with one string array parameter that
            // returns void. for details, see
            // https://docs.oracle.com/javase/8/docs/technotes/guides/jni/spec/types.html#type_signatures
            String mainJniSignature = "([Ljava/lang/String;)V";
            boolean isMain = method.isPublic() && method.isStatic() && method.name().equals("main")
                && method.signature().equals(mainJniSignature);

            if (isMain) {
              System.out.println("Main exited!");
              snapshotTheWorld(mee.thread(), loadedClasses);
            }
          }
          case VMDeathEvent vde -> {
            System.out.println(vde);
            endEventLoop = true;
            break;
          }
          default -> {
            System.out.println(event);
          }
        }

        vm.resume();
      }
    }
  }

  public static void snapshotTheWorld(ThreadReference worldThread, List<ClassType> loadedClasses)
      throws IncompatibleThreadStateException, AbsentInformationException {

    Queue<ObjectReference> heapReferences = new LinkedList<>();

    System.err.println("Stack frames:");
    for (StackFrame frame : worldThread.frames()) {
      frame.visibleVariables().stream().forEachOrdered(lv -> {
        switch (frame.getValue(lv)) {
          case PrimitiveValue pv -> System.out.println(lv + ": " + pv);
          case ObjectReference or -> {
            System.out.println(lv + ": UID" + or.uniqueID());
            heapReferences.add(or);
          }
          case null -> System.out.println(lv + ": null");
          default -> System.out.println(lv);
        }
      });
    }

    System.err.println("Heap:");
    Set<Value> heapSeen = new HashSet<>();
    for (ObjectReference heapReference : heapReferences) {
      walkHeapFromRootObject(heapReference, heapSeen);
    }

    System.err.println("Static fields:");
    for (ClassType loadedClass : loadedClasses) {
      loadedClass.allFields().stream()
          .filter(f -> f.isStatic())
          .forEachOrdered(f -> System.err.println(f.hashCode() + ": " + f.toString()));
    }
  }

  public static void walkHeapFromRootObject(ObjectReference root, Set<Value> seen) {
    seen.add(root);
    if (root instanceof ArrayReference) {
      ArrayReference ar = (ArrayReference)root;
      System.err.println("LIST" + ar.getValues());
      return;
    } else {
      System.err.println("INSTANCE" + root);
    }

    ClassType ct = (ClassType)root.referenceType();
    for (Field f : ct.fields()) {
      switch (root.getValue(f)) {
        case PrimitiveValue pv -> System.err.println("PRIM" + f + pv);
        case ObjectReference or -> walkHeapFromRootObject(or, seen);
        case null -> System.err.println("null");
        default -> {}
      };
    }
  }

  public static Path createWorkingDir() throws IOException {
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

  public static List<String> getAncestorFqn(CompilationUnit cu, BodyDeclaration<?> node) {
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

    cu.getPackageDeclaration().ifPresent(p -> {
      ancestorNames.addAll(0, Arrays.asList(p.getNameAsString().split("\\.")));
    });

    return ancestorNames;
  }

  public static String findTopLevelClassBinaryName(CompilationUnit cu) {
    List<Node> topLevelNodes = new ArrayList<>();
    new Node.DirectChildrenIterator(cu).forEachRemaining(topLevelNodes::add);
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
    List<String> fqn = getAncestorFqn(cu, fileClass);
    fqn.add(fileClass.getNameAsString());

    return String.join(".", fqn);
  }

  /**
   * Parse the provided Java source code and locate the main method.
   *
   * @param javaSource the Java source code
   * @return the parsed method declaration
   * @throws ParseProblemException    if the source code has parser errors
   * @throws IllegalArgumentException if the source code doesn't have exactly one
   *                                  main method
   */
  public static MethodDeclaration findMain(CompilationUnit cu) {
    Predicate<MethodDeclaration> isMain = m -> {
      boolean isNamedMain = m.getNameAsString().equals("main");
      boolean hasVoidReturn = m.getType().isVoidType();
      boolean hasStringArrArg = m.getParameterByType(String[].class).isPresent();
      boolean hasStringVarargsArg = m.getParameterByType(String.class).map(p -> p.isVarArgs()).orElse(false);
      boolean hasOneArg = m.getParameters().size() == 1;
      return m.isPublic() && m.isStatic() && hasVoidReturn && isNamedMain && (hasStringArrArg ^ hasStringVarargsArg)
          && hasOneArg;
    };

    List<MethodDeclaration> mainMethods = cu.findAll(MethodDeclaration.class, isMain);

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

  /**
   * Parse command-line options into a CommandLine instance. If parsing fails or
   * the help option is encountered, a usage message is printed to stdout and the
   * empty value is returned.
   *
   * @param args command-line arguments, usually provided directly from main
   * @return a constructed CommandLine object, or empty if one could not be
   *         created
   */
  public static Optional<CommandLine> getOptions(String[] args) {
    Options options = new Options();

    options.addOption(
        Option.builder("i")
            .longOpt("input")
            .desc("input path to Java source file (defaults to stdin if omitted)")
            .required(false)
            .hasArg()
            .build());
    options.addOption(
        Option.builder("o")
            .longOpt("output")
            .desc("output path (defaults to stdout if omitted)")
            .required(false)
            .hasArg()
            .build());
    options.addOption(
        Option.builder("h")
            .longOpt("help")
            .desc("print this help message")
            .required(false)
            .build());

    CommandLineParser parser = new DefaultParser();

    try {
      CommandLine cmd = parser.parse(options, args);
      if (cmd.hasOption("help")) {
        new HelpFormatter().printHelp("code-tracer", options);

        return Optional.empty();
      }

      return Optional.of(cmd);
    } catch (ParseException e) {
      System.err.println(e.getMessage());
      new HelpFormatter().printHelp("code-tracer", options);

      return Optional.empty();
    }
  }
}
