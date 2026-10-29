// Functions that reference defined strings containing a substring.
// Args: substring [maxStrings]   Output: "STR <addr> <text> | <function@entry rva> ..."
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import java.util.LinkedHashSet;
import java.util.Set;

public class StringXrefs extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String needle = args[0];
        int max = args.length > 1 ? Integer.parseInt(args[1]) : 50;
        long base = currentProgram.getImageBase().getOffset();
        int n = 0;
        DataIterator it = currentProgram.getListing().getDefinedData(true);
        while (it.hasNext() && n < max && !monitor.isCancelled()) {
            Data d = it.next();
            if (!d.hasStringValue()) continue;
            String s = String.valueOf(d.getValue());
            if (!s.contains(needle)) continue;
            n++;
            Set<String> fs = new LinkedHashSet<>();
            for (Reference r : getReferencesTo(d.getAddress())) {
                Function f = getFunctionContaining(r.getFromAddress());
                fs.add(f == null ? r.getFromAddress().toString()
                                 : String.format("%s@0x%x", f.getName(), f.getEntryPoint().getOffset() - base));
            }
            println(String.format("STR %s %s | %s", d.getAddress(), s.replace("\n", "\\n"), String.join(" ", fs)));
        }
    }
}
