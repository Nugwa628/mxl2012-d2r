// Instructions whose operands address anything within [rva - before, rva + after] (for data reached at an offset,
// e.g. assertion descriptors). Args: [scalar] before after rva [rva...] ("scalar": match plain numbers, e.g. sizes)   Output: "NEAR <rva> <- <instr addr> <func@entry>: <instr>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;

public class NearRefs extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] a = getScriptArgs();
        boolean raw = a[0].equals("scalar");  // "scalar before after value...": plain numbers, not RVAs
        if (raw) a = java.util.Arrays.copyOfRange(a, 1, a.length);
        long before = Long.decode(a[0]), after = Long.decode(a[1]);
        long base = currentProgram.getImageBase().getOffset();
        long[] t = new long[a.length - 2];
        for (int i = 2; i < a.length; i++) { long v = Long.decode(a[i]); t[i - 2] = raw || v >= base ? v : base + v; }
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            for (int op = 0; op < ins.getNumOperands(); op++) {
                for (Object o : ins.getOpObjects(op)) {
                    long v = o instanceof Address ? ((Address) o).getOffset() : o instanceof Scalar ? ((Scalar) o).getUnsignedValue() : -1;
                    for (long x : t) {
                        if (v >= x - before && v <= x + after) {
                            Function f = getFunctionContaining(ins.getAddress());
                            println(String.format("NEAR 0x%x <- %s %s: %s", raw ? x : x - base, ins.getAddress(),
                                f == null ? "-" : String.format("%s@0x%x", f.getName(), f.getEntryPoint().getOffset() - base), ins));
                        }
                    }
                }
            }
        }
    }
}
