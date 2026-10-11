using Microsoft.PowerShell;

namespace AudionAddressProcessor.Ps;

/// <summary>
/// pwsh under the program's name: the same arguments (-NoProfile, -File, -Command...), the same
/// console host, the engine pinned by the package. Nothing of its own - a script the engine ran
/// with pwsh.exe runs with this file unchanged.
/// </summary>
static class Program
{
    static int Main(string[] args) => UnmanagedPSEntry.Start(args, args.Length);
}
