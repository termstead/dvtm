#!/usr/bin/env python3
"""Generate wcwidth_table.h from the Unicode tables of the wcwidth package.

usage: pip install wcwidth && tools/gen-wcwidth.py > wcwidth_table.h
"""
import wcwidth.table_wide as wide
import wcwidth.table_zero as zero

version = max(wide.WIDE_EASTASIAN, key=lambda v: tuple(map(int, v.split('.'))))


print('typedef struct { unsigned int lo, hi; } WidthRange;\n')


def emit(name, ranges):
    print(f'static const WidthRange {name}[] = {{')
    for lo, hi in ranges:
        print(f'\t{{ 0x{lo:04X}, 0x{hi:04X} }},')
    print('};\n')


emit('wcwidth_zero', [r for r in zero.ZERO_WIDTH[version] if r[1] >= 0x80])
emit('wcwidth_wide', wide.WIDE_EASTASIAN[version])
