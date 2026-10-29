// Dump 32-bit little-endian values from the image. Args: startRva count   Output: "DW <rva>: <value hex> [<function@rva>]"
// (a value that is the entry of a defined function, or inside one, is annotated).
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DumpDwords extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] args = getScriptArgs();
        long s = Long.decode(args[0]);
        int n = Integer.decode(args[1]);
        Address a = toAddr(s >= base ? s : base + s);
        for (int i = 0; i < n; i++) {
            Address p = a.add(4L * i);
            long v = currentProgram.getMemory().getInt(p) & 0xffffffffL;
            String note = "";
            if (v >= base && v < base + 0x2000000L) {
                Function f = getFunctionContaining(toAddr(v));
                if (f != null) note = String.format(" fn@0x%x", f.getEntryPoint().getOffset() - base);
                else if (getInstructionAt(toAddr(v)) != null || v < base + 0x160000L) note = " code?";
            }
            println(String.format("DW 0x%x: 0x%x%s", p.getOffset() - base, v, note));
        }
    }
}
