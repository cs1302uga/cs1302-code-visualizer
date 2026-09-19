#!/bin/bash -e

cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null

BATCH=true
FORWARD_ARGS=()
EXTRA_BATCH_ARGS=()

while [ "$#" -gt 0 ]; do
    arg="$1"
    case "${arg}" in
        --batch)
            BATCH=true
            shift
            ;;
        --no-batch)
            BATCH=false
            shift
            ;;
        -w|--workers)
            EXTRA_BATCH_ARGS+=("--workers" "$2")
            shift 2
            ;;
        --workers=*)
            EXTRA_BATCH_ARGS+=("--workers" "${arg#*=}")
            shift
            ;;
        --browsers)
            EXTRA_BATCH_ARGS+=("--browsers" "$2")
            shift 2
            ;;
        --browsers=*)
            EXTRA_BATCH_ARGS+=("--browsers" "${arg#*=}")
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Runs all example tests, forwarding options to each test."
            echo "Batch mode (default) uses a persistent browser pool for fast parallel rendering."
            echo "If no options are provided, defaults to: --open --rm-json --rm-image"
            echo ""
            echo "Options:"
            echo "  --batch                  Run in batch mode using pooled browser rendering (default)"
            echo "  --no-batch               Run sequentially launching fresh processes for each example"
            echo "  -w, --workers <N>        Number of tracer worker JVMs in batch mode (default: 1)"
            echo "  --browsers <N>           Number of browser instances in rendering pool (default: 2)"
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
        *)
            FORWARD_ARGS+=("${arg}")
            shift
            ;;
    esac
done

if [ ${#FORWARD_ARGS[@]} -eq 0 ] && [ ${#EXTRA_BATCH_ARGS[@]} -eq 0 ]; then
    FORWARD_ARGS=("--open" "--rm-json" "--rm-image")
fi

if [ "${BATCH}" = true ]; then
    echo "========================================"
    echo "Running all example tests in batch mode..."
    echo "========================================"
    BATCH_PY_ARGS=("${EXTRA_BATCH_ARGS[@]}")
    for arg in "${FORWARD_ARGS[@]}"; do
        case "${arg}" in
            -J|--rm-json)
                BATCH_PY_ARGS+=("--rm-json")
                ;;
            -j|--no-rm-json)
                ;;
            -I|--rm-image)
                BATCH_PY_ARGS+=("--rm-image")
                ;;
            -i|--no-rm-image)
                ;;
            -o|--open)
                BATCH_PY_ARGS+=("--open")
                ;;
            -O|--no-open)
                ;;
            -y|--yes|--non-interactive|-n)
                BATCH_PY_ARGS+=("--open" "--rm-json" "--rm-image")
                ;;
        esac
    done
    uv run python run_batch.py "${BATCH_PY_ARGS[@]}"
    echo "========================================"
    echo "All example tests completed successfully!"
    echo "========================================"
    exit 0
fi

# Unbatched sequential fallback
for i in {0..33}; do
    dir="example${i}"
    if [ -d "${dir}" ] && [ -f "${dir}/test.sh" ]; then
        echo "========================================"
        echo "Running test in ${dir}... (unbatched)"
        echo "========================================"
        (
            cd "${dir}"
            ./test.sh "${FORWARD_ARGS[@]}"
        )
    fi
done

echo "========================================"
echo "All example tests completed successfully!"
echo "========================================"
