# Examples Visualizer Gallery

This catalog links the Java sources for all 34 example suites in `examples/`. Rendered PNG files are generated locally and ignored by Git, so a clean checkout does not include them. For checked-in visual comparisons, see the [array orientation gallery](../docs/array-orientation/README.md).

After completing [contributor setup](../CONTRIBUTING.md), run `make test-examples` from the repository root to generate the images. For one suite, run `bash examples/example0/test.sh --no-rm-json --no-rm-image --no-open`, substituting its example number. See the [CLI guide](../docs/cli.md) for other rendering workflows.

---

## Table of Contents

- [Example 0: Record Instances & Constructors](#example-0-record-instances--constructors)
- [Example 1: Enums & Enum Constants](#example-1-enums--enum-constants)
- [Example 2: Complex Object Graphs & References](#example-2-complex-object-graphs--references)
- [Example 3: Array of References & Element Swapping](#example-3-array-of-references--element-swapping)
- [Example 4: Instance Methods & `this` References](#example-4-instance-methods--this-references)
- [Example 5: Recursion & Call Stack Frames](#example-5-recursion--call-stack-frames)
- [Example 6: Java Collections & Maps](#example-6-java-collections--maps)
- [Example 7: Loops & Breakpoint Accumulation](#example-7-loops--breakpoint-accumulation)
- [Example 8: Multi-Dimensional Arrays](#example-8-multi-dimensional-arrays)
- [Example 9: Functional Interfaces & Lambdas](#example-9-functional-interfaces--lambdas)
- [Example 10: Packages, Fully-Qualified Names & Custom Structs](#example-10-packages-fully-qualified-names--custom-structs)
- [Example 11: Control Flow & Conditionals](#example-11-control-flow--conditionals)
- [Example 12: Static Helper Methods & Multi-Frame Stack](#example-12-static-helper-methods--multi-frame-stack)
- [Example 13: Encapsulation & Mutator Methods](#example-13-encapsulation--mutator-methods)
- [Example 14: Java 8+ Streams & Method References](#example-14-java-8-streams--method-references)
- [Example 15: Reference Aliasing & In-Place Mutation](#example-15-reference-aliasing--in-place-mutation)
- [Example 16: Singly Linked Nodes & Pointer Chaining](#example-16-singly-linked-nodes--pointer-chaining)
- [Example 17: Inheritance & Subtype Polymorphism](#example-17-inheritance--subtype-polymorphism)
- [Example 18: Exception Handling & Stack Frame Unwinding](#example-18-exception-handling--stack-frame-unwinding)
- [Example 19: Custom Generic Classes & Type Resolution](#example-19-custom-generic-classes--type-resolution)
- [Example 20: Varargs & Synthesized Parameter Arrays](#example-20-varargs--synthesized-parameter-arrays)
- [Example 21: Unbuffered Standard Output & Progress Prompts](#example-21-unbuffered-standard-output--progress-prompts)
- [Example 22: Interleaved Standard Output & Standard Error Logging](#example-22-interleaved-standard-output--standard-error-logging)
- [Example 23: Uncaught Runtime Exceptions & Trace Termination](#example-23-uncaught-runtime-exceptions--trace-termination)
- [Example 24: Generic Integer Lists & Autoboxing](#example-24-generic-integer-lists--autoboxing)
- [Example 25: Instance Method Execution & Active Call Stack Frames](#example-25-instance-method-execution--active-call-stack-frames)
- [Example 26: Polymorphic Generics, Subclass Reification & Wildcards](#example-26-polymorphic-generics-subclass-reification--wildcards)
- [Example 27: Multi-Level Inheritance, Constructor Chaining & Polymorphism](#example-27-multi-level-inheritance-constructor-chaining--polymorphism)
- [Example 28: Empty Strings and Zero-Length Array Instances](#example-28-empty-strings-and-zero-length-array-instances)
- [Example 29: Numeric Primitive Wrapper Classes](#example-29-numeric-primitive-wrapper-classes)
- [Example 30: Non-Numeric Primitive Wrapper Classes](#example-30-non-numeric-primitive-wrapper-classes)
- [Example 31: java.awt.Color Objects and Transparency](#example-31-javaawtcolor-objects-and-transparency)
- [Example 32: Guest Standard Input with java.util.Scanner](#example-32-guest-standard-input-with-javautilscanner)
- [Example 33: Guest Standard Input with java.lang.IO](#example-33-guest-standard-input-with-javalangio)

---

## Example 0: Record Instances & Constructors

- **Source Code**: [Driver.java](example0/Driver.java)
- **Concepts**: Record construction, a `Person` instance on the heap, and its `name` and `age` components.

### Standard Visualizer

Generated image: `example0/Driver.java.png`.

### Raw JSON Pre-formatted Visualizer (`--visualizer=json-pre`)

Generated image: `example0/Driver.java.pre.png`.

---

## Example 1: Enums & Enum Constants

- **Source Code**: [Driver.java](example1/Driver.java)
- **Concepts**: Enum types (`Day`, `MealType`), enum constant references, method calls, and static fields.

### Default (With Enum Static Constants)

Generated image: `example1/Driver.java.png`.

### No Static Fields (`--no-enum-static-fields`)

Generated image: `example1/nostatic.png`.

---

## Example 2: Complex Object Graphs & References

- **Source Code**: [Driver.java](example2/Driver.java)
- **Concepts**: Multi-level pointer references linking `CourseOffering` to an instructor `Person` and a `Semester` enum.

Generated image: `example2/Driver.java.png`.

---

## Example 3: Array of References & Element Swapping

- **Source Code**: [Driver.java](example3/Driver.java)
- **Concepts**: Arrays of object references (`Person[]`), pass-by-value reference passing, manipulating array elements in helper methods.

Generated image: `example3/Driver.java.png`.

---

## Example 4: Instance Methods & `this` References

- **Source Code**: [Driver.java](example4/Driver.java)
- **Concepts**: Instance method dispatch, `this` receiver pointer binding inside method execution frames.

Generated image: `example4/Driver.java.png`.

---

## Example 5: Recursion & Call Stack Frames

- **Source Code**: [Driver.java](example5/Driver.java)
- **Concepts**: Recursive execution of `factorial(n)`, stack growth with independent local frames, unwinding at base cases.

Generated image: `example5/Driver.java.png`.

---

## Example 6: Java Collections & Maps

- **Source Code**: [Driver.java](example6/Driver.java)
- **Concepts**: Standard library `ArrayList` and `HashMap`, recovered generic types (`ArrayList<String>`, `HashMap<String, Integer>`).

Generated image: `example6/Driver.java.png`.

---

## Example 7: Loops & Breakpoint Accumulation

- **Source Code**: [Driver.java](example7/Driver.java)
- **Concepts**: Loop control variable iteration, multi-iteration accumulation with `--accumulate-breakpoints`.

Generated image: `example7/Driver.java.png`.

---

## Example 8: Multi-Dimensional Arrays

- **Source Code**: [Driver.java](example8/Driver.java)
- **Concepts**: Multi-dimensional 2D arrays (`int[][]`), jagged array referencing on the heap.

Generated image: `example8/Driver.java.png`.

---

## Example 9: Functional Interfaces & Lambdas

- **Source Code**: [Driver.java](example9/Driver.java)
- **Concepts**: Java 8+ lambda expressions, standard functional interfaces (`Function`, `Predicate`), functional type attributes, and heap object box representations for lambda expressions.

Generated image: `example9/Driver.java.png`.

---

## Example 10: Packages, Fully-Qualified Names & Custom Structs

- **Source Code**: [Driver.java](example10/cs1302/example/Driver.java)
- **Concepts**: Package hierarchies (`cs1302.example`), cross-package class instantiation (`Person`).

Generated image: `example10/cs1302/example/Driver.java.png`.

---

## Example 11: Control Flow & Conditionals

- **Source Code**: [Driver.java](example11/Driver.java)
- **Concepts**: Branching execution (`if` / `else if` / `else`), chronological execution snapshots via `-a`.

Generated image: `example11/Driver.java.png`.

---

## Example 12: Static Helper Methods & Multi-Frame Stack

- **Source Code**: [Driver.java](example12/cs1302/math/Driver.java)
- **Concepts**: Static method delegation across classes (`Calculator.add`), caller-callee stack frame rendering.

Generated image: `example12/cs1302/math/Driver.java.png`.

---

## Example 13: Encapsulation & Mutator Methods

- **Source Code**: [Driver.java](example13/cs1302/account/Driver.java)
- **Concepts**: Private field encapsulation (`balance`), mutating heap state through methods (`deposit`, `withdraw`).

Generated image: `example13/cs1302/account/Driver.java.png`.

---

## Example 14: Java 8+ Streams & Method References

- **Source Code**: [Stream.java](example14/Stream.java)
- **Concepts**: Stream pipelines (`filter`, `map`, `reduce`), method references (`Calculator::isPositive`, `Calculator::square`).

Generated image: `example14/Stream.java.png`.

---

## Example 15: Reference Aliasing & In-Place Mutation

- **Source Code**: [Driver.java](example15/cs1302/aliasing/Driver.java)
- **Concepts**: Reference aliasing (`Person friend = alice;`), shared heap object mutation, modern trace conversion.

Generated image: `example15/cs1302/aliasing/Driver.java.png`.

---

## Example 16: Singly Linked Nodes & Pointer Chaining

- **Source Code**: [Driver.java](example16/cs1302/nodes/Driver.java)
- **Concepts**: Recursive pointer chains (`Node`), pointer manipulation (`head = new Node("Alpha", head);`), list traversal.

Generated image: `example16/cs1302/nodes/Driver.java.png`.

---

## Example 17: Inheritance & Subtype Polymorphism

- **Source Code**: [Driver.java](example17/cs1302/shapes/Driver.java)
- **Concepts**: Class inheritance (`Shape`, `Circle`, `Rectangle`), superclass constructor delegation, polymorphic array dispatch.

Generated image: `example17/cs1302/shapes/Driver.java.png`.

---

## Example 18: Exception Handling & Stack Frame Unwinding

- **Source Code**: [Driver.java](example18/cs1302/exceptions/Driver.java)
- **Concepts**: Instantiating and throwing exceptions (`IllegalArgumentException`), call stack unwinding, `try-catch-finally` handling.

Generated image: `example18/cs1302/exceptions/Driver.java.png`.

---

## Example 19: Custom Generic Classes & Type Resolution

- **Source Code**: [Driver.java](example19/cs1302/generics/Driver.java)
- **Concepts**: Parameterized generic classes (`Pair<K, V>`), static AST generic type reification (`Pair<String, Integer>`, `Pair<Integer, Boolean>`), reified heap instance labels and field types.

Generated image: `example19/cs1302/generics/Driver.java.png`.

---

## Example 20: Varargs & Synthesized Parameter Arrays

- **Source Code**: [Driver.java](example20/cs1302/varargs/Driver.java)
- **Concepts**: Varargs parameters (`int... values`), automatic compiler array synthesis on the heap.

Generated image: `example20/cs1302/varargs/Driver.java.png`.

---

## Example 21: Unbuffered Standard Output & Progress Prompts

- **Source Code**: [Driver.java](example21/cs1302/io/stdout/Driver.java)
- **Concepts**: Unbuffered console output via `System.out.print`, iterative dot accumulator loops, step-by-step stdout preservation.

Generated image: `example21/cs1302/io/stdout/Driver.java.png`.

---

## Example 22: Interleaved Standard Output & Standard Error Logging

- **Source Code**: [Driver.java](example22/cs1302/io/stderr/Driver.java)
- **Concepts**: Dual stream capture (`System.out` vs `System.err`), validation warning logs, modern trace formatting (`--format=modern -a`).

Generated image: `example22/cs1302/io/stderr/Driver.java.png`.

---

## Example 23: Uncaught Runtime Exceptions & Trace Termination

- **Source Code**: [Driver.java](example23/cs1302/exceptions/uncaught/Driver.java)
- **Concepts**: Uncaught `ArithmeticException: / by zero`, execution crash snapshot, call stack preservation at exception site, JVM stderr capture.

Generated image: `example23/cs1302/exceptions/uncaught/Driver.java.png`.

---

## Example 24: Generic Integer Lists & Autoboxing

- **Source Code**: [Driver.java](example24/cs1302/list/Driver.java)
- **Concepts**: Interface vs implementation references (`List<Integer>`, `ArrayList<Integer>`), primitive autoboxing, in-place element mutation in helper methods.

Generated image: `example24/cs1302/list/Driver.java.png`.

---

## Example 25: Instance Method Execution & Active Call Stack Frames

- **Source Code**: [Driver.java](example25/cs1302/banking/Driver.java)
- **Concepts**: Instance method dispatch, multi-frame call stacks, implicit `this` reference binding, method parameter passing and local variables.

Generated image: `example25/cs1302/banking/Driver.java.png`.

---

## Example 26: Polymorphic Generics, Subclass Reification & Wildcards

- **Source Code**: [Driver.java](example26/cs1302/poly/Driver.java)
- **Concepts**: Interface pointing to multi-parameter generic subclass (`Container<String>` to `PairContainer<String, Object>`), non-generic subclass implementation (`IntContainer`), wildcard upper bound normalization (`List<? extends Number>`), and nested generic container structures (`List<List<String>>`).

Generated image: `example26/cs1302/poly/Driver.java.png`.

---

## Example 27: Multi-Level Inheritance, Constructor Chaining & Polymorphism

- **Source Code**: [Driver.java](example27/cs1302/inheritance/Driver.java)
- **Concepts**: Multi-level inheritance (`Person` -> `Employee` -> `Manager`), constructor chaining with `super(...)`, polymorphic reference variables, dynamic method dispatch, and safe downcasting.

Generated image: `example27/cs1302/inheritance/Driver.java.png`.

---

## Example 28: Empty Strings and Zero-Length Array Instances

- **Source Code**: [Driver.java](example28/cs1302/empty/Driver.java)
- **Concepts**: Empty String object (`""`) labeled `String (length 0)`, zero-length primitive array (`new int[0]`) labeled `int[] (length 0)`, zero-length reference array (`new String[0]`) labeled `String[] (length 0)`.

Generated image: `example28/cs1302/empty/Driver.java.png`.

---

## Example 29: Numeric Primitive Wrapper Classes

- **Source Code**: [Driver.java](example29/cs1302/wrappers/numeric/Driver.java)
- **Concepts**: Boxed numeric wrapper instances (`Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`) with field `value` and primitive type labels.

Generated image: `example29/cs1302/wrappers/numeric/Driver.java.png`.

---

## Example 30: Non-Numeric Primitive Wrapper Classes

- **Source Code**: [Driver.java](example30/cs1302/wrappers/other/Driver.java)
- **Concepts**: Boxed boolean and character wrapper instances (`Boolean`, `Character`) with field `value`, primitive type labels, and array of wrapper references.

Generated image: `example30/cs1302/wrappers/other/Driver.java.png`.

---

## Example 31: java.awt.Color Objects and Transparency

- **Source Code**: [Driver.java](example31/cs1302/color/Driver.java)
- **Concepts**: `java.awt.Color` instances on the heap with swatch previews, RGB and RGBA hex labels, and alpha transparency rendering.

Generated image: `example31/cs1302/color/Driver.java.png`.

---

## Example 32: Guest Standard Input with java.util.Scanner

- **Source Code**: [Driver.java](example32/cs1302/scanner/Driver.java)
- **Concepts**: Guest standard input streaming (`--stdin`), interactive token parsing via `java.util.Scanner`, and standard output trace capture.

Generated image: `example32/cs1302/scanner/Driver.java.png`.

---

## Example 33: Guest Standard Input with java.lang.IO

- **Source Code**: [Driver.java](example33/cs1302/io/Driver.java)
- **Concepts**: Java 25 simplified console I/O (`java.lang.IO.readln`, `java.lang.IO.println`), guest stdin ingestion, and standard output capture.

Generated image: `example33/cs1302/io/Driver.java.png`.
