// Finds "read a record field, then call through a table" sites: an instruction whose memory operand has the given
// displacement (e.g. MOVZX r, word ptr [r + 0x4e]) followed within N instructions by an indirect CALL/JMP.
// Args: displacement [window]   Output: "SITE <function@rva> <instr addr>: <instr> ... <call instr>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;

public class FieldDispatch extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long disp = Long.decode(args[0]);
        int window = args.length > 1 ? Integer.parseInt(args[1]) : 25;
        long base = currentProgram.getImageBase().getOffset();
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            String m = ins.getMnemonicString();
            if (!m.startsWith("MOVZX") && !m.startsWith("MOV")) continue;
            if (!ins.toString().contains("word ptr") || !hasDisp(ins, disp)) continue;
            Instruction cur = ins;
            for (int i = 0; i < window && cur != null; i++) {
                cur = cur.getNext();
                if (cur == null) break;
                String cm = cur.getMnemonicString();
                if ((cm.equals("CALL") || cm.equals("JMP")) && cur.getFlowType().isComputed()) {
                    Function f = getFunctionContaining(ins.getAddress());
                    println(String.format("SITE %s %s: %s ... %s: %s",
                            f == null ? "-" : String.format("%s@0x%x", f.getName(), f.getEntryPoint().getOffset() - base),
                            ins.getAddress(), ins, cur.getAddress(), cur));
                    break;
                }
            }
        }
    }

    private boolean hasDisp(Instruction ins, long disp) {
        for (int op = 0; op < ins.getNumOperands(); op++) {
            for (Object o : ins.getOpObjects(op)) {
                if (o instanceof Scalar && ((Scalar) o).getUnsignedValue() == disp) return true;
            }
        }
        return false;
    }
}
