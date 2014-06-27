#! /usr/bin/python3

import argparse
import csv
import random
import math
import re
import sys
import string
from collections import defaultdict
from hashlib import md5
from collections import Counter

__version__ = "1.4.1"

# ================
# Argument Parsing
# ================

class Parser:
    def __init__(self):
        self.parser = self._build_base_parser()
        self.subparsers = self._build_subparsers()
        self.usage = '<fastafile> | smof {} <options>'

    def _build_base_parser(self):
        parser = argparse.ArgumentParser(
            prog='smof',
            usage='<fastafile> | smof <subcommand> <options>',
            description='Tools for studying and manipulating fasta files')

        parser.add_argument(
            '-v', '--version',
            action='version',
            version='%(prog)s {}'.format(__version__))
        return(parser)

    def _build_subparsers(self):
        subparsers = self.parser.add_subparsers(
            metavar='[ for help on each: smof <subcommand> -h ]',
            title='subcommands')
        return(subparsers)

def parse(argv=None):

    if sys.argv[1] in ('idsearch', 'retrieve', 'search', 'rmfields'):
        print("{} is deprecated, use 'smof grep'".format(sys.argv[1]))
        raise SystemExit

    parser = Parser()

    Chksum(parser)
    Clean(parser)
    Complexity(parser)
    Fasta2csv(parser)
    Grep(parser)
    Perm(parser)
    Rename(parser)
    Reverse(parser)
    Sample(parser)
    Sniff(parser)
    Sort(parser)
    Split(parser)
    Stat(parser)
    Subseq(parser)
    Uniq(parser)
    Wc(parser)
    Winnow(parser)

    if(len(sys.argv) == 1):
        parser.parser.print_help()
        raise SystemExit

    args = parser.parser.parse_args(argv)

    return(args)


# =================
# CLASS DEFINITIONS
# =================

class Maps:
    DNA_AMB = {
        'R':'AG',
        'Y':'CT',
        'S':'GC',
        'W':'AT',
        'K':'GT',
        'M':'AC',
        'B':'CGT',
        'D':'AGT',
        'H':'ACT',
        'V':'ACG',
        'N':'ACGT'
    }

class Alphabet:
    # Including U, for selenocysteine, and * for STOP
    PROT     = set('ACDEFGHIKLMNPQRSTUVWYX*')
    PROT_UNK = set('X')
    PROT_AMB = set('BZJ')
    PROT_EXC = set('EFILQPXJZ*') # unique to protein sequences
    DNA      = set('ACGTN')
    DNA_UNK  = set('N')
    DNA_AMB  = set('RYSWKMDBHV')
    RNA      = set('ACGUN')
    RNA_UNK  = set('N')
    RNA_AMB  = set('RYSWKMDBHV')
    GAP      = set('.-_')
    STOP     = {'TAG', 'TAA', 'TGA', 'UAG', 'UAA', 'UGA'}
    START    = {'ATG', 'AUG'}

class FSeqGenerator:
    def __init__(self, fh=sys.stdin):
        self.fh = fh

    def next(self):
        seq_list = []
        header = ''
        nseqs = 0
        for line in self.fh:
            line = line.strip()
            if not line:
                continue
            if ">" == line[0]:
                if(seq_list):
                    nseqs += 1
                    yield FSeq(header, ''.join(seq_list))
                seq_list = []
                header = line.split('>')[1]
            elif header:
                seq_list.append(line)
            else:
                print("First line must begin with '>'", file=sys.stderr)
                raise SystemExit
        if header:
            nseqs += 1
            yield FSeq(header, ''.join(seq_list))
        if not nseqs:
            print("smof could not retrieve any sequence from this file, exiting", file=sys.stderr)
            raise SystemExit

class FSeq:
    # The translator for taking reverse complements
    revcomp_translator = str.maketrans('acgtACGT', 'tgcaTGCA')
    def __init__(self, header, seq):
        self.seq = seq
        self.header = header
        self.headerfields = {}
        self.colseq = ColorString()
        self.colheader = ColorString()

    def __hash__(self):
        return(hash((self.header, self.seq)))

    def __eq__(self, other):
        return((self.header, self.seq) == (other.header, other.seq))

    def parse_header(self):
        '''
        Parses headers of the format:
           '>field_1|value_1|field_2|value_2|...|field_k|value_k| description (optional)
        For example:
            >locus|AT3G01015|taxon|3702|gi|186509637|gb|NP_186749.2| TPX2 targeting protein
        '''
        fields = self.header.split('|')
        # If there is no delimitation with '|', set whatever there is to field
        # 'header'
        if(len(fields) == 1):
            self.headerfields['header'] = fields[0]
        else:
            if(len(fields) % 2  == 1 and fields[-1]):
                self.headerfields['desc'] = fields.pop().strip()
            for i in range(0, len(fields), 2):
                self.headerfields[fields[i].strip()] = fields[i+1].strip()

    def getvalue(self, field, quiet=False, missing=''):
        if not self.headerfields:
            self.parse_header()
        try:
            return(self.headerfields[field])
        except:
            if missing:
                return missing
            if not quiet:
                print("Header lacks field '{}'".format(field), file=sys.stderr)
                print(self.header, file=sys.stderr)
            raise SystemExit

    def subseq(self, a, b):
        try:
            return(self.seq[a:b])
        except IndexError as e:
            print("Cannot extract subsequence ({}, {}) from".format(a,b))
            print('>' + self.header)
        except:
            print("Unknown error in extraction of subsequence ({}, {}) from".format(a,b))
            print('>' + self.header)

    def ungap(self):
        self.seq = re.sub('[._-]', '', self.seq)

    def print(self, column_width=80):
        if self.colheader.seq:
            self.colheader.print(column_width)
        else:
            print('>' + self.header)
        for i in range(0, len(self.seq), column_width):
            if self.colseq.seq:
                self.colseq.print(column_width)
                break
            else:
                print(self.seq[i:i + column_width])

    def get_pretty_string(self, column_width=80):
        out = ['>' + self.header]
        for i in range(0, len(self.seq), column_width):
            out.append(self.seq[i:i + column_width])
        outstr = '\n'.join(out)
        return(outstr)

    def seq_upper(self):
        self.seq = self.seq.upper()

    def header_upper(self):
        self.header = self.header.upper()

    @classmethod
    def getrevcomp(cls, seq):
        return(seq[::-1].translate(FSeq.revcomp_translator))

class Colors:
    HIGHLIGHT = chr(27) + '[32m'
    BACKGROUND = chr(27) + '[0m'

class ColorString:
    def __init__(self,
                 seq=None,
                 bgcolor=Colors.BACKGROUND,
                 default=Colors.HIGHLIGHT):
        self.bgcolor = bgcolor
        self.default = default
        self.seq = []
        if seq:
            self.setseq(seq)

    def setseq(self, seq):
        '''
        Pair every character in the input string with a color
        @param seq: string that will ultimately be colored
        @type seq: string
        '''
        if not self.seq:
            self.seq = [[self.bgcolor, s] for s in seq]

    def colorpos(self, pos, col=None):
        '''
        Change color at specified positions
        @param pos: indices to recolor
        @type pos: iterable
        @param col: new color
        @type col: stringy thing that colorifies
        '''
        col = self.default if not col else col
        for i in pos:
            self.seq[i][0] = col

    def print(self, colwidth=None):
        lastcol = self.seq[0][0]
        for i in range(1, len(self.seq)):
            if(self.seq[i][0] == lastcol):
                self.seq[i][0] = ''
            else:
                lastcol = self.seq[i][0]
        for i in range(len(self.seq)):
            print(''.join(self.seq[i]), end='')
            if(colwidth and i % colwidth == 0 and i != 0):
                print()
        print(self.bgcolor)

    def colormatch(self, pattern, col=None):
        col = self.default if not col else col
        s = ''.join([x[1] for x in self.seq])
        for m in re.compile(pattern).finditer(s):
            a = m.start()
            b = m.start() + len(m.group())
            self.colorpos(list(range(a,b)), col)

class FileDescription:
    def __init__(self):
        self.seqs = set()
        self.headers = set()
        self.ntype = {
            'prot':0,
            'dna':0,
            'rna':0,
            'illegal':0,
            'ambiguous':0}
        self.ncase = {
            'uppercase':0,
            'lowercase':0,
            'mixedcase':0}
        self.pfeat = {
            'selenocysteine':0,
            'initial-Met':0,
            'internal-stop':0,
            'terminal-stop':0}
        self.nfeat = {
            'start|coding|stop':0,
            'start|coding':0,
            'start|nonsense|stop':0,
            'start|nonsense':0,
            'coding|stop':0,
            'nonsense|stop':0,
            'start|n|stop':0,
            'start':0,
            'stop':0,
            'not-CDS':0}
        self.ufeat = {
            'gapped':0,
            'unknown':0,
            'ambiguous':0}

    def add_seq(self, seq):
        '''
        Calculates properties for one sequence
        @type seq: FSeq object
        '''

        # Add md5 hashes of sequences and headers to respective sets
        self.seqs.update([md5(bytes(seq.seq, 'ascii')).digest()])
        self.headers.update([md5(bytes(seq.header, 'ascii')).digest()])

        counts = Counter(seq.seq)

        # Ungapped the sequence is required for downstream analysis
        is_gapped = self._handle_gaps(seq, counts)
        if is_gapped:
            seq.ungap()
            counts = Counter(seq.seq)

        scase = self._handle_case(counts)
        # Sum upper and lowercase
        if scase not in 'upper':
            counts = counter_caser(counts)

        # ('prot'|'dna'|'rna'|'amb'|'bad')
        stype = self._handle_type(counts)

        if stype == 'prot':
            self.ufeat['unknown'] += 'X' in counts
            self.ufeat['ambiguous'] += bool(Alphabet.PROT_AMB & set(counts))
            self.pfeat['selenocysteine'] += 'U' in counts
            self.pfeat['initial-Met'] += 'M' == seq.seq[0].upper()
            tstop = '*' == seq.seq[-1]
            self.pfeat['terminal-stop'] += tstop
            self.pfeat['internal-stop'] += (counts['*'] - tstop) > 0
        elif stype in ('dna', 'rna'):
            self.ufeat['unknown'] += 'N' in counts
            self.ufeat['ambiguous'] += bool(Alphabet.DNA_AMB & set(counts))
            triple = len(seq.seq) % 3 == 0
            # Is last three bases STOP?
            tstop = seq.seq[-3:].upper() in Alphabet.STOP

            codons_1 = [seq.seq[i:i+3].upper() for i in range(0, len(seq.seq) - 3, 3)]
            start_1 = 'ATG' == codons_1[0]
            stop_1 = codons_1[-1] in Alphabet.STOP
            internal_stop_1 = bool(set(codons_1[:-1]) & Alphabet.STOP)

            # Triplet and START-STOP
            if start_1 and triple and stop_1 and not internal_stop_1:
                self.nfeat['start|coding|stop'] += 1
            elif start_1 and triple and stop_1 and internal_stop_1:
                self.nfeat['start|nonsense|stop'] += 1
            # Triplet and START
            elif start_1 and triple and not stop_1 and not internal_stop_1:
                self.nfeat['start|coding'] += 1
            elif start_1 and triple and not stop_1 and internal_stop_1:
                self.nfeat['start|nonsense'] += 1
            # Triplet and STOP
            elif not start_1 and tstop and triple and not internal_stop_1:
                self.nfeat['coding|stop'] += 1

            # START and terminal-STOP
            elif start_1 and tstop and not triple:
                self.nfeat['start|n|stop'] += 1
            elif start_1 and not tstop:
                self.nfeat['start'] += 1
            elif not start_1 and not tstop:
                self.nfeat['stop'] += 1
            else:
                self.nfeat['not-CDS'] += 1

    def _handle_gaps(self, seq, counts):
        # Handle gaps
        if Alphabet.GAP & set(counts):
            self.ufeat['ngapped'] += 1
            return(True)
        return(False)

    def _handle_case(self, counts):
        has_lower = set(string.ascii_lowercase) & set(counts)
        has_upper = set(string.ascii_uppercase) & set(counts)
        if has_lower and has_upper:
            case = 'mixedcase'
        elif has_lower:
            case = 'lowercase'
        else:
            case = 'uppercase'
        self.ncase[case] += 1
        return(case)

    def _handle_type(self, counts):
        # If all chars are in ACGT
        if set(counts) <= Alphabet.DNA:
            stype = 'dna'
        # If all chars in ACGU
        elif set(counts) <= Alphabet.RNA:
            stype = 'rna'
        # If has any chars unique to proteins (EFILQPXJZ*)
        elif set(counts) & Alphabet.PROT_EXC:
            if set(counts) <= Alphabet.PROT | Alphabet.PROT_AMB:
                stype = 'prot'
            else:
                stype = 'illegal'
        # If all the residues could be aa, DNA, or RNA
        elif set(counts) <= (Alphabet.PROT | Alphabet.PROT_AMB):
            # If more than 80% look like nucleic acids, set 'amb_nucl'
            if (sum([counts[x] for x in 'ACGTUN' if x in counts]) / sum(counts.values())) > 0.8:
                stype = 'rna' if 'U' in counts else 'dna'
            # Otherwise set as ambibuous
            else:
                stype = 'ambiguous'
        # If none of these match, something is horribly wrong with your
        # sequence
        else:
            stype = 'illegal'
        self.ntype[stype] += 1
        return(stype)

class SeqStat:
    def __init__(self, seq, count=True):
        self.counts = Counter(seq.seq) if count else None
        self.header = seq.header
        self.length = len(seq.seq)

    def aslist(self,
               charset=None,
               length=False,
               masked=False,
               header_fun=None,
               ignorecase=False):

        if not charset:
            charset = set(self.counts)
        line = []
        if header_fun:
            try:
                line.append(header_fun(self.header))
            except TypeError:
                print ("Cannot process header: '{}'".format(self.header))
                raise SystemExit
        if length:
            line.append(self.length)

        if masked:
            line.append(sum_lower(self.counts))

        if ignorecase:
            charset = set(''.join(charset).upper())
            self.counts = counter_caser(self.counts)

        line += [self.counts[c] for c in sorted(charset)]

        return(line)

    @classmethod
    def getheader(cls, charset, length=False, masked=False, ignorecase=False):
        header = ['seqid']

        if ignorecase:
            charset = set(''.join(charset).upper())

        if length:
            header += ['length']

        if masked:
            header += ['masked']

        header += list(sorted(charset))

        return(header)

class FileStat:
    def __init__(self):
        self.counts = Counter()
        self.nseqs = 0
        self.lengths = []

    def add_seq(self, stat):
        if stat.counts:
            self.counts += stat.counts
        self.nseqs += 1
        self.lengths.append(stat.length)

class ParseHeader:
    def firstword(h):
        return(re.sub('^(\S+).*', '\\1', h))

    def ncbi_format(h, fields):
        raise NotImplemented

    def regex_group(h, regex):
        raise NotImplemented

class StatFun:
    @classmethod
    def N50(cls, x, issorted=False):
        x = sorted(x) if not issorted else x
        N = sum(x)
        total = 0
        for i in range(len(x)-1, -1, -1):
            total += x[i]
            if total > N / 2:
                return(x[i])

    @classmethod
    def mean(cls, x):
        return(sum(x) / len(x))

    @classmethod
    def median(cls, x, issorted=False):
        return(cls.quantile(x, 0.5, issorted=issorted))

    @classmethod
    def sd(cls, x):
        if(len(x) < 2):
            return('NA')
        else:
            mean = sum(x) / len(x)
            stdev = (sum((y - mean) ** 2 for y in x) / (len(x) - 1)) ** 0.5
            return(stdev)
        return(sd)

    @classmethod
    def quantile(cls, x, q, issorted=False):
        '''
        Calculates quantile as the weighted average between indices
        '''
        # Die if out of bounds
        if not (0 <= q <= 1):
            print('quantile must be between 0 and 1', file=sys.stderr)
            raise SystemExit

        # Ensure the vector is sorted
        x = sorted(x) if not issorted else x

        # Return max or min for q = 1 or 0
        if q == 1:
            return(x[-1])
        elif q == 0:
            return(x[0])

        v = (len(x) - 1) * q
        r = v % 1
        i = math.floor(v)
        quantile = x[i] * (1-r) + x[i+1] * r
        return(quantile)

    @classmethod
    def summary(cls, x):
        x = sorted(x)
        out = {
            'min':x[0],
            'max':x[-1],
            '1st_qu':cls.quantile(x, 0.25, issorted=True),
            'median':cls.quantile(x, 0.50, issorted=True),
            '3rd_qu':cls.quantile(x, 0.75, issorted=True),
            'mean':cls.mean(x),
            'sd':cls.sd(x),
            'N50':cls.N50(x, issorted=True)
        }
        return(out)


# =================
# UTILITY FUNCTIONS
# =================

def csvrowGenerator(filename):
    try:
        f = open(filename, 'r')
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        reader = csv.reader(f, dialect)
    except IOError as e:
        print(e)
        sys.exit(0)
    for row in reader:
        yield row

def counter_caser(counter, lower=False):
    '''
    Sums cases in Collections.Counter object
    '''
    if lower:
        counts_obj = Counter({k:v for k,v in counter.items() if k.islower()}) + \
                     Counter({k.lower():v for k,v in counter.items() if k.isupper()})
    else:
        counts_obj = Counter({k:v for k,v in counter.items() if k.isupper()}) + \
                     Counter({k.upper():v for k,v in counter.items() if k.islower()})
    return(counts_obj)

def sum_lower(counter):
    lc = [v for k,v in counter.items() if k in string.ascii_lowercase]
    return(sum(lc))


# ====================
# ONE-BY-ONE FUNCTIONS
# ====================

class Subcommand:
    def __init__(self, parser_obj, write=True):
        self.func = self.write if write else self.generator
        self.usage = parser_obj.usage
        self.subparsers = parser_obj.subparsers
        self._parse()

    def _parse(self):
        raise NotImplemented

    def generator(self, args, gen):
        raise NotImplemented

    def write(self, args, gen):
        for out in self.generator(args, gen):
            if(isinstance(out, FSeq)):
                out.print()
            else:
                print(out)

class Chksum(Subcommand):
    def _parse(self):
        cmd_name = 'chksum'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Calculate an md5 checksum for the input sequences"
        )
        parser.add_argument(
            '-i', '--ignore-case',
            help='Convert all to uppercase, before hashing',
            action='store_true',
            default=False
        )
        method = parser.add_mutually_exclusive_group(required=False)
        method.add_argument(
            '-w', '--whole-file',
            help='Calculate single md5sum for all headers and sequences (default action)',
            action='store_true',
            default=False
        )
        method.add_argument(
            '-q', '--each-sequence',
            help='Calculate md5sum for each sequence, write as TAB delimited list',
            action='store_true',
            default=False
        )
        method.add_argument(
            '-s', '--all-sequences',
            help='Calculate single md5sum for all sequences',
            action='store_true',
            default=False
        )
        method.add_argument(
            '-d', '--all-headers',
            help='Calculate single md5sum for all headers',
            action='store_true',
            default=False
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        from hashlib import md5
        md5hash = md5()
        # Hash the sequences only (in input order)
        if(args.all_sequences):
            fun = lambda s,h: md5hash.update(s)
        # Hash the headers only (in input order)
        elif(args.all_headers):
            fun = lambda s,h: md5hash.update(h)
        # DEFAULT: Hash each header-sequence pair
        else:
            fun = lambda s,h: md5hash.update(h + b'\n' + s)

        for seq in gen.next():
            if args.ignore_case:
                if args.all_headers or args.whole_file :
                    seq.header_upper()
                if not args.all_headers:
                    seq.seq_upper()
            s = seq.seq.encode('ascii')
            h = seq.header.encode('ascii')
            # Write <header>\t<sequence hash> for each sequence
            if(args.each_sequence):
                yield h.decode() + '\t' + md5(s).hexdigest()
            else:
                fun(s,h)

        # Print output hash for cumulative options
        if not args.each_sequence:
            yield md5hash.hexdigest()

class Complexity(Subcommand):
    def _parse(self):
        cmd_name = 'complexity'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help='Calculates linguistic complexity'
        )
        parser.add_argument(
            '-k', '--alphabet-size',
            help='Number of letters in the alphabet (4 for DNA, 20 for proteins)',
            type=int,
            metavar='INT',
            default=4
        )
        parser.add_argument(
            '-w', '--window-length',
            help='Window length (if provided, output will average of window complexities)',
            type=int,
            metavar='INT',
            default=100
        )
        parser.add_argument(
            '-m', '--word-length',
            help='Length of each word',
            type=int,
            metavar='INT',
            default=1
        )
        parser.add_argument(
            '-j', '--jump',
            help='Distance between adjacent windows',
            type=int,
            metavar='INT',
            default=1
        )
        parser.add_argument(
            '-o', '--offset',
            help='Index of start point',
            type=int,
            metavar='INT',
            default=0
        )
        parser.add_argument(
            '-d', '--drop',
            help="Drop sequence if contains this character (e.g. 'X' or 'N')",
            metavar='CHAR',
            default=None
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        try:
            w = int(args.window_length)
            m = int(args.word_length)
            k = pow(int(args.alphabet_size), m)
            p = int(args.jump)
            offset = int(args.offset)
        except ValueError:
            print('All values must be integers', file=sys.stderr)
            raise SystemExit

        # Calculates the variable component of a single window's score
        def varscore_generator(seq, words):
            for i in range(offset, len(seq) - w + 1, p):
                counts = defaultdict(int)
                for j in range(i, i+w):
                    try:
                        counts[words[j]] += 1
                    except IndexError:
                        break
                yield sum([math.log(math.factorial(x), k) for x in counts.values()])

        w_fact = math.log(math.factorial(w), k)

        seq_id = 0
        for seq in gen.next():
            seq_id += 1
            mean = 'NA'
            var = 'NA'
            if(len(seq.seq) < w + offset): pass
            elif(args.drop and args.drop in seq.seq): pass
            else:
                words = tuple(seq.seq[i:i+m] for i in range(offset, len(seq.seq) - m + 1))
                varscores = tuple(score for score in varscore_generator(seq.seq, words))
                winscores = tuple((1 / w) * (w_fact - v) for v in varscores)
                mean = sum(winscores) / len(winscores)
                try:
                    var = sum([pow(mean - x, 2) for x in winscores]) / (len(varscores) - 1)
                except ZeroDivisionError:
                    var = 'NA'
                try:
                    col1 = seq.getvalue('gb', quiet=True)
                except:
                    col1 = seq_id
                yield "{},{},{}".format(col1, mean, var)

class Clean(Subcommand):
    def _parse(self):
        cmd_name = 'clean'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Masks things (optionally), pretty prints")
        parser.add_argument(
            '-t', '--type',
            metavar='n|p',
            help='Sequence type'
        )
        parser.add_argument(
            '-u', '--toupper',
            help="Convert to uppercase",
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-l', '--tolower',
            help="Convert to lowercase",
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-x', '--toseq',
            help="Removes all nonletter characters (gaps, stops, etc.)",
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-r', '--mask-irregular',
            help="Converts irregular letters to unknown",
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-m', '--mask-lowercase',
            help='Convert lower-case to unknown',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '--nir',
            help='Nucleotide irregulars [default=(not ACGT)]',
            metavar='STR',
            default=''.join(set(string.ascii_letters) - set('ACGTNacgtn'))
        )
        parser.add_argument(
            '--pir',
            metavar='STR',
            help='Protein irregulars [default=BJOUZbjouz]',
            default='BJOUXZbjouxz'
        )
        parser.add_argument(
            '--nunk',
            metavar='CHAR',
            help='Nucleotide unknown character (default=N)',
            default='N'
        )
        parser.add_argument(
            '--punk',
            metavar='CHAR',
            help='Protein unknown character (default=X)',
            default='X'
        )
        parser.set_defaults(func=self.func)

    def _process_args(self, args):
        if (args.mask_lowercase or args.mask_irregular) and not args.type:
            print('Please provide sequence type (--type)', file=sys.stderr)
            raise SystemExit

        if args.tolower and args.toupper:
            print('Err, you want me to convert to lower AND upper?', file=sys.stderr)
            raise SystemExit

    def generator(self, args, gen):

        # Catches illegal combinations of arguments
        self._process_args(args)

        # Make translator, this is only possible if type is given
        trans = None
        if args.type:
            if args.type.lower()[0] in ['a', 'p']:
                irr = args.pir
                unk = args.punk
            elif args.type.lower()[0] in ['n', 'd']:
                irr = args.nir
                unk = args.nunk
            else:
                print('Type not recognized', file=sys.stderr)
                raise SystemExit

            a = ''
            # Get irregular characters
            if args.mask_irregular:
                a += irr

            # convert lowercase to unknown
            if args.mask_lowercase:
                a += string.ascii_lowercase

            a = ''.join(set(a))

            b = unk * len(a)
            if irr:
                trans = str.maketrans(a, b)

        for seq in gen.next():
            # Irregular or lowercase to unknown
            if trans:
                seq.seq = seq.seq.translate(trans)

            # Change everything to desired case
            if args.toupper:
                seq.seq = seq.seq.upper()
            elif args.tolower:
                seq.seq = seq.seq.lower()

            # Remove all nonletters or wanted, otherwise just remove space
            if args.toseq:
                seq.seq = re.sub('[^A-Za-z]', '', seq.seq)
            else:
                seq.seq = re.sub('[^\S]', '', seq.seq)

            yield seq

class Stat(Subcommand):
    def _parse(self):
        cmd_name = 'stat'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Calculate sequence statistics")
        parser.add_argument(
            '-d', '--delimiter',
            help='Output delimiter'
        )
        parser.add_argument(
            '-q', '--byseq',
            help='Write a line for each sequence',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '-I', '--case-sensitive',
            help='Match case',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '-m', '--count-lower',
            help='Count the number of lowercase characters',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '-c', '--counts',
            help='Write counts of all characters',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '-l', '--length',
            help='Write sequence length',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '-p', '--proportion',
            help='Write proportion of each character',
            default=False,
            action='store_true'
        )
        parser.set_defaults(func=self.func)

    def _process_args(self, args):
        # If no output options are specified, do length stats
        if not any((args.counts, args.length, args.proportion, args.count_lower)):
            args.length = True
        return(args)

    def _byfile(self, args, gen):
        g = FileStat()
        # Do I need to count the characters? (much faster if I don't)
        need_count = args.counts or args.proportion or args.count_lower
        for seq in gen.next():
            g.add_seq(SeqStat(seq, count=need_count))

        if need_count:
            lower = sum_lower(g.counts) if args.count_lower else None

            if not args.case_sensitive:
                g.counts = counter_caser(g.counts)

            N = sum(g.lengths)
            slen = str(len(str(max(g.counts.values()))) + 2)
            count_iter = sorted(g.counts.items(), key=lambda x: -x[1])
            if args.counts ^ args.proportion:
                for k,v in count_iter:
                    val = v/N if args.proportion else v
                    if args.counts:
                        exp = "{}{:>%sd}" % slen
                    else:
                        exp = "{}{:>11.5%}"
                    yield(exp.format(k,val))
            elif args.counts and args.proportion:
                for k,v in count_iter:
                    outstr = "{}{:>" + slen + "d}{:>11.5%}"
                    yield(outstr.format(k,v,v/N))

            if args.count_lower:
                yield("{:10s} {} ({:.1%})".format('lower:', lower, lower/N))

        if args.length:
            total = sum(g.lengths)
            N = len(g.lengths)
            if N > 1:
                s = StatFun.summary(g.lengths)

                # Yield total number of sequences
                yield("{:10s} {}".format('nseq:', len(g.lengths)))

                # Yield totla number of letters
                yield("{:10s} {}".format('nchars:', sum(g.lengths)))

                # Yield five number summary of sequence lengths
                fivesum = [round(s[x]) for x in ('min','1st_qu','median','3rd_qu','max')]
                fivesum_str = "{:10s} {} {} {} {} {}"
                yield(fivesum_str.format('5sum:', *fivesum))

                # Yield mean and standard deviation
                meansd_str="{:10s} {:d} ({:d})"
                yield(meansd_str.format('mean(sd):', round(s['mean']), round(s['sd'])))

                # Yield N50
                yield("{:10s} {}".format('N50:', s['N50']))
            else:
                lstr = ', '.join([str(x) for x in sorted(g.lengths)])
                yield("nchars: {}".format(lstr))

    def _byseq(self, args, gen):
        seqlist = []
        charset = set()
        if args.length and not (args.counts or args.proportion):
            delimiter = args.delimiter if args.delimiter else '\t'
            for seq in gen.next():
                seqid = ParseHeader.firstword(seq.header)
                yield("{}{}{}".format(seqid, delimiter, len(seq.seq)))
        else:
            for seq in gen.next():
                seqstat = SeqStat(seq)
                seqlist.append(seqstat)
                charset.update(seqstat.counts)

            delimiter = args.delimiter if args.delimiter else ','
            joiner = lambda s,d: '{}'.format(d).join([str(x) for x in s])

            ignorecase = not args.case_sensitive
            kwargs = {'masked':args.count_lower,
                    'length':args.length,
                    'ignorecase':ignorecase}

            yield joiner(SeqStat.getheader(charset, **kwargs), delimiter)

            for q in seqlist:
                line = q.aslist(charset=charset,
                                header_fun=ParseHeader.firstword,
                                **kwargs)
                yield(joiner(line, delimiter))

    def generator(self, args, gen):
        args = self._process_args(args)
        if args.byseq:
            g = self._byseq(args, gen)
        else:
            g = self._byfile(args, gen)
        for item in g:
            yield(item)

class Subseq(Subcommand):
    def _parse(self):
        cmd_name = 'subseq'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Extract subsequence from each entry")
        parser.add_argument(
            'bounds',
            help="from and to values (indexed from 1)",
            nargs=2,
            type=int)
        parser.add_argument(
            '-r', '--revcomp',
            help='Take the reverse complement if bounds[0] > bounds[1]',
            action='store_true',
            default=False)
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        ''' Index starting from 1 (not 0) '''
        for seq in gen.next():
            a = args.bounds[0]
            b = args.bounds[1]
            # If a > b, take reverse complement if that option is enabled,
            # if not die
            if(a > b):
                if(args.revcomp):
                    newseq = FSeq.getrevcomp(seq.seq[b-1:a])
                else:
                    print('Lower bound cannot be greater than upper bound ' + \
                        '(do you want reverse complement? See options)', file=sys.stderr)
                    sys.exit()
            # If b >= a, this is a normal forward sequence
            else:
                newseq = seq.seq[a-1:b]
            yield FSeq(seq.header, newseq)

class Fasta2csv(Subcommand):
    def _parse(self):
        cmd_name = 'fasta2csv'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Converts a fasta file to 2-column csv")
        parser.add_argument(
            '-d', '--delimiter',
            help="Set delimiter (',' by default)",
            metavar='CHAR',
            default=',')
        parser.add_argument(
            '-r', '--header',
            help='Write header (default=False)',
            action='store_true',
            default=False)
        parser.add_argument(
            '-f', '--fields',
            help='Extract given fields from the header',
            metavar='STR',
            nargs='+')
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        if(args.header):
            if(args.fields):
                yield args.fields + ['seq']
            else:
                yield ['header', 'seq']
        for seq in gen.next():
            if(args.fields):
                row = [seq.getvalue(field) for field in args.fields]
            else:
                row = [seq.header]
            yield tuple(row + [seq.seq])

    def write(self, args, gen):
        w = csv.writer(sys.stdout, delimiter=args.delimiter)
        for row in self.generator(args, gen):
            w.writerow(row)

class Perm(Subcommand):
    def _parse(self):
        cmd_name = 'perm'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Randomly order sequence"
        )
        parser.add_argument(
            '-w', '--word-size',
            help='Size of each word (default=1)',
            type=int,
            metavar='INT',
            default=1
        )
        parser.add_argument(
            '-s', '--start-offset',
            help='Number of letters to ignore at beginning (default=0)',
            type=int,
            metavar='INT',
            default=0
        )
        parser.add_argument(
            '-e', '--end-offset',
            help='Number of letters to ignore at end (default=0)',
            type=int,
            metavar='INT',
            default=0
        )
        parser.add_argument(
            '-f', '--field',
            metavar='STR',
            help="Header field (e.g. 'gi' or 'locus')"
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        w = args.word_size
        start = args.start_offset
        end = args.end_offset
        for seq in gen.next():
            s = seq.seq
            L = len(s)
            prefix = s[0:start]
            suffix = s[L-end:L]
            rseq = s[start:L-end]
            M = len(rseq)
            words = list(rseq[i:i+w] for i in range(0, M - w + 1, w))
            words.append(rseq[(M - M % w):M])
            random.shuffle(words)
            out = ''.join(prefix + ''.join(words) + suffix)
            if(args.field):
                header='|'.join((args.field, seq.getvalue(args.field), 'start', str(start), 'end', str(end), 'word_size', str(w)))
            else:
                header=seq.header
            yield FSeq(header, out)

class Sniff(Subcommand):
    def _parse(self):
        cmd_name = 'sniff'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Extract info about the sequence"
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        seqsum = FileDescription()
        for seq in gen.next():
            seqsum.add_seq(seq)
        yield seqsum

    def write(self, args, gen):
        seqsum = next(self.generator(args, gen))
        nseqs = sum(seqsum.ncase.values())

        has_degen_headers = nseqs != len(seqsum.headers)
        has_degen_seqs = nseqs != len(seqsum.seqs)
        has_bad = seqsum.ntype['illegal'] != 0

        if has_degen_seqs:
            print("{} uniq sequences ({} total)".format(len(seqsum.seqs), nseqs))
        else:
            print("Total sequences: {}".format(nseqs))

        if has_degen_headers:
            print("WARNING: headers are not unique ({}/{})".format(len(seqsum.headers), nseqs))
        if has_bad:
            print("WARNING: illegal characters found")

        def write_dict(d, name, N):
            uniq = [[k,v] for  k,v in d.items() if v != 0]
            if len(uniq) == 1:
                print("All {}".format(uniq[0][0]))
            else:
                print("{}:".format(name))
                for k,v in sorted(uniq, key=lambda x: -x[1]):
                    print("  {:<20} {:<10} {:>7.4%}".format(k + ':', v, v/N))

        write_dict(seqsum.ntype, 'Sequence types', nseqs)
        write_dict(seqsum.ncase, 'Sequences cases', nseqs)

        nnucl = sum([v for k,v in seqsum.ntype.items() if k in {'dna', 'rna'}])
        nprot = sum([v for k,v in seqsum.ntype.items() if k == 'prot'])

        def write_feat(d, text, N):
            if not N:
                return(0)
            print(text)
            for k,v in sorted(list(d.items()), key=lambda x: -x[1]):
                print("  {:<20} {:<10} {:>7.4%}".format(k + ':', v, v/N))

        write_feat(seqsum.nfeat, "Nucleotide Features:", nnucl)
        write_feat(seqsum.pfeat, "Protein Features:", nprot)
        write_feat(seqsum.ufeat, "Universal Features:", nseqs)

class Reverse(Subcommand):
    def _parse(self):
        cmd_name = 'reverse'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Reverse each sequence (NOT reverse complement)")
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        ''' Reverse each sequence '''
        for seq in gen.next():
            yield FSeq(seq.header, seq.seq[::-1])

class Winnow(Subcommand):
    def _parse(self):
        cmd_name = 'winnow'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Remove sequences which meet given conditions"
        )
        parser.add_argument(
            '-c', '--contain',
            metavar='STR',
            help="Remove if contains any of these characters"
        )
        parser.add_argument(
            '-C', '--not-contain',
            metavar='STR',
            help="Remove if contains any of these characters"
        )
        parser.add_argument(
            '-s', '--shorter-than',
            help="Remove if sequence is shorter than i",
            metavar='INT',
            type=int
        )
        parser.add_argument(
            '-S', '--longer-than',
            help="Remove if sequence is longer than i",
            metavar='INT',
            type=int
        )
        parser.add_argument(
            '-v', '--invert',
            help="Invert selection",
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-p', '--composition',
            metavar='EXPR',
            help="Composition (e.g. -p 'GC < 0.5')"
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        tests = []
        if args.contain:
            tests.append(lambda s, v=args.contain: bool(set(v) & set(s)))
        if args.not_contain:
            tests.append(lambda s, v=args.not_contain: bool(set(v) & set(s)))
        if args.longer_than:
            tests.append(lambda s, v=args.longer_than: len(s) > v)
        if args.shorter_than:
            tests.append(lambda s, v=args.shorter_than: len(s) < v)
        if args.composition:
            try:
                ch,sign,per = args.composition.split()
            except ValueError:
                print('Composition argument have 3 values', file=sys.stderr)
                raise SystemExit
            legal_signs = ('<', '<=', '>=', '>', '==')
            if not sign in legal_signs:
                print("Middle term must be a comparison symbol ('<', '<=', '>=', '>', '==')", file=sys.stderr)
                raise SystemExit
            try:
                per = float(per)
            except ValueError:
                print("Third value must be a float")
                raise SystemExit
            if not 0 <= per <= 1:
                print("Third value must be between 0 and 1")
                raise SystemExit
            ch = set(str(ch))

            def evaluate(s):
                c = Counter(s)
                p = sum([c[x] for x in ch]) / len(s)
                return(eval('p {} {}'.format(sign, per)))

            tests.append(evaluate)


        for seq in gen.next():
            reject = [x(seq.seq) for x in tests]
            if (any(reject) and args.invert) or (not any(reject) and not args.invert):
                yield seq


# ==============
# FULL FUNCTIONS
# ==============

class Sample(Subcommand):
    def _parse(self):
        cmd_name = 'sample'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Randomly select entries from fasta file")
        parser.add_argument(
            'n',
            help="Sample size",
            type=int,
            default=1)
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        ''' Randomly sample n entries from input file '''
        seqs = [s for s in gen.next()]
        sample_indices = random.sample(range(len(seqs)), min(len(seqs), args.n))
        for i in sample_indices:
            yield seqs[i]

class Split(Subcommand):
    def _parse(self):
        cmd_name = 'split'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help='Split a multifasta file into k smaller files'
        )
        parser.add_argument(
            '-n', '--nfiles',
            help='Number of output files'
        )
        parser.add_argument(
            '-p', '--prefix',
            help='Prefix for output files',
            default='xxx'
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        for s in gen.next():
            yield s

    def write(self, args, gen):
        k = int(args.nfiles)
        p = args.prefix
        seqs = list(self.generator(args, gen))
        for i in range(0, k):
            begin = i * (len(seqs) // k + 1)
            end = min(len(seqs), (i+1) * (len(seqs) // k + 1))
            outfile = p + str(i) + '.fasta'
            with open(outfile, 'w+') as fo:
                for seq in (seqs[x] for x in range(begin, end)):
                    fo.write(seq.get_pretty_string() + '\n')

class Sort(Subcommand):
    def _parse(self):
        cmd_name = 'sort'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Sort sequences by given fields")
        parser.add_argument(
            'fields',
            help="Header fields by which to sort sequences",
            nargs='+')
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        seqs = [s for s in gen.next()]
        seqs.sort(key=lambda x: list(x.getvalue(y) for y in args.fields))
        for s in seqs:
            yield s


# ==============
# UNIX EMULATORS
# ==============

class Grep(Subcommand):
    def _parse(self):
        cmd_name = 'grep'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Roughly emulates the UNIX grep command"
        )
        parser.add_argument(
            'patterns',
            metavar='PATTERNS',
            help='Patterns to match',
            nargs='*'
        )
        parser.add_argument(
            '-q', '--match-sequence',
            help='Match sequence rather than header',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-f', '--file',
            metavar='FILE',
            type=argparse.FileType('r'),
            help='Obtain patterns from FILE, one per line'
        )
        parser.add_argument(
            '-w', '--wrap',
            metavar='REG',
            help='A regular expression to capture PATTERNS'
        )
        parser.add_argument(
            '-P', '--perl-regexp',
            help='Treat PATTERNS as perl regular expressions',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-B', '--ambiguous-nucl',
            help='Parse extended nucleotide alphabet',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-I', '--case-sensitive',
            help='DO NOT ignore case distinctions (ignore by default)',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-v', '--invert-match',
            help='Print non-matching entries',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-c', '--count',
            help='Print number of entries with matches',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-m', '--count-matches',
            help='Print number of non-overlapping matches',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-b', '--both-strands',
            help='Search both strands',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-r', '--reverse-only',
            help='Only search the reverse strand',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '--color',
            help='Print in color',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '--gff',
            help='Output matches in gff format',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '--gff-type',
            help='Name of searched feature',
            metavar='STR',
            default='regex_match'
        )
        parser.set_defaults(func=self.func)

    def _process_arguments(self, args):
        # Stop if there are any incompatible options
        if args.count_matches and args.invert_match:
            print('--count-matches argument is incompatible with --invert-matches',
                    file=sys.stderr)
            raise SystemExit

        if args.wrap and args.perl_regexp:
            print("PATTERNS found in --wrap captures must be literal ",
                  "(-P option and -w are incompatible)", file=sys.stderr)
            raise SystemExit

        if args.ambiguous_nucl:
            args.perl_regexp = True

        # Some things just don't make sense in header searches ...
        if args.gff or args.ambiguous_nucl:
            args.match_sequence = True

        # Others don't make sense with color
        if args.gff or args.count_matches and args.color:
            args.color = False

        if args.gff:
            args.count = False
            args.count_matches = False

        return(args)

    def _create_matcher(self, args, pat, wrapper):
        # Check existence for matches to wrapper captures
        def swrpmatcher(text, strand='.'):
            for m in re.finditer(wrapper, text):
                if m.group(1) in pat:
                    return(True)
            return(False)

        # Check existence of matches
        def spatmatcher(text, strand='.'):
            for p in pat:
                if re.search(p, text):
                    return(True)
            return(False)

        # Find locations of matches to wrappers
        def gwrpmatcher(text, strand='.'):
            pos = []
            for m in re.finditer(wrapper, text):
                if m.group(1) in pat:
                    match = {'pos':(m.start(), m.end()), 'strand':strand}
                    pos.append(match)
            return(pos)

        # Find locations of matches
        def gpatmatcher(text, strand='.'):
            pos = []
            for p in pat:
                for m in re.finditer(p, text):
                    match = {'pos':(m.start(), m.end()), 'strand':strand}
                    pos.append(match)
            return(pos)

        if args.gff or args.count_matches or args.color:
            matcher = gwrpmatcher if wrapper else gpatmatcher
        else:
            matcher = swrpmatcher if wrapper else spatmatcher

        if args.reverse_only or args.both_strands:
            if matcher.__name__ in ('swrmatcher', 'spatmatcher'):
                if args.reverse_only:
                    def rmatcher(text):
                        match = matcher(FSeq.getrevcomp(text))
                        return(match)
                else:
                    def rmatcher(text):
                        match = matcher(text) + matcher(FSeq.getrevcomp(text))
                        return(match)
            else:
                def rev(matcher, text):
                    rmatch = []
                    for d in matcher(FSeq.getrevcomp(text), strand='-'):
                        d['pos'] = (len(text) - d['pos'][1], len(text) - d['pos'][0])
                        rmatch.append(d)
                    return(rmatch)
                if args.reverse_only:
                    def rmatcher(text):
                        return(rev(matcher, text))
                else:
                    def rmatcher(text):
                        fmatch = matcher(text)
                        rmatch = rev(matcher, text)
                        return(fmatch + rmatch)
            return(rmatcher)
        else:
            return(matcher)

    def _get_pattern(self, args):
        pat = set()
        if args.file:
            pat.update([l.rstrip('\n') for l in args.file])
        if args.patterns:
            pat.update(args.patterns)

        if args.ambiguous_nucl:
            apat = set()
            for p in pat:
                perlpat = p
                for k,v in Maps.DNA_AMB.items():
                    perlpat = re.sub(k, '[%s]' % v, perlpat)
                apat.update([perlpat])
            pat = apat

        if not pat:
            print('Please provide a pattern', file=sys.stderr)
            raise SystemExit

        # TODO searching for perfect matches would be faster without using
        # regex (just <str>.find(pat))
        if not args.perl_regexp and not args.wrap:
            pat = [re.escape(p) for p in pat]

        return(pat)

    def _makegen(self, args):
        if args.match_sequence:
            gettext = lambda x: x.seq
        else:
            gettext = lambda x: x.header

        if args.gff:
            def sgen(gen, matcher):
                source = "smof-{}".format(__version__)
                gfftype = args.gff_type
                row = [None,    #1 seqid
                       source,  #2 source
                       gfftype, #3 type
                       None,    #4 start
                       None,    #5 end
                       '.',     #6 score
                       None,    #7 strand
                       '.',     #8 phase
                       '.'      #9 attributes
                      ]
                for seq in gen.next():
                    row[0] = re.sub('^>(\S+)', '\1', seq.header)
                    for m in matcher(seq.seq):
                        row[3] = m['pos'][0] + 1
                        row[4] = m['pos'][1]
                        row[6] = m['strand']
                        yield('\t'.join([str(s) for s in row]))

        elif args.count or args.count_matches:
            def sgen(gen, matcher):
                count, matches = 0, 0
                for seq in gen.next():
                    text = gettext(seq)
                    m = matcher(text)
                    if (m and not args.invert_match) or (not m and args.invert_match):
                        count += 1
                        try:
                            matches += len(m)
                        except:
                            pass
                if args.count and args.count_matches:
                    yield "{}\t{}".format(count, matches)
                elif args.count:
                    yield count
                elif args.count_matches:
                    yield matches
        else:
            def sgen(gen, matcher):
                for seq in gen.next():
                    text = gettext(seq)
                    m = matcher(text)
                    if (m and not args.invert_match) or (not m and args.invert_match):
                        if args.color:
                            coltext = ColorString(text)
                            for d in m:
                                coltext.colorpos(range(*d['pos']))
                            if args.match_sequence:
                                seq.colseq = coltext
                            else:
                                seq.colheader = coltext
                        yield(seq)
        return(sgen)

    def generator(self, args, gen):

        args = self._process_arguments(args)

        pat = self._get_pattern(args)

        flags = re.IGNORECASE if not args.case_sensitive else 0

        if args.wrap:
            wrapper = re.compile(args.wrap, flags=flags)
        else:
            pat = set((re.compile(p, flags=flags) for p in pat))
            wrapper = None

        matcher = self._create_matcher(args, pat, wrapper)

        sgen = self._makegen(args)

        for item in sgen(gen, matcher):
            yield item

class Uniq(Subcommand):
    def _parse(self):
        cmd_name = 'uniq'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Emulates UNIX uniq command (prior sorting needless)"
        )
        parser.add_argument(
            '-c', '--count',
            help='Writes (count|header) in tab-delimited format',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-d', '--repeated',
            help='Print only repeated entries',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-u', '--uniq',
            help='Print only unique entries',
            action='store_true',
            default=False
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        seqs = defaultdict(int)
        for seq in gen.next():
            seqs[seq] += 1

        if args.repeated:
            sgen = ((k,v) for k,v in seqs.items() if v > 1)
        elif args.uniq:
            sgen = ((k,v) for k,v in seqs.items() if v == 1)
        else:
            sgen = seqs.items()

        if args.count:
            for k,v in sgen:
                yield("{}\t{}".format(v, k.header))
        else:
            for k,v in sgen:
                yield(k)

class Wc(Subcommand):
    def _parse(self):
        cmd_name = 'wc'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Roughly emulates the UNIX wc command"
        )
        parser.add_argument(
            '-m', '--chars',
            help='Writes the summed length of all sequences',
            action='store_true',
            default=False
        )
        parser.add_argument(
            '-l', '--lines',
            help='Writes the total number of sequences',
            action='store_true',
            default=False
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        nchars, nseqs = 0, 0
        for seq in gen.next():
            nchars += len(seq.seq)
            nseqs += 1
        yield nseqs
        yield nchars

    def write(self, args, gen):
        nseqs, nchars = list(self.generator(args, gen))
        if args.chars and not args.lines:
            print(nchars)
        elif args.lines and not args.chars:
            print(nseqs)
        else:
            print("{}\t{}".format(nseqs, nchars))

class Rename(Subcommand):
    def _parse(self):
        cmd_name = 'rename'
        parser = self.subparsers.add_parser(
            cmd_name,
            usage=self.usage.format(cmd_name),
            help="Larry Wall's rename pythonized for headers"
        )
        parser.add_argument(
            'pattern',
            metavar='PATTERN',
            help="Regex pattern"
        )
        parser.add_argument(
            'replacement',
            metavar='REPLACEMENT',
            nargs='?',
            default='',
            help="Regex replacement (default='', i.e. delete PATTERN)"
        )
        parser.add_argument(
            'headers',
            metavar='HEADERS',
            nargs='?',
            default=None,
            help="Regex to select headers (if not supplied, select all)"
        )
        parser.set_defaults(func=self.func)

    def generator(self, args, gen):
        matcher = re.compile(args.headers) if args.headers else None
        for seq in gen.next():
            if not matcher or re.search(matcher, seq.header):
                seq.header = re.sub(args.pattern, args.replacement, seq.header)
            yield seq


# =======
# EXECUTE
# =======

if __name__ == '__main__':
    gen = FSeqGenerator()
    args = parse()
    args.func(args, gen)
