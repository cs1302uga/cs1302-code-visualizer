package cs1302.tracer.trace;

import java.util.List;
import java.util.Map;

public record ExecutionSnapshot(List<StackSnapshot> stack,
    List<Field> statics, Map<Long, TraceValue> heap) {

  public static final record StackSnapshot(String methodName, long methodLine,
      List<Field> visibleVariables) {
  }

  public static record Field(String identifier, TraceValue value) {
  }
}
