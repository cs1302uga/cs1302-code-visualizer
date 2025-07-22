package cs1302.tracer.trace;

import java.util.*;
import com.sun.jdi.*;

public sealed interface TraceValue {

  public static sealed interface Primitive extends TraceValue {
    public static final record Boolean(boolean value) implements Primitive {
    }

    public static final record Byte(byte value) implements Primitive {
    }

    public static final record Character(char value) implements Primitive {
    }

    public static final record Short(short value) implements Primitive {
    }

    public static final record Integer(int value) implements Primitive {
    }

    public static final record Long(long value) implements Primitive {
    }

    public static final record Float(float value) implements Primitive {
    }

    public static final record Double(double value) implements Primitive {
    }

    public static Primitive fromJdiPrimitive(PrimitiveValue primitiveValue) {
      return switch (primitiveValue) {
        case BooleanValue bv -> new Boolean(bv.value());
        case ByteValue bv -> new Byte(bv.value());
        case CharValue cv -> new Character(cv.value());
        case DoubleValue dv -> new Double(dv.value());
        case FloatValue fv -> new Float(fv.value());
        case IntegerValue iv -> new Integer(iv.value());
        case LongValue lv -> new Long(lv.value());
        case ShortValue sv -> new Short(sv.value());
        default -> throw new IllegalArgumentException("""
            Primitive value must be one of the following types:
            boolean, byte, char, double, float, integer, long, short""");
      };
    }

    public static Optional<Primitive> tryFromJdiValue(ThreadReference mainThread, Value value) {
      if (!(value instanceof ObjectReference) || !(value.type() instanceof ClassType)) {
        return Optional.empty();
      }

      ObjectReference objectReference = (ObjectReference) value;
      ClassType classType = (ClassType) objectReference.type();

      java.lang.String getterPrefix = switch (classType.signature()) {
        case "Ljava/lang/Boolean;" -> "boolean";
        case "Ljava/lang/Byte;" -> "byte";
        case "Ljava/lang/Character;" -> "char";
        case "Ljava/lang/Short;" -> "short";
        case "Ljava/lang/Integer;" -> "int";
        case "Ljava/lang/Long;" -> "long";
        case "Ljava/lang/Float;" -> "float";
        case "Ljava/lang/Double;" -> "double";
        default -> null;
      };

      if (getterPrefix == null) {
        // value is not a primitive wrapper
        return Optional.empty();
      }

      java.lang.String primitiveJniSignature = switch (getterPrefix) {
        case "boolean" -> "Z";
        case "byte" -> "B";
        case "char" -> "C";
        case "short" -> "S";
        case "int" -> "I";
        case "long" -> "J";
        case "float" -> "F";
        case "double" -> "D";
        default -> throw new IllegalStateException("Unreachable.");
      };

      Method getterMethod = classType.concreteMethodByName(getterPrefix + "Value", "()" + primitiveJniSignature);

      if (getterMethod == null) {
        throw new IllegalStateException(java.lang.String.format(
            "Expected JDI value with JNI signature %s to have a method named %s with JNI signature %s.",
            classType.signature(), getterPrefix + "Value", "()" + classType.signature()));
      }

      try {
        // this cast is safe because we've confirmed that the return type is a primitive
        // via the previous switch and the method signature we requested
        PrimitiveValue primitiveValue = (PrimitiveValue) objectReference.invokeMethod(mainThread, getterMethod,
            java.util.List.of(), 0);

        return Optional.of(Primitive.fromJdiPrimitive(primitiveValue));
      } catch (IllegalArgumentException | ClassNotLoadedException | InvalidTypeException | InvocationException e) {
        // these exceptions should be impossible to trigger since given the constraints
        // we established above.
        throw new IllegalStateException("The previous exception should not have been able to occur.", e);
      } catch (IncompatibleThreadStateException e) {
        // rethrow as an unchecked exception so we don't have to clutter siguatures up
        // the calling chain
        throw new IllegalArgumentException("Expected the passed thread to be suspended by an event.", e);
      }
    }
  }

  public static final record Reference(long uniqueId) implements TraceValue {
  }

  public static final record Null() implements TraceValue {
  }

  public static final record Object(java.lang.String classFqn, java.util.Collection<ExecutionSnapshot.Field> fields)
      implements TraceValue {
  }

  public static final record String(java.lang.String value) implements TraceValue {
  }

  public static final record Map(java.util.Map<? extends TraceValue, ? extends TraceValue> value)
      implements TraceValue {
    public static Optional<Map> tryFromJdiObjectReference(ThreadReference mainThread, ObjectReference or,
        Optional<java.util.List<ObjectReference>> outEncounteredReferences) {
      ClassType ct = (ClassType) or.referenceType();
      VirtualMachine vm = or.virtualMachine();

      boolean isMap = !Collections.disjoint(ct.allInterfaces(), vm.classesByName("java.util.Map"));
      if (!isMap) {
        return Optional.empty();
      }

      try {
        Method entrySet = ct.concreteMethodByName("entrySet", "()Ljava/util/Set;");
        ObjectReference entries = (ObjectReference) or.invokeMethod(mainThread, entrySet, java.util.List.of(), 0);
        ClassType entriesCt = (ClassType) entries.referenceType();
        Method entriesToArray = entriesCt.concreteMethodByName("toArray", "()[Ljava/lang/Object;");
        ArrayReference ar = (ArrayReference) entries.invokeMethod(mainThread, entriesToArray, java.util.List.of(),
            0);
        java.util.Map<TraceValue, TraceValue> map = new HashMap<>();
        for (int i = 0; i < ar.length(); i++) {
          ObjectReference entry = (ObjectReference) ar.getValue(i);
          ClassType entryCt = (ClassType) entry.referenceType();
          Method entryGetKey = entryCt.concreteMethodByName("getKey", "()Ljava/lang/Object;");
          ObjectReference entryKey = (ObjectReference) entry.invokeMethod(mainThread, entryGetKey,
              java.util.List.of(),
              0);
          Method entryGetValue = entryCt.concreteMethodByName("getValue", "()Ljava/lang/Object;");
          ObjectReference entryValue = (ObjectReference) entry.invokeMethod(mainThread, entryGetValue,
              java.util.List.of(), 0);
          outEncounteredReferences.ifPresent(l -> l.add(entryKey));
          outEncounteredReferences.ifPresent(l -> l.add(entryValue));
          map.put(new Reference(entryKey.uniqueID()), new Reference(entryValue.uniqueID()));
        }
        return Optional.of(new Map(map));
      } catch (IllegalArgumentException | ClassNotLoadedException | InvalidTypeException e) {
        throw new IllegalStateException("The previous exception should not have been able to occur.", e);
      } catch (InvocationException e) {
        // the map object threw an exception while we were examining its state, so we
        // can't parse it
        return Optional.empty();
      } catch (IncompatibleThreadStateException e) {
        // rethrow as an unchecked exception so we don't have to clutter siguatures up
        // the calling chain
        throw new IllegalArgumentException("Expected the passed thread to be suspended by an event.", e);
      }
    }
  }

  public static final record Collection(java.util.Collection<? extends TraceValue> value) implements TraceValue {
  }

  public static final record List(java.util.List<? extends TraceValue> value) implements TraceValue {

  }

  private static TraceValue fromJdiValue(ThreadReference mainThread, Value value,
      Optional<java.util.List<ObjectReference>> outEncounteredReferences) {
    VirtualMachine vm = value.virtualMachine();

    return switch (value) {
      case null -> new Null();
      case PrimitiveValue pv -> Primitive.fromJdiPrimitive(pv);
      case ArrayReference ar -> new List(arrayReferenceToList(mainThread, ar, outEncounteredReferences));
      case StringReference sr -> new String(sr.value());
      case ObjectReference or -> {
        Optional<Primitive> maybeWrappedPrimitive = Primitive.tryFromJdiValue(mainThread, value);
        if (maybeWrappedPrimitive.isPresent()) {
          outEncounteredReferences.ifPresent(l -> l.add(or));
          yield maybeWrappedPrimitive.get();
        }

        // handle composite terminating objects (lists, collections, maps)
        if (or.referenceType() instanceof ClassType) {
          // wrap up collections and lists
          ClassType ct = (ClassType) or.referenceType();
          boolean isCollection = !Collections.disjoint(ct.allInterfaces(),
              vm.classesByName("java.util.Collection"));
          if (isCollection) {
            try {
              Method toArray = ct.concreteMethodByName("toArray", "()[Ljava/lang/Object;");
              ArrayReference ar = (ArrayReference) or.invokeMethod(mainThread, toArray, java.util.List.of(),
                  0);
              boolean isList = !Collections.disjoint(ct.allInterfaces(), vm.classesByName("java.util.List"));
              java.util.List<TraceValue> traceArray = arrayReferenceToList(mainThread, ar,
                  outEncounteredReferences);
              if (isList) {
                yield new List(traceArray);
              } else {
                yield new Collection(traceArray);
              }
            } catch (IllegalArgumentException | ClassNotLoadedException | InvalidTypeException e) {
              throw new IllegalStateException("The previous exception should not have been able to occur.", e);
            } catch (InvocationException e) {
              // the collection object threw an exception while we were examining its state,
              // so we
              // can't parse it
            } catch (IncompatibleThreadStateException e) {
              // rethrow as an unchecked exception so we don't have to clutter siguatures up
              // the calling chain
              throw new IllegalArgumentException("Expected the passed thread to be suspended by an event.", e);
            }
          } else {
            Optional<Map> maybeMap = Map.tryFromJdiObjectReference(mainThread, or, outEncounteredReferences);
            if (maybeMap.isPresent()) {
              yield maybeMap.get();
            }
          }
        }

        // not a terminating object, fall back to simply listing object fields
        java.util.Collection<ExecutionSnapshot.Field> objectSnapshotFields = new ArrayList<>();
        java.util.List<Field> objectJdiFields = or.referenceType().allFields().stream()
            .filter(f -> !f.isStatic())
            .toList();
        for (Field objectField : objectJdiFields) {
          Value fieldValue = or.getValue(objectField);
          switch (fieldValue) {
            case null ->
              objectSnapshotFields.add(new ExecutionSnapshot.Field(objectField.name(), new Null()));
            case PrimitiveValue pf ->
              objectSnapshotFields
                  .add(new ExecutionSnapshot.Field(objectField.name(), Primitive.fromJdiPrimitive(pf)));
            case ObjectReference of -> {
              objectSnapshotFields.add(
                  new ExecutionSnapshot.Field(objectField.name(), new Reference(of.uniqueID())));
              outEncounteredReferences.ifPresent(l -> l.add(of));
            }
            default -> {
            }
          }
        }

        yield new Object(or.referenceType().name(), objectSnapshotFields);
      }
      default ->
        throw new IllegalArgumentException("Couldn't figure out what this value is. This should be unreachable.");
    };
  }

  public static TraceValue fromJdiValue(VirtualMachine vm, ThreadReference mainThread, Value value,
      java.util.List<ObjectReference> outEncounteredReferences) {
    return fromJdiValue(mainThread, value, Optional.ofNullable(outEncounteredReferences));
  }

  public static TraceValue fromJdiValue(VirtualMachine vm, ThreadReference mainThread, Value value) {
    return fromJdiValue(mainThread, value, Optional.empty());
  }

  private static java.util.List<TraceValue> arrayReferenceToList(ThreadReference mainThread,
      ArrayReference arrayReference,
      Optional<java.util.List<ObjectReference>> outEncounteredReferences) {
    java.util.List<TraceValue> tvs = new ArrayList<>(arrayReference.length());

    for (int i = 0; i < arrayReference.length(); i++) {
      tvs.add(fromJdiValue(mainThread, arrayReference.getValue(i), outEncounteredReferences));
    }

    return tvs;
  }
}
