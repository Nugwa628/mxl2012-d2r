// Dump 64-bit little-endian values from the image (vtables). Args: startRva count   Output: "QW <rva>: <value> [<function@rva>]"
// (a value that is the entry of a defined function, or inside one, is annotated with the function's rva).
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DumpQwords extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] args = getScriptArgs();
        long s = Long.decode(args[0]);
        int n = Integer.decode(args[1]);
        Address a = toAddr(s >= base ? s : base + s);
        for (int i = 0; i < n; i++) {
            Address p = a.add(8L * i);
            long v = currentProgram.getMemory().getLong(p);
            String note = "";
            if (v >= base && v < base + 0x4000000L) {
                Function f = getFunctionContaining(toAddr(v));
                if (f != null) {
                    note = " [fn rva 0x" + Long.toHexString(f.getEntryPoint().getOffset() - base) + (f.getEntryPoint().getOffset() == v ? "" : "+") + "]";
                }
            }
            println("QW 0x" + Long.toHexString(p.getOffset() - base) + ": 0x" + Long.toHexString(v) + note);
        }
    }
}
