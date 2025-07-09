package cs1302.tracer;

import org.apache.commons.cli.Options;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;

import org.apache.commons.cli.ParseException;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Optional;
import java.util.Queue;
import java.util.Scanner;
import java.util.Set;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.DefaultParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Option;

import com.sun.jdi.AbsentInformationException;
import com.sun.jdi.ArrayReference;
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
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.request.ClassPrepareRequest;
import com.sun.jdi.request.MethodExitRequest;

import cs1302.tracer.CompilationHelper.CompilationResult;

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

    CompilationResult c = CompilationHelper.compile(source);

    /*
     * Start debugging session for newly compiled code
     */
    LaunchingConnector launchingConnector = Bootstrap.virtualMachineManager().defaultConnector();
    Map<String, Connector.Argument> env = launchingConnector.defaultArguments();

    env.get("main").setValue(c.mainClass());
    env.get("options").setValue("-classpath " + c.classPath());
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
      methodExitRequest.addClassFilter(c.mainClass());
      methodExitRequest.enable();
    }

    for (String className : c.compiledClassNames()) {
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
            if (c.compiledClassNames().contains(ct.name())) {
              loadedClasses.add(ct);
              // NOTE this requests a step given that we're already at a breakpoint, I think.
              // we want this to create breakpoints.
              // StepRequest sr = vm.eventRequestManager().createStepRequest(cpe.thread(),
              // StepRequest.STEP_LINE,
              // StepRequest.STEP_OVER);
              // sr.addClassFilter(ct.name());
              // sr.enable();
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
      ArrayReference ar = (ArrayReference) root;
      System.err.println("LIST" + ar.getValues());
      return;
    } else {
      System.err.println("INSTANCE" + root);
    }

    ClassType ct = (ClassType) root.referenceType();
    for (Field f : ct.fields()) {
      switch (root.getValue(f)) {
        case PrimitiveValue pv -> System.err.println("PRIM" + f + pv);
        case ObjectReference or -> walkHeapFromRootObject(or, seen);
        case null -> System.err.println("null");
        default -> {
        }
      }
      ;
    }
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
