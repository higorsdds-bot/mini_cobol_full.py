import re
import sys
from datetime import datetime

# ==================================================
# OPCODES
# ==================================================
OP = {
    "DISPLAY": 1,
    "ACCEPT": 2,
    "MOVE": 3,
    "STRING": 4,
    "UNSTRING": 5,
    "CONTINUE": 6,
    "STOP": 255
}

# ==================================================
# MEMÓRIA LINEAR (MAPEAMENTO PIC)
# ==================================================
class Memory:
    def __init__(self):
        self.buffer = bytearray()
        self.symbols = {}

    def alloc(self, name, pic, size):
        if name in self.symbols:
            return
        offset = len(self.buffer)
        self.symbols[name] = (offset, pic, size)
        self.buffer.extend(b" " * size)

    def write(self, name, value):
        offset, pic, size = self.symbols[name]
        value = str(value)

        if pic == "9" and not value.isdigit():
            raise RuntimeError(f"Valor inválido para campo numérico: {name}")

        data = value.encode()[:size].ljust(size, b" ")
        self.buffer[offset:offset + size] = data

    def read(self, name):
        offset, _, size = self.symbols[name]
        return self.buffer[offset:offset + size].decode().strip()

# ==================================================
# PARSER COBOL (FORMATO FIXO + PONTO FINAL OBRIGATÓRIO)
# ==================================================
def parse(code):
    sentences = []
    buffer = ""

    for raw in code.splitlines():
        if len(raw) >= 7 and raw[6] == "*":
            continue  # comentário

        line = raw[7:72].rstrip() if len(raw) >= 7 else raw.rstrip()
        if not line.strip():
            continue

        buffer += " " + line.strip()

        if line.strip().endswith("."):
            sentences.append(buffer.strip().upper())
            buffer = ""

    if buffer:
        raise RuntimeError("Erro COBOL: sentença sem ponto final.")

    return sentences

# ==================================================
# COMPILADOR → BYTECODE
# ==================================================
def compile_cobol(lines):
    mem = Memory()
    bc = bytearray()

    stop_found = False
    end_program_found = False

    for line in lines:
        l = line.replace(".", "").strip()

        # ------------------------------------------
        # WORKING-STORAGE (GRUPOS E PIC)
        # ------------------------------------------
        if re.match(r"\d+\s+\w+", l):
            parts = l.split()

            # Grupo sem PIC → ignorar
            if "PIC" not in parts:
                continue

            lvl = parts[0]
            name = parts[1]
            pic = parts[parts.index("PIC") + 1]

            pic_type = pic[0]
            size = int(pic[pic.find("(") + 1:pic.find(")")])

            mem.alloc(name, pic_type, size)
            continue

        # ------------------------------------------
        # DISPLAY
        # ------------------------------------------
        if l.startswith("DISPLAY"):
            upon = "CONSOLE"
            if "UPON" in l:
                left, right = l.split("UPON")
                text = left.replace("DISPLAY", "").strip()
                upon = right.strip()
            else:
                text = l.replace("DISPLAY", "").strip()

            bc.append(OP["DISPLAY"])
            bc.append(len(text))
            bc.extend(text.encode())
            bc.append(len(upon))
            bc.extend(upon.encode())
            continue

        # ------------------------------------------
        # ACCEPT
        # ------------------------------------------
        if l.startswith("ACCEPT"):
            parts = l.split()
            var = parts[1]
            src = "INPUT"

            if "FROM" in parts:
                src = parts[parts.index("FROM") + 1]

            bc.append(OP["ACCEPT"])
            bc.append(len(var))
            bc.extend(var.encode())
            bc.append(len(src))
            bc.extend(src.encode())
            continue

        # ------------------------------------------
        # MOVE
        # ------------------------------------------
        if l.startswith("MOVE"):
            _, src, _, dst = l.split()
            bc.append(OP["MOVE"])
            for v in (src, dst):
                bc.append(len(v))
                bc.extend(v.encode())
            continue

        # ------------------------------------------
        # STRING
        # ------------------------------------------
        if l.startswith("STRING"):
            parts = l.replace("STRING", "").split("INTO")
            srcs = parts[0].split()
            dst = parts[1].strip()

            bc.append(OP["STRING"])
            bc.append(len(dst))
            bc.extend(dst.encode())
            bc.append(len(srcs))

            for s in srcs:
                bc.append(len(s))
                bc.extend(s.encode())
            continue

        # ------------------------------------------
        # UNSTRING
        # ------------------------------------------
        if l.startswith("UNSTRING"):
            _, src, _, delim, _, dst = l.split()
            bc.append(OP["UNSTRING"])
            for v in (src, delim, dst):
                bc.append(len(v))
                bc.extend(v.encode())
            continue

        # ------------------------------------------
        # CONTINUE
        # ------------------------------------------
        if l.startswith("CONTINUE"):
            bc.append(OP["CONTINUE"])
            continue

        # ------------------------------------------
        # STOP RUN
        # ------------------------------------------
        if l.startswith("STOP RUN"):
            bc.append(OP["STOP"])
            stop_found = True
            continue

        if l.startswith("END PROGRAM"):
            end_program_found = True

    if not stop_found:
        raise RuntimeError("Erro COBOL: STOP RUN obrigatório.")

    if not end_program_found:
        raise RuntimeError("Erro COBOL: END PROGRAM obrigatório.")

    return bc, mem

# ==================================================
# VIRTUAL MACHINE
# ==================================================
def run_vm(bc, mem):
    pc = 0

    while pc < len(bc):
        op = bc[pc]
        pc += 1

        if op == OP["DISPLAY"]:
            ln = bc[pc]; pc += 1
            txt = bc[pc:pc + ln].decode(); pc += ln
            ln = bc[pc]; pc += 1
            upon = bc[pc:pc + ln].decode(); pc += ln

            out = mem.read(txt) if txt in mem.symbols else txt.strip('"')
            if upon == "STDERR":
                print(out, file=sys.stderr)
            else:
                print(out)

        elif op == OP["ACCEPT"]:
            ln = bc[pc]; pc += 1
            var = bc[pc:pc + ln].decode(); pc += ln
            ln = bc[pc]; pc += 1
            src = bc[pc:pc + ln].decode(); pc += ln

            if src == "DATE":
                mem.write(var, datetime.now().strftime("%Y%m%d"))
            elif src == "DAY":
                mem.write(var, datetime.now().strftime("%Y%j"))
            elif src == "TIME":
                mem.write(var, datetime.now().strftime("%H%M%S"))
            else:
                mem.write(var, input("> "))

        elif op == OP["MOVE"]:
            ln = bc[pc]; pc += 1
            src = bc[pc:pc + ln].decode(); pc += ln
            ln = bc[pc]; pc += 1
            dst = bc[pc:pc + ln].decode(); pc += ln
            mem.write(dst, mem.read(src))

        elif op == OP["STRING"]:
            ln = bc[pc]; pc += 1
            dst = bc[pc:pc + ln].decode(); pc += ln
            count = bc[pc]; pc += 1
            val = ""
            for _ in range(count):
                ln = bc[pc]; pc += 1
                src = bc[pc:pc + ln].decode(); pc += ln
                val += mem.read(src) if src in mem.symbols else src.strip('"')
            mem.write(dst, val)

        elif op == OP["UNSTRING"]:
            ln = bc[pc]; pc += 1
            src = bc[pc:pc + ln].decode(); pc += ln
            ln = bc[pc]; pc += 1
            delim = bc[pc:pc + ln].decode(); pc += ln
            ln = bc[pc]; pc += 1
            dst = bc[pc:pc + ln].decode(); pc += ln

            parts = mem.read(src).split(delim)
            if parts:
                mem.write(dst, parts[0])

        elif op == OP["CONTINUE"]:
            pass

        elif op == OP["STOP"]:
            break

# ==================================================
# EXECUÇÃO
# ==================================================
if __name__ == "__main__":
    cobol = """
000100 IDENTIFICATION DIVISION.
000200 PROGRAM-ID. DEMO.
000300 DATA DIVISION.
000400 WORKING-STORAGE SECTION.
000500 01 NOME PIC X(20).
000600 01 DATA-ATUAL.
000700    05 ANO PIC 9(4).
000800    05 MES PIC 9(2).
000900    05 DIA PIC 9(2).
001000 01 MSG PIC X(40).

001100 PROCEDURE DIVISION.
001200 DISPLAY "NOME:" UPON CONSOLE.
001300 ACCEPT NOME.
001400 ACCEPT ANO FROM DATE.
001500 STRING "OLA " NOME INTO MSG.
001600 DISPLAY MSG.
001700 CONTINUE.
001800 STOP RUN.
001900 END PROGRAM DEMO.
"""

    bc, mem = compile_cobol(parse(cobol))
    run_vm(bc, mem)
