package cs1302.tracer;

import org.apache.commons.cli.Options;

import org.apache.commons.cli.ParseException;
import org.fusesource.jansi.Ansi;
import org.fusesource.jansi.AnsiConsole;

import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Collection;
import java.util.Map;
import java.util.Optional;
import java.util.Scanner;
import java.util.stream.Stream;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.DefaultParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Option;

import cs1302.tracer.CompilationHelper.CompilationResult;
import cs1302.tracer.trace.DebugTraceHelper;
import cs1302.tracer.trace.ExecutionSnapshot;
import cs1302.tracer.serialize.PyTutorSerializer;

/**
 * Hello world!
 */
public class App {
  public static void main(String[] args) throws Exception {
    CommandLine opts = App.getOptions(args).orElseThrow();

    // read java source code input to a string (and parse it for later)
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

    // compile the source code
    CompilationResult c = CompilationHelper.compile(source);

    // and then debug it
    if (opts.hasOption("list-available-breakpoints")) {
      Collection<Integer> availableBreakpoints = DebugTraceHelper.getValidBreakpointLines(c);
      String[] sourceLines = source.split("\n");
      int digitLength = ((int) Math.log10(sourceLines.length)) + 1;
      StringBuilder annotatedSource = new StringBuilder();
      AnsiConsole.systemInstall();
      for (int i = 0; i < sourceLines.length; i++) {
        if (availableBreakpoints.contains(i + 1)) {
          annotatedSource.append(Ansi.ansi().fgGreen().a(String.format("b %" + digitLength + "d | ", i + 1)));
        } else {
          annotatedSource.append(String.format("  %" + digitLength + "d | ", i + 1));
        }
        annotatedSource.append(sourceLines[i]);
        annotatedSource.append(Ansi.ansi().reset());
        if (i < sourceLines.length - 1) {
          annotatedSource.append('\n');
        }
      }
      AnsiConsole.systemUninstall();
      System.out.println(annotatedSource.toString());
    } else {
      String[] breakpoints = opts.getOptionValues("breakpoint");
      Map<Integer, ExecutionSnapshot> snapshot = switch (breakpoints) {
        case null -> Map.of(-1, DebugTraceHelper.trace(c));
        default -> DebugTraceHelper.trace(c, Stream.of(breakpoints).map(Integer::parseInt).toList());
      };

      for (ExecutionSnapshot s : snapshot.values()) {
        System.out.println(PyTutorSerializer.serialize(source, s));
      }
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

    // TODO add an option for restricting which classes/objects have their full set
    // of fields dumped vs just a class fqn. would help declutter snapshots
    // containing java builtins like scanner, stringbuilder, etc

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
        Option.builder("b")
            .longOpt("breakpoint")
            .desc(
                """
                    breakpoint at which to take a snapshot. the snapshot taken will represent the
                    state of memory immediately before this line is executed. multiple instances of
                    this option can be provided. if none are provided, the default behavior is to
                    take one snapshot at the end of the program's main method.""")
            .required(false)
            .hasArg()
            .build());
    options.addOption(
        Option.builder("l")
            .longOpt("list-available-breakpoints")
            .desc("instead of running a trace, list the breakpoints available in provided source file")
            .required(false)
            .build());
    options.addOption(
        Option.builder("h")
            .longOpt("help")
            .desc("print this help message and then exit")
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
