// Symbols (labels) whose name contains a substring. Args: substring [max]   Output: "SYM <rva> <name>"
// For a C++ vftable the first entries are listed too (4-byte pointers on 32-bit images, 8-byte on 64-bit).
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

public class SymFind extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String needle = args[0];
        int max = args.length > 1 ? Integer.parseInt(args[1]) : 20;
        long base = currentProgram.getImageBase().getOffset();
        int ptr = currentProgram.getDefaultPointerSize();
        int n = 0;
        SymbolIterator it = currentProgram.getSymbolTable().getAllSymbols(true);
        while (it.hasNext() && n < max && !monitor.isCancelled()) {
            Symbol s = it.next();
            if (!s.getName(true).contains(needle)) continue;
            ++n;
            Address a = s.getAddress();
            println("SYM 0x" + Long.toHexString(a.getOffset() - base) + " " + s.getName(true));
            if (s.getName().contains("vftable")) {
                for (int i = 0; i < 4; i++) {
                    long v = ptr == 4 ? (currentProgram.getMemory().getInt(a.add(4L * i)) & 0xffffffffL) : currentProgram.getMemory().getLong(a.add(8L * i));
                    Function f = getFunctionContaining(toAddr(v));
                    println("  [" + i + "] 0x" + Long.toHexString(v - base) + (f != null ? " fn rva 0x" + Long.toHexString(f.getEntryPoint().getOffset() - base) : ""));
                }
            }
        }
    }
}
