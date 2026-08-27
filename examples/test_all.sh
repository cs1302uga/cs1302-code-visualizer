#!/bin/bash -e

cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null

for arg in "$@"; do
    case "${arg}" in
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Runs all example tests sequentially, forwarding options to each test."
            echo "If no options are provided, defaults to: --open --rm-json --rm-image"
            echo ""
            echo "Options:"
            echo "  -J, --rm-json            Automatically delete generated JSON trace files"
            echo "  -j, --no-rm-json         Do not delete generated JSON trace files"
            echo "  -I, --rm-image           Automatically delete generated PNG image files"
            echo "  -i, --no-rm-image        Do not delete generated PNG image files"
            echo "  -o, --open               Automatically open generated images"
            echo "  -O, --no-open            Do not open generated images"
            echo "  --non-interactive        Non-interactive mode (defaults to open and delete all)"
            echo "  -h, --help               Show this help message"
            exit 0
            ;;
    esac
done

ARGS=("$@")
if [ "$#" -eq 0 ]; then
    ARGS=("--open" "--rm-json" "--rm-image")
fi

for dir in example*/; do
    if [ -d "${dir}" ]; then
        if [ -f "${dir}/Driver.java" ]; then
            echo "========================================"
            echo "Running test in ${dir}..."
            echo "========================================"
            (
                cd "${dir}"
                ../test.sh "${ARGS[@]}" Driver.java
            )
        fi
    fi
done

echo "========================================"
echo "All example tests completed successfully!"
echo "========================================"
