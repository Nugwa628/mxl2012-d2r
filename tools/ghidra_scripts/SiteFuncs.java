// For each RVA, print the function containing it (entry RVA, size) and the instruction there plus the next two.
// Args: rva [rva...]   Output: "SITE <rva> in <func@entry> size 0x..: <instr> | <next> | <next>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class SiteFuncs extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        for (String arg : getScriptArgs()) {
            long v = Long.decode(arg);
            Address a = toAddr(v >= base ? v : base + v);
            Function f = getFunctionContaining(a);
            Instruction i = currentProgram.getListing().getInstructionContaining(a);
            if (i == null) { disassemble(a); i = currentProgram.getListing().getInstructionAt(a); }
            StringBuilder sb = new StringBuilder();
            Instruction j = i;
            for (int k = 0; k < 3 && j != null; k++) { sb.append(j).append(" | "); j = j.getNext(); }
            String fs = f == null ? "none" : String.format("%s@0x%x size 0x%x", f.getName(), f.getEntryPoint().getOffset() - base, f.getBody().getNumAddresses());
            println(String.format("SITE 0x%x in %s: %s", v, fs, sb));
        }
    }
}
