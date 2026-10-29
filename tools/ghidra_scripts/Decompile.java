// Decompile functions (by RVA or address) into ../ghidra/decomp[/<program>]/<rva>.c and print where they went.
// Args: rva [rva...]   (hex, e.g. 0x3dd710; values >= the image base are taken as addresses)
//@category mxl
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import java.io.File;
import java.io.FileWriter;

public class Decompile extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        // ../ghidra/decomp for the D2R dump, ../ghidra/decomp/<program> for other programs (D2Sigma.dll)
        File outDir = new File(new File(currentProgram.getExecutablePath()).getParentFile(), "decomp");
        if (!currentProgram.getName().startsWith("D2RLoader")) {
            outDir = new File(new File(new File(currentProgram.getExecutablePath()).getParentFile(), "ghidra"),
                              "decomp/" + currentProgram.getName());
        }
        outDir.mkdirs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        for (String arg : getScriptArgs()) {
            long v = Long.decode(arg);
            Address a = toAddr(v >= base ? v : base + v);
            Function f = getFunctionContaining(a);
            if (f == null) {  // only reached through a pointer table: define it on the fly (-readOnly, not saved)
                disassemble(a);
                f = createFunction(a, null);
            }
            if (f == null) { println("no function at " + a); continue; }
            DecompileResults res = di.decompileFunction(f, 120, monitor);
            String rva = String.format("0x%x", f.getEntryPoint().getOffset() - base);
            File out = new File(outDir, rva + ".c");
            try (FileWriter w = new FileWriter(out)) {
                w.write("// " + f.getName() + " rva " + rva + "\n");
                w.write(res.decompileCompleted() ? res.getDecompiledFunction().getC() : "// failed: " + res.getErrorMessage());
            }
            println("DECOMP " + rva + " " + f.getName() + " -> " + out.getPath());
        }
        di.dispose();
    }
}
