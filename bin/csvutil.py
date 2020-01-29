#!/usr/bin/python3

import argparse
import csv
import re
import statistics
import sys
import textwrap


# Print an error and exit.
def fatal(s):
    print(sys.argv[0] + ' error:', file=sys.stderr)
    print(s)
    sys.exit(1)


# Iterate over rows in a CSV file, calling fn on each.  Return the list of
# per-row results.
def csv_rows(filename, delim, fn):
    def iterate(inchannel):
        r = csv.reader(inchannel, delimiter=delim)
        return [fn([e.strip() for e in row]) for row in r]

    if filename == '':
        return iterate(sys.stdin)
    else:
        with open(filename) as rawfile:
            return iterate(rawfile)


# -------------------------------------------------------------------------- #
#                                    Pick                                    #
# -------------------------------------------------------------------------- #


op_pick_desc = "Pick a field or set of fields from each row."


def op_pick():
    parser = argparse.ArgumentParser(prog=sys.argv[0] + " pick",
                                     description=op_pick_desc)
    parser.add_argument(
        'filename',
        help='CSV input file.  Default: stdin.',
        default='',
        nargs='?')
    parser.add_argument(
        '-f',
        '--fields',
        help='comma-separated list of (zero-indexed) fields.',
        type=str,
        default='')
    parser.add_argument(
        '-d',
        '--delimiter',
        help='CSV field delimiter.  Default: ",".',
        default=',')

    args = parser.parse_args(sys.argv[2:])
    fields = [int(x) for x in args.fields.split(',')]
    csv_rows(args.filename, args.delimiter,
             lambda row: print(args.delimiter.join([row[n] for n in fields])))


# -------------------------------------------------------------------------- #
#                                   Merge                                    #
# -------------------------------------------------------------------------- #


op_merge_desc = "Merge similar sequential lines."


def op_merge():
    parser = argparse.ArgumentParser(prog=sys.argv[0] + " merge",
                                     description=op_merge_desc)
    parser.add_argument(
        'filename',
        help='CSV input file.  Default: stdin.',
        default='',
        nargs='?')
    parser.add_argument(
        '-d',
        '--delimiter',
        help='CSV field delimiter.  Default: ",".',
        default=',')
    parser.add_argument(
        '-f',
        '--field_function',
        help=("Specify a field:function merge operation when a field is not " +
              "expected to be identical across rows. Functions are: " +
              "sum, min, max, mean, median, stdev, first, last, ignore. " +
              "E.g., \"-f 0:max\". The result is appended to the output as a" +
              "new field. Multiple pairs can be specified."),
        nargs='*',
        default=[])

    def numberify(f):
        return lambda l: f([float(n) for n in l])

    # stdev doesn't accept lists of length = 1. For the purposes of this
    # utility, just duplicate the single entry.
    def trivial_multiple(f):
        return lambda l: f(l) if len(l) > 1 else f([l[0], l[0]])

    fcn_set = {'sum': numberify(sum),
               'min': numberify(min),
               'max': numberify(max),
               'mean': numberify(statistics.mean),
               'median': numberify(statistics.median),
               'stdev': numberify(trivial_multiple(statistics.stdev)),
               'first': (lambda l: l[0]),
               'last': (lambda l: l[-1]),
               'ignore': (lambda l: None)}

    args = parser.parse_args(sys.argv[2:])

    # Get the user's collection of field/function pairs.
    def ff(s):
        nonlocal fcn_set
        m = re.search("^([0-9]+):([a-z]+)$", s)
        if m is None:
            fatal("unable to interpret field:function " + s)
        if m.group(2) not in fcn_set:
            fatal("no such field:function operation: " + m.group(2))
        return int(m.group(1)), fcn_set[m.group(2)]

    field_functions = [ff(s) for s in args.field_function]
    sfield_set = set(set([p[0] for p in field_functions]))
    aggregate_values = {}
    cmp_line = None

    def make_comparable(l):
        nonlocal sfield_set
        ret = []
        for n in range(len(l)):
            if n not in sfield_set:
                ret.append(l[n])
        return ret

    def add_mergeable(l):
        nonlocal field_functions
        for n, f in field_functions:
            l.append(str(f(aggregate_values[n])))

    def reset_cmp_line(row):
        nonlocal cmp_line, make_comparable, sfield_set, aggregate_values
        cmp_line = make_comparable(row)
        for n in sfield_set:
            aggregate_values[n] = [row[n]]

    # Collect and aggregate the data, merging specific fields according to the
    # field_functions specified by the user.
    def collect_and_aggregate(row):
        nonlocal cmp_line, make_comparable, add_mergeable, reset_cmp_line
        nonlocal sfield_set, aggregate_values
        if cmp_line is None:
            reset_cmp_line(row)
        else:
            if make_comparable(row) == cmp_line:
                for n in sfield_set:
                    aggregate_values[n].append(row[n])
            else:
                printable = cmp_line
                add_mergeable(printable)
                print(args.delimiter.join(printable))
                reset_cmp_line(row)

    csv_rows(args.filename, args.delimiter, collect_and_aggregate)
    if cmp_line is not None:
        add_mergeable(cmp_line)
        print(args.delimiter.join(cmp_line))


# -------------------------------------------------------------------------- #
#                                    Sort                                    #
# -------------------------------------------------------------------------- #


op_sort_desc = "Sort rows based on the specified fields."


def op_sort():
    parser = argparse.ArgumentParser(prog=sys.argv[0] + " merge",
                                     description=op_merge_desc)
    parser.add_argument(
        'filename',
        help='CSV input file.  Default: stdin.',
        default='',
        nargs='?')
    parser.add_argument(
        '-d',
        '--delimiter',
        help='CSV field delimiter.  Default: ",".',
        default=',')
    parser.add_argument(
        '-f',
        '--fields',
        help='Zero-indexed fields on which to sort. An optional type ' +
        'qualifier (int, float, string) may be specified. E.g., ' +
        '"-f 3:float" sorts on the fourth field, interpreting elements as ' +
        'floating point values. "-f 3" would merely sort on the fourth ' +
        'field as strings by default.',
        nargs='+')

    args = parser.parse_args(sys.argv[2:])
    field_set = []

    # Get the user's collection of field (and optional type) values.
    def ff(s):
        nonlocal field_set
        m = re.search("^([0-9]+)(:[a-z]+)?$", s)
        if m is None:
            fatal("unable to interpret field " + s)
        if not m.group(2) or m.group(2) == ":string":
            return int(m.group(1)), str
        elif m.group(2) == ":float":
            return int(m.group(1)), float
        elif m.group(2) == ":int":
            return int(m.group(1)), int
        fatal("unknown type for field/type pair: " + s)

    fields = [ff(s) for s in args.fields]

    row_list = []
    csv_rows(args.filename, args.delimiter, lambda row: row_list.append(row))
    for n, fcn in fields:
        row_list.sort(key=lambda row: fcn(row[n]))
    for row in row_list:
        print(args.delimiter.join(row))


# -------------------------------------------------------------------------- #
#                                    Main                                    #
# -------------------------------------------------------------------------- #


ops = {"pick": (op_pick, op_pick_desc),
       "merge": (op_merge, op_merge_desc),
       "sort": (op_sort, op_sort_desc)}


def usage():
    print("usage: " + sys.argv[0] + " [ARGS]\n")
    print("  Perform operations on a CSV file or input.\n")
    print("      -h|--help: This usage message.")
    print("      -v|--version: Version information.\n")
    print("  CSV operations:\n")
    for k in ops:
        print("      " + k + ": " + ops[k][1])
    print("\n  Use " + sys.argv[0] + " [OP] -h for help on a specific op.")
    sys.exit(0)


def version():
    print(sys.argv[0])
    print("Copyright (C) 2019 William M. Leiserson")
    free_txt = textwrap.wrap("This is free software; see the source for " +
                             "copying conditions.  There is NO warranty; " +
                             "not even for MERCHANTABILITY or FITNESS FOR A " +
                             "PARTICULAR PURPOSE.", 80)
    for s in free_txt:
        print(s)
    sys.exit(0)


if len(sys.argv) < 2 or sys.argv[1] in set(["-h", "--help"]):
    usage()

if sys.argv[1] in set(["-v", "--version"]):
    version()

if sys.argv[1] in ops.keys():
    ops[sys.argv[1]][0]()
    sys.exit(0)

fatal(sys.argv[1] + " is not a supported operation.  Use -h for help.")
