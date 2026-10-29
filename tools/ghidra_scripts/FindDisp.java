// Lists every instruction with a memory operand of the given displacement (e.g. 0x22c, a record field), grouped by
// function. Args: displacement [mnemonic prefix]   Output: "<function@rva> <instr rva>: <instr>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;

public class FindDisp extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long disp = Long.decode(args[0]);
        String prefix = args.length > 1 ? args[1] : "";
        long base = currentProgram.getImageBase().getOffset();
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            if (!ins.getMnemonicString().startsWith(prefix)) continue;
            String s = ins.toString();
            if (!s.contains("[")) continue;
            boolean hit = false;
            for (int op = 0; op < ins.getNumOperands() && !hit; op++) {
                for (Object o : ins.getOpObjects(op)) {
                    if (o instanceof Scalar && ((Scalar) o).getUnsignedValue() == disp && s.contains("+ 0x" + Long.toHexString(disp) + "]")) {
                        hit = true;
                    }
                }
            }
            if (!hit) continue;
            Function f = getFunctionContaining(ins.getAddress());
            String fn = f == null ? "?" : String.format("%s@0x%x", f.getName(), f.getEntryPoint().getOffset() - base);
            println(String.format("%s 0x%x: %s", fn, ins.getAddress().getOffset() - base, s));
        }
    }
}
