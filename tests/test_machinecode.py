from dfrus.opcodes import mov_rm_imm, Reg, call_near, mov_reg_imm, jmp_near, nop
from dfrus.disasm import join_byte
from dfrus.binio import to_dword
from dfrus.machine_code import MachineCode, Reference
from dfrus.machine_code_utils import mach_strlen


def test_machinecode_1():
    """
    # Sample code:
    use32

    func = 222222h
    return_addr = 777777h

    org 123456h

    mov dword [esi+14h], 0fh
    call near func
    mov edi, 0fh
    jmp near return_addr
    """

    code = MachineCode(
        (mov_rm_imm | 1), join_byte(1, 0, Reg.esi), 0x14, to_dword(0xf),  # mov dword [esi+14h], 0fh
        call_near, Reference.relative(name='func', size=4),  # call near func
        mov_reg_imm | 8 | Reg.edi.code, to_dword(0xf),  # mov edi, 0fh
        jmp_near, Reference.relative(name='return_addr', size=4)  # jmp near return_addr
    )

    code.origin_address = 0x123456
    code.fields['func'] = 0x222222
    code.fields['return_addr'] = 0x777777

    assert bytes(code) == bytes.fromhex('C7 46 14 0F 00 00 00 E8 C0 ED 0F 00 BF 0F 00 00 00 E9 0B 43 65 00')


def test_machinecode_2():
    # Test getting addresses of absolute references
    code = MachineCode(
        bytes(123),
        Reference.absolute(name='b', size=4),
        bytes(12345),
        Reference.absolute(name='a', size=4),
        bytes(10)
    )

    code.origin_address = 0
    code.fields['a'] = 0xDEAD
    code.fields['b'] = 0xBEEF

    b = bytes(code)
    found_refs = sorted(b.index(to_dword(code.fields[ref_name])) for ref_name in 'ab')
    assert found_refs == list(code.absolute_references)


def test_mach_strlen():
    # Test the new mach_strlen:
    code = mach_strlen(nop)
    assert bytes(code) == bytes.fromhex('51 31 C9 80 3C 08 00 74 0B 81 F9 00 01 00 00 7F 04 41 EB EF 90 59')
