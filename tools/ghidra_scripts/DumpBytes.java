// Bytes at RVAs, as the C++ array body the plugin's entry checks use. Args: count rva [rva...]
// Output: "BYTES <rva> 0x48, 0x89, ..."
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class DumpBytes extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] args = getScriptArgs();
        int n = Integer.decode(args[0]);
        for (int k = 1; k < args.length; k++) {
            long rva = Long.decode(args[k]);
            Address a = toAddr(rva >= base ? rva : base + rva);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < n; i++) {
                int b = currentProgram.getMemory().getByte(a.add(i)) & 0xff;
                sb.append(String.format(i == 0 ? "0x%02x" : ", 0x%02x", b));
            }
            println("BYTES 0x" + Long.toHexString(rva) + " " + sb);
        }
    }
}
