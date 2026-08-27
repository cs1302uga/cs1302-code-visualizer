#!/bin/bash -e

OPEN_IMAGE=""
RM_JSON=""
RM_IMAGE=""
INPUT_FILE=""

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        -J|--rm-json)
            RM_JSON=true
            shift
            ;;
        -j|--no-rm-json)
            RM_JSON=false
            shift
            ;;
        -I|--rm-image)
            RM_IMAGE=true
            shift
            ;;
        -i|--no-rm-image)
            RM_IMAGE=false
            shift
            ;;
        -o|--open|--open-image)
            OPEN_IMAGE=true
            shift
            ;;
        -O|--no-open)
            OPEN_IMAGE=false
            shift
            ;;
        -y|--yes|--non-interactive|-n)
            [ -z "${OPEN_IMAGE}" ] && OPEN_IMAGE=true
            [ -z "${RM_JSON}" ] && RM_JSON=true
            [ -z "${RM_IMAGE}" ] && RM_IMAGE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options] <path-to-java-file>"
            echo ""
            echo "Options:"
            echo "  -J, --rm-json            Automatically delete the generated JSON trace file"
            echo "  -j, --no-rm-json         Do not delete the generated JSON trace file"
            echo "  -I, --rm-image           Automatically delete the generated PNG image file"
            echo "  -i, --no-rm-image        Do not delete the generated PNG image file"
            echo "  -o, --open               Automatically open the generated image"
            echo "  -O, --no-open            Do not open the generated image"
            echo "  --non-interactive        Non-interactive mode (defaults to open and delete all)"
            echo "  -h, --help               Show this help message"
            exit 0
            ;;
        *)
            INPUT_FILE="$1"
            shift
            ;;
    esac
done

if [ -z "${INPUT_FILE}" ]; then
    echo "Usage: $0 [options] <path-to-java-file>" >&2
    exit 1
fi

TRACE_FILE="${INPUT_FILE}.json"
IMAGE_FILE="${INPUT_FILE}.png"

TRACER_INFO=$(uv run python -c "
import subprocess, re
from cs1302_code_visualizer.trace_generator import ensure_jdk_installed, ensure_code_tracer_installed, CACHE_DIR, read_tracer_url_and_sum_from_toml
ensure_code_tracer_installed()
java_home = ensure_jdk_installed()
jar = CACHE_DIR / 'code-tracer.jar'
bin_ver = subprocess.check_output([str(java_home / 'bin' / 'java'), '-jar', str(jar), '--version'], text=True).strip()
toml_info = read_tracer_url_and_sum_from_toml()
conf_ver = 'unknown'
if toml_info:
    m = re.search(r'/(v[0-9]+\.[0-9]+\.[0-9]+)/', toml_info[0])
    conf_ver = m.group(1) if m else toml_info[0]
print(f'{conf_ver} (binary reported: {bin_ver})')
")
echo "Tracer version: ${TRACER_INFO}"

open_file() {
    local file="${1}"
    case "${OSTYPE}" in
        darwin*) # macOS
            (
                set -x
                qlmanage -p "${file}" >/dev/null 2>&1
            )
            ;;
        linux*) # Linux (requires xdg-utils)
            (
                set -x
                xdg-open "${file}"
            )
            ;; # Windows (Git Bash/Cygwin)
        msys*|cygwin*)
            (
                set -x
                start "${file}"
            )
            ;;
        *)
            echo "unable to open file automatically: OSTYPE=${OSTYPE} not supported"
            ;;
    esac
} # open_file

(
    set -x
    uv run generate_trace < "${INPUT_FILE}" > "${TRACE_FILE}"
    uv run generate_visualization < "${TRACE_FILE}" > "${IMAGE_FILE}"
)

# Open image handling
if [ "${OPEN_IMAGE}" = true ]; then
    open_file "${IMAGE_FILE}"
elif [ "${OPEN_IMAGE}" = false ]; then
    :
else
    echo "Do you want to open ${IMAGE_FILE}?"
    select yn in "Yes" "No"; do
        case ${yn} in
            Yes )
                open_file "${IMAGE_FILE}"
                break
                ;;
            No )
                break
                ;;
        esac
    done
fi

# Delete JSON trace file handling
if [ "${RM_JSON}" = true ]; then
    (
        set -x
        rm -f "${TRACE_FILE}"
    )
elif [ "${RM_JSON}" = false ]; then
    :
else
    echo "Do you want to delete ${TRACE_FILE}?"
    select yn in "Yes" "No"; do
        case ${yn} in
            Yes )
                (
                    set -x
                    rm -f "${TRACE_FILE}"
                )
                break
                ;;
            No )
                break
                ;;
        esac
    done
fi

# Delete image file handling
if [ "${RM_IMAGE}" = true ]; then
    (
        set -x
        rm -f "${IMAGE_FILE}"
    )
elif [ "${RM_IMAGE}" = false ]; then
    :
else
    echo "Do you want to delete ${IMAGE_FILE}?"
    select yn in "Yes" "No"; do
        case ${yn} in
            Yes )
                (
                    set -x
                    rm -f "${IMAGE_FILE}"
                )
                break
                ;;
            No )
                break
                ;;
        esac
    done
fi
