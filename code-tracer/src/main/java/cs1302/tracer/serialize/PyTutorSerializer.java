package cs1302.tracer.serialize;

import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

import org.apache.commons.text.StringEscapeUtils;

import cs1302.tracer.trace.ExecutionSnapshot;
import cs1302.tracer.trace.ExecutionSnapshot.StackSnapshot;
import cs1302.tracer.trace.TraceValue;

public class PyTutorSerializer {
  public static String serialize(String javaSource, ExecutionSnapshot snapshot) {
    String currentMethod = snapshot.stack().getLast().methodName();
    long currentLine = snapshot.stack().getLast().methodLine();

    String serializedStatics = snapshot.statics().stream()
        .map(f -> String.format("\"%s\": %s", StringEscapeUtils.escapeJson(f.identifier()),
            serializeTraceValue(f.value())))
        .collect(Collectors.joining(", ", "{", "}"));

    String orderedStatics = snapshot.statics().stream()
        .map(s -> String.format("\"%s\"", StringEscapeUtils.escapeJson(s.identifier())))
        .collect(Collectors.joining(", ", "[", "]"));

    String serializedHeap = snapshot.heap().entrySet().stream()
        .map(e -> String.format("\"%d\": %s", e.getKey(), serializeTraceValue(e.getValue())))
        .collect(Collectors.joining(", ", "{", "}"));

    List<String> encodedStacks = new ArrayList<>();
    for (int i = 0; i < snapshot.stack().size(); i++) {
      encodedStacks.add(serializeStackSnapshot(snapshot.stack().get(i), i));
    }

    String serializedStackToRender = encodedStacks.stream().collect(Collectors.joining(", ", "[", "]"));

    return String.format("""
        {
          "code": "%s",
          "stdin": "",
          "trace": [{
            "stdout": "",
            "event": "step_line",
            "func_name": "%s",
            "line": %d,
            "stack_to_render": %s,
            "globals": %s,
            "ordered_globals": %s,
            "heap": %s
          }],
          "userlog": ""
        }""",
        StringEscapeUtils.escapeJson(javaSource),
        currentMethod,
        currentLine,
        serializedStackToRender,
        serializedStatics,
        orderedStatics,
        serializedHeap);
  }

  private static String serializeStackSnapshot(StackSnapshot stackSnapshot, int uniqueFrameId) {
    return String.format("""
        {
          "func_name": "%s:%d",
          "encoded_locals": %s,
          "ordered_varnames": %s,
          "parent_frame_id_list": [],
          "is_highlighted": true,
          "is_zombie": false,
          "is_parent": false,
          "unique_hash": "%d",
          "frame_id": %d
        }
        """, stackSnapshot.methodName(), stackSnapshot.methodLine(),
        stackSnapshot.visibleVariables().stream()
            .map(v -> String.format("\"%s\": %s", StringEscapeUtils.escapeJson(v.identifier()),
                serializeTraceValue(v.value())))
            .collect(Collectors.joining(", ", "{", "}")),
        stackSnapshot.visibleVariables().stream()
            .map(v -> String.format("\"%s\"", StringEscapeUtils.escapeJson(v.identifier())))
            .collect(Collectors.joining(", ", "[", "]")),
        uniqueFrameId,
        uniqueFrameId);
  }

  private static String serializeTraceValue(TraceValue value) {
    return switch (value) {
      case TraceValue.Primitive.Float f -> {
        if (f.value() == Float.POSITIVE_INFINITY) {
          yield "[\"SPECIAL_FLOAT\", \"Infinity\"]";
        } else if (f.value() == Float.NEGATIVE_INFINITY) {
          yield "[\"SPECIAL_FLOAT\", \"-Infinity\"]";
        } else if (Float.isNaN(f.value())) {
          yield "[\"SPECIAL_FLOAT\", \"NaN\"]";
        } else {
          yield f.valueToString();
        }
      }
      case TraceValue.Primitive.Double d -> {
        if (d.value() == Double.POSITIVE_INFINITY) {
          yield "[\"SPECIAL_FLOAT\", \"Infinity\"]";
        } else if (d.value() == Double.NEGATIVE_INFINITY) {
          yield "[\"SPECIAL_FLOAT\", \"-Infinity\"]";
        } else if (Double.isNaN(d.value())) {
          yield "[\"SPECIAL_FLOAT\", \"NaN\"]";
        } else {
          yield d.valueToString();
        }
      }
      case TraceValue.Primitive tp -> tp.valueToString();
      case TraceValue.Reference tr -> String.format("[\"REF\", %d]", tr.uniqueId());
      case TraceValue.Null n -> "null";
      case TraceValue.String s -> String.format("\"%s\"", StringEscapeUtils.escapeJson(s.value()));
      case TraceValue.List l -> {
        if (l.value().isEmpty()) {
          yield "[\"LIST\"]";
        } else {
          yield l.value().stream()
              .map(PyTutorSerializer::serializeTraceValue)
              .collect(Collectors.joining(", ", "[\"LIST\", ", "]"));
        }
      }
      case TraceValue.Collection c -> {
        if (c.value().isEmpty()) {
          yield "[\"SET\"]";
        } else {
          yield c.value().stream()
              .map(PyTutorSerializer::serializeTraceValue)
              .collect(Collectors.joining(", ", "[\"SET\", ", "]"));
        }
      }
      case TraceValue.Map m -> {
        if (m.value().isEmpty()) {
          yield "[\"DICT\"]";
        } else {
          yield m.value().entrySet().stream()
              .map(e -> String.format("[%s, %s]", serializeTraceValue(e.getKey()), serializeTraceValue(e.getValue())))
              .collect(Collectors.joining(", ", "[\"DICT\", ", "]"));
        }
      }
      case TraceValue.Object o -> {
        if (o.fields().isEmpty()) {
          yield String.format("[\"INSTANCE\", \"%s\"]", StringEscapeUtils.escapeJson(o.classFqn()));
        } else {
          yield o.fields().stream()
              .map(f -> String.format("[\"%s\", %s]", StringEscapeUtils.escapeJson(f.identifier()),
                  serializeTraceValue(f.value())))
              .collect(Collectors.joining(", ",
                  String.format("[\"INSTANCE\", \"%s\", ", StringEscapeUtils.escapeJson(o.classFqn())), "]"));
        }
      }
    };

  }
}
