#!/bin/bash -e

cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null

../test.sh "$@" cs1302/generics/Driver.java -a
