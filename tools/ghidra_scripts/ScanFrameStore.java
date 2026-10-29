// Finds MOV stores to [reg+dst] within N instructions after a MOV read of [reg+src]. Args: srcOffHex dstOffHex window
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

public class ScanFrameStore extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] a = getScriptArgs();
        String src = "+ 0x" + a[0].replace("0x", "") + "]";
        String dst = "+ 0x" + a[1].replace("0x", "") + "]";
        int win = Integer.parseInt(a[2]);
        long lastSrc = -1;
        int idx = 0;
        int n = 0;
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext()) {
            Instruction ins = it.next();
            idx++;
            String s = ins.toString();
            if (s.contains(src) && s.startsWith("MOV")) {
                lastSrc = idx;
            }
            if (s.startsWith("MOV") && s.contains(dst + ",") && lastSrc > 0 && idx - lastSrc <= win) {
                println(String.format("HIT 0x%x: %s", ins.getAddress().getOffset() - base, s));
                if (++n > 60) {
                    return;
                }
            }
        }
    }
}
