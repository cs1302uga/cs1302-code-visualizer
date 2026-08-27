# Example 13: Encapsulation & Mutable State

This example demonstrates encapsulation using private instance variables, getters, and state-modifying mutator methods.

## Concepts Illustrated

- **Encapsulation**: Private fields `owner` and `balance` protected by methods.
- **Mutator Methods**: `deposit` and `withdraw` modifying heap object fields in place.
- **Return Values**: Method returns updating local frame state.

## Files

- `cs1302/account/Account.java`: Bank account class with balance validation.
- `cs1302/account/Driver.java`: Driver creating accounts and performing transactions.
