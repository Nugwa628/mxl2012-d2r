// Find raw 32-bit little-endian immediates (no RVA translation) in the image memory and name the function around each hit.
// Args: value [value...]   Output: "IMM <value hex> at <rva> in <function>@<function rva>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;

public class FindImm extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        for (String arg : getScriptArgs()) {
            long v = Long.decode(arg);
            byte[] pat = new byte[] {(byte) v, (byte) (v >> 8), (byte) (v >> 16), (byte) (v >> 24)};
            for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
                if (!b.isInitialized() || !b.isExecute()) continue;
                Address a = b.getStart();
                while (a != null && a.getOffset() <= b.getEnd().getOffset()) {
                    Address f = currentProgram.getMemory().findBytes(a, b.getEnd(), pat, null, true, monitor);
                    if (f == null) break;
                    Function fn = getFunctionContaining(f);
                    println(String.format("IMM 0x%x at 0x%x in %s", v, f.getOffset() - base,
                            fn == null ? "?" : fn.getName() + "@0x" + Long.toHexString(fn.getEntryPoint().getOffset() - base)));
                    a = f.add(1);
                }
            }
        }
    }
}
