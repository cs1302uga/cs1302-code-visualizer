# Example 21: Instance Method Execution & Active Call Stack Frames

This example demonstrates pausing execution in the middle of an instance method call (`checking.transferTo(savings, 150.00)`), capturing multiple active stack frames and the implicit `this` reference.

## Concepts Illustrated

- **Multi-Frame Call Stack**: The `main` method frame is waiting at the invocation site while the `transferTo` instance method frame is actively executing.
- **`this` Parameter Binding**: Within `transferTo`, the receiver object (`checking`, Alice's account) is bound to `this`, while `target` refers to Bob's `savings` account.
- **Local Method Variables**: Method-level calculations (`fee`, `totalDeduction`) exist within the method's stack frame alongside object references.

## Files

- `cs1302/banking/BankAccount.java`: Bank account class defining `deposit` and `transferTo`.
- `cs1302/banking/Driver.java`: Driver creating accounts and executing a funds transfer.
