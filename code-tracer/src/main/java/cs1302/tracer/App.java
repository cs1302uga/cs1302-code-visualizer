package cs1302.tracer;

import org.apache.commons.cli.Options;

import org.apache.commons.cli.ParseException;

import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Optional;
import java.util.Scanner;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.DefaultParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Option;

import cs1302.tracer.CompilationHelper.CompilationResult;

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
    System.out.println(DebugTraceHelper.trace(c));
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
