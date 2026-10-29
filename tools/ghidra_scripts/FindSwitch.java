// Switches with a given case bound: "CMP reg, N" (or "ADD/LEA ... ; CMP reg, N") followed within a few instructions
// by JA/JBE and a computed JMP. Args: bound [window]   e.g. 0x1b for a switch over values 0-27 (or 1-28 after DEC)
// Output: "SWITCH <function@rva> <cmp addr>: <cmp> ... <jmp>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;

public class FindSwitch extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long bound = Long.decode(args[0]);
        int window = args.length > 1 ? Integer.parseInt(args[1]) : 8;
        long base = currentProgram.getImageBase().getOffset();
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            if (!ins.getMnemonicString().equals("CMP")) continue;
            Object[] o = ins.getOpObjects(1);
            if (o.length != 1 || !(o[0] instanceof Scalar) || ((Scalar) o[0]).getUnsignedValue() != bound) continue;
            Instruction cur = ins;
            boolean ja = false;
            for (int i = 0; i < window; i++) {
                cur = cur.getNext();
                if (cur == null) break;
                String m = cur.getMnemonicString();
                if (m.equals("JA") || m.equals("JBE") || m.equals("JG") || m.equals("JLE")) ja = true;
                if (m.equals("JMP") && cur.getFlowType().isComputed() && ja) {
                    Function f = getFunctionContaining(ins.getAddress());
                    String fn = f == null ? "?" : f.getName() + "@0x" + Long.toHexString(f.getEntryPoint().getOffset() - base);
                    println("SWITCH " + fn + " 0x" + Long.toHexString(ins.getAddress().getOffset() - base) + ": " + ins + " ... " + cur);
                    break;
                }
            }
        }
    }
}
