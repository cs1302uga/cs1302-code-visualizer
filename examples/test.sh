#!/bin/bash -e

INPUT_FILE="${1}"
TRACE_FILE="${INPUT_FILE}.json"
IMAGE_FILE="${INPUT_FILE}.png"

open_file() {
    local file="${1}"
    case "${OSTYPE}" in
        darwin*) # macOS
            (
                set -x
                qlmanage -p Driver.java.png >/dev/null 2>&1
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
            echo "unable to open file automaticcally: OSTYPE=${OSTYPE} not supported";
            ;;
    esac
} # open_file

(
    set -x
    env CS1302_DEBUG=1 uv run generate_trace < ${INPUT_FILE} > ${TRACE_FILE}
    env CS1302_DEBUG=1 uv run generate_visualization < ${TRACE_FILE} > ${IMAGE_FILE}
)

echo "Do you want to open ${IMAGE_FILE}?"
select yn in "Yes" "No"; do
    case ${yn} in
        Yes )
            open_file ${IMAGE_FILE}
            break
            ;;
        No )
            break
            ;;
    esac
done

echo "Do you want to delete ${TRACE_FILE} and ${IMAGE_FILE}?"
select yn in "Yes" "No"; do
    case ${yn} in
        Yes )
            (
                set -x
                rm -f ${TRACE_FILE}
                rm -f ${IMAGE_FILE}
            )
            break
            ;;
        No )
            break
            ;;
    esac
done


