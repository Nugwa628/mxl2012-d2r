// List the functions whose entry lies in an RVA range. Args: startRva endRva   Output: "FN <rva> <name> size <n>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

public class ListFuncs extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] args = getScriptArgs();
        long s = Long.decode(args[0]), e = Long.decode(args[1]);
        Address a = toAddr(base + s);
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(a, true);
        while (it.hasNext()) {
            Function f = it.next();
            long rva = f.getEntryPoint().getOffset() - base;
            if (rva >= e) break;
            println(String.format("FN 0x%x %s size %d", rva, f.getName(), f.getBody().getNumAddresses()));
        }
    }
}
