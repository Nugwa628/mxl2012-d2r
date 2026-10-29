// References to addresses (by RVA): who reads them and from which function.
// Args: rva [rva...]   Output: "REF <target rva> <- <from address> <function@entry rva>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class Refs extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        for (String arg : getScriptArgs()) {
            long v = Long.decode(arg);
            Address a = toAddr(v >= base ? v : base + v);
            int n = 0;
            for (Reference r : getReferencesTo(a)) {
                Function f = getFunctionContaining(r.getFromAddress());
                println(String.format("REF 0x%x <- %s %s", a.getOffset() - base, r.getFromAddress(),
                        f == null ? "-" : String.format("%s@0x%x", f.getName(), f.getEntryPoint().getOffset() - base)));
                n++;
            }
            if (n == 0) println(String.format("REF 0x%x <- (none)", a.getOffset() - base));
        }
    }
}
