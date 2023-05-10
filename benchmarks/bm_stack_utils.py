import os

from elasticapm.utils.stacks import (get_frame_info, get_lines_from_file,
                                     iter_stack_frames)
from elasticapmspeedups import read_lines_from_file as get_lines_from_file_rust

FILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "lines.txt"
)


def bench_get_lines_from_file_start():
    if hasattr(get_lines_from_file, "cache_clear"):
        get_lines_from_file.cache_clear()
    pre, context, post = get_lines_from_file(FILE_PATH, 1, 5)


def bench_get_lines_from_file_middle():
    if hasattr(get_lines_from_file, "cache_clear"):
        get_lines_from_file.cache_clear()
    pre, context, post = get_lines_from_file(FILE_PATH, 250, 5)


def bench_get_lines_from_file_end():
    if hasattr(get_lines_from_file, "cache_clear"):
        get_lines_from_file.cache_clear()
    pre, context, post = get_lines_from_file(FILE_PATH, 500, 5)


def bench_get_lines_from_file_rust_start():
    if hasattr(get_lines_from_file, "cache_clear"):
        get_lines_from_file.cache_clear()
    pre, context, post = get_lines_from_file_rust(FILE_PATH, 1, 5)


def bench_get_lines_from_file_rust_middle():
    if hasattr(get_lines_from_file, "cache_clear"):
        get_lines_from_file.cache_clear()
    pre, context, post = get_lines_from_file_rust(FILE_PATH, 250, 5)


def bench_get_lines_from_file_rust_end():
    if hasattr(get_lines_from_file, "cache_clear"):
        get_lines_from_file.cache_clear()
    pre, context, post = get_lines_from_file_rust(FILE_PATH, 500, 5)

#
# def bench_iter_stack_frames():
#     for frame, lineno in iter_stack_frames():
#         info = get_frame_info(frame, lineno)
