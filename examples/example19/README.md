# Example 19: Custom Generic Classes & Type Resolution

This example demonstrates custom generic classes with parameterized types and Tracer's AST static type resolution (Chapter 10: Generics).

## Concepts Illustrated

- **Custom Generic Classes**: Parameterized generic class `Pair<K, V>`.
- **Type Arguments**: Instantiating `Pair<String, Integer>` and `Pair<Integer, Boolean>`.
- **Reified Metadata**: Static AST type extraction mapping generic arguments into heap metadata.

## Files

- `cs1302/generics/Pair.java`: Generic pair implementation.
- `cs1302/generics/Driver.java`: Driver instantiating multiple specialized generic pairs.
