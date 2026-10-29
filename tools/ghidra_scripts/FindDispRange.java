// Instructions with a memory operand whose displacement lies in [lo, hi) and whose base register is not RSP/RBP
// (skips stack locals). Args: lo hi   Output: "<function@rva> <instr rva>: <instr>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class FindDispRange extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long lo = Long.decode(args[0]);
        long hi = Long.decode(args[1]);
        long base = currentProgram.getImageBase().getOffset();
        Pattern mem = Pattern.compile("\\[([A-Z0-9]+)(?: \\+ [A-Z0-9]+\\*0x[0-9a-f]+)? \\+ 0x([0-9a-f]+)\\]");
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            String s = ins.toString();
            Matcher m = mem.matcher(s);
            while (m.find()) {
                String reg = m.group(1);
                if (reg.equals("RSP") || reg.equals("RBP") || reg.equals("RIP")) {
                    continue;
                }
                long disp = Long.parseLong(m.group(2), 16);
                if (disp >= lo && disp < hi) {
                    Function f = getFunctionContaining(ins.getAddress());
                    String fn = f == null ? "?" : String.format("%s@0x%x", f.getName(), f.getEntryPoint().getOffset() - base);
                    println(String.format("%s 0x%x: %s", fn, ins.getAddress().getOffset() - base, s));
                }
            }
        }
    }
}
