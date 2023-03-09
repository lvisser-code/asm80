"""Assembler for 8080 & 8085 microprocessors

Author: Leonard Visser

This script creates object code by translating combinations of
mnemonics and syntax for operations and addressing modes into their
numerical equivalents. This representation typically includes an
operation code ("opcode") as well as other control bits and data.
The assembler also calculates constant expressions and resolves
symbolic names for memory locations and other entities. The use of
symbolic references is a key feature of this assembler, saving
tedious calculations and manual address updates after program
modifications. 

This is a two pass assembler, using the first pass to look up Opcodes,
decode operands, and locate labels.  The second pass uses the labels
to resolve address references. The final step is .hex file creation.

Assembler directives supported:
 DB - define byte (value, value,...)
 DW - define word (address)
 DS - data storage (reserved bytes have no initial value)
 HIGH - high order 8 bits of 16 bit address
 LOW - low order 8 bits of 16 bit address
 ORG - origin of the program counter (address). Default = 0
 EQU - equate expression (value1 oper value2)

Number formats:
 nnnn  - decimal
 nnnnB - binary
 nnnnH - hexadecimal format
 nnnnQ - octal format
 'Yes' - ASCII

Input file:   source.asm
Output files: source.tmp, source.lst, source.hex (Intel HEX format)

Source line syntax
  Label  Code  Operand  Comment
  START: MVI   C,0A1H   ;Load the C register with A1 hexadecimal

Listing fields
  Err  Addr  B1 B2 B3  Line  Label   Code  Operand  Comment
       0000  0E A1        1  START:  MVI   C,0A1H   ;Load the C reg

  Err codes: *O* = undefined opcode
             *V* = illegal value
             *U* = undefined symbol 
             *D* = duplicate symbol
"""

import sys
ver = '1.0'      # Program version

class Instruction808x(object):
    """Instruction set for 808x microprocessor"""
    def __init__(self):
        """Initialization code"""
        # Dictionary of 808x CPU Instrucions - 'Mnemonic':'Opcode*'
        # *=operand type
        #  - no operand
        #  b data byte
        #  r register
        #  a address 
        #  e expression
        #  p register pair
        #  d register pair B or D
        #  m regster, register
        #  w register pair, data word
        #  v register, data byte
        #  i interrupt 0 - 7
        self.instr = {'CMA':'2F-', 'CMC':'3F-', 'DAA':'27-', 'DI':'F3-',
            'EI':'FB-', 'HLT':'76-', 'NOP':'00-', 'PCHL':'E9-', 'RAL':'17-',
            'RAR':'1F-', 'RC':'D8-', 'RET':'C9-', 'RIM':'20-', 'RLC':'07-',
            'RM':'F8-', 'RNC':'D0-', 'RNZ':'C0-', 'RP':'F0-', 'RPE':'E8-',
            'RPO':'E0-', 'RRC':'0F-', 'RZ':'C8-', 'SIM':'30-', 'SPHL':'F9-',
            'STC':'37-', 'XCHG':'EB-', 'XTHL':'E3-', 'ARHL':'10-', 'DSUB':'08-',
            'LHLX':'ED-', 'RDEL':'18-', 'RSTV':'CB-', 'SHLX':'D9-',
            'ACI':'CEb', 'ADI':'C6b', 'ANI':'E6b', 'CPI':'FEb', 'ORI':'F6b',
            'SBI':'DEb', 'SUI':'D6b', 'XRI':'EEb', 'IN':'DBb', 'OUT':'D3b',
            'LDHI':'28b', 'LDSI':'38b',
            'ADC':'88r', 'ADD':'80r', 'ANA':'A0r', 'CMP':'B8r', 'DCR':'05r',
            'INR':'04r', 'ORA':'B0r', 'SBB':'98r', 'SUB':'90r', 'XRA':'A8r',
            'CALL':'CDa', 'CC':'DCa', 'CM':'FCa', 'CNC':'D4a', 'CNZ':'C4a',
            'CP':'F4a', 'CPE':'ECa', 'CPO':'E4a', 'CZ':'CCa', 'JC':'DAa',
            'JM':'FAa', 'JMP':'C3a', 'JNC':'D2a', 'JNZ':'C2a', 'JP':'F2a',
            'JPE':'EAa', 'JPO':'E2a', 'JZ':'CAa', 'LDA':'3Aa', 'LHLD':'2Aa',
            'SHLD':'22a', 'STA':'32a', 'JNUI':'DDa', 'JUI':'FDa',
            'DAD':'09p', 'DCX':'0Bp', 'INX':'03p', 'POP':'C1p', 'PUSH':'C5p',
            'LDAX':'0Ad', 'STAX':'02d', 'MOV':'40m', 'LXI':'01w', 'MVI':'06v',
            'RST':'C7i', 
            # Assembler directives
            'DB':'00b', 'DW':'00a', 'DS':'00a', 'ORG':'00a', 'EQU':'00e'}
    def opCode(self, mnemonic):
        """Look up mnemonic in dictionary and return the matching Opcode*"""
        if mnemonic not in self.instr:
            return 'Error'
        inst_op = self.instr[mnemonic]
        if len(inst_op) != 3: # instruction + operation type must be 3 chars
            return 'Error'
        return inst_op

class Parse(object):
    """ Parse text line to identify the label, mnemonic, operands,
        and comments.  Lookup the Opcode and generate line number
        program count and program bytes.  Report any errors."""
    def __init__(self):
        self.err = ''   # error code
        self.ln = 0     # line number
        self.pc = 0     # program counter
        self.b1 = ''    # byte 1
        self.b2 = ''    # byte 2
        self.b3 = ''    # byte 3
        self.label = '' # label
        self.mne = ''   # mnemonic
        self.oper = ''  # operands
        self.bytes = 0  # bytes
        self.comment = ''
        self.errors = 0 # error count
        self.symbols = []

    def Op_byte(self, operand):
        # Parse operand string representation of number: decimal, hex,
        # octal, binary or ASCII.  Return hex byte or 'Error'.
        try:
            # Is it ASCII? 'A'
            if operand.find("'") == 0 and len(operand) > 1:
                return format(ord(operand[1]),'X').zfill(2)
            # Is it Hexadecimal? 0FFH
            elif operand.upper().find("H") > 0 and operand[0].isdigit():
                ph = operand.upper().find("H")
                dec = int(operand[0:ph], 16)
                if dec < 0 or dec > 255:
                    return 'Error'
                else:
                    return format(dec, 'X').zfill(2)
            # Is it Octal? 377Q
            elif operand.upper().find("Q") > 0 and operand[0].isdigit():
                ph = operand.upper().find("Q")
                dec = int(operand[0:ph], 8)
                if dec < 0 or dec > 255:
                    return 'Error'
                else:
                    return format(dec, 'X').zfill(2)
            # Is it Binary? 11111111B
            elif operand.upper().find("B") > 0 and operand[0].isdigit():
                pb = operand.upper().find("B")
                dec = int(operand[0:pb], 2)
                if dec < 0 or dec > 255:
                    return 'Error'
                else:
                    return format(dec, 'X').zfill(2)
            # Is it Decimal? 255
            else:
                dec = int(operand)
                if dec < 0 or dec > 255:
                    return 'Error'
                else:
                    return format(dec, 'X').zfill(2)
        except:
            return 'Error'

    def Op_addr(self, operand):
        # Parse operand string as a number address or label.  Return
        # hex word or 'Label'.  Return 'Error' if error detected.
        if len(operand) == 0:
            return 'Error'
        if operand[0].isalpha():
            return 'Label'
        try:
            # Is it ASCII? 'A'
            if operand.find("'") == 0 and len(operand) > 1:
                return format(ord(operand[1]),'X').zfill(4)
            # Is it Hexadecimal? 0FFFFH
            if operand.upper().find("H") > 0 and operand[0].isdigit():
                ph = operand.upper().find("H")
                dec = int(operand[0:ph], 16)
                if dec < 0 or dec > 65535:
                    return 'Error'
                else:
                    return format(dec, 'X').zfill(4)
            # Is it Octal? 177777Q
            if operand.upper().find("Q") > 0 and operand[0].isdigit():
                ph = operand.upper().find("Q")
                dec = int(operand[0:ph], 8)
                if dec < 0 or dec > 65535:
                    return 'Error'
                else:
                    return format(dec, 'X').zfill(4)
            # Is it Binary? 1111111111111111B
            if operand.upper().find("B") > 0 and operand[0].isdigit():
                ph = operand.upper().find("B")
                dec = int(operand[0:ph], 2)
                if dec < 0 or dec > 65535:
                    return 'Error'
                else:
                    return format(dec, 'X').zfill(4)
            # Is it Decimal? 65535
            else:
                dec = int(operand)
                if dec < 0 or dec > 65535:
                    return 'Error'
                else:
                    return format(dec, 'X').zfill(4)
        except:
            return 'Error'

    def Op_reg(self, operand):
        # Parse operand for register A-E, H or L.  Return SSS value.
        if operand == 'B':
            sss = 0
        elif operand == 'C':
            sss = 1
        elif operand == 'D':
            sss = 2
        elif operand == 'E':
            sss = 3
        elif operand == 'H':
            sss = 4
        elif operand == 'L':
            sss = 5
        elif operand == 'M':
            sss = 6
        elif operand == 'A':
            sss = 7
        elif operand == 'PSW':
            sss = 0
        else:
            sss = -1  # Error
        return sss

    def Op_regpr(self, operand):
        # Parse operand for register pair B, D, H, SP or PSW. Return RP value.
        if operand == 'B':
            rp = 0
        elif operand == 'D':
            rp = 1
        elif operand == 'H':
            rp = 2
        elif operand == 'SP':
            rp = 3
        elif operand == 'PSW':
            rp = 3
        else:
            rp = -1 # Error
        return rp

    def Op_regpr2(self, operand):
        # Parse operand for register pair B, D.  Return RP value.
        if operand == 'B':
            rp = 0
        elif operand == 'D':
            rp = 1
        else:
            rp = -1 # Error
        return rp

#----------------------------------------------------------------------

    def Pass1(self, line):
        # Parse the text in line to identify comments, mnemonics, etc.
        # Reset the class attributes
        self.err = ''   # error code
        self.b1 = ''    # byte 1
        self.b2 = ''    # byte 2
        self.b3 = ''    # byte 3
        self.long = ''  # long byte list
        self.label = '' # label
        self.mne = ''   # mnemonic
        self.oper = ''  # operands
        self.bytes = 0  # bytes
        self.comment = ''

        # Remove any leading blanks and '\n' returns
        line = line.lstrip().replace('\n', '')
        self.ln = self.ln + 1  # Increment line number

        # If line contains nothing we're done.
        if len(line) == 0:
            return

        # Check for a comment beginning with ';'
        pos = line.find(';')
        if pos >= 0:
            self.comment = line[pos:]
            if pos == 0: # If line contains only a comment we're done
                return
            line = line[0:pos].rstrip() # Strip the comment out

        # Line may now contain only: a label, a mnemonic, operands

        # Check for a label ending with ':'
        pos = line.find(':')
        posq = line.find("'") # If ':' is in a string then not a label
        if pos > 0 and posq > 0 and pos > posq:
            pos = -1
        if pos > 0:
            if pos > 6: # Maximum label length is 6 chars
                line = line[:6] + line[pos:]
                pos = 6
            self.label = line[0:pos]
            line = line[pos+1:].lstrip()
            # Check for a duplicate label error
            i = len(self.symbols)
            for c in range(i):
                if self.label == self.symbols[c][0]:
                    self.err = '*D*' # duplicate label error
                    self.errors = self.errors + 1
            # Save the label and pc in list of symbols
            self.symbols.append((self.label, self.pc))
            if len(line) == 0:
                return

        # Line may now contain only: a mnemonic and operands

        # Check for a mnemonic
        inst = Instruction808x() # Instruction set class
        self.mne = line.split()[0].upper() # mne is upper case
        if len(line) > len(self.mne)+1: # Strip mnemnonic from line
            line = line[len(self.mne)+1:].lstrip().rstrip()
        else:
            line = ''
        # Line may now contain only: operands

        opcodes = inst.opCode(self.mne) # Look up the opcodes
        if opcodes == 'Error':
            self.err = '*O*' # undefined opcode
            self.errors = self.errors + 1
            return
        # Split opcodes string into 2 char opcode, 1 char op_type
        opcode = opcodes[0:2]
        op_type = opcodes[2]
        self.b1 = opcode
        
        # Check the operand type: -,b,r,a,e,p,d,m,w,v,i
        if op_type == '-': # Check for no operand
            self.bytes = 1 # Instruction length
            return
        
        elif op_type == 'b': # Check for byte data operand
            if self.mne == 'DB': # e.g. 'A', 0FFH, 377Q, 11111111B, 255
                # Split operands separated by ','; ignore ',' in strings
                linesp = []
                open_quote = False
                close_quote = False
                temp = ''
                for a in line:
                    if a == "'" and open_quote == False:
                        open_quote = True
                        temp =  temp + '"'
                    elif a == "'" and open_quote == True:
                        close_quote = True
                        temp = temp + '"'
                    elif a == ',' and open_quote == False:
                        linesp.append(temp)
                        temp = ''
                    else:
                        temp = temp + a
                    if open_quote == True and close_quote == True:
                        open_quote = False
                        close_quote = False
                linesp.append(temp)
                for op in linesp:         # and inspect each
                    op = op.lstrip()
                    if op.find('"') == 0: # String data?
                        for char in op:
                            if char != '"':
                                b = self.Op_byte("'" + char + "'")
                                self.long = self.long + b
                    else:
                        b = self.Op_byte(op)
                        if b == 'Error':
                            self.b1 = '??'
                        else:
                            self.long = self.long + b
                self.oper = line
                self.bytes = 1
            else: # e.g. OUT 1, CPI 0FFH
                b = self.Op_byte(line)
                if b == 'Error':
                    self.b2 = '??'
                else:
                    self.b2 = b
                self.bytes = 2
                self.oper = line
            return

        elif op_type == 'r': # Check for register operand
            sss = self.Op_reg(line) # sss adder to base register B
            if sss == -1:
                self.err = '*R*' # illegal register
                self.errors = self.errors + 1
            else:
                # If special case mne 'DCR' or 'INR' ddd = 8*sss
                if self.mne == 'DCR' or self.mne == 'INR':
                    self.b1 = format(int(self.b1, 16) + 8*sss, 'X').zfill(2)
                else:
                    self.b1 = format(int(self.b1, 16) + sss, 'X').zfill(2)
            self.oper = line
            self.bytes = 1
            return
        
        elif op_type == 'a': # Check for address operand
            a = self.Op_addr(line)
            if self.mne == 'DW': # Check for directive 'DW'
                if a == 'Error':
                    self.err = '*V*' # illegal value
                    self.errors = self.errors + 1
                    self.b2 = '00'
                elif a == 'Label': # label requires '??' until pass 2
                    self.b1 = '??'
                    self.b2 = '??'
                else:
                    self.b1 = a[2:4] # low byte of address first
                    self.b2 = a[0:2] # high byte of address next
                self.oper = line.upper()
                self.bytes = 2
                return
            if self.mne == 'DS': # Check for directive 'DS'
                if a == 'Error':
                    self.err = '*V*' # illegal value
                    self.errors = self.errors + 1
                else:
                    self.b1 = ''
                    self.pc = self.pc + int(a, 16)
                self.bytes = 0
                self.oper = line
                return
            if self.mne == 'ORG': # Check for directive 'ORG'
                if a == 'Error':
                    self.err = '*V*' # illegal value
                    self.errors = self.errors + 1
                else:
                    self.b1 = ''
                    self.pc = int(a, 16)
                self.bytes = 0
                self.oper = line
                return
            if a == 'Error':
                self.err = '*V*' # illegal value
                self.errors = self.errors + 1
                self.b2 = '00'
                self.b3 = '00'
            elif a == 'Label': # label requires '??' until pass 2
                self.b2 = '??'
                self.b3 = '??'
            else:
                self.b2 = a[2:4] # low byte of address first
                self.b3 = a[0:2] # high byte of address next
            self.oper = line.upper()
            self.bytes = 3
            return
        
        elif op_type == 'p': # Check for register pair operand
            rp = self.Op_regpr(line) # rp adder to base register pair B
            if rp == -1:
                self.err = '*R*' # illegal register pair
                self.errors = self.errors + 1
            else:
                self.b1 = format(int(self.b1, 16) + 16*rp, 'X').zfill(2)
            self.oper = line
            self.bytes = 1
            return
        
        elif op_type == 'd': # Check for register pair B or D operand
            rp = self.Op_regpr2(line) # rp adder to register pair B
            if rp == -1:
                self.err = '*R*' # illegal register pair
                self.errors = self.errors + 1
            else:
                self.b1 = format(int(self.b1, 16) + 16*rp, 'X').zfill(2)
            self.oper = line
            self.bytes = 1
            return
        
        elif op_type == 'w': # Check for LXI register pair, data operand
            line_rp_d = line.split(',')
            rp = self.Op_regpr(line_rp_d[0])
            if rp == -1:
                self.err = '*R*' # illegal register pair
                self.errors = self.errors + 1
                self.b2 = '00'
                self.b3 = '00'
            else:
                self.b1 = format(int(self.b1, 16) + 16*rp, 'X').zfill(2)
            if len(line_rp_d) > 1:
                a = self.Op_addr(line_rp_d[1].lstrip())
            else:
                a = 'Error'
            if a == 'Error':
                self.err = '*V*' # illegal value
                self.errors = self.errors + 1
                self.b2 = '00'
                self.b3 = '00'
            elif a == 'Label': # label requires '??' until pass 2
                self.b2 = '??'
                self.b3 = '??'
            else:
                self.b2 = a[2:4] # low byte of address first
                self.b3 = a[0:2] # high byte of address next
            self.oper = line
            self.bytes = 3
            return
        
        elif op_type == 'm': # Check for register, register operand
            line_rr = line.split(',')
            if len(line_rr) != 2:
                self.err = '*R*' # missing register
                self.errors = self.errors + 1
            else:
                ddd = self.Op_reg(line_rr[0]) # ddd adder to 1st register B
                sss = self.Op_reg(line_rr[1].lstrip()) # sss adder 2nd reg
                if ddd == -1 or sss == -1 or (ddd == 6 and sss == 6):
                    self.err = '*R*' # illegal register
                    self.errors = self.errors + 1
                else:
                    self.b1 = format(int(self.b1, 16) + 8*ddd + sss, 'X').zfill(2)
            self.oper = line
            self.bytes = 1
            return
        
        elif op_type == 'v': # Check for register, data operand
            line_rd = line.split(',')
            ddd = self.Op_reg(line_rd[0]) # ddd adder to register
            if len(line_rd) > 1:
                b = self.Op_byte(line_rd[1].lstrip()) # byte data
            else:
                self.err = '*V*' # illegal value
                self.errors = self.errors + 1
                self.b2 = '00'
            if ddd == -1:
                self.err = '*R*' # illegal register
                self.errors = self.errors + 1
                self.b2 = '00'
            elif b == 'Error': # not byte data, label??
                self.b1 = format(int(self.b1, 16) + 8*ddd, 'X').zfill(2)
                self.b2 = '??'
            else:
                self.b1 = format(int(self.b1, 16) + 8*ddd, 'X').zfill(2)
                self.b2 = b
            self.oper = line
            self.bytes = 2
            return
        
        elif op_type == 'i': # Check for RST code 0-7 operand
            i = self.Op_byte(line)
            ih = i[0]
            if i == 'Error' or ih != '0':
                self.err = '*V*' # illegal value
            else:
                self.b1 = format(int(self.b1, 16) + 8*int(i[1]), 'X').zfill(2)
            self.oper = line
            self.bytes = 1
            return

        elif op_type == 'e':       #Check for EQU expression
            if line.find('+') > 0:   #Check for + operator
                operands = line.split('+', 2)
                p0 = self.Op_addr(operands[0])
                p1 = self.Op_addr(operands[1])
                if p0 == 'Error' or p1 == 'Error':
                    a = 'Error'
                elif p0 == 'Label' or p1 == 'Label':
                    a = 'Label'
                else:
                    a = format(int(p0, 16) + int(p1, 16), 'x').zfill(4)

            elif line.find('-') > 0: #Check for - operator
                operands = line.split('-', 2)
                p0 = self.Op_addr(operands[0])
                p1 = self.Op_addr(operands[1])
                if p0 == 'Error' or p1 == 'Error':
                    a = 'Error'
                elif p0 == 'Label' or p1 == 'Label':
                    a = 'Label'
                else:
                    a = format(int(p0, 16) - int(p1, 16), 'x').zfill(4)
            
            elif line.find('*') > 0: #Check for * operator
                operands = line.split('*', 2)
                p0 = self.Op_addr(operands[0])
                p1 = self.Op_addr(operands[1])
                if p0 == 'Error' or p1 == 'Error':
                    a = 'Error'
                elif p0 == 'Label' or p1 == 'Label':
                    a = 'Label'
                else:
                    a = format(int(int(p0, 16) * int(p1, 16)), 'x').zfill(4)
            
            elif line.find('/') > 0: #Check for / operator
                operands = line.split('/', 2)
                p0 = self.Op_addr(operands[0])
                p1 = self.Op_addr(operands[1])
                if p1 == 0:
                    p1 = 'Error'
                if p0 == 'Error' or p1 == 'Error':
                    a = 'Error'
                elif p0 == 'Label' or p1 == 'Label':
                    a = 'Label'
                else:
                    a = format(int(int(p0, 16) / int(p1, 16)), 'x').zfill(4)
            
            else:
               a = self.Op_addr(line)

            if a == 'Error':
                self.err = '*V*' # illegal value
                self.errors = self.errors + 1
                self.oper = line.upper()
                return

            if a == 'Label':
                self.b1 = '??'   # label requires ?? until pass 2
                self.b2 = '??'
                self.oper = line.upper()
                return

            self.symbols.pop()
            self.symbols.append((self.label, int(a, 16)))
            self.oper = line.upper()
            self.b1 = ''
            return



def open_file(file_name, mode):
    """"Open a file."""
    try:
        the_file = open(file_name, mode)
    except IOError as e:
        print("\n*** Unable to open the file", file_name, "\n", e)
        sys.exit()
    else:
        return the_file


#----------------------------------------------------------------------
# main
#----------------------------------------------------------------------
# Get the source file name. Create a temp file with extension .tmp
print("\n--- Assembler for 8080 & 8085 microprocessors ---")
source_file = input("Enter the source file name: ")
list_file = source_file[0:source_file.find('.')] + '.tmp'
print ("Assembling " + source_file + "... ", end="")
# Open the source file for reading and a temp listing file for writing
# Write the listing header line
source = open_file(source_file, 'r')
listing = open_file(list_file, 'w')
listing.write("ERR LINE  ADDR B1 B2 B3   *** ASM80 ASSEMBLER VER "+ver+" ***\n")

parser = Parse() # Use the Parse class to parse the source lines

# Pass 1: Parse source file lines to build the temp listing file
for line in source:
    # The parser will take a line and assign values to parser.err, .b1,
    # .b2, .b3, .long, .label, .mne, .oper, .bytes, .comment
    parser.Pass1(line)
    if parser.label != '' or parser.mne != '':
        label = ''
        if parser.label != '': # Add a ':' to the end of the label
            label = parser.label + ':'
        # Make a string with the label, mnemonic, operands and comment
        lmoc = label.ljust(8) + parser.mne.ljust(5) + parser.oper.ljust(11) \
            + parser.comment + '\n'
    else: # Make a  string with comment only
        lmoc = parser.comment + '\n'
    
    if parser.long == '': # If not long data list, then do this
        if len(parser.b1) != 0: # if b1 has data, include address, increment pc
            a = format(parser.pc, 'X').zfill(4)
            parser.pc = parser.pc + parser.bytes
        else: # address should be blank
            a = '    '
        # Assemble the whole line: 'ERR(4) LINE(4) ADDR(5) B1(3) B2(3) B3(3)
        # LABEL(7) MNE(5) OPER(11) COMMENT' and write it to temp listing file
        list_line = parser.err.ljust(4) + \
            str(parser.ln).rjust(4) + '  ' + a + ' ' + \
            parser.b1.ljust(3) + parser.b2.ljust(3) + \
            parser.b3.ljust(5) + lmoc
        listing.write(list_line)
    else: # Long data list found, so place data on multiple lines if needed
        a = format(parser.pc, 'X').zfill(4)
        b1 = parser.long[0:2]
        b2 = parser.long[2:4]
        byte_count = 2
        if len(parser.long) >= 6:
            b3 = parser.long[4:6]
            byte_count = 3
        else:
            b3 = '  '
        parser.pc = parser.pc + byte_count
        list_line = parser.err.ljust(4) + \
            str(parser.ln).rjust(4) + '  ' + a + ' ' + \
            b1.ljust(3) + b2.ljust(3) + b3.ljust(5) + lmoc
        listing.write(list_line)
        if len(parser.long) > 6:
            ll = parser.long[6:]
        else:
            ll = ''
        while len(ll) > 6:
            list_line = format(parser.pc, 'X').zfill(4).rjust(14) + \
            ' ' + ll[0:2] + ' ' + ll[2:4] + ' ' + ll[4:6] + '\n'
            listing.write(list_line)
            parser.pc = parser.pc + 3
            ll = ll[6:]
        b1 = b2 = b3 = '  '
        if len(ll) >= 2:
            b1 = ll[0:2]
            byte_count = 1
        if len(ll) >= 4:
            b2 = ll[2:4]
            byte_count = 2
        if len(ll) == 6:
            b3 = ll[4:6]
            byte_count = 3
        if b1 != '  ':
            list_line = format(parser.pc, 'X').zfill(4).rjust(14) + \
            ' ' + b1 + ' ' + b2 + ' ' + b3 + '\n'
            listing.write(list_line)
            parser.pc = parser.pc + byte_count

source.close()
listing.close()

# Pass 2: Resolve address and EQU references using the symbols list
list2_file = source_file[0:source_file.find('.')] + '.lst'
listing = open_file(list_file, 'r')
listing2 = open_file(list2_file, 'w')
for line in listing:
    s = line.find('?? ??') # Check for unresolved address
    if s > 0 :
        ln = line # Copy of line can be modified
        c = ln.find(';') # Check for a comment
        if c > 0: # Strip off the comment
            ln = ln[0:c].rstrip()
        # get mne_lab: a list with (label) mne label
        mne_lab = ln[s+5:].lstrip().split()
        if len(mne_lab) == 5 and 'EQU' in mne_lab:
            p0 = parser.Op_addr(mne_lab[2])
            p1 = parser.Op_addr(mne_lab[4])
            if p0 == 'Label':
                for sym in parser.symbols: # search for symbol in symbol table
                    if sym[0] == mne_lab[2]:
                        p0 = format(sym[1], 'x').zfill(4)
                        continue
            if p1 == 'Label':
                for sym in parser.symbols: # search for symbol in symbol table
                    if sym[0] == mne_lab[4]:
                        p1 = format(sym[1], 'x').zfill(4)
                        continue
            if mne_lab[3] == '+' and p0 != 'Label' and p1 != 'Label':
                a = int(p0, 16) + int(p1, 16)
            if mne_lab[3] == '-' and p0 != 'Label' and p1 != 'Label':
                a = int(p0, 16) - int(p1, 16)
            if mne_lab[3] == '*' and p0 != 'Label' and p1 != 'Label':
                a = int(p0, 16) * int(p1, 16)
            if mne_lab[3] == '/' and p0 != 'Label' and p1 != 'Label' and p1 != 0:
                a = int(p0, 16) / int(p1, 16)
            if p0 == 'Label' or p1 == 'Label': # symbol not found in symbol table?
                line = '*U*' + line[3:]
                line = line[0:s] + '-- --' + line[s+5:]
                parser.errors = parser.errors + 1
            else: # update symbol table with EQU value
                label = mne_lab[0][:-1] # strip off ':'
                i = parser.symbols.index((label,0))
                parser.symbols[i] = (label, a)
                # replace ?? ?? with spaces
                line = line[0:8] + ' '*15 + line[23:]
        else:
            label = mne_lab[len(mne_lab)-1] # target label is last in list
            offset = 0
            if label.find('+') > 0:         # check for + operator
                label_plus = label.split('+', 2)
                label = label_plus[0]
                try:
                    offset = int(label_plus[1])
                except ValueError:
                    label = label_plus[0]+label_plus[1]
            if label.find('-') > 0:         # check for - operator
                label_minus = label.split('-', 2)
                label = label_minus[0]
                try:
                    offset = -int(label_minus[1])
                except ValueError:
                    label = label_plus[0]+label_plus[1]
            add = ''
            for sym in parser.symbols: # search for symbol in symbol table
                if sym[0] == label:
                    add = sym[1] + offset # address = decimal
                    continue
            if add == '': # symbol not found in symbol table?
                line = '*U*' + line[3:]
                line = line[0:s] + '-- --' + line[s+5:]
                parser.errors = parser.errors + 1
            else:
                a = format(add, 'X').zfill(4) # Convert decimal to 4 byte hex
                w = a[2:4] + ' ' + a[:2] # swap bytes and add a space
                # replace ?? ?? with address
                line = line[0:s] + w + line[s+5:]
    
    s = line.find('??') # Check for unresolved byte value
    if s > 0 :
        ln = line # Copy of line can be chopped up
        c = ln.find(';') # Check for a comment
        if c > 0: # Strip off the comment
            ln = ln[0:c].rstrip()
        # get mne_lab: a list with (label) mne label
        mne_lab = ln[s+5:].lstrip().split()
        label = mne_lab[len(mne_lab)-1] # target label is last in list
        val = ''
        for sym in parser.symbols: # search for symbol in symbol table
            if sym[0] == label:
                val = sym[1] # byte value in decimal
                continue
        if val == '': # symbol not found in symbol table?
            line = '*U*' + line[3:]
            parser.errors = parser.errors + 1
        else:
            a = format(val, 'X').zfill(4) # Convert decimal to 4 byte hex
            if any('HIGH' in string for string in mne_lab): # use HIGH byte of address
                line = line[0:s] + a[0:2] + ' ' + line[s+3:]
            else: # use LOW byte of address
                line = line[0:s] + a[2:4] + ' ' + line[s+3:]
    listing2.write(line)

# List the symbols
listing2.write('\n----------------------------------------------------------------------------')
listing2.write('\nSymbols:')
parser.symbols.sort()
line = ''
pos = 1
for sym in parser.symbols:
    line = line + sym[0].rjust(6, ' ') + ' ' + format(sym[1], 'X').zfill(4) + '    '
    pos = pos + 1
    if pos > 5:
        listing2.write('\n' + line)
        line = ''
        pos = 1
listing2.write('\n' + line)


# Display the error information
listing2.write('\n----------------------------------------------------------------------------')
listing2.write('\nError codes: *O*=undefined opcode, *V*=illegal value, *R*=illegal register,')
listing2.write('\n             *U*=undefined symbol, *D*=duplicate symbol')
listing2.write('\nTotal Errors = ' + str(parser.errors) + '\n')
listing.close()
listing2.close()


# Generate the Intel Hex file
# Ref: https://en.wikipedia.org/wiki/Intel_HEX
if parser.errors == 0:
    hex_file = source_file[0:source_file.find('.')] + '.hex'
    listing2 = open_file(list2_file, 'r')
    hexfile = open_file(hex_file, 'w')
    for line in listing2:
        if line[:3] == '---': # Check for end of assembly - exit loop if found
            break
        if len(line) < 22:
            continue
        else:
            addr = line[10:14]
            try: # Is addr a valid hex number?
                int(addr, 16)
            except: # If not, then skip line
                continue
            b1 = line[15:17]
            b2 = line[18:20]
            b3 = line[21:23]
        if b2 == '  ': # Check for 1 data byte
            sum_hex = format(1 + int(addr[0:2], 16) + int(addr[2:4], 16) + \
                int(b1, 16), 'X')
            checksum = format(255 - int(sum_hex[-2:], 16) + 1, 'X').zfill(2)
            intel_hex = ':01' + addr + '00' + b1 + checksum
        elif b3 == '  ':# Check for 2 data bytes
            sum_hex = format(1 + int(addr[0:2], 16) + int(addr[2:4], 16) + \
                int(b1, 16) + int(b2, 16), 'X')
            checksum = format(255 - int(sum_hex[-2:], 16) + 1, 'X').zfill(2)
            intel_hex = ':02' + addr + '00' + b1 + b2 + checksum
        else: # 3 data bytes
            sum_hex = format(1 + int(addr[0:2], 16) + int(addr[2:4], 16) + \
                int(b1, 16) + int(b2, 16) + int(b3, 16), 'X')
            checksum = format(255 - int(sum_hex[-2:], 16) + 1, 'X').zfill(2)
            intel_hex = ':03' + addr + '00' + b1 + b2 + b3 + checksum
        hexfile.write(intel_hex + '\n') # Write the record
    intel_hex = ':00000001FF' # End of file record
    hexfile.write(intel_hex + '\n')
    listing2.close()
    hexfile.close()

print("Done")
print("Assembled Lines = "+str(parser.ln)+", Errors = "+str(parser.errors)+'\n')
