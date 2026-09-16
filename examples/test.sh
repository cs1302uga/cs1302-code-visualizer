#!/bin/bash -e

OPEN_IMAGE=""
RM_JSON=""
RM_IMAGE=""
INPUT_FILE=""
EXTRA_TRACER_ARGS=()

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
            echo "Usage: $0 [options] <path-to-java-file> [extra-tracer-options...]"
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
            if [ -z "${INPUT_FILE}" ]; then
                INPUT_FILE="$1"
            else
                EXTRA_TRACER_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

if [ -z "${INPUT_FILE}" ]; then
    echo "Usage: $0 [options] <path-to-java-file> [extra-tracer-options...]" >&2
    exit 1
fi

TRACE_FILE="${INPUT_FILE}.json"
IMAGE_FILE="${INPUT_FILE}.png"

TRACER_INFO=$(uv run python -c "
import subprocess, re
from cs1302_code_visualizer.trace_generator import ensure_jdk_installed, ensure_code_tracer_installed, CACHE_DIR, read_tracer_url_and_sum_from_toml, get_sanitized_java_env
ensure_code_tracer_installed()
java_home = ensure_jdk_installed()
jar = CACHE_DIR / 'code-tracer.jar'
bin_ver = subprocess.check_output([str(java_home / 'bin' / 'java'), '-Djava.awt.headless=true', '-jar', str(jar), '--version'], text=True, stderr=subprocess.DEVNULL, env=get_sanitized_java_env()).strip()
toml_info = read_tracer_url_and_sum_from_toml()
conf_ver = 'unknown'
if toml_info:
    m = re.search(r'/(v[0-9]+\.[0-9]+\.[0-9]+)/', toml_info[0])
    conf_ver = m.group(1) if m else toml_info[0]
print(f'{conf_ver} (binary reported: {bin_ver})')
")
echo "Tracer version: ${TRACER_INFO}"

HAS_BREAKPOINT_ARG=false
for arg in "${EXTRA_TRACER_ARGS[@]}"; do
    case "${arg}" in
        -a|--all-breakpoints|-b|--breakpoint|--breakpoints|-b=*|--breakpoint=*|--breakpoints=*)
            HAS_BREAKPOINT_ARG=true
            break
            ;;
    esac
done

if [ "${HAS_BREAKPOINT_ARG}" = false ]; then
    EXTRA_TRACER_ARGS=("-a" "${EXTRA_TRACER_ARGS[@]}")
fi

open_files() {
    local files=("$@")
    case "${OSTYPE}" in
        darwin*) # macOS
            (
                set -x
                qlmanage -p "${files[@]}" >/dev/null 2>&1
            )
            ;;
        linux*) # Linux (requires xdg-utils)
            (
                set -x
                for f in "${files[@]}"; do
                    xdg-open "${f}"
                done
            )
            ;; # Windows (Git Bash/Cygwin)
        msys*|cygwin*)
            (
                set -x
                for f in "${files[@]}"; do
                    start "${f}"
                done
            )
            ;;
        *)
            echo "unable to open file automatically: OSTYPE=${OSTYPE} not supported"
            ;;
    esac
} # open_files

(
    set -x
    uv run generate_trace "${EXTRA_TRACER_ARGS[@]}" < "${INPUT_FILE}" > "${TRACE_FILE}"
    uv run generate_visualization --all-steps --output "${IMAGE_FILE}" < "${TRACE_FILE}"
)

# Collect all generated step images
STEP_IMAGES=()
idx=0
while [ -f "${INPUT_FILE}.${idx}.png" ]; do
    STEP_IMAGES+=("${INPUT_FILE}.${idx}.png")
    ((idx++))
done
if [ ${#STEP_IMAGES[@]} -eq 0 ] && [ -f "${IMAGE_FILE}" ]; then
    STEP_IMAGES+=("${IMAGE_FILE}")
fi

# Open image handling
if [ "${OPEN_IMAGE}" = true ]; then
    open_files "${STEP_IMAGES[@]}"
elif [ "${OPEN_IMAGE}" = false ]; then
    :
else
    echo "Do you want to open generated image(s) for ${INPUT_FILE}?"
    select yn in "Yes" "No"; do
        case ${yn} in
            Yes )
                open_files "${STEP_IMAGES[@]}"
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
        rm -f "${INPUT_FILE}".*.png "${IMAGE_FILE}"
    )
elif [ "${RM_IMAGE}" = false ]; then
    :
else
    echo "Do you want to delete generated image(s) for ${INPUT_FILE}?"
    select yn in "Yes" "No"; do
        case ${yn} in
            Yes )
                (
                    set -x
                    rm -f "${INPUT_FILE}".*.png "${IMAGE_FILE}"
                )
                break
                ;;
            No )
                break
                ;;
        esac
    done
fi
