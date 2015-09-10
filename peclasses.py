#! python3
import struct
import bisect
import collections
from collections import OrderedDict
from array import array

from disasm import align


class Structure:
    _struct = struct.Struct('L')

    @property
    @classmethod
    def sizeof(cls):
        return cls._struct.size

    _field_names = ('foo',)
    _formatters = '%x'.split()

    def __init__(self, *args, **kwargs):
        if len(args) > 0:
            assert len(args) == len(self._field_names)
            self.raw = None
            self.items = OrderedDict(zip(self._field_names, args))
        elif len(kwargs) > 0:
            assert all(field in kwargs for field in self._field_names)
            assert all(key in self._field_names for key in kwargs)
            self.raw = None
            self.items = OrderedDict(zip(self._field_names, (kwargs[key] for key in self._field_names)))

    @classmethod
    def from_bytes(cls, buffer):
        new_obj = cls(cls._struct.unpack(buffer))
        new_obj.raw = buffer
        return new_obj

    @classmethod
    def read(cls, file, offset=None):
        if offset is not None:
            file.seek(offset)

        raw = file.read(cls.sizeof)
        new_obj = cls(*cls._struct.unpack(raw))
        new_obj.raw = raw
        return new_obj

    def __getattr__(self, attr):
        return self.items[attr]

    def __iter__(self):
        return iter(self.items.values())

    def __bytes__(self):
        return self._struct.pack(*self)

    def write(self, file, offset=None):
        if offset is not None:
            file.seek(offset)

        file.write(bytes(self))

    def __repr__(self):
        return 'Section(%s)' % ', '.join('%s=%s' % (name, self._formatters[i] % self.items[name])
                                         for i, name in enumerate(self._field_names))


class ImageDosHeader:
    sizeof = 0x40

    def __init__(self, file, offset=0):
        file.seek(offset)
        self.raw = file.read(self.sizeof)
        self.signature = self.raw[:2]
        if self.signature != b'MZ':
            raise ValueError('IMAGE_DOS_HEADER wrong signature: %r' % self.signature)
        self.e_lfanew = int.from_bytes(self.raw[0x3C:], 'little')


class ImageFileHeader:
    sizeof = 0x14
    _template = '2H 3L 2H'
    _field_names = ('machine', 'number_of_sections', 'timedate_stamp', 'pointer_to_symbol_table',
                    'number_of_symbols', 'size_of_optional_header', 'characteristics')
    _formatters = '0x%x %d 0x%x 0x%x %d 0x%x 0x%x'.split()

    def __init__(self, file, offset=None):
        if offset is not None:
            file.seek(offset)
        else:
            offset = file.tell()
        self.offset = offset
        self.raw = file.read(self.sizeof)
        self.items = OrderedDict(zip(self._field_names, struct.unpack(self._template, self.raw)))
    
    def __getattr__(self, attr):
        return self.items[attr]

    def __str__(self):
        return 'ImageFileHeader(\n\t%s\n)' % ',\n\t'.join('%s=%s' % (name, self._formatters[i] % self.items[name])
                                                          for i, name in enumerate(self._field_names))


class DataDirectoryEntry:
    __slots__ = ('virtual_address', 'size')
    _struct = struct.Struct('2L')
    sizeof = _struct.size

    def __init__(self, virtual_address, size):
        self.virtual_address = virtual_address
        self.size = size

    def __iter__(self):
        yield self.virtual_address
        yield self.size

    @classmethod
    def iter_unpack(cls, data):
        return (cls(*x) for x in cls._struct.iter_unpack(data))

    @classmethod
    def unpack(cls, data):
        return cls(*(cls._struct.unpack(data)))

    def __bytes__(self):
        return self._struct.pack(*self)

    def __repr__(self):
        return self.__class__.__name__ + '(virtual_address=%s, size=%s)' % tuple(hex(x) for x in self)


class DataDirectory:
    _number_of_directory_entries = 16
    sizeof = DataDirectoryEntry.sizeof * _number_of_directory_entries
    _field_names = ('export', 'import', 'resource', 'exception', 'security', 'basereloc', 'debug', 'copyright',
                    'globalptr', 'tls', 'load_config', 'bound_import', 'iat', 'delay_import', 'com_descriptor')

    def __init__(self, raw):
        self.items = OrderedDict(zip(self._field_names, DataDirectoryEntry.iter_unpack(raw)))
        self.offset = None

    def __getattr__(self, attr):
        return self.items[attr]

    def __bytes__(self):
        return bytes(b''.join(bytes(self.items[field]) for field in self._field_names) +
                     bytes(DataDirectoryEntry.sizeof))

    def __str__(self):
        return 'DataDirectory(\n\t%s\n)' % ',\n\t'.join('%-14s = %s' % (name, self.items[name])
                                                        for i, name in enumerate(self._field_names))


class ImageOptionalHeader:
    _struct = struct.Struct('H B B 9L 6H 4L 2H 6L')
    _field_names = (
        'magic', 'major_linker_version', 'minor_linker_version', 'size_of_code',
        'size_of_initialized_data', 'size_of_uninitialized_data', 'address_of_entry_point', 'base_of_code',
        'base_of_data', 'image_base', 'section_alignment', 'file_alignment',
        'major_operating_system_version', 'minor_operating_system_version',
        'major_image_version', 'minor_image_version',
        'major_subsystem_version', 'minor_subsystem_version',
        'win32_version_value', 'size_of_image', 'size_of_headers', 'check_sum',
        'subsystem', 'dll_characteristics', 'size_of_stack_reserve', 'size_of_stack_commit',
        'size_of_heap_reserve', 'size_of_heap_commit', 'loader_flags', 'number_of_rva_and_sizes'
    )

    _formatters = '''
        0x%x %d %d 0x%x
        0x%x 0x%x 0x%x 0x%x
        0x%x 0x%x 0x%x 0x%x
        %d %d
        %d %d
        %d %d
        %d 0x%x 0x%x 0x%x
        %d 0x%x 0x%x 0x%x
        0x%x 0x%x 0x%x 0x%x
    '''.split()

    _data_directory_offset = 0x60

    def __init__(self, file, offset=None, sizeof=224):
        if offset is not None:
            file.seek(offset)
        else:
            offset = file.tell()
        self.offset = offset
        self.sizeof = sizeof
        self.raw = file.read(self.sizeof)
        self.items = OrderedDict(zip(self._field_names,
                                     self._struct.unpack(self.raw[:self._data_directory_offset])))

        self._data_directory = DataDirectory(self.raw[self._data_directory_offset:])
        self._data_directory.offset = offset + self._data_directory_offset

    def __getattr__(self, attr):
        if attr == 'data_directory':
            return self._data_directory
        else:
            return self.items[attr]

    def __iter__(self):
        return (self.items[field] for field in self._field_names)

    def __bytes__(self):
        return self._struct.pack(*self)

    def __str__(self):
        return 'ImageOptionalHeader(\n\t%s\n)' % ',\n\t'.join('%s=%s' % (name, self._formatters[i] % self.items[name])
                                                              for i, name in enumerate(self._field_names))


class ImageNTHeaders:
    def __init__(self, file, offset):
        self.offset = offset
        file.seek(offset)
        self.signature = file.read(4)
        if self.signature != b'PE\0\0':
            raise ValueError('IMAGE_NT_HEADERS wrong signature: %r' % self.signature)
        self.file_header = ImageFileHeader(file)
        assert self.file_header.size_of_optional_header == 224
        self.optional_header = ImageOptionalHeader(file)
        self.sizeof = len(self.signature) + self.file_header.sizeof + self.optional_header.sizeof


class Section(Structure):
    IMAGE_SCN_CNT_CODE = 0x00000020
    IMAGE_SCN_CNT_INITIALIZED_DATA = 0x00000040
    IMAGE_SCN_CNT_UNINITIALIZED_DATA = 0x00000080
    IMAGE_SCN_MEM_DISCARDABLE = 0x02000000
    IMAGE_SCN_MEM_SHARED = 0x10000000
    IMAGE_SCN_MEM_EXECUTE = 0x20000000
    IMAGE_SCN_MEM_READ = 0x40000000
    IMAGE_SCN_MEM_WRITE = 0x80000000

    _struct = struct.Struct('8s4L12xL')
    sizeof = _struct.size
    _field_names = ('name', 'virtual_size', 'rva', 'physical_size', 'physical_offset', 'flags')
    _formatters = '%s 0x%x 0x%x 0x%x 0x%x 0x%x'.split()

    def offset_to_rva(self, offset):
        return offset - self.physical_offset + self.rva

    def rva_to_offset(self, rva):
        return rva - self.rva + self.physical_offset


class ImageSectionHeader(Structure):
    _struct = struct.Struct('8s 6L 2H L')
    sizeof = _struct.size
    assert sizeof == Section.sizeof
    _field_names = (
        'name', 'physical_address', 'virtual_address', 'size_of_raw_data', 'pointer_to_raw_data',
        'pointer_to_relocations', 'pointer_to_linenumbers', 'number_of_relocations', 'number_of_linenumbers',
        'characteristics'
    )
    _formatters = '''
        %s 0x%x 0x%x 0x%x 0x%x
        0x%x 0x%x %d %d 0x%x
    '''.split()

    def offset_to_rva(self, offset):
        return offset - self.pointer_to_raw_data + self.virtual_address

    def rva_to_offset(self, virtual_address):
        return virtual_address - self.virtual_address + self.pointer_to_raw_data


class Key:
    def __init__(self, iterable, key):
        self.iterable = iterable
        self.key = key

    def __len__(self):
        return len(self.iterable)

    def __getitem__(self, i):
        return self.key(self.iterable[i])


class SectionTable(list):
    def __init__(self, sections):
        super().__init__(sections)
        # Make auxiliary objects to perform bisection search among physical offsets and rvas:
        self._offset_key = Key(self, lambda x: x.physical_offset)
        self._rva_key = Key(self, lambda x: x.rva)
        assert all(x.rva < self[i+1].rva for i, x in enumerate(self[:-1]))
        assert all(x.physical_offset < self[i+1].physical_offset for i, x in enumerate(self[:-1]))

    @classmethod
    def read(cls, file, offset, number):
        file.seek(offset)
        return cls([Section.read(file) for _ in range(number)])

    def write(self, file, offset=None):
        if offset is not None:
            file.seek(offset)

        for section in self:
            file.write(bytes(section))

    def offset_to_rva(self, offset):
        i = bisect.bisect(self._offset_key, offset) - 1
        return self[i].offset_to_rva(offset)

    def rva_to_offset(self, rva):
        i = bisect.bisect(self._rva_key, rva) - 1
        return self[i].rva_to_offset(rva)

    def which_section(self, offset=None, rva=None):
        if offset is not None:
            return bisect.bisect(self._offset_key, offset) - 1
        elif rva is not None:
            return bisect.bisect(self._rva_key, rva) - 1
        else:
            return None
    
    def __repr__(self):
        return 'SectionTable([\n\t%s\n])' % ',\n\t'.join(repr(x) for x in self)


class RelocationTable:
    IMAGE_REL_BASED_ABSOLUTE = 0
    IMAGE_REL_BASED_HIGHLOW = 3

    def __init__(self, table: dict):
        if not isinstance(table, dict):
            raise ValueError
        self._table = table

    def __iter__(self):
        for page, records in self._table.items():
            for record in records:
                yield page | (record & 0x0FFF)

    @classmethod
    def build(cls, relocs: collections.Iterable):
        reloc_table = dict()
        for item in relocs:
            page = item & 0xFFFFF000
            offset = item & 0x00000FFF
            if page not in reloc_table:
                reloc_table[page] = []
            bisect.insort(reloc_table[page], offset)
        return RelocationTable(reloc_table)

    @staticmethod
    def iter_read(file, reloc_size):
        cur_off = 0
        while cur_off < reloc_size:
            cur_page = int.from_bytes(file.read(4), 'little')
            block_size = int.from_bytes(file.read(4), 'little')
            assert (block_size > 8)
            assert ((block_size - 8) % 2 == 0)
            relocs = array('H')
            relocs.fromfile(file, (block_size - 8) // 2)
            yield cur_page, [x for x in relocs if x >> 12 == RelocationTable.IMAGE_REL_BASED_HIGHLOW]
            cur_off += block_size

    @classmethod
    def from_file(cls, file, reloc_size):
        return RelocationTable(dict(cls.iter_read(file, reloc_size)))

    @property
    def size(self):
        words = sum(align(len(val), 2) for val in self._table.values())
        return len(self._table) * 8 + words * 2

    def to_file(self, file):
        for page in sorted(self._table):
            records = [item | RelocationTable.IMAGE_REL_BASED_HIGHLOW << 12 for item in self._table[page]]
            # Padding records:
            if len(records) % 2 == 1:
                records.append(RelocationTable.IMAGE_REL_BASED_ABSOLUTE << 12 | 0)
            block_size = 8 + 2 * len(records)  # 2 dwords + N words
            array('L', [page, block_size]).tofile(file)
            array('H', records).tofile(file)


class PortableExecutable:
    def __init__(self, file):
        self.file = file
        self.dos_header = ImageDosHeader(file)
        self.nt_headers = ImageNTHeaders(file, self.dos_header.e_lfanew)
        self.file_header = self.nt_headers.file_header
        self.optional_header = self.nt_headers.optional_header
        self.data_directory = self.optional_header.data_directory
        self._section_table = None
        self._relocation_table = None

    @property
    def section_table(self):
        if self._section_table is None:
            n = self.file_header.number_of_sections
            offset = self.nt_headers.offset + self.nt_headers.sizeof
            self._section_table = SectionTable.read(self.file, offset, n)
        return self._section_table

    @property
    def relocation_table(self):
        if self._relocation_table is None:
            rva = self.data_directory.basereloc.virtual_address
            offset = self.section_table.rva_to_offset(rva)
            size = self.data_directory.basereloc.size
            self.file.seek(offset)
            self._relocation_table = RelocationTable.from_file(self.file, size)
        return self._relocation_table

    def reread(self):
        self.__init__(self.file)

    def info(self):
        return (
            'DOS signature: %s\n' % self.dos_header.signature +
            'e_lfanew: 0x%x\n' % self.dos_header.e_lfanew +
            'PE signature: %s\n' % self.nt_headers.signature +
            'Entry point address: 0x%x\n' % (self.optional_header.address_of_entry_point +
                                             self.optional_header.image_base) +
            '%s\n' % self.file_header +
            '%s\n' % self.optional_header +
            '%s\n' % self.data_directory +
            '%r\n' % self.section_table
        )


def main():
    with open(r"d:\Games\df_40_24_win_s\Dwarf Fortress.exe", 'rb') as file:
        pe = PortableExecutable(file)
        print(pe.info())
        assert pe.section_table.which_section(offset=pe.section_table[0].physical_offset-1) == -1
        assert pe.section_table.which_section(offset=pe.section_table[0].physical_offset) == 0
        assert pe.section_table.which_section(offset=pe.section_table[0].physical_offset+1) == 0

if __name__ == "__main__":
    main()
