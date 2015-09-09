#! python3
import struct
# from operator import itemgetter
from collections import OrderedDict, namedtuple


class ImageDosHeader:
    size = 0x40
    
    def __init__(self, file, offset=0):
        file.seek(offset)
        self.raw = file.read(self.size)
        self.signature = self.raw[:2]
        if self.signature != b'MZ':
            raise ValueError('IMAGE_DOS_HEADER wrong signature: %r' % self.signature)
        self.e_lfanew = int.from_bytes(self.raw[0x3C:], 'little')


class ImageFileHeader:
    size = 0x14
    _template = '2H 3L 2H'
    _field_names = ('machine', 'number_of_sections', 'timedate_stamp', 'pointer_to_symbol_table',
                    'number_of_symbols', 'size_of_optional_header', 'characteristics')
    _formatters = '0x%x %d 0x%x 0x%x %d 0x%x 0x%x'.split()

    def __init__(self, file, offset=None):
        if offset is not None:
            file.seek(offset)
        self.raw = file.read(self.size)
        self.items = OrderedDict(zip(self._field_names, struct.unpack(self._template, self.raw)))
    
    def __getattr__(self, attr):
        return self.items[attr]

    def __str__(self):
        return 'ImageFileHeader(%s)' % ', '.join('%s=%s' % (name, self._formatters[i] % self.items[name])
                                                 for i, name in enumerate(self._field_names))


data_directory_entry = namedtuple('data_directory_entry', ('virtual_address', 'size'))


class DataDirectory:
    _number_of_directory_entries = 16
    _field_names = ('export', 'import', 'resource', 'exception', 'security', 'basereloc', 'debug', 'copyright,'
                    'globalptr', 'tls', 'load_config', 'bound_import', 'iat', 'delay_import', 'com_descriptor')

    def __init__(self, raw):
        self.raw = raw
        self.items = OrderedDict(zip(self._field_names,
                                     (data_directory_entry._make(x) for x in struct.iter_unpack('LL', self.raw))))

    def __getattr__(self, attr):
        return self.items[attr]


class ImageOptionalHeader:
    _template = 'H B B 9L 6H 4L 2H 6L'
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

    _formatters = '''0x%x %d %d 0x%x
                     0x%x 0x%x 0x%x 0x%x
                     0x%x 0x%x 0x%x 0x%x
                     %d %d
                     %d %d
                     %d %d
                     %d 0x%x 0x%x 0x%x
                     %d 0x%x 0x%x 0x%x
                     0x%x 0x%x 0x%x 0x%x'''.split()

    _data_directory_offset = 0x60

    def __init__(self, file, offset=None, size=224):
        if offset is not None:
            file.seek(offset)
        self.size = size
        self.raw = file.read(self.size)
        self.items = OrderedDict(zip(self._field_names,
                                     struct.unpack(self._template, self.raw[:self._data_directory_offset])))

        self._data_directory = DataDirectory(self.raw[self._data_directory_offset:])

    def __getattr__(self, attr):
        if attr == 'data_directory':
            return self._data_directory
        else:
            return self.items[attr]

    def __str__(self):
        return 'ImageOptionalHeader(%s)' % ', '.join('%s=%s' % (name, self._formatters[i] % self.items[name])
                                                     for i, name in enumerate(self._field_names))


class ImageNTHeaders:
    def __init__(self, file, offset):
        self.offset = offset
        file.seek(offset)
        self.signature = file.read(4)
        assert self.signature == b'PE\0\0'
        if self.signature != b'PE\0\0':
            raise ValueError('IMAGE_NT_HEADERS wrong signature: %r' % self.signature)
        self.file_header = ImageFileHeader(file)
        assert self.file_header.size_of_optional_header == 224
        self.optional_header = ImageOptionalHeader(file)
        self.size = 4 + self.file_header.size + self.optional_header.size


class Section:
    _struct = struct.Struct('8s4L12xL')
    _size = _struct.size
    _field_names = ('name', 'virtual_size', 'rva', 'physical_size', 'physical_offset', 'flags')
    _formatters = '%s 0x%x 0x%x 0x%x 0x%x 0x%x'.split()

    def __init__(self, name, virtual_size, rva, physical_size, physical_offset, flags):
        self.raw = None
        self.items = OrderedDict(name=name, virtual_size=virtual_size, rva=rva, physical_size=physical_size,
                                 physical_offset=physical_offset, flags=flags)

    @classmethod
    def read(cls, file, offset=None):
        if offset is not None:
            file.seek(offset)

        raw = file.read(cls._size)
        section = Section(*cls._struct.unpack(raw))
        section.raw = raw
        return section

    def __getattr__(self, attr):
        return self.items[attr]

    def offset_to_rva(self, offset):
        return offset - self.physical_offset + self.rva

    def rva_to_offset(self, rva):
        return rva - self.rva + self.physical_offset

    def __repr__(self):
        return 'Section(%s)' % ', '.join('%s=%s' % (name, self._formatters[i] % self.items[name])
                                         for i, name in enumerate(self._field_names))


class Pe:
    def __init__(self, file):
        self.dos_header = ImageDosHeader(file)
        self.nt_headers = ImageNTHeaders(file, self.dos_header.e_lfanew)
        self.file_header = self.nt_headers.file_header
        self.optional_header = self.nt_headers.optional_header
        self.data_directory = self.optional_header.data_directory
        self._section_table = None

    @property
    def section_table(self):
        if self._section_table is None:
            n = self.file_header.number_of_sections
            file.seek(self.nt_headers.offset + self.nt_headers.size)
            self._section_table = [Section.read(file) for _ in range(n)]

        return self._section_table

    def info(self):
        return ('DOS signature: %s\n' % self.dos_header.signature +
                'e_lfanew: 0x%x\n' % self.dos_header.e_lfanew +
                'PE signature: %s\n' % self.nt_headers.signature +
                'Image file header:\n%s\n' % self.file_header +
                'Image optional header:\n%s\n' % self.optional_header +
                'Data directory:\n%r\n' % self.data_directory.items +
                'Section table:\n%r\n' % self.section_table)


if __name__ == "__main__":
    with open(r"d:\Games\df_40_24_win_s\Dwarf Fortress.exe", 'rb') as file:
        pe = Pe(file)
        print(pe.info())