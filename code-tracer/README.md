To compile:
```console
$ mvn clean compile assembly:single
```

To run:
```console
$ java -jar target/code-tracer-1.0-SNAPSHOT-jar-with-dependencies.jar -h
usage: code-tracer
 -b,--breakpoint <arg>   breakpoint at which to take a snapshot (defaults
                         to after main if none are provided)
 -h,--help               print this help message
 -i,--input <arg>        input path to Java source file (defaults to stdin
                         if omitted)
 -o,--output <arg>       output path (defaults to stdout if omitted)
```

References:
- https://wayne-adams.blogspot.com/2011/12/examining-variables-in-jdi.html
- https://itsallbinary.com/java-debug-interface-api-jdi-hello-world-example-programmatic-debugging-for-beginners/
