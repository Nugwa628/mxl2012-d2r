// Function starts without analysis: 16-aligned addresses preceded by INT3 padding (MSVC). Args: lo hi (RVAs)
// Output: "START <rva>" for each candidate; use with DecompOut (which creates the function).
//@category mxl
import ghidra.app.script.GhidraScript;

public class ScanStarts extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] a = getScriptArgs();
        long lo = Long.decode(a[0]), hi = Long.decode(a[1]);
        StringBuilder sb = new StringBuilder();
        int n = 0;
        for (long r = (lo + 15) & ~15L; r < hi; r += 16) {
            int prev = getByte(toAddr(base + r - 1)) & 0xff;
            int cur = getByte(toAddr(base + r)) & 0xff;
            if (prev == 0xcc && cur != 0xcc) {
                sb.append(String.format("0x%x ", r));
                if (++n % 8 == 0) { println("START " + sb); sb.setLength(0); }
            }
        }
        if (sb.length() > 0) println("START " + sb);
    }
}
