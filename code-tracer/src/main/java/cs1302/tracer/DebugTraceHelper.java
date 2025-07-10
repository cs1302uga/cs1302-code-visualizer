package cs1302.tracer;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

import com.sun.jdi.AbsentInformationException;
import com.sun.jdi.BooleanValue;
import com.sun.jdi.Bootstrap;
import com.sun.jdi.ByteValue;
import com.sun.jdi.CharValue;
import com.sun.jdi.ClassType;
import com.sun.jdi.DoubleValue;
import com.sun.jdi.Field;
import com.sun.jdi.FloatValue;
import com.sun.jdi.IncompatibleThreadStateException;
import com.sun.jdi.IntegerValue;
import com.sun.jdi.Location;
import com.sun.jdi.LongValue;
import com.sun.jdi.Method;
import com.sun.jdi.ObjectReference;
import com.sun.jdi.PrimitiveValue;
import com.sun.jdi.ShortValue;
import com.sun.jdi.StackFrame;
import com.sun.jdi.ThreadReference;
import com.sun.jdi.Value;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.connect.IllegalConnectorArgumentsException;
import com.sun.jdi.connect.LaunchingConnector;
import com.sun.jdi.connect.VMStartException;
import com.sun.jdi.event.BreakpointEvent;
import com.sun.jdi.event.ClassPrepareEvent;
import com.sun.jdi.event.Event;
import com.sun.jdi.event.MethodExitEvent;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.request.ClassPrepareRequest;
import com.sun.jdi.request.MethodExitRequest;

import cs1302.tracer.CompilationHelper.CompilationResult;
import cs1302.tracer.DebugTraceHelper.ExecutionSnapshot.TraceValue;

public class DebugTraceHelper {
  public static record ExecutionSnapshot(List<List<Pair<String, ? extends TraceValue>>> stack,
      List<Pair<String, ? extends TraceValue>> statics, Map<Long, TraceValue.TraceObject> heap) {
    public static record Pair<L, R>(L l, R r) {
    }

    public static sealed interface TraceValue {
      public static TraceValue fromJdiValue(Value value) {
        return fromJdiValue(value, null);
      }

      public static TraceValue fromJdiValue(Value value, List<ObjectReference> outEncounteredReferences) {
        return switch (value) {
          case PrimitiveValue pv -> new TracePrimitive(switch (pv) {
            case BooleanValue bv -> bv.value();
            case ByteValue bv -> bv.value();
            case CharValue cv -> cv.value();
            case DoubleValue dv -> dv.value();
            case FloatValue fv -> fv.value();
            case IntegerValue iv -> iv.value();
            case LongValue lv -> lv.value();
            case ShortValue sv -> sv.value();
            default -> null;
          });
          case ObjectReference or -> {
            Optional.ofNullable(outEncounteredReferences).ifPresent(l -> l.add(or));
            yield new TraceReference(or.uniqueID());
          }
          case null -> null;
          default -> null;
        };
      }

      public static final record TraceReference(long uniqueId) implements TraceValue {
      }

      public static final record TracePrimitive(Object value) implements TraceValue {
      }

      public static final record TraceObject(Map<String, ? extends TraceValue> fields) implements TraceValue {
      }
    }
  }

  /**
   * @param compilationResult a properly filled CompilationResult (probably from a
   *                          call to CompilationHelper.compile())
   * @param breakPoints       the source line numbers that you want to take
   *                          snapshots at. if it contains the special value -1,
   *                          is null, or is empty, a snapshot will be taken at
   *                          the time the main method exits.
   * @return a mapping from line numbers to execution snapshots. if a snapshot was
   *         taken at the end of main (as described above), it is provided under
   *         the special key -1.
   */
  public static Map<Integer, ExecutionSnapshot> trace(CompilationResult compilationResult,
      Collection<Integer> breakPoints)
      throws IOException, IllegalConnectorArgumentsException, VMStartException, InterruptedException,
      IncompatibleThreadStateException, AbsentInformationException {
    boolean snapMainEnd = breakPoints == null || breakPoints.isEmpty() || breakPoints.contains(-1);
    Map<Integer, ExecutionSnapshot> snapshots = new HashMap<>();

    /*
     * Start debugging session for newly compiled code
     */
    LaunchingConnector launchingConnector = Bootstrap.virtualMachineManager().defaultConnector();
    Map<String, Connector.Argument> env = launchingConnector.defaultArguments();

    env.get("main").setValue(compilationResult.mainClass());
    env.get("options").setValue("-classpath " + compilationResult.classPath());
    VirtualMachine vm = launchingConnector.launch(env);

    // TODO the JVM will crash if output buffers (stdout/err) are filled, so we need
    // to empty them as they're populated during debugging

    // fire an event when exiting main
    {
      MethodExitRequest methodExitRequest = vm.eventRequestManager().createMethodExitRequest();
      methodExitRequest.addClassFilter(compilationResult.mainClass());
      methodExitRequest.enable();
    }

    for (String className : compilationResult.compiledClassNames()) {
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
            ClassType ct = (ClassType) cpe.referenceType();
            if (compilationResult.compiledClassNames().contains(ct.name())) {
              if (breakPoints != null) {
                for (int breakLine : breakPoints) {
                  List<Location> locations = ct.locationsOfLine(breakLine);
                  if (locations.isEmpty()) {
                    break;
                  }
                  vm.eventRequestManager().createBreakpointRequest(locations.get(0)).enable();
                }
              }
              loadedClasses.add(ct);
            }
          }
          case BreakpointEvent bpe -> {
            Location breakLocation = bpe.location();
            if (compilationResult.compiledClassNames().contains(breakLocation.declaringType().name())) {
              snapshots.put(breakLocation.lineNumber(), snapshotTheWorld(bpe.thread(), loadedClasses));
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

            if (isMain && snapMainEnd) {
              snapshots.put(-1, snapshotTheWorld(mee.thread(), loadedClasses));
            }
          }
          case VMDeathEvent vde -> {
            endEventLoop = true;
            break;
          }
          default -> {
          }
        }

        vm.resume();
      }
    }

    return snapshots;
  }

  /**
   * @param compilationResult a properly filled CompilationResult (probably from a
   *                          call to CompilationHelper.compile())
   * @return an execution snapshot taken at the end of the main method
   */
  public static ExecutionSnapshot trace(CompilationResult compilationResult)
      throws IOException, IllegalConnectorArgumentsException, VMStartException, InterruptedException,
      IncompatibleThreadStateException, AbsentInformationException {
    return trace(compilationResult, null).get(-1);
  }

  private static ExecutionSnapshot snapshotTheWorld(ThreadReference worldThread, Iterable<ClassType> loadedClasses)
      throws IncompatibleThreadStateException, AbsentInformationException {

    List<ObjectReference> heapReferencesToWalk = new ArrayList<>();

    // collect stack values
    List<List<ExecutionSnapshot.Pair<String, ? extends TraceValue>>> stack = new ArrayList<>();
    for (StackFrame frame : worldThread.frames()) {
      stack.add(frame.visibleVariables().stream()
          .map(v -> new ExecutionSnapshot.Pair<>(v.name(),
              TraceValue.fromJdiValue(frame.getValue(v), heapReferencesToWalk)))
          .collect(Collectors.toList()));
    }

    // collect static values
    List<ExecutionSnapshot.Pair<String, ? extends TraceValue>> statics = new ArrayList<>();
    for (ClassType loadedClass : loadedClasses) {
      statics.addAll(loadedClass.allFields().stream()
          .filter(f -> f.isStatic())
          .map(f -> new ExecutionSnapshot.Pair<>(String.join(".", loadedClass.name(), f.name()),
              TraceValue.fromJdiValue(loadedClass.getValue(f), heapReferencesToWalk)))
          .toList());
    }

    // collect heap values
    Map<Long, TraceValue.TraceObject> heap = new HashMap<>();
    while (!heapReferencesToWalk.isEmpty()) {
      ObjectReference workingObject = heapReferencesToWalk.removeFirst();
      if (heap.containsKey(workingObject.uniqueID())) {
        continue;
      }

      Map<String, TraceValue> namedFields = new HashMap<>();
      List<Field> workingObjectFields = workingObject.referenceType().allFields().stream().filter(f -> !f.isStatic())
          .toList();
      for (Field workingObjectField : workingObjectFields) {
        Value fieldValue = workingObject.getValue(workingObjectField);
        namedFields.put(workingObjectField.name(), TraceValue.fromJdiValue(fieldValue, heapReferencesToWalk));
      }

      heap.put(workingObject.uniqueID(), new TraceValue.TraceObject(namedFields));
    }

    return new ExecutionSnapshot(stack, statics, heap);
  }
}
