#!/bin/bash -e

cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null

../test.sh Driver.java
