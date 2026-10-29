// Disassembly of an RVA range with the instruction bytes. Args: startRva endRva
// Output: "INS <rva> <bytes> <text>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;

public class Disasm extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] args = getScriptArgs();
        long from = Long.decode(args[0]);
        long to = Long.decode(args[1]);
        Address a = toAddr(from >= base ? from : base + from);
        Address end = toAddr(to >= base ? to : base + to);
        while (a.compareTo(end) < 0) {
            Instruction ins = currentProgram.getListing().getInstructionAt(a);
            if (ins == null) {
                ins = currentProgram.getListing().getInstructionContaining(a);
                if (ins == null) {
                    a = a.add(1);
                    continue;
                }
            }
            StringBuilder sb = new StringBuilder();
            for (byte b : ins.getBytes()) {
                sb.append(String.format("%02x ", b & 0xff));
            }
            println("INS 0x" + Long.toHexString(ins.getAddress().getOffset() - base) + " " + sb + " " + ins);
            a = ins.getAddress().add(ins.getLength());
        }
    }
}
