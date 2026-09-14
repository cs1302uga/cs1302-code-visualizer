#!/bin/bash -e

cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null

../test.sh "$@" cs1302/scanner/Driver.java --stdin "Hello 1302 98.5"
