// Find a UTF-16 string (or ASCII with -a) in the image bytes and list the functions that reference it
// (Ghidra references, then a raw rip-relative lea/mov scan of the code blocks).
// Args: text-without-spaces-use-underscore-for-space [-a]   Output: "WSTR <addr> <- <from> <function@entry rva>"
//@category mxl
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;

public class FindWide extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String text = args[0].replace('_', ' ');
        boolean ascii = args.length > 1 && args[1].equals("-a");
        byte[] pat = new byte[ascii ? text.length() : text.length() * 2];
        for (int i = 0; i < text.length(); i++) {
            pat[ascii ? i : i * 2] = (byte) text.charAt(i);
        }
        long base = currentProgram.getImageBase().getOffset();
        Address from = currentProgram.getMinAddress();
        int found = 0;
        while (found < 10) {
            Address a = currentProgram.getMemory().findBytes(from, pat, null, true, monitor);
            if (a == null) break;
            found++;
            println("WSTR " + a + " rva " + Long.toHexString(a.getOffset() - base));
            for (Reference r : getReferencesTo(a)) {
                Function f = getFunctionContaining(r.getFromAddress());
                println("WSTR ref <- " + r.getFromAddress() + " " + (f == null ? "-" : f.getName() + "@0x" + Long.toHexString(f.getEntryPoint().getOffset() - base)));
            }
            // raw scan: 7-byte rip-relative instructions (48 8d 0d / 48 8d 15 / 4c 8d 05 ...) whose target is a
            for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
                if (!b.isExecute()) continue;
                byte[] buf = new byte[(int) b.getSize()];
                b.getBytes(b.getStart(), buf);
                for (int i = 0; i + 7 <= buf.length; i++) {
                    if ((buf[i] & 0xf8) != 0x48 && (buf[i] & 0xf8) != 0x4c) continue;
                    int op = buf[i + 1] & 0xff;
                    int modrm = buf[i + 2] & 0xff;
                    if ((op != 0x8d && op != 0x8b) || (modrm & 0xc7) != 0x05) continue;
                    int rel = (buf[i + 3] & 0xff) | ((buf[i + 4] & 0xff) << 8) | ((buf[i + 5] & 0xff) << 16) | ((buf[i + 6] & 0xff) << 24);
                    Address at = b.getStart().add(i);
                    if (at.add(7 + rel).equals(a)) {
                        Function f = getFunctionContaining(at);
                        println("WSTR lea <- " + at + " " + (f == null ? "-" : f.getName() + "@0x" + Long.toHexString(f.getEntryPoint().getOffset() - base)));
                    }
                }
            }
            from = a.add(1);
        }
        println("WSTR done, found " + found);
    }
}
