// Lists runs of consecutive 8-byte pointers to function entry points in the non-code blocks (dispatch tables).
// Args: minRun maxRun   e.g. 140 170
// Output: one line per run: start address, length, first entries, and the code that references the start.
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;

public class FindPtrTables extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        int minRun = args.length > 0 ? Integer.parseInt(args[0]) : 100;
        int maxRun = args.length > 1 ? Integer.parseInt(args[1]) : 100000;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (b.isExecute() || !b.isInitialized()) continue;
            Address a = b.getStart();
            Address end = b.getEnd();
            Address runStart = null;
            int run = 0;
            while (a.compareTo(end) < 0) {
                if (monitor.isCancelled()) return;
                long v;
                try { v = currentProgram.getMemory().getLong(a); } catch (Exception e) { break; }
                Function f = null;
                try { f = getFunctionAt(toAddr(v)); } catch (Exception e) { }
                if (f != null) {
                    if (run == 0) runStart = a;
                    run++;
                } else {
                    report(runStart, run, minRun, maxRun);
                    run = 0;
                }
                a = a.add(8);
            }
            report(runStart, run, minRun, maxRun);
        }
    }

    private void report(Address start, int run, int minRun, int maxRun) throws Exception {
        if (start == null || run < minRun || run > maxRun) return;
        StringBuilder sb = new StringBuilder();
        sb.append(String.format("TABLE %s len %d rva 0x%x |", start, run,
                start.getOffset() - currentProgram.getImageBase().getOffset()));
        for (int i = 0; i < 4; i++) {
            sb.append(" ").append(Long.toHexString(currentProgram.getMemory().getLong(start.add(8L * i))));
        }
        sb.append(" | refs:");
        for (Reference r : getReferencesTo(start)) {
            Function f = getFunctionContaining(r.getFromAddress());
            sb.append(" ").append(r.getFromAddress()).append(f != null ? "(" + f.getName() + ")" : "");
        }
        println(sb.toString());
    }
}
