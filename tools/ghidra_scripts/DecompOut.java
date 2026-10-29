// DecompOut <outdir> rva...: decompile functions (by RVA or address) into <outdir>/<rva>.c (lane-private output dir).
// Callees are listed at the top of each file as a comment: "// calls: rva ...".
//@category mxl
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import java.io.File;
import java.io.FileWriter;

public class DecompOut extends GhidraScript {
    @Override
    protected void run() throws Exception {
        long base = currentProgram.getImageBase().getOffset();
        String[] args = getScriptArgs();
        File outDir = new File(args[0]);
        outDir.mkdirs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        for (int i = 1; i < args.length; i++) {
            long v = Long.decode(args[i]);
            Address a = toAddr(v >= base ? v : base + v);
            Function f = getFunctionContaining(a);
            if (f == null) {
                disassemble(a);
                f = createFunction(a, null);
            }
            if (f == null) { println("no function at " + a); continue; }
            DecompileResults res = di.decompileFunction(f, 180, monitor);
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
