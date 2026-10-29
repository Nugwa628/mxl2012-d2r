// Find 64-bit little-endian values in the image memory. Args: value [value...]  (a value below the image base is
// taken as an RVA and the base is added)   Output: "FOUND <value hex> at <rva>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;

public class FindQword extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        for (String arg : getScriptArgs()) {
            long v = Long.decode(arg);
            if (v < base) v += base;
            byte[] pat = new byte[8]; for (int i = 0; i < 8; i++) pat[i] = (byte) (v >> (8 * i));
            for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
                if (!b.isInitialized()) continue;
                Address a = b.getStart();
                while (a != null && a.getOffset() <= b.getEnd().getOffset()) {
                    Address f = currentProgram.getMemory().findBytes(a, b.getEnd(), pat, null, true, monitor);
                    if (f == null) break;
                    println(String.format("FOUND 0x%x at 0x%x (%s)", v, f.getOffset() - base, b.getName()));
                    a = f.add(1);
                }
            }
        }
    }
}
