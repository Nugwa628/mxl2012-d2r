// Linear disassembly of an address range (for code the analysis did not turn into functions, e.g. switch arms).
// Args: startRva endRva   Output: "ASM <rva>: <instruction>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;

public class DisasmRange extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] args = getScriptArgs();
        long s = Long.decode(args[0]), e = Long.decode(args[1]);
        Address a = toAddr(s >= base ? s : base + s);
        long end = e >= base ? e : base + e;
        while (a.getOffset() < end) {
            Instruction ins = getInstructionAt(a);
            if (ins == null) { disassemble(a); ins = getInstructionAt(a); }
            if (ins == null) { println(String.format("ASM 0x%x: ??", a.getOffset() - base)); a = a.add(1); continue; }
            println(String.format("ASM 0x%x: %s", a.getOffset() - base, ins));
            a = ins.getMaxAddress().add(1);
        }
    }
}
