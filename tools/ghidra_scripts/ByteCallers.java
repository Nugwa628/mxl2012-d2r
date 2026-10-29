// Raw-byte search for callers: E8/E9 rel32 to a target and absolute 4-byte references (32-bit images, e.g. D2Sigma),
// independent of Ghidra's analysis. Args: rva [rva...]   Output: "BCALL <target rva> <- <address> <function@entry rva>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;

public class ByteCallers extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] a = getScriptArgs();
        for (String s : a) {
            long t = Long.decode(s);
            if (t >= base) t -= base;
            for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
                if (!b.isInitialized()) continue;
                long n = b.getSize();
                byte[] buf = new byte[(int) n];
                b.getBytes(b.getStart(), buf);
                long bs = b.getStart().getOffset() - base;
                for (int i = 0; i + 5 <= n; i++) {
                    int op = buf[i] & 0xff;
                    if (op == 0xe8 || op == 0xe9) {
                        int rel = (buf[i + 1] & 0xff) | (buf[i + 2] & 0xff) << 8 | (buf[i + 3] & 0xff) << 16 | (buf[i + 4] & 0xff) << 24;
                        if (bs + i + 5 + rel == t) emit(t, base, bs + i, "call");
                    }
                }
                long abs = base + t;
                for (int i = 0; i + 4 <= n; i++) {
                    long v = (buf[i] & 0xffL) | (buf[i + 1] & 0xffL) << 8 | (buf[i + 2] & 0xffL) << 16 | (buf[i + 3] & 0xffL) << 24;
                    if (v == abs) emit(t, base, bs + i, "abs");
                }
            }
        }
    }

    private void emit(long t, long base, long at, String kind) {
        Function f = getFunctionContaining(toAddr(base + at));
        println(String.format("BCALL %s 0x%x <- 0x%x %s", kind, t, at, f == null ? "-" : String.format("0x%x", f.getEntryPoint().getOffset() - base)));
    }
}
